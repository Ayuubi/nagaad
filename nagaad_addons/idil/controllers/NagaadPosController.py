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

    @http.route('/nagaad/api/submit_order', type='json', auth='public', csrf=False, cors='*')
    def submit_order(self, order_data, **kwargs):
        try:
            # 1. Determine Real User (Option B Strategy)
            real_uid = order_data.get('user_id') or order_data.get('waiter_id') 
            if not real_uid:
                 # Fallback to current request user if logged in, else error or defaults
                 real_uid = request.uid
            
            real_uid = int(real_uid)
            _logger.warning("🚀 SUBMIT_ORDER: real_uid=%s request.uid=%s", real_uid, request.uid)

            lines = []
            for line in order_data.get('order_lines', []):
                lines.append((0, 0, {
                    'product_id': line.get('product_id'),
                    'quantity': line.get('quantity'),
                    'sale_price': line.get('sale_price'),
                    'menu_id': line.get('menu_id'),
                    'menu_name': line.get('menu_name'),
                    'status': 'normal',
                    'kitchen_printed_qty': 0.0,
                }))

            vals = {
                'customer_id': order_data.get('customer_id'),
                'waiter_id': real_uid,
                'order_mode': order_data.get('order_mode'),
                'table_no': order_data.get('table_no'),
                'company_id': order_data.get('company_id'),
                'order_lines': lines,
            }

            # 2. Key Fix: Use .with_user() to force create_uid even if auth='public'
            # Note: The user must have permission to create this record.
            res = request.env['idil.customer.place.order'].with_user(real_uid).create(vals)
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
            existing = Device.sudo().search([('device_id', '=', d_id)], limit=1)
            
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

    @http.route('/nagaad/api/get_waiter_orders', type='json', auth='public', csrf=False, cors='*')
    def get_waiter_orders(self, user_id=None, **kwargs):
        try:
            uid = int(user_id) if user_id else request.uid
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

    @http.route('/nagaad/api/update_order_line', type='json', auth='public', csrf=False, cors='*')
    def update_order_line(self, line_id, quantity, **kwargs):
        try:
            real_uid = kwargs.get('user_id') or request.uid
            real_uid = int(real_uid)
            
            # Use with_user to ensure write_uid is correct
            line = request.env['idil.customer.place.order.line'].with_user(real_uid).browse(line_id)
            if not line.exists():
                return {'status': 'error', 'message': 'Line not found'}

            if line.order_id.state != 'draft':
                 return {'status': 'error', 'message': 'Cannot edit confirmed orders directly. Please create a new order.'}

            new_qty = float(quantity)
            old_qty = float(line.quantity or 0.0)

            if new_qty < old_qty:
                allowed, msg = check_permission(request.env, 'allow_reduce_qty')
                if not allowed:
                    return {'status': 'error', 'message': "Manager approval required to reduce quantity."}
                
                # Rule 4: Reduction resets pending to 0
                line.write({'quantity': new_qty, 'kitchen_printed_qty': 0.0, 'status': 'normal'})
                return {'status': 'success'}
            
            if new_qty > old_qty:
                diff = new_qty - old_qty
                # Rule 3 & 6: Increase accumulates diff to existing pending
                new_pending = (line.kitchen_printed_qty or 0.0) + diff
                line.write({'quantity': new_qty, 'kitchen_printed_qty': new_pending, 'status': 'add'})
                return {'status': 'success'}

            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @http.route('/nagaad/api/delete_order_line', type='json', auth='public', csrf=False, cors='*')
    def delete_order_line(self, line_id, **kwargs):
        try:
            real_uid = kwargs.get('user_id') or request.uid
            real_uid = int(real_uid)

            line = request.env['idil.customer.place.order.line'].with_user(real_uid).browse(line_id)
            if not line.exists():
                return {'status': 'error', 'message': 'Line not found'}
            
            allowed, msg = check_permission(request.env, 'allow_delete_line')
            if not allowed:
                return {'status': 'error', 'message': "Manager approval required to delete items."}

            line.unlink()
            return {'status': 'success'}
        except Exception as e:
             return {'status': 'error', 'message': str(e)}

    @http.route('/nagaad/api/add_order_line', type='json', auth='public', csrf=False, cors='*')
    def add_order_line(self, order_id, product_id, quantity, **kwargs):
        try:
            real_uid = kwargs.get('user_id') or request.uid
            real_uid = int(real_uid)

            order = request.env['idil.customer.place.order'].with_user(real_uid).browse(order_id)
            # Find existing product? Usually better to add new line or merge?
            # Standard merge logic:
            existing = order.order_lines.filtered(lambda l: l.product_id.id == int(product_id))
            if existing:
                line = existing[0]
                qty_val = float(quantity)
                # Rule 6: Accumulate to pending
                new_pending = (line.kitchen_printed_qty or 0.0) + qty_val
                line.write({
                    'quantity': line.quantity + qty_val,
                    'kitchen_printed_qty': new_pending,
                    'status': 'add'
                })
            else:
                 request.env['idil.customer.place.order.line'].with_user(real_uid).create({
                     'order_id': order.id,
                     'product_id': int(product_id),
                     'quantity': float(quantity),
                     'kitchen_printed_qty': float(quantity), # Rule 5: New line pending full qty
                     'status': 'add'
                 })
            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @http.route('/nagaad/api/confirm_print', type='json', auth='public', csrf=False, cors='*')
    def confirm_print(self, order_id, **kwargs):
        """
        Rule 2: Reset pending qty after successful print confirmation.
        """
        try:
            real_uid = kwargs.get('user_id') or request.uid
            real_uid = int(real_uid)

            order = request.env['idil.customer.place.order'].with_user(real_uid).browse(order_id)
            for line in order.order_lines:
                if (line.kitchen_printed_qty or 0.0) > 0:
                    line.write({'kitchen_printed_qty': 0.0, 'status': 'normal'})
            return {'status': 'success'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    # @http.route('/nagaad/api/confirm_order', type='json', auth='public', csrf=False, cors='*')
    # def confirm_order(self, order_id, **kwargs):
    #     try:
    #         real_uid = kwargs.get('user_id') or request.uid
    #         real_uid = int(real_uid)
    #
    #         # Use sudo for accounting/finance operations to avoid access errors for waiters
    #         order = request.env['idil.customer.place.order'].sudo().browse(order_id)
    #         if not order.exists():
    #             return {'status': 'error', 'message': 'Order not found'}
    #
    #         # 1. Get Receivable Account from Order Creator (Waiter)
    #         creator_user = order.create_uid
    #         creator_emp = request.env['idil.employee'].sudo().search([('user_id', '=', creator_user.id)], limit=1)
    #         receivable_id = creator_emp.receivable_account_id.id
    #         if not receivable_id:
    #             return {'status': 'error', 'message': f'Receivable account missing for employee {creator_emp.name or creator_user.name}'}
    #
    #         # 2. Create Transaction Booking
    #         booking_vals = {
    #             'customer_id': order.customer_id.id,
    #             'sale_order_id': order.id,
    #             'reffno': order.name or str(order.id),
    #             'Sales_order_number': str(order.id),
    #             'payment_method': 'bank_transfer',
    #             'payment_status': 'pending',
    #             'bank_reff': '0000',
    #             'trx_date': fields.Date.today(),
    #             'amount': order.total_price,
    #             'company_id': order.company_id.id or request.env.company.id,
    #         }
    #         booking = request.env['idil.transaction_booking'].sudo().create(booking_vals)
    #
    #         # 3. Debit Line (Waiter Receivable)
    #         request.env['idil.transaction_bookingline'].sudo().create({
    #             'transaction_booking_id': booking.id,
    #             'description': f"Waiter sale receivable for Order #{order.id}",
    #             'account_number': receivable_id,
    #             'transaction_type': 'dr',
    #             'dr_amount': order.total_price,
    #             'cr_amount': 0,
    #             'transaction_date': fields.Date.today(),
    #             'bank_reff': '0000',
    #         })
    #
    #         # 4. Credit Lines (Product Income)
    #         for line in order.order_lines:
    #             product = line.product_id
    #             income_id = product.income_account_id.id
    #             if not income_id:
    #                  raise Exception(f'Income account missing for {product.name}')
    #
    #             request.env['idil.transaction_bookingline'].sudo().create({
    #                 'transaction_booking_id': booking.id,
    #                 'description': f"Sales Income for - {product.name}",
    #                 'product_id': product.id,
    #                 'account_number': income_id,
    #                 'transaction_type': 'cr',
    #                 'dr_amount': 0,
    #                 'cr_amount': line.line_total,
    #                 'transaction_date': fields.Date.today(),
    #                 'bank_reff': '0000',
    #             })
    #
    #         # 5. Update Order State (write as superuser to bypass restriction, but track confirmed_by)
    #         order.write({
    #             'state': 'confirmed',
    #             'confirmed_by': real_uid,
    #             'confirmed_at': fields.Datetime.now(),
    #         })
    #
    #         return {'status': 'success'}
    #
    #     except Exception as e:
    #         _logger.error("Confirm Order Error: %s", str(e))
    #         return {'status': 'error', 'message': str(e)}

    def _real_uid(self, user_id=None, **kwargs):
        """
        Resolve the real user id in public routes.
        Priority:
          1) explicit user_id param
          2) kwargs['user_id']
          3) request.jsonrequest['user_id']
          4) request.uid (will be public=4 usually)
        """
        uid = user_id or kwargs.get('user_id')
        if not uid:
            try:
                uid = (request.jsonrequest or {}).get('user_id')
            except Exception:
                uid = None
        if not uid:
            uid = request.uid
        return int(uid)

    def _get_emp(self, real_uid):
        emp = request.env['idil.employee'].sudo().search([('user_id', '=', int(real_uid))], limit=1)
        return emp

    def _deny(self, msg):
        return {'status': 'error', 'message': msg}

    # ------------------------------------------------------------------
    # ✅ KITCHEN: Reduce Line Qty
    # ------------------------------------------------------------------
    @http.route('/nagaad/api/kitchen_reduce_line_qty', type='json', auth='public', csrf=False, cors='*')
    def kitchen_reduce_line_qty(self, user_id=None, order_id=None, line_id=None, new_qty=None, **kwargs):
        try:
            real_uid = self._real_uid(user_id=user_id, **kwargs)
            _logger.warning("KITCHEN_REDUCE: real_uid=%s request.uid=%s", real_uid, request.uid)

            # 1) Employee / Permission
            emp = self._get_emp(real_uid)
            if not emp:
                return self._deny(f"Permission Denied: User {real_uid} not linked to Employee.")

            # Only kitchen/manager allowed (change if you want waiter too)
            if getattr(emp, 'access_type', '') not in ['waiter', 'kitchen', 'manager']:
                return self._deny("Permission Denied: Only Waiter/Kitchen/Manager can reduce quantity.")

            if not getattr(emp, 'allow_reduce_qty', False):
                return self._deny("Permission Denied: You are not allowed to reduce quantity.")

            # 2) Validate order
            order = request.env['idil.customer.place.order'].sudo().browse(int(order_id))
            if not order.exists():
                return self._deny("Order not found")

            if order.state == 'confirmed':
                return self._deny("Cannot edit confirmed orders.")

            # 3) Validate line belongs to order
            line = request.env['idil.customer.place.order.line'].sudo().browse(int(line_id))
            if not line.exists() or line.order_id.id != order.id:
                return self._deny("Line not found or does not belong to order")

            new_qty_val = float(new_qty)
            current_qty = float(line.quantity or 0.0)

            if new_qty_val < 0:
                return self._deny("Quantity cannot be negative")

            if new_qty_val >= current_qty:
                return self._deny("New quantity must be less than current quantity")

            # 4) Execute as REAL user (fix write_uid)
            LineUser = request.env['idil.customer.place.order.line'].with_user(real_uid)

            if new_qty_val == 0:
                if not getattr(emp, 'allow_delete_line', False):
                    return self._deny("Permission Denied: Reducing to 0 requires delete permission.")

                LineUser.browse(line.id).unlink()
                return {'status': 'success', 'message': 'Line deleted (qty 0)', 'line_id': int(line_id), 'new_qty': 0}

            # Reduce to smaller qty
            LineUser.browse(line.id).write({
                'quantity': new_qty_val,
                # optional: reset kitchen pending, depends on your rule
                # 'kitchen_printed_qty': 0.0,
                # 'status': 'normal',
            })

            return {'status': 'success', 'message': 'Qty updated', 'line_id': int(line_id), 'new_qty': new_qty_val}

        except Exception as e:
            _logger.exception("Kitchen Reduce Qty Error")
            return self._deny(str(e))

    # ------------------------------------------------------------------
    # ✅ KITCHEN: Delete Line
    # ------------------------------------------------------------------
    @http.route('/nagaad/api/kitchen_delete_line', type='json', auth='public', csrf=False, cors='*')
    def kitchen_delete_line(self, user_id=None, order_id=None, line_id=None, **kwargs):
        try:
            real_uid = self._real_uid(user_id=user_id, **kwargs)
            _logger.warning("KITCHEN_DELETE: real_uid=%s request.uid=%s", real_uid, request.uid)

            # 1) Employee / Permission
            emp = self._get_emp(real_uid)
            if not emp:
                return self._deny(f"Permission Denied: User {real_uid} not linked to Employee.")

            if getattr(emp, 'access_type', '') not in [ 'waiter', 'kitchen', 'manager']:
                return self._deny("Permission Denied: Only Waiter/Kitchen/Manager can delete lines.")

            if not getattr(emp, 'allow_delete_line', False):
                return self._deny("Permission Denied: You are not allowed to delete lines.")

            # 2) Validate order
            order = request.env['idil.customer.place.order'].sudo().browse(int(order_id))
            if not order.exists():
                return self._deny("Order not found")

            if order.state == 'confirmed':
                return self._deny("Cannot edit confirmed orders.")

            # 3) Validate line belongs to order
            line = request.env['idil.customer.place.order.line'].sudo().browse(int(line_id))
            if not line.exists() or line.order_id.id != order.id:
                return self._deny("Line not found or does not belong to order")

            # 4) Execute as REAL user (fix write_uid)
            request.env['idil.customer.place.order.line'].with_user(real_uid).browse(line.id).unlink()

            return {'status': 'success', 'message': 'Line deleted', 'line_id': int(line_id)}

        except Exception as e:
            _logger.exception("Kitchen Delete Line Error")
            return self._deny(str(e))