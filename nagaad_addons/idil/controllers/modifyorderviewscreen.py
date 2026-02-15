from odoo import http
from odoo.http import request
import json
import logging


class NagaadApi(http.Controller):

    def _get_uid_from_request(self, params):
        # 0. Trusted user_id param (from mobile app secure storage)
        # This is critical for session recovery when cookies are lost
        uid_param = params.get('user_id')
        if uid_param:
            return int(uid_param)

        # 1. Try standard request session
        uid = request.session.uid
        if uid:
            return uid
            
        # 2. Try session_id from params (for mobile fallback)
        sid = params.get('session_id')
        if sid:
            # Re-associate session if SID is provided
            session = http.root.session_store.get(sid)
            if session and session.get('uid'):
                # Forcefully update the current request session
                request.session.update(session)
                return session.get('uid')
        return None

    # 1. THE BIG FETCH: Get all orders and products in one go
    @http.route('/nagaad/api/get_waiter_orders', type='json', auth='none', csrf=False, cors='*')
    def get_waiter_orders(self, **params):
        _logger = logging.getLogger(__name__)
        _logger.warning("🔍 VIEW SCREEN PARAMS: %s", params)
        
        uid = self._get_uid_from_request(params)
        _logger.warning("🔍 VIEW SCREEN RESOLVED UID: %s", uid)
        
        if not uid:
            _logger.error("❌ Session expired check failed")
            return {'status': 'error', 'message': 'Session expired'}

        # Fetch Orders for this waiter
        orders = request.env['idil.customer.place.order'].sudo().search_read(
            [('waiter_id', '=', uid)],
            ['id', 'customer_id', 'order_lines', 'create_date', 'state', 'total_price', 'order_mode', 'table_no'],
            order='id desc', limit=100
        )
        # ... logic for group/fetch products
        # ... (rest of the fetching logic)
        
        # Mapping lines to their orders
        all_line_ids = []
        for o in orders:
            all_line_ids.extend(o.get('order_lines', []))

        lines = request.env['idil.customer.place.order.line'].sudo().search_read(
            [('id', 'in', all_line_ids)],
            ['id', 'order_id', 'product_id', 'quantity', 'sale_price', 'status', 'line_total', 'menu_name', 'kitchen_printed_qty']
        )

        line_map = {}
        for l in lines:
            oid = l['order_id'][0] if isinstance(l['order_id'], (list, tuple)) else l['order_id']
            if oid not in line_map: line_map[oid] = []
            line_map[oid].append(l)

        orders_by_date = {}
        for o in orders:
            o['lines'] = line_map.get(o['id'], [])
            date_key = str(o['create_date']).split(' ')[0] if o['create_date'] else 'Unknown'
            if date_key not in orders_by_date: orders_by_date[date_key] = []
            orders_by_date[date_key].append(o)

        products = request.env['my_product.product'].sudo().search_read([], ['id', 'name', 'sale_price', 'pos_categ_ids'])

        return {
            'status': 'success',
            'orders_by_date': orders_by_date,
            'product_list': products
        }

    # 2. UPDATE QTY: Only if draft
    @http.route('/nagaad/api/update_order_line', type='json', auth='none', csrf=False, cors='*')
    def update_order_line(self, line_id, quantity, **params):
        uid = self._get_uid_from_request(params)
        if not uid:
            return {'status': 'error', 'message': 'Session expired'}
        
        line = request.env['idil.customer.place.order.line'].sudo().browse(line_id)
        # ...
        if line.order_id.state != 'draft':
            return {'status': 'error', 'message': 'Confirmed orders cannot be modified.'}

        new_qty = float(quantity)
        old_qty = float(line.quantity or 0.0)

        if new_qty < old_qty:
            # Rule 4: Reduction resets pending print
            line.write({'quantity': new_qty, 'kitchen_printed_qty': 0.0, 'status': 'normal'})
        elif new_qty > old_qty:
            # Rule 3: Increase accumulates diff
            diff = new_qty - old_qty
            new_pending = (line.kitchen_printed_qty or 0.0) + diff
            line.write({'quantity': new_qty, 'kitchen_printed_qty': new_pending, 'status': 'add'})
        
        return {'status': 'success'}

    # 3. DELETE ITEM: Only if draft
    @http.route('/nagaad/api/delete_order_line', type='json', auth='none', csrf=False, cors='*')
    def delete_order_line(self, line_id, **params):
        uid = self._get_uid_from_request(params)
        if not uid:
            return {'status': 'error', 'message': 'Session expired'}
        line = request.env['idil.customer.place.order.line'].sudo().browse(line_id)
        if line.order_id.state != 'draft':
            return {'status': 'error', 'message': 'Confirmed orders cannot be modified.'}
        line.unlink()
        return {'status': 'success'}

    # 4. ADD ITEM: Only if draft
