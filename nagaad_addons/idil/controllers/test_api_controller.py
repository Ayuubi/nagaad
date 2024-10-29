from odoo import http
from odoo.http import request
import json
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

class PosOrderAPI(http.Controller):

    @http.route('/api/pos/products', type='http', auth='public', methods=['GET'])
    def get_products(self, **kwargs):
        products = request.env['product.product'].search([('available_in_pos', '=', True)])
        product_data = []
        
        for product in products:
            product_data.append({
                'id': product.id,
                'name': product.name,
                'price': product.lst_price,
                'type': product.categ_id.name,
                'image_url': product.image_url
            })
        
        return request.make_response(
            json.dumps({
                'status': 'success',
                'products': product_data,
            }),
            headers={'Content-Type': 'application/json'}
        )

    @http.route('/api/pos/order', type='json', auth='public', methods=['POST'], csrf=False)
    def create_order(self, **kwargs):
        data = request.httprequest.get_json()
        _logger.info("Received data: %s", data)

        try:
            partner_id = data.get('partner_id')
            order_lines = data.get('order_lines')
            session_id = data.get('session_id')

            if not order_lines:
                return {'status': 'error', 'message': 'Order lines cannot be empty'}

            pos_session = request.env['pos.session'].browse(session_id) if session_id else request.env['pos.session'].search([('state', '=', 'opened')], limit=1)
            if not pos_session or pos_session.state != 'opened':
                return {'status': 'error', 'message': 'No valid open POS session found'}

            cashier_name = pos_session.user_id.name  # Retrieve the cashier's name
            total_price = 0
            pos_order_lines = []

            # Get the current timestamp
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

            # Get the product category from the first product in the order lines
            first_product_id = order_lines[0]['product_id']
            product_category = request.env['product.product'].browse(first_product_id).categ_id.name or "Uncategorized"

            # Generate the order reference
            last_order = request.env['pos.order'].search([], order='id desc', limit=1)
            incremental_number = (last_order.id + 1) if last_order else 1
            order_reference = f"nagaad/{cashier_name}/{product_category}/api/{timestamp}-{incremental_number}"

            for line in order_lines:
                product = request.env['product.product'].browse(line['product_id'])
                if not product:
                    return {'status': 'error', 'message': f"Product ID {line['product_id']} not found"}

                price_unit = line['price']
                quantity = line['quantity']
                price_subtotal = price_unit * quantity
                price_subtotal_incl = price_subtotal * 1.05  # Including 5% tax

                pos_order_lines.append((0, 0, {
                    'product_id': product.id,
                    'price_unit': price_unit,
                    'qty': quantity,
                    'price_subtotal': price_subtotal,
                    'price_subtotal_incl': price_subtotal_incl,
                    'tax_ids': [(6, 0, product.taxes_id.ids)],
                }))
                total_price += price_subtotal_incl  # Add the subtotal with tax to the total

            amount_tax = total_price * 0.05  # Calculate total tax based on 5% tax rate

            pos_order = request.env['pos.order'].create({
                'partner_id': partner_id,
                'session_id': pos_session.id,
                'amount_total': total_price,
                'amount_tax': amount_tax,
                'amount_paid': 0.0,
                'amount_return': 0.0,
                'lines': pos_order_lines,
                'name': order_reference  # Set custom order reference
            })

            # Trigger recompute on related fields
            pos_order.lines._compute_product_id()

            return {
                'status': 'success',
                'order_id': pos_order.id,
                'session_id': pos_session.id,
                'order_reference': order_reference
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error("Error creating POS order: %s", str(e))
            return {
                'status': 'error',
                'message': 'Failed to create POS order',
                'details': str(e)
            }
