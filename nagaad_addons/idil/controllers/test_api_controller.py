from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class PosOrderController(http.Controller):

    @http.route('/api/pos/order', type='json', auth='public', methods=['POST'], csrf=False)
    def create_order(self, **kwargs):
        data = request.httprequest.get_json()
        _logger.info("Received data: %s", data)

        try:
            # Extract partner_id, order_lines, session_id, and cashier_id from the request data
            partner_id = data.get('partner_id')
            order_lines = data.get('order_lines')
            session_id = data.get('session_id')
            cashier_id = data.get('cashier_id')  # Optional field for hr.employee

            # Validate mandatory fields
            if not order_lines:
                return {'status': 'error', 'message': 'Order lines cannot be empty'}
            if not session_id:
                return {'status': 'error', 'message': 'Session ID is required'}

            # Get the POS session
            pos_session = request.env['pos.session'].browse(session_id)
            if not pos_session or pos_session.state != 'opened':
                return {'status': 'error', 'message': 'No valid open POS session found'}

            # Validate partner (customer)
            partner = None
            if partner_id:
                partner = request.env['res.partner'].browse(partner_id)
                if not partner.exists():
                    return {'status': 'error', 'message': f"Partner ID {partner_id} not found"}

            # Validate cashier (from hr.employee)
            cashier = None
            if cashier_id:
                cashier = request.env['hr.employee'].browse(cashier_id)
                if not cashier.exists():
                    return {'status': 'error', 'message': f"Cashier ID {cashier_id} not found"}

            # Process order lines
            pos_order_lines = []
            total_price = 0.0
            total_tax = 0.0

            for line in order_lines:
                product = request.env['product.product'].browse(line['product_id'])
                if not product.exists():
                    return {'status': 'error', 'message': f"Product ID {line['product_id']} not found"}

                # Calculate line totals
                price_unit = line.get('price', 0.0)
                quantity = line.get('quantity', 1)
                price_subtotal = price_unit * quantity
                taxes = product.taxes_id.compute_all(price_unit, pos_session.currency_id, quantity)
                price_subtotal_incl = taxes['total_included']
                tax_ids = [(6, 0, [tax.id for tax in product.taxes_id])]

                # Add to order lines
                pos_order_lines.append((0, 0, {
                    'product_id': product.id,
                    'name': product.name,
                    'price_unit': price_unit,
                    'qty': quantity,
                    'price_subtotal': price_subtotal,
                    'price_subtotal_incl': price_subtotal_incl,
                    'tax_ids': tax_ids,
                }))
                total_price += price_subtotal_incl
                total_tax += taxes['total_included'] - taxes['total_excluded']

            # Create POS order in 'draft' state (not finalized)
            pos_order_vals = {
                'name': pos_session.config_id.sequence_id.next_by_id(),  # Generate the order name
                'session_id': pos_session.id,
                'partner_id': partner_id,
                'pricelist_id': pos_session.config_id.pricelist_id.id,
                'currency_id': pos_session.currency_id.id,
                'amount_total': total_price,
                'amount_tax': total_tax,
                'amount_paid': 0.0,  # Can be updated later for payments
                'amount_return': 0.0,
                'lines': pos_order_lines,
                'state': 'draft',  # Set the state to 'draft'
                'cashier': cashier.name if cashier else "Unknown Cashier",  # Use provided cashier or default
            }
            pos_order = request.env['pos.order'].create(pos_order_vals)

            # Return success response with all relevant order details
            return {
                'status': 'success',
                'order': {
                    'id': pos_order.id,
                    'name': pos_order.name,  # Order Ref
                    'session_id': pos_order.session_id.id,  # Session
                    'date_order': pos_order.date_order,  # Date
                    'point_of_sale': pos_order.session_id.config_id.display_name,  # Point of Sale
                    'receipt_number': pos_order.pos_reference,  # Receipt Number
                    'customer_name': pos_order.partner_id.name if pos_order.partner_id else None,  # Customer
                    'employee': cashier.name if cashier else "Unknown Cashier",  # Employee (Cashier from hr.employee)
                    'amount_total': pos_order.amount_total,  # Total
                    'status': pos_order.state,  # Status
                    'lines': [
                        {
                            'product_id': line.product_id.id,
                            'product_name': line.product_id.name,
                            'qty': line.qty,
                            'price_unit': line.price_unit,
                            'price_subtotal': line.price_subtotal,
                            'price_subtotal_incl': line.price_subtotal_incl,
                        }
                        for line in pos_order.lines
                    ],
                }
            }

        except Exception as e:
            request.env.cr.rollback()
            _logger.error("Error creating POS order: %s", str(e))
            return {
                'status': 'error',
                'message': 'Failed to create POS order',
                'details': str(e)
            }
