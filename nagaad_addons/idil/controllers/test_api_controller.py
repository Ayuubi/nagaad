from odoo import http
from odoo.http import request
import json

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
                'type': product.categ_id.name,  # You can use product type or category name
                'image_url': product.image_url  # Adjust as needed for image handling
            })
        
        # Return JSON response with products list
        return request.make_response(
            json.dumps({
                'status': 'success',
                'products': product_data ,
                'Type': list(pos_categories)
            }),
            headers={'Content-Type': 'application/json'}
        )

    @http.route('/api/pos/order', type='json', auth='public', methods=['POST'], csrf=False)
    def create_order(self, **kwargs):
        """Endpoint to create a POS order."""
        data = request.jsonrequest
        
        # Fetch necessary data from the request
        partner_id = data.get('partner_id')  # Optional, if you track customers
        order_lines = data.get('order_lines')
        
        if not order_lines:
            return {'status': 'error', 'message': 'Order lines cannot be empty'}
        
        # Get active session
        pos_session = request.env['pos.session'].search([('state', '=', 'opened')], limit=1)
        if not pos_session:
            return {'status': 'error', 'message': 'No open POS session found'}
        
        # Create the POS order
        pos_order = request.env['pos.order'].create({
            'partner_id': partner_id,
            'session_id': pos_session.id,
            'lines': [(0, 0, {
                'product_id': line['product_id'],
                'price_unit': line['price'],
                'qty': line['quantity'],
            }) for line in order_lines]
        })
        
        return {
            'status': 'success',
            'order_id': pos_order.id
        }
