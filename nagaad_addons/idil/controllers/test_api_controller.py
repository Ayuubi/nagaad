from odoo import http
from odoo.http import request
import json
import logging

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

            # Get the open session or verify if the provided session_id is valid
            pos_session = request.env['pos.session'].browse(session_id) if session_id else request.env['pos.session'].search([('state', '=', 'opened')], limit=1)
            if not pos_session or pos_session.state != 'opened':
                return {'status': 'error', 'message': 'No valid open POS session found'}

            total_price = 0
            pos_order_lines = []

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
                    'name': product.display_name,  # Ensures product name is included
                    'price_unit': price_unit,
                    'qty': quantity,
                    'price_subtotal': price_subtotal,
                    'price_subtotal_incl': price_subtotal_incl,
                    'tax_ids': [(6, 0, product.taxes_id.ids)],
                }))
                total_price += price_subtotal_incl

            amount_tax = total_price * 0.05  # Calculate total tax based on 5% tax rate

            # Create POS order with Order Reference
            pos_order = request.env['pos.order'].create({
                'partner_id': partner_id,
                'session_id': pos_session.id,
                'name': request.env['ir.sequence'].next_by_code('pos.order'),  # Generates the reference if missing
                'amount_total': total_price,
                'amount_tax': amount_tax,
                'amount_paid': 0.0,
                'amount_return': 0.0,
                'lines': pos_order_lines
            })

            # Adding a dummy payment line (modify if required by your POS configuration)
            payment_method = pos_session.config_id.journal_id
            if payment_method:
                pos_order.add_payment({
                    'amount': total_price,
                    'payment_date': fields.Datetime.now(),
                    'payment_method_id': payment_method.id,
                })

            return {
                'status': 'success',
                'order_id': pos_order.id,
                'session_id': pos_session.id
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error("Error creating POS order: %s", str(e))
            return {
                'status': 'error',
                'message': 'Failed to create POS order',
                'details': str(e)
            }
