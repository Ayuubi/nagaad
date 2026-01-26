from odoo import http
from odoo.http import request
import json


class NagaadApi(http.Controller):

    def _get_uid_from_request(self, params):
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
        uid = self._get_uid_from_request(params)
        if not uid:
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
            ['id', 'order_id', 'product_id', 'quantity', 'sale_price', 'status', 'line_total', 'menu_name']
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
        line.write({'quantity': float(quantity)})
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
    @http.route('/nagaad/api/add_order_line', type='json', auth='none', csrf=False, cors='*')
    def add_order_line(self, order_id, product_id, quantity, **params):
        uid = self._get_uid_from_request(params)
        if not uid:
            return {'status': 'error', 'message': 'Session expired'}
        order = request.env['idil.customer.place.order'].sudo().browse(order_id)
        if order.state != 'draft':
            return {'status': 'error', 'message': 'Cannot add items to a confirmed order.'}
        product = request.env['my_product.product'].sudo().browse(product_id)
        request.env['idil.customer.place.order.line'].sudo().create({
            'order_id': order_id,
            'product_id': product_id,
            'quantity': float(quantity),
            'sale_price': product.sale_price,
            'menu_id': product.pos_categ_ids[0].id if product.pos_categ_ids else False,
            'status': 'add'
        })
        return {'status': 'success'}