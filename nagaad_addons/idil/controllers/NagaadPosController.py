from odoo import http, fields
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

def get_employee(env):
    """
    Helper to find the idil.employee record linked to current user.
    Assumes idil.employee has user_id or similar link, or we define it.
    The model has `user_id` field.
    """
    return env['idil.employee'].sudo().search([('user_id', '=', env.uid)], limit=1)

def check_permission(env, permission_field):
    """
    Checks if current user's employee has the given permission flag set to True.
    """
    emp = get_employee(env)
    if not emp:
        # If no employee linked, default to restrictive or allow? 
        # Safest is restrictive.
        return False, "User is not linked to an Employee record."
    
    if not getattr(emp, permission_field, False):
        return False, "Permission Denied."
    
    return True, None

class NagaadPosController(http.Controller):

    @http.route('/nagaad/api/ping', type='json', auth='public', csrf=False)
    def ping(self):
        return {'status': 'success', 'message': 'Odoo API is online!'}

    @http.route('/nagaad/api/get_pos_data', type='json', auth='public', csrf=False)
    def get_pos_data(self, **kwargs):
        """
        ROBUST: Fetches master data using manual recordset counting.
        """
        try:
            # 1. Fetch Customers
            customers = request.env['idil.customer.registration'].sudo().search_read(
                [], ['id', 'name'], limit=200
            )

            # 2. Fetch Categories and count them manually (Bypasses read_group errors)
            products = request.env['my_product.product'].sudo().search([('available_in_pos', '=', True)])
            all_cats = products.mapped('pos_categ_ids')

            categories = []
            seen_ids = set()
            for cat in all_cats:
                if cat.id not in seen_ids:
                    # Filter products in memory - very fast in Python
                    count = len(products.filtered(lambda p: cat.id in p.pos_categ_ids.ids))
                    categories.append({
                        'id': cat.id,
                        'name': cat.name,
                        'count': count
                    })
                    seen_ids.add(cat.id)

            categories.sort(key=lambda x: x['name'])

            return {
                'status': 'success',
                'customers': customers,
                'categories': categories
            }
        except Exception as e:
            _logger.error("POS API Error: %s", str(e))
            return {'status': 'error', 'message': str(e)}

    @http.route('/nagaad/api/get_products', type='json', auth='public', csrf=False)
    def get_products(self, category_id=None, **kwargs):
        """
        FIXED: Using 'image_1920' as defined in your model.
        """
        try:
            domain = [('available_in_pos', '=', True)]
            if category_id:
                domain.append(('pos_categ_ids', 'in', [int(category_id)]))

            # We use image_1920 since image_128 doesn't exist on your model
            products = request.env['my_product.product'].sudo().search_read(
                domain,
                ['id', 'name', 'pos_categ_ids', 'sale_price', 'image_1920'],
                order='name asc'
            )

            return {'status': 'success', 'products': products}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @http.route('/nagaad/api/submit_order', type='json', auth='public', csrf=False)
    def submit_order(self, order_data, **kwargs):
        try:
            lines = []
            for line in order_data.get('order_lines', []):
                lines.append((0, 0, {
                    'product_id': line.get('product_id'),
                    'quantity': line.get('quantity'),
                    'sale_price': line.get('sale_price'),
                    'menu_id': line.get('menu_id'),
                    'menu_name': line.get('menu_name'),
                    'status': 'normal',
                }))

            vals = {
                'customer_id': order_data.get('customer_id'),
                'waiter_id': order_data.get('waiter_id'),
                'order_mode': order_data.get('order_mode'),
                'table_no': order_data.get('table_no'),
                'order_lines': lines,
            }

            res = request.env['idil.customer.place.order'].sudo().create(vals)
            return {'status': 'success', 'order_id': res.id}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}


    @http.route('/nagaad/api/register_device', type='json', auth='user', csrf=False)
    def register_device(self, device_data, **kwargs):
        """
        Registers or updates a mobile device connection.
        Expected device_data: { 'name', 'device_id', 'platform', 'app_version' }
        """
        try:
            Device = request.env['idil.mobile.device'].sudo()
            uid = request.uid
            
            d_id = device_data.get('device_id')
            if not d_id:
                 return {'status': 'error', 'message': 'Missing device_id'}

            # Find existing by device_id
            existing = Device.search([('device_id', '=', d_id)], limit=1)
            
            vals = {
                'name': device_data.get('name', 'Unknown Device'),
                'user_id': uid,
                'ip_address': request.httprequest.remote_addr,
                'platform': device_data.get('platform'),
                'app_version': device_data.get('app_version'),
                'last_login': fields.Datetime.now(),
                'last_lat': device_data.get('lat'),
                'last_long': device_data.get('long'),
            }

            # Prepare log values
            log_vals = {
                'user_id': uid,
                'login_time': fields.Datetime.now(),
                'ip_address': request.httprequest.remote_addr,
                'lat': device_data.get('lat'),
                'long': device_data.get('long'),
                'platform': device_data.get('platform'),
                'app_version': device_data.get('app_version'),
            }

            if existing:
                if existing.state == 'blocked':
                    return {'status': 'error', 'message': 'This device has been blocked by admin.'}
                
                # Update device info
                vals['login_count'] = existing.login_count + 1
                existing.write(vals)

                # Create audit log
                log_vals['device_ref_id'] = existing.id
                request.env['idil.mobile.device.log'].sudo().create(log_vals)

                return {'status': 'success', 'message': 'Device updated'}
            else:
                vals['device_id'] = device_data.get('device_id')
                vals['login_count'] = 1
                new_device = Device.create(vals)

                # Create audit log
                log_vals['device_ref_id'] = new_device.id
                request.env['idil.mobile.device.log'].sudo().create(log_vals)
                
                return {'status': 'success', 'message': 'Device registered'}

        except Exception as e:
            _logger.error("Device Register Error: %s", str(e))
            return {'status': 'error', 'message': str(e)}

    @http.route('/nagaad/api/get_waiter_orders', type='json', auth='user', csrf=False)
    def get_waiter_orders(self, **kwargs):
        try:
            uid = request.uid
            orders = request.env['idil.customer.place.order'].sudo().search(
                [('waiter_id', '=', uid), ('state', 'in', ['draft', 'confirmed'])],
                order='create_date desc'
            )

            product_list = request.env['my_product.product'].sudo().search_read(
                [('available_in_pos', '=', True)],
                ['id', 'name', 'sale_price'],
                limit=1000
            )

            # Permissions
            emp = get_employee(request.env)
            permissions = {
                'allow_delete_order': emp.allow_delete_order if emp else False,
                'allow_delete_line': emp.allow_delete_line if emp else False,
                'allow_reduce_qty': emp.allow_reduce_qty if emp else False,
            }

            orders_by_date = {}
            for o in orders:
                d = o.create_date.strftime('%Y-%m-%d')
                if d not in orders_by_date:
                    orders_by_date[d] = []
                
                lines = []
                for l in o.order_lines:
                    lines.append({
                        'id': l.id,
                        'product_id': [l.product_id.id, l.product_id.name],
                        'quantity': l.quantity,
                        'kitchen_printed_qty': l.kitchen_printed_qty,
                        'sale_price': l.sale_price,
                        'line_total': l.line_total,
                        'menu_name': l.menu_name,
                        'status': l.status,
                    })
                
                orders_by_date[d].append({
                    'id': o.id,
                    'name': o.name,
                    'state': o.state,
                    'customer_id': [o.customer_id.id, o.customer_id.name],
                    'waiter_id': [o.waiter_id.id, o.waiter_id.name],
                    'order_mode': o.order_mode,
                    'table_no': o.table_no,
                    'total_price': o.total_price,
                    'create_date': str(o.create_date),
                    'lines': lines
                })

            return {
                'status': 'success',
                'orders_by_date': orders_by_date,
                'product_list': product_list,
                'permissions': permissions
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @http.route('/nagaad/api/update_order_line', type='json', auth='user', csrf=False)
    def update_order_line(self, line_id, quantity, **kwargs):
        try:
            line = request.env['idil.customer.place.order.line'].sudo().browse(line_id)
            if not line.exists():
                return {'status': 'error', 'message': 'Line not found'}

            if line.order_id.state != 'draft':
                 return {'status': 'error', 'message': 'Cannot edit confirmed orders directly. Please create a new order.'}

            new_qty = float(quantity)
            old_qty = line.quantity

            if new_qty < old_qty:
                allowed, msg = check_permission(request.env, 'allow_reduce_qty')
                if not allowed:
                    return {'status': 'error', 'message': "Manager approval required to reduce quantity."}

            line.write({'quantity': new_qty})
            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @http.route('/nagaad/api/delete_order_line', type='json', auth='user', csrf=False)
    def delete_order_line(self, line_id, **kwargs):
        try:
            line = request.env['idil.customer.place.order.line'].sudo().browse(line_id)
            if not line.exists():
                return {'status': 'error', 'message': 'Line not found'}
            
            allowed, msg = check_permission(request.env, 'allow_delete_line')
            if not allowed:
                return {'status': 'error', 'message': "Manager approval required to delete items."}

            line.unlink()
            return {'status': 'success'}
        except Exception as e:
             return {'status': 'error', 'message': str(e)}

    @http.route('/nagaad/api/add_order_line', type='json', auth='user', csrf=False)
    def add_order_line(self, order_id, product_id, quantity, **kwargs):
        try:
            order = request.env['idil.customer.place.order'].sudo().browse(order_id)
            # Find existing product? Usually better to add new line or merge?
            # Standard merge logic:
            existing = order.order_lines.filtered(lambda l: l.product_id.id == int(product_id))
            if existing:
                # Merging -> requires update permission if reducing? Adding is usually fine.
                existing[0].write({'quantity': existing[0].quantity + float(quantity)})
            else:
                 request.env['idil.customer.place.order.line'].sudo().create({
                     'order_id': order.id,
                     'product_id': int(product_id),
                     'quantity': float(quantity)
                 })
            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @http.route('/nagaad/api/confirm_print', type='json', auth='user', csrf=False)
    def confirm_print(self, order_id, **kwargs):
        """
        Updates kitchen_printed_qty to match current quantity for all lines.
        Call this AFTER successfully printing the delta receipt.
        """
        try:
            order = request.env['idil.customer.place.order'].sudo().browse(order_id)
            for line in order.order_lines:
                if line.quantity > line.kitchen_printed_qty:
                    line.kitchen_printed_qty = line.quantity
            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}