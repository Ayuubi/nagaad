from datetime import datetime
import json
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class POSOrderController(http.Controller):

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
                'products': product_data   
            }),
            headers={'Content-Type': 'application/json'}
        )

    @http.route('/api/pos/order', type='json', auth='public', methods=['POST'], csrf=False)
    def create_order(self, **kwargs):
        # Get JSON data from the request
        data = request.httprequest.get_json()
        _logger.info("Received data: %s", data)

        try:
            # Extract partner_id, order_lines, and session_id from the request data
            partner_id = data.get('partner_id')
            order_lines = data.get('order_lines')
            session_id = data.get('session_id')

            # Check if order lines are present
            if not order_lines:
                return {'status': 'error', 'message': 'Order lines cannot be empty'}

            # Get the POS session; check if it's opened and valid
            pos_session = request.env['pos.session'].browse(session_id) if session_id else request.env['pos.session'].search([('state', '=', 'opened')], limit=1)
            if not pos_session or pos_session.state != 'opened':
                return {'status': 'error', 'message': 'No valid open POS session found'}

            # Retrieve the cashier's name from the POS session
            cashier_name = pos_session.user_id.name
            total_price = 0
            pos_order_lines = []

            # Process each order line and add it to pos_order_lines
            for line in order_lines:
                product = request.env['product.product'].browse(line['product_id'])
                if not product:
                    return {'status': 'error', 'message': f"Product ID {line['product_id']} not found"}

                price_unit = line['price']
                quantity = line['quantity']
                price_subtotal = price_unit * quantity
                price_subtotal_incl = price_subtotal * 1.05  # Applying a 5% tax

                pos_order_lines.append((0, 0, {
                    'product_id': product.id,
                    'name': product.display_name,
                    'price_unit': price_unit,
                    'qty': quantity,
                    'price_subtotal': price_subtotal,
                    'price_subtotal_incl': price_subtotal_incl,
                    'tax_ids': [(6, 0, product.taxes_id.ids)],  # Applying taxes
                }))
                total_price += price_subtotal_incl  # Adding to the total with tax

            # Calculate total tax amount
            amount_tax = total_price * 0.05

            # Create the POS order
            pos_order = request.env['pos.order'].create({
                'partner_id': partner_id,
                'session_id': pos_session.id,
                'amount_total': total_price,
                'amount_tax': amount_tax,
                'amount_paid': 0.0,
                'amount_return': 0.0,
                'lines': pos_order_lines,
            })

            # Retrieve the auto-generated receipt number from the `name` field
            receipt_number = pos_order.name

            # Return success response, including the auto-generated receipt number
            return {
                'status': 'success',
                'order_id': pos_order.id,
                'session_id': pos_session.id,
                'receipt_number': receipt_number,  # This will match the format in Odoo
                'cashier': cashier_name
            }

        except Exception as e:
            # Rollback any database transactions in case of an error
            request.env.cr.rollback()
            _logger.error("Error creating POS order: %s", str(e))
            # Return error response
            return {
                'status': 'error',
                'message': 'Failed to create POS order',
                'details': str(e)
            }
