from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)

class PosOrderAPI(http.Controller):

    @http.route('/api/pos/products', type='http', auth='public', methods=['GET'])
    def get_products(self, **kwargs):
        """Endpoint to retrieve POS products with necessary details."""
        products = request.env['product.product'].search([('available_in_pos', '=', True)])
        product_data = []
        
        for product in products:
            product_data.append({
                'id': product.id,
                'name': product.name,
                'price': product.lst_price,
                'type': product.categ_id.name,  # Use product type or category name
                'image_url': product.image_url  # Adjust as needed for image handling
            })
        
        # Return JSON response with products list
        return request.make_response(
            json.dumps({
                'status': 'success',
                'products': product_data,
            }),
            headers={'Content-Type': 'application/json'}
        )

    @http.route('/api/pos/order', type='json', auth='public', methods=['POST'], csrf=False)
    def create_order(self, **kwargs):
        """Endpoint to create a POS order with a 5% tax calculation."""
        # Parse incoming JSON data
        data = request.httprequest.get_json()
        _logger.info("Received data: %s", data)  # Log the request data for debugging

        # Fetch necessary data from the request
        partner_id = data.get('partner_id')  # Optional, if tracking customers
        order_lines = data.get('order_lines')
        session_id = data.get('session_id')  # Specify session ID if provided

        # Validate the existence of order lines
        if not order_lines:
            return {'status': 'error', 'message': 'Order lines cannot be empty'}
        
        # Find or validate the POS session
        pos_session = request.env['pos.session'].browse(session_id) if session_id else request.env['pos.session'].search([('state', '=', 'opened')], limit=1)
        if not pos_session or pos_session.state != 'opened':
            return {'status': 'error', 'message': 'No valid open POS session found'}

        # Calculate the total price and tax
        total_price = sum(line['price'] * line['quantity'] for line in order_lines)
        amount_tax = total_price * 0.05  # 5% tax

        # Initial amounts for the order
        amount_paid = 0.0  # Initially, no amount is paid
        amount_return = 0.0  # No return amount at order creation

        # Prepare the order lines in the format expected by Odoo
        pos_order_lines = [(0, 0, {
            'product_id': line['product_id'],
            'price_unit': line['price'],
            'qty': line['quantity'],
            'tax_ids': [(6, 0, request.env['product.product'].browse(line['product_id']).taxes_id.ids)],  # Retrieve tax_ids from the product
        }) for line in order_lines]

        # Create the POS order
        try:
            pos_order = request.env['pos.order'].create({
                'partner_id': partner_id,
                'session_id': pos_session.id,
                'amount_total': total_price,
                'amount_tax': amount_tax,
                'amount_paid': amount_paid,
                'amount_return': amount_return,
                'lines': pos_order_lines
            })

            return {
                'status': 'success',
                'order_id': pos_order.id,
                'session_id': pos_session.id
            }

        except Exception as e:
            _logger.error("Error creating POS order: %s", str(e))
            return {
                'status': 'error',
                'message': 'Failed to create POS order',
                'details': str(e)
            }
