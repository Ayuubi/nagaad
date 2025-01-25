from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class PosOrderController(http.Controller):

    @http.route('/api/pos/session', type='json', auth='public', methods=['GET'], csrf=False)
    def get_latest_session(self):
        try:
            # Get the latest open session
            pos_session = request.env['pos.session'].sudo().search([
                ('state', '=', 'opened')
            ], limit=1, order='create_date desc')

            if not pos_session:
                return {'status': 'error', 'message': 'No open POS session found'}

            return {
                'status': 'success',
                'session_id': pos_session.id
            }
        except Exception as e:
            _logger.error("Error getting latest session: %s", str(e))
            return {'status': 'error', 'message': str(e)}

    @http.route('/api/pos/order', type='json', auth='public', methods=['POST'], csrf=False)
    def create_order(self, **kwargs):
        data = request.httprequest.get_json()
        _logger.info("Received data from Flutter: %s", data)

        try:
            # Extract data from Flutter request
            params = data.get('params', {})
            partner_id = params.get('partner_id')
            order_lines = params.get('order_lines', [])
            session_id = params.get('session_id')
            # Default employee_id if not provided
            employee_id = params.get('employee_id') or 1  # Using 1 as default employee ID

            # Validate mandatory fields
            if not order_lines:
                return {'status': 'error', 'message': 'Order lines cannot be empty'}

            # Get the POS session if not provided
            if not session_id:
                pos_session = request.env['pos.session'].sudo().search([
                    ('state', '=', 'opened')
                ], limit=1, order='create_date desc')
                if not pos_session:
                    return {'status': 'error', 'message': 'No valid open POS session found'}
                session_id = pos_session.id

            # Get the POS session
            pos_session = request.env['pos.session'].sudo().browse(session_id)
            if not pos_session.exists() or pos_session.state != 'opened':
                return {'status': 'error', 'message': 'No valid open POS session found'}

            # Process order lines
            pos_order_lines = []
            total_price = 0.0
            total_tax = 0.0

            for line in order_lines:
                product_id = line.get('product_id')
                price_unit = float(line.get('price_unit', 0.0))
                quantity = float(line.get('qty', 1))
                name = line.get('name', '')

                # Try to find product by ID first, then by name if ID is not found
                product = request.env['product.product'].sudo().browse(product_id)
                if not product.exists():
                    # Search by name as fallback
                    product = request.env['product.product'].sudo().search([
                        ('name', '=ilike', name)
                    ], limit=1)
                    if not product:
                        return {'status': 'error', 'message': f"Product not found: {name}"}

                # Calculate line totals
                price_subtotal = price_unit * quantity
                taxes = product.taxes_id.compute_all(price_unit, pos_session.currency_id, quantity)
                price_subtotal_incl = taxes['total_included']
                tax_ids = [(6, 0, [tax.id for tax in product.taxes_id])]

                pos_order_lines.append((0, 0, {
                    'product_id': product.id,
                    'name': name or product.name,
                    'full_product_name': product.name,
                    'price_unit': price_unit,
                    'qty': quantity,
                    'price_subtotal': price_subtotal,
                    'price_subtotal_incl': price_subtotal_incl,
                    'tax_ids': tax_ids,
                }))
                total_price += price_subtotal_incl
                total_tax += taxes['total_included'] - taxes['total_excluded']

            # Generate pos_reference
            pos_config_name = pos_session.config_id.name or "POS"
            sequence_number = request.env['ir.sequence'].sudo().next_by_id(pos_session.config_id.sequence_id.id)
            pos_reference = f"{pos_config_name}/{sequence_number}"

            # Create POS order
            pos_order = request.env['pos.order'].sudo().create({
                'name': pos_reference,
                'pos_reference': pos_reference,
                'session_id': pos_session.id,
                'partner_id': partner_id,
                'pricelist_id': pos_session.config_id.pricelist_id.id,
                'currency_id': pos_session.currency_id.id,
                'amount_total': total_price,
                'amount_tax': total_tax,
                'amount_paid': total_price,  # Mark as paid for Flutter orders
                'amount_return': 0.0,
                'lines': pos_order_lines,
                'state': 'paid',  # Set as paid for Flutter orders
                'user_id': request.env.user.id,
                'employee_id': employee_id,
            })

            # Create payment
            payment_method = request.env['pos.payment.method'].sudo().search([], limit=1)
            if payment_method:
                request.env['pos.payment'].sudo().create({
                    'amount': total_price,
                    'payment_method_id': payment_method.id,
                    'pos_order_id': pos_order.id,
                })

            return {
                'status': 'success',
                'message': 'Order created successfully',
                'data': {
                    'order_id': pos_order.id,
                    'pos_reference': pos_reference,
                    'amount_total': total_price,
                }
            }

        except Exception as e:
            _logger.error("Error creating order: %s", str(e), exc_info=True)
            return {'status': 'error', 'message': str(e)}
