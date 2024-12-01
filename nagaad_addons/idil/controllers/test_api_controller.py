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
            # Extract partner_id, order_lines, session_id, and employee_id
            partner_id = data.get('partner_id')
            order_lines = data.get('order_lines')
            session_id = data.get('session_id')
            employee_id = data.get('employee_id')  # Employee ID provided by the user

            # Validate mandatory fields
            if not order_lines:
                return {'status': 'error', 'message': 'Order lines cannot be empty'}
            if not session_id:
                return {'status': 'error', 'message': 'Session ID is required'}
            if not employee_id:
                return {'status': 'error', 'message': 'Employee ID is required'}

            # Validate the employee_id
            employee = request.env['hr.employee'].browse(employee_id)
            if not employee.exists():
                return {'status': 'error', 'message': f"Employee ID {employee_id} not found"}

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
            sequence_id = pos_session.config_id.sequence_id.id
            sequence_number = request.env['ir.sequence'].sudo().browse(sequence_id).next_by_id()
            pos_reference = f"{pos_config_name}/{sequence_number}"  # Match Odoo's standard format

            _logger.info("Generated pos_reference: %s", pos_reference)

            # Create POS order
            pos_order_vals = {
                'name': pos_reference,  # Order name
                'pos_reference': pos_reference,  # Ensure this field is never null
                'session_id': pos_session.id,
                'partner_id': partner_id or None,
                'pricelist_id': pos_session.config_id.pricelist_id.id,
                'currency_id': pos_session.currency_id.id,
                'amount_total': total_price,
                'amount_tax': total_tax,
                'amount_paid': 0.0,
                'amount_return': 0.0,
                'lines': pos_order_lines or [],
                'state': 'draft',
                'user_id': request.env.user.id,
                'employee_id': employee_id,
            }

            _logger.info("pos_order_vals: %s", pos_order_vals)

            pos_order = request.env['pos.order'].create(pos_order_vals)

            # Commit changes
            request.env.cr.commit()

            # Return success response
            return {
                'status': 'success',
                'order': {
                    'id': pos_order.id,
                    'name': pos_order.name,
                    'session_id': pos_order.session_id.id,
                    'date_order': pos_order.date_order,
                    'point_of_sale': pos_order.session_id.config_id.display_name,
                    'receipt_number': pos_order.pos_reference,
                    'customer_name': pos_order.partner_id.name if pos_order.partner_id else None,
                    'employee': employee.name,
                    'amount_total': pos_order.amount_total,
                    'status': pos_order.state,
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
