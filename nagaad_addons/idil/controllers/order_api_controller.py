from odoo import http
from odoo.http import request, Response
import json

class OrderAPIController(http.Controller):

    @http.route('/api/orders', type='json', auth='public', methods=['POST'], csrf=False)
    def create_order(self, **kwargs):
        # Retrieve session ID, order details, and cashier ID from request
        session_id = kwargs.get('session_id')
        cashier_id = kwargs.get('cashier_id')  # New parameter for cashier ID
        order_data = kwargs.get('order_data')  # Example: [{'product_id': 1, 'quantity': 2}, ...]

        # Check if session exists and is active
        pos_session = request.env['pos.session'].sudo().browse(session_id)
        if not pos_session or pos_session.state != 'opened':
            return Response(json.dumps({'error': 'Session not found or not active'}), status=400, content_type='application/json')

        # Create the order in Odoo POS
        try:
            order = request.env['pos.order'].sudo().create({
                'session_id': pos_session.id,
                'user_id': cashier_id,  # Assign the cashier who placed the order
                'lines': [(0, 0, {
                    'product_id': item['product_id'],
                    'qty': item['quantity'],
                }) for item in order_data],
            })
            # Return a success message with the order ID
            return Response(json.dumps({'success': True, 'order_id': order.id}), content_type='application/json')
        except Exception as e:
            return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')
