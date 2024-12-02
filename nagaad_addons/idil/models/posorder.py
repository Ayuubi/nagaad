from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_is_zero, float_round
import logging
import time

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = "pos.order"

    def action_pos_order_paid(self):
        _logger.info("Starting action_pos_order_paid for order: %s", self.name)
        super(PosOrder, self).action_pos_order_paid()

        if self.state == 'paid':
            self.create_transaction_booking_lines()
        return True

    def get_manual_transaction_source_id(self):
        trx_source = self.env['idil.transaction.source'].search([('name', '=', 'Point of Sale')], limit=1)
        if not trx_source:
            raise ValidationError(_('Transaction source "Point of Sale" not found.'))
        return trx_source.id

    # def create_transaction_booking_lines(self):
    #     trx_source_id = self.get_manual_transaction_source_id()
    #
    #     for order in self:
    #         try:
    #             # Start a database transaction
    #             self.env.cr.execute('SAVEPOINT start_transaction')
    #
    #             # Step 1: Create the transaction booking
    #             payment_methods = self.determine_payment_methods(order)
    #             payment_method_id = next(iter(payment_methods))  # Get one payment method ID
    #             balance = order.amount_total - order.amount_paid
    #
    #             transaction_booking = self.env['idil.transaction_booking'].with_context(skip_validations=True).create({
    #                 'transaction_number': order.id,
    #                 'order_number': order.name,
    #                 'trx_source_id': trx_source_id,
    #                 'payment_method': 'other',
    #                 'pos_payment_method': payment_method_id,
    #                 'payment_status': 'paid' if order.amount_total == order.amount_paid else 'partial_paid',
    #                 'trx_date': order.date_order,
    #                 'amount': order.amount_total,
    #                 'amount_paid': order.amount_paid,
    #                 'remaining_amount': balance
    #             })
    #             _logger.info("Transaction Booking ID: %s", transaction_booking.id)
    #
    #             # Step 2: Create debit booking lines for each payment
    #             for payment in order.payment_ids:
    #                 payment_method_id = payment.payment_method_id.idil_payment_method_id.id
    #                 payment_method_record = self.env['idil.payment.method'].search(
    #                     [('id', '=', payment_method_id)], limit=1)
    #                 if not payment_method_record:
    #                     _logger.error("Payment method not found for ID %s", payment_method_id)
    #                     raise ValidationError(_("Payment method not found for ID %s") % payment_method_id)
    #
    #                 debit_line_vals = {
    #                     'transaction_booking_id': transaction_booking.id,
    #                     'description': payment_method_record.name,
    #                     'account_number': payment_method_record.account_number.id,
    #                     'transaction_type': 'dr',
    #                     'dr_amount': round(order.lines.price_subtotal, 2),
    #                     'cr_amount': 0.0,
    #                     'transaction_date': order.date_order
    #                 }
    #                 self.env['idil.transaction_bookingline'].create(debit_line_vals)
    #                 _logger.info("Created debit booking line for payment method: %s", payment_method_record.name)
    #
    #             # Step 3: Create credit booking lines for order lines
    #             for line in order.lines:
    #                 custom_product = self.env['my_product.product'].search(
    #                     [('id', '=', line.product_id.my_product_id.id)], limit=1)
    #                 if not custom_product:
    #                     _logger.error("Custom product not found for product %s", line.product_id.id)
    #                     raise ValidationError(_("Custom product not found for product %s") % line.product_id.id)
    #
    #                 credit_line_vals = {
    #                     'transaction_booking_id': transaction_booking.id,
    #                     'description': line.product_id.name,
    #                     'account_number': custom_product.income_account_id.id,
    #                     'transaction_type': 'cr',
    #                     'dr_amount': 0.0,
    #                     'cr_amount': round(line.price_subtotal, 2),
    #                     'transaction_date': order.date_order
    #                 }
    #                 self.env['idil.transaction_bookingline'].create(credit_line_vals)
    #                 _logger.info("Created credit booking line for product: %s", line.product_id.name)
    #
    #             # Step 4: Handle tax booking lines
    #             total_tax_amount = sum(
    #                 line.price_subtotal * line.product_id.taxes_id.amount / 100 for line in order.lines)
    #
    #             if total_tax_amount > 0:
    #                 for payment in order.payment_ids:
    #                     payment_method_id = payment.payment_method_id.idil_payment_method_id.id
    #                     payment_method_record = self.env['idil.payment.method'].search(
    #                         [('id', '=', payment_method_id)], limit=1)
    #                     debit_line_vals = {
    #                         'transaction_booking_id': transaction_booking.id,
    #                         'description': _('Tax Amount'),
    #                         'account_number': payment_method_record.account_number.id,
    #                         'transaction_type': 'dr',
    #                         'dr_amount': round(total_tax_amount, 2),
    #                         'cr_amount': 0.0,
    #                         'transaction_date': order.date_order
    #                     }
    #                     self.env['idil.transaction_bookingline'].create(debit_line_vals)
    #                     if not payment_method_record:
    #                         _logger.error("Payment method not found for ID %s", payment_method_id)
    #                         raise ValidationError(_("Payment method not found for ID %s") % payment_method_id)
    #
    #                 vat_account = self.get_vat_account()
    #                 tax_line_vals = {
    #                     'transaction_booking_id': transaction_booking.id,
    #                     'description': _('Tax Amount'),
    #                     'account_number': vat_account.id,
    #                     'transaction_type': 'cr',
    #                     'dr_amount': 0.0,
    #                     'cr_amount': round(total_tax_amount, 2),
    #                     'transaction_date': order.date_order
    #                 }
    #                 self.env['idil.transaction_bookingline'].create(tax_line_vals)
    #                 _logger.info("Created tax booking line for order: %s", order.name)
    #
    #             # Commit the transaction if all operations are successful
    #             self.env.cr.execute('RELEASE SAVEPOINT start_transaction')
    #
    #         except Exception as e:
    #             # Rollback the transaction if any exception occurs
    #             _logger.error("Error creating transaction booking lines for order %s: %s", order.name, str(e))
    #             self.env.cr.execute('ROLLBACK TO SAVEPOINT start_transaction')
    #             raise ValidationError(_("Error creating transaction booking lines: %s") % str(e))
    def create_transaction_booking_lines(self):
        trx_source_id = self.get_manual_transaction_source_id()

        for order in self:
            try:
                # Start a database transaction
                self.env.cr.execute('SAVEPOINT start_transaction')

                # Step 1: Create the transaction booking
                payment_methods = self.determine_payment_methods(order)
                payment_method_id = next(iter(payment_methods), None)  # Get one payment method ID safely
                balance = order.amount_total - order.amount_paid

                transaction_booking = self.env['idil.transaction_booking'].with_context(skip_validations=True).create({
                    'transaction_number': order.id,
                    'order_number': order.name,
                    'trx_source_id': trx_source_id,
                    'payment_method': 'other',
                    'pos_payment_method': payment_method_id,
                    'payment_status': 'paid' if order.amount_total == order.amount_paid else 'partial_paid',
                    'trx_date': order.date_order,
                    'amount': order.amount_total,
                    'amount_paid': order.amount_paid,
                    'remaining_amount': balance
                })
                _logger.info("Transaction Booking ID: %s", transaction_booking.id)

                # Step 2: Create debit booking lines for each payment
                for payment in order.payment_ids:
                    payment_method_record = payment.payment_method_id.idil_payment_method_id
                    if not payment_method_record:
                        _logger.error("Payment method not found for ID %s", payment.payment_method_id.id)
                        raise ValidationError(_("Payment method not found for ID %s") % payment.payment_method_id.id)

                    payment_method_record.ensure_one()  # Ensure the record is a singleton
                    debit_line_vals = {
                        'transaction_booking_id': transaction_booking.id,
                        'description': payment_method_record.name,
                        'account_number': payment_method_record.account_number.id,
                        'transaction_type': 'dr',
                        'dr_amount': round(sum(line.price_subtotal for line in order.lines), 2),
                        'cr_amount': 0.0,
                        'transaction_date': order.date_order
                    }
                    self.env['idil.transaction_bookingline'].create(debit_line_vals)
                    _logger.info("Created debit booking line for payment method: %s", payment_method_record.name)

                # Step 3: Create credit booking lines for order lines
                for line in order.lines:
                    custom_product = self.env['my_product.product'].search(
                        [('id', '=', line.product_id.my_product_id.id)], limit=1)
                    if not custom_product:
                        _logger.error("Custom product not found for product %s", line.product_id.id)
                        raise ValidationError(_("Custom product not found for product %s") % line.product_id.id)

                    credit_line_vals = {
                        'transaction_booking_id': transaction_booking.id,
                        'description': line.product_id.name,
                        'account_number': custom_product.income_account_id.id,
                        'transaction_type': 'cr',
                        'dr_amount': 0.0,
                        'cr_amount': round(line.price_subtotal, 2),
                        'transaction_date': order.date_order
                    }
                    self.env['idil.transaction_bookingline'].create(credit_line_vals)
                    _logger.info("Created credit booking line for product: %s", line.product_id.name)

                # Step 4: Handle tax booking lines
                total_tax_amount = sum(
                    line.price_subtotal * sum(tax.amount for tax in line.product_id.taxes_id) / 100 for line in
                    order.lines)

                if total_tax_amount > 0:
                    vat_account = self.get_vat_account()

                    tax_line_vals = {
                        'transaction_booking_id': transaction_booking.id,
                        'description': _('Tax Amount'),
                        'account_number': vat_account.id,
                        'transaction_type': 'cr',
                        'dr_amount': 0.0,
                        'cr_amount': round(total_tax_amount, 2),
                        'transaction_date': order.date_order
                    }
                    self.env['idil.transaction_bookingline'].create(tax_line_vals)
                    _logger.info("Created tax booking line for order: %s", order.name)

                    for payment in order.payment_ids:
                        payment_method_record = payment.payment_method_id.idil_payment_method_id
                        if not payment_method_record:
                            _logger.error("Payment method not found for ID %s", payment.payment_method_id.id)
                            raise ValidationError(
                                _("Payment method not found for ID %s") % payment.payment_method_id.id)

                        debit_line_vals = {
                            'transaction_booking_id': transaction_booking.id,
                            'description': payment_method_record.name + _('Tax Amount'),
                            'account_number': payment_method_record.account_number.id,
                            'transaction_type': 'dr',
                            'dr_amount': round(total_tax_amount, 2),
                            'cr_amount': 0.0,
                            'transaction_date': order.date_order
                        }
                        self.env['idil.transaction_bookingline'].create(debit_line_vals)

                # Commit the transaction if all operations are successful
                self.env.cr.execute('RELEASE SAVEPOINT start_transaction')

            except Exception as e:
                # Rollback the transaction if any exception occurs
                _logger.error("Error creating transaction booking lines for order %s: %s", order.name, str(e))
                self.env.cr.execute('ROLLBACK TO SAVEPOINT start_transaction')
                raise ValidationError(_("Error creating transaction booking lines: %s") % str(e))

    def determine_payment_methods(self, order):
        payment_methods = {}
        for payment in order.payment_ids:
            if payment.payment_method_id.id in payment_methods:
                payment_methods[payment.payment_method_id.id] += payment.amount
            else:
                payment_methods[payment.payment_method_id.id] = payment.amount
        return payment_methods

    def get_vat_account(self):
        # Search for the VAT account by name
        vat_account = self.env['idil.chart.account'].search([('name', '=', 'VAT')], limit=1)
        if not vat_account:
            raise ValidationError(_("VAT account not found. Please ensure that the VAT account exists in the system."))
        return vat_account
