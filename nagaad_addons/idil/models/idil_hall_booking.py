from odoo import models, fields, api
from datetime import datetime

from odoo.exceptions import UserError, ValidationError


class HallBooking(models.Model):
    _name = 'idil.hall.booking'
    _description = 'Hall Booking Management'

    name = fields.Char(string='Booking No', required=True, copy=False, readonly=True, index=True, default='New')

    customer_id = fields.Many2one('idil.customer.registration', string='Customer', required=True)
    hall_id = fields.Many2one('idil.hall', string='Hall', required=True)
    booking_date = fields.Date(string='Booking Date', default=fields.Date.today, required=True)
    start_time = fields.Datetime(string='Start Time', required=True)
    end_time = fields.Datetime(string='End Time', required=True)
    duration = fields.Float(string='Duration (Hours)', compute='_compute_duration', store=True)
    no_of_guest = fields.Float(string='Total Guests')
    total_price = fields.Float(string='Total Price', compute='_compute_total_price', store=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('booked', 'Booked'),
        ('confirmed', 'Confirmed'),
        ('canceled', 'Canceled')
    ], string='Status', default='draft')
    # Adding payment method field
    payment_method_id = fields.Many2one('idil.payment.method', string='Payment Method', required=True)
    # Account Number Field (related to the selected Payment Method)
    account_number = fields.Char(string='Account Number', compute='_compute_account_number', store=True)

    # Total amount paid will now be computed from the sum of payments
    amount = fields.Float(string='Amount to Pay', store=True, default='')

    amount_paid = fields.Float(string='Amount Paid', default=0.0, compute='_compute_amount_paid', store=True)
    remaining_amount = fields.Float(string='Remaining Amount', default=0.0, store=True)

    payment_ids = fields.One2many('idil.hall.booking.payment', 'booking_id', string='Payments')

    @api.model
    def create(self, vals):
        hall = self.env['idil.hall'].browse(vals.get('hall_id'))

        # Check if the hall is under maintenance by checking its availability
        if hall.availability == 'maintenance':
            # Fetch the maintenance schedule for this hall to get the maintenance end time
            maintenance_schedule = self.env['idil.hall.schedule'].search([
                ('hall_id', '=', hall.id),
                ('status', '=', 'maintenance')
            ], order='end_time desc', limit=1)

            if maintenance_schedule:
                raise ValidationError(
                    "The selected hall is currently under maintenance and will be available after {}.".format(
                        maintenance_schedule.end_time
                    )
                )

        # Check if the selected hall is already booked
        hall = self.env['idil.hall'].browse(vals.get('hall_id'))
        if hall.availability == 'booked':
            # Find the last booking for this hall to get the end time
            last_booking = self.env['idil.hall.booking'].search([('hall_id', '=', hall.id)], order='end_time desc',
                                                                limit=1)
            if last_booking:
                raise ValidationError(
                    "The selected hall is not available at the moment. "
                    "It will become available after {}.".format(last_booking.end_time)
                )

        # Check if the number of guests is valid
        if 'no_of_guest' not in vals or vals.get('no_of_guest') <= 0:
            raise UserError("Please insert a valid number of guests.")

        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('idil.hall.booking') or 'New'

        # Create the booking record
        booking = super(HallBooking, self).create(vals)

        # Set the status and hall availability based on the amount and remaining amount
        if booking.remaining_amount > 0:
            booking.status = 'booked'
            booking.hall_id.availability = 'booked'
        elif booking.amount == 0:
            booking.status = 'draft'
        elif booking.total_price == booking.amount:
            booking.status = 'confirmed'
            booking.hall_id.availability = 'booked'

        # Create a payment entry if there is an amount to pay
        if booking.amount > 0:
            self.env['idil.hall.booking.payment'].create({
                'booking_id': booking.id,
                'payment_date': fields.Date.today(),
                'amount': booking.amount,
                'payment_method_id': booking.payment_method_id.id,
                'payment_reference': 'Initial Payment for Booking {}'.format(booking.name),
            })

        # Create the transaction after booking
        if booking.amount == 0:
            booking._create_transaction()

        return booking

    def _create_transaction(self):
        """Create a transaction based on the total price, amount paid, and remaining amount."""
        total_price = self.total_price
        amount_paid = self.amount
        remaining_amount = self.total_price - self.amount

        # Create the main transaction record
        transaction = self.env['idil.transaction_booking'].create({
            'transaction_number': self.env['ir.sequence'].next_by_code('idil.transaction_booking'),
            'reffno': self.name,
            'customer_id': self.customer_id.id,
            'trx_date': fields.Date.today(),
            'amount': total_price,
            'payment_method': 'cash',  # Assuming cash payment
        })

        # Create the credit line for the income (total price)
        self.env['idil.transaction_bookingline'].create({
            'transaction_booking_id': transaction.id,
            'description': 'Income for Hall Booking {}'.format(self.name),
            'account_number': self.hall_id.income_account_id.id,
            'transaction_type': 'cr',
            'cr_amount': total_price,
            'dr_amount': 0,
            'transaction_date': fields.Date.today(),
        })

        # Create debit line for the cash payment (if any amount was paid)
        if amount_paid > 0:
            self.env['idil.transaction_bookingline'].create({
                'transaction_booking_id': transaction.id,
                'description': 'Cash Payment for Hall Booking {}'.format(self.name),
                'account_number': self.payment_method_id.account_number.id,
                'transaction_type': 'dr',
                'dr_amount': amount_paid,
                'cr_amount': 0,
                'transaction_date': fields.Date.today(),
            })

        # Create debit line for the receivable if there is a remaining amount
        if remaining_amount > 0:
            self.env['idil.transaction_bookingline'].create({
                'transaction_booking_id': transaction.id,
                'description': 'Receivable for Hall Booking {}'.format(self.name),
                'account_number': self.hall_id.Receivable_account_id.id,
                'transaction_type': 'dr',
                'dr_amount': remaining_amount,
                'cr_amount': 0,
                'transaction_date': fields.Date.today(),
            })

    @api.depends('payment_method_id')
    def _compute_account_number(self):
        for record in self:
            if record.payment_method_id:
                record.account_number = record.payment_method_id.account_number.name
            else:
                record.account_number = ''

    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        for booking in self:
            if booking.start_time and booking.end_time:
                delta = fields.Datetime.from_string(booking.end_time) - fields.Datetime.from_string(booking.start_time)
                booking.duration = delta.total_seconds() / 3600  # Convert seconds to hours

    @api.depends('no_of_guest', 'hall_id')
    def _compute_total_price(self):
        for booking in self:
            if booking.no_of_guest and booking.hall_id:
                booking.total_price = booking.no_of_guest * booking.hall_id.price_per_hour

    def action_cancel_booking(self):
        """Custom action to cancel the booking"""
        self.status = 'canceled'

    @api.onchange('amount')
    def _onchange_amount(self):
        """Restrict modification of 'amount' if the booking is booked."""
        if self.status == 'booked':
            raise ValidationError("You cannot modify the 'Amount to Pay' field for a booking that is already booked.")

    def write(self, vals):
        """Override write method to handle changes, including updating transactions
        when the number of guests increases or decreases."""
        for booking in self:
            old_total_price = booking.total_price  # Store the old total price before the update

            # Call the original write method to update the booking record
            res = super(HallBooking, self).write(vals)

            # Check if the number of guests has changed, impacting the total price
            if 'no_of_guest' in vals or 'hall_id' in vals:
                new_total_price = booking.no_of_guest * booking.hall_id.price_per_hour
                price_difference = new_total_price - old_total_price

                # Update the booking's total price
                booking.total_price = new_total_price
                booking.remaining_amount = booking.total_price - booking.amount_paid

                # Adjust the transaction if the total price changes
                transaction = self.env['idil.transaction_booking'].search([('reffno', '=', booking.name)], limit=1)
                if transaction:
                    # Adjust the transaction lines based on the price difference
                    self._adjust_transaction_lines_on_price_change(transaction, price_difference, new_total_price)

                # Set the status and hall availability based on the amount and remaining amount
                if booking.remaining_amount > 0:
                    booking.status = 'booked'
                    booking.hall_id.availability = 'booked'
                elif booking.amount == 0:
                    booking.status = 'draft'
                elif booking.total_price == booking.amount:
                    booking.status = 'confirmed'
                    booking.hall_id.availability = 'booked'

        return res

    def _adjust_transaction_lines_on_price_change(self, transaction, price_difference, new_total_price):
        """Adjust transaction lines based on price change when number of guests increases or decreases."""
        booking = self
        cash_paid = booking.amount_paid

        # Adjust the main transaction amount (total price)
        new_total_amount = new_total_price
        transaction.write({'amount': new_total_amount})

        # Adjust the income line
        income_line = self.env['idil.transaction_bookingline'].search([
            ('transaction_booking_id', '=', transaction.id),
            ('account_number', '=', booking.hall_id.income_account_id.id),
            ('transaction_type', '=', 'cr')
        ], limit=1)

        if income_line:
            new_income_amount = income_line.cr_amount + price_difference

            # Ensure income doesn't go below the cash paid
            if new_income_amount < cash_paid:
                raise ValidationError("Income cannot be less than cash received.")
            income_line.write({
                'cr_amount': new_income_amount
            })

        # Adjust the receivable line if there is a remaining amount
        receivable_line = self.env['idil.transaction_bookingline'].search([
            ('transaction_booking_id', '=', transaction.id),
            ('account_number', '=', booking.hall_id.Receivable_account_id.id),
            ('transaction_type', '=', 'dr')
        ], limit=1)

        if receivable_line:
            new_receivable_amount = max(0, receivable_line.dr_amount + price_difference)
            receivable_line.write({
                'dr_amount': new_receivable_amount
            })
        else:
            # If no receivable line exists and price difference is positive, create one
            remaining_amount = max(0, booking.total_price - booking.amount_paid)
            if remaining_amount > 0:
                self.env['idil.transaction_bookingline'].create({
                    'transaction_booking_id': transaction.id,
                    'description': 'Receivable for Hall Booking {}'.format(booking.name),
                    'account_number': booking.hall_id.Receivable_account_id.id,
                    'transaction_type': 'dr',
                    'dr_amount': remaining_amount,
                    'cr_amount': 0,
                    'transaction_date': fields.Date.today(),
                })

    def unlink(self):
        """Override unlink to delete related payments and transactions when a booking is deleted."""
        for booking in self:
            # Delete related payments
            if booking.payment_ids:
                booking.payment_ids.unlink()

            # Find the related transaction
            transaction = self.env['idil.transaction_booking'].search([('reffno', '=', booking.name)], limit=1)
            if transaction:
                # Delete related transaction lines
                transaction.booking_lines.unlink()

                # Delete the main transaction
                transaction.unlink()

        # Finally, call the original unlink method to delete the booking
        return super(HallBooking, self).unlink()


class HallBookingPayment(models.Model):
    _name = 'idil.hall.booking.payment'
    _description = 'Hall Booking Payment'

    booking_id = fields.Many2one('idil.hall.booking', string='Hall Booking', required=True, ondelete='cascade')
    payment_date = fields.Date(string='Payment Date', default=fields.Date.today, required=True)
    amount = fields.Float(string='Payment Amount', required=True)
    payment_method_id = fields.Many2one('idil.payment.method', string='Payment Method', required=True)
    payment_reference = fields.Char(string='Payment Reference')

    @api.model
    def create(self, vals):
        """Override create method to automatically update the remaining amount after each payment."""
        payment = super(HallBookingPayment, self).create(vals)
        if payment.booking_id:
            # Update the booking's amount paid and remaining amount
            booking = payment.booking_id
            booking.amount_paid += payment.amount
            booking.remaining_amount = booking.total_price - booking.amount_paid

            # Set the status and hall availability based on the amount and remaining amount
            if booking.remaining_amount > 0:
                booking.status = 'booked'
                booking.hall_id.availability = 'booked'
            elif booking.amount == 0:
                booking.status = 'draft'
            elif booking.total_price == booking.amount:
                booking.status = 'confirmed'
                booking.hall_id.availability = 'booked'

            # Create the transaction booking only for the first payment
            payment._handle_transaction()

        return payment

    def _handle_transaction(self):
        """Create or update a transaction and booking lines when a payment is made."""
        booking = self.booking_id

        # Check if a main transaction booking already exists for this hall booking
        transaction = self.env['idil.transaction_booking'].search([('reffno', '=', booking.name)], limit=1)

        if not transaction:
            # Create a new transaction booking for the first payment with the total hall amount
            transaction = self.env['idil.transaction_booking'].create({
                'transaction_number': self.env['ir.sequence'].next_by_code('idil.transaction_booking'),
                'reffno': booking.name,
                'customer_id': booking.customer_id.id,
                'vendor_id': 0,
                'trx_date': fields.Date.today(),
                'amount': booking.total_price,  # Use the total hall price for the booking
                'payment_method': 'cash',
            })

        # Add booking lines for the current payment
        self._add_booking_lines(transaction)

    def _add_booking_lines(self, transaction):
        """Add booking lines based on the payment amount."""
        booking = self.booking_id
        paid_amount = self.amount

        # Find or create Debit Line for the cash (paid amount)
        debit_line = self.env['idil.transaction_bookingline'].search([
            ('transaction_booking_id', '=', transaction.id),
            ('account_number', '=', self.payment_method_id.account_number.id),  # Cash account
            ('transaction_type', '=', 'dr')
        ], limit=1)

        if debit_line:
            # If the line exists, update the cash amount
            debit_line.write({
                'dr_amount': debit_line.dr_amount + paid_amount
            })
        else:
            # If the line does not exist, create it
            self.env['idil.transaction_bookingline'].create({
                'transaction_booking_id': transaction.id,
                'description': 'Cash Payment for Hall Booking {}'.format(booking.name),
                'account_number': self.payment_method_id.account_number.id,
                'transaction_type': 'dr',
                'dr_amount': paid_amount,
                'cr_amount': 0,
                'transaction_date': fields.Date.today(),
            })

        # The income should stay the same, so we don't update the income line.
        # Check if an income line exists, if not, create it.

        income_line = self.env['idil.transaction_bookingline'].search([
            ('transaction_booking_id', '=', transaction.id),
            ('account_number', '=', booking.hall_id.income_account_id.id),
            ('transaction_type', '=', 'cr')
        ], limit=1)

        if not income_line:
            # If the income line does not exist, create it with the full income amount
            self.env['idil.transaction_bookingline'].create({
                'transaction_booking_id': transaction.id,
                'description': 'Income for Hall Booking {}'.format(booking.name),
                'account_number': booking.hall_id.income_account_id.id,
                'transaction_type': 'cr',
                'cr_amount': booking.total_price,
                'dr_amount': 0,
                'transaction_date': fields.Date.today(),
            })

        # Update or create the A/R (receivable) line for the remaining balance
        receivable_amount = max(0, booking.remaining_amount)

        receivable_line = self.env['idil.transaction_bookingline'].search([
            ('transaction_booking_id', '=', transaction.id),
            ('account_number', '=', booking.hall_id.Receivable_account_id.id),
            ('transaction_type', '=', 'dr')
        ], limit=1)

        if receivable_line:
            # If the A/R line exists, reduce the receivable amount
            receivable_line.write({
                'dr_amount': receivable_line.dr_amount - paid_amount
            })
        else:
            # If the A/R line does not exist, create it
            self.env['idil.transaction_bookingline'].create({
                'transaction_booking_id': transaction.id,
                'description': 'Receivable for Hall Booking {}'.format(booking.name),
                'account_number': booking.hall_id.Receivable_account_id.id,
                'transaction_type': 'dr',
                'cr_amount': 0,
                'dr_amount': receivable_amount,
                'transaction_date': fields.Date.today(),
            })

    def write(self, vals):
        """Override write method to adjust amount_paid, remaining_amount, and transactions when payment is updated."""
        for payment in self:
            old_amount = payment.amount  # Store the old amount before the update
            booking = payment.booking_id
            transaction = self.env['idil.transaction_booking'].search([('reffno', '=', booking.name)], limit=1)

            if not transaction:
                raise UserError('Transaction not found for this booking.')

            # Perform the write (update the payment record)
            res = super(HallBookingPayment, self).write(vals)

            # Get the new amount after the update
            new_amount = vals.get('amount', payment.amount)
            difference = new_amount - old_amount

            # Adjust the booking's amount paid and remaining amount
            booking.amount_paid += difference
            booking.remaining_amount = booking.total_price - booking.amount_paid

            # Set the status and hall availability based on the amount and remaining amount
            if booking.remaining_amount > 0:
                booking.status = 'booked'
                booking.hall_id.availability = 'booked'
            elif booking.amount == 0:
                booking.status = 'draft'
            elif booking.total_price == booking.amount:
                booking.status = 'confirmed'
                booking.hall_id.availability = 'booked'

            # Adjust transaction lines accordingly
            self._adjust_booking_lines(transaction, difference)

            return res

    def _adjust_booking_lines(self, transaction, difference):
        """Adjust booking lines based on the payment difference."""
        booking = self.booking_id

        # Adjust Cash (Debit) Line
        cash_line = self.env['idil.transaction_bookingline'].search([
            ('transaction_booking_id', '=', transaction.id),
            ('account_number', '=', self.payment_method_id.account_number.id),
            ('transaction_type', '=', 'dr')
        ], limit=1)

        if cash_line:
            # If the cash line exists, update the cash amount
            cash_line.write({
                'dr_amount': cash_line.dr_amount + difference
            })
        else:
            # If the cash line doesn't exist (edge case), create it
            self.env['idil.transaction_bookingline'].create({
                'transaction_booking_id': transaction.id,
                'description': 'Adjusted Cash Payment for Hall Booking {}'.format(booking.name),
                'account_number': self.payment_method_id.account_number.id,
                'transaction_type': 'dr',
                'dr_amount': difference,
                'cr_amount': 0,
                'transaction_date': fields.Date.today(),
            })

        # Adjust Receivables (Debit) Line
        receivable_line = self.env['idil.transaction_bookingline'].search([
            ('transaction_booking_id', '=', transaction.id),
            ('account_number', '=', booking.hall_id.Receivable_account_id.id),
            ('transaction_type', '=', 'dr')
        ], limit=1)

        if receivable_line:
            # Update receivables: decrease or increase based on payment adjustment
            receivable_line.write({
                'dr_amount': receivable_line.dr_amount - difference
            })
        else:
            # If no receivable line exists, create one for the remaining amount
            receivable_amount = max(0, booking.remaining_amount)
            if receivable_amount > 0:
                self.env['idil.transaction_bookingline'].create({
                    'transaction_booking_id': transaction.id,
                    'description': 'Adjusted Receivable for Hall Booking {}'.format(booking.name),
                    'account_number': booking.hall_id.Receivable_account_id.id,
                    'transaction_type': 'dr',
                    'cr_amount': 0,
                    'dr_amount': receivable_amount,
                    'transaction_date': fields.Date.today(),
                })

        # The income line remains unchanged as it reflects the total booking price.

    def unlink(self):
        """Override unlink method to adjust the amount paid and remaining amount when a payment is deleted."""
        for payment in self:
            booking = payment.booking_id
            transaction = self.env['idil.transaction_booking'].search([('reffno', '=', booking.name)], limit=1)

            if not transaction:
                raise UserError('Transaction not found for this booking.')

            old_amount = payment.amount  # Store the payment amount to be deleted

            # Adjust the booking's amount paid and remaining amount
            booking.amount_paid -= old_amount
            booking.remaining_amount = booking.total_price - booking.amount_paid

            # Set the status and hall availability based on the amount and remaining amount
            if booking.remaining_amount > 0:
                booking.status = 'booked'
                booking.hall_id.availability = 'booked'
            elif booking.amount == 0:
                booking.status = 'draft'
            elif booking.total_price == booking.amount:
                booking.status = 'confirmed'
                booking.hall_id.availability = 'booked'

            # Adjust the transaction lines accordingly
            self._adjust_booking_lines_on_unlink(transaction, old_amount)

        # Call the original unlink method to delete the record
        return super(HallBookingPayment, self).unlink()

    def _adjust_booking_lines_on_unlink(self, transaction, deleted_amount):
        """Adjust booking lines based on the deleted payment amount."""
        booking = self.booking_id

        # Adjust Cash (Debit) Line
        cash_line = self.env['idil.transaction_bookingline'].search([
            ('transaction_booking_id', '=', transaction.id),
            ('account_number', '=', self.payment_method_id.account_number.id),
            ('transaction_type', '=', 'dr')
        ], limit=1)

        if cash_line:
            # Reduce the cash amount by the deleted amount
            if cash_line.dr_amount >= deleted_amount:
                cash_line.write({
                    'dr_amount': cash_line.dr_amount - deleted_amount
                })
            else:
                raise UserError("Cash debit amount cannot go negative.")

        # Adjust Receivables (Debit) Line
        receivable_line = self.env['idil.transaction_bookingline'].search([
            ('transaction_booking_id', '=', transaction.id),
            ('account_number', '=', booking.hall_id.Receivable_account_id.id),
            ('transaction_type', '=', 'dr')
        ], limit=1)

        if receivable_line:
            # Increase receivables by the deleted amount
            receivable_line.write({
                'dr_amount': receivable_line.dr_amount + deleted_amount
            })
        else:
            # If no receivable line exists, create one for the remaining amount
            receivable_amount = booking.remaining_amount
            if receivable_amount > 0:
                self.env['idil.transaction_bookingline'].create({
                    'transaction_booking_id': transaction.id,
                    'description': 'Receivable for Hall Booking {}'.format(booking.name),
                    'account_number': booking.hall_id.Receivable_account_id.id,
                    'transaction_type': 'dr',
                    'cr_amount': 0,
                    'dr_amount': receivable_amount,
                    'transaction_date': fields.Date.today(),
                })

        # The income line remains unchanged since it reflects the total booking price.


class HallBookingPaymentWizard(models.TransientModel):
    _name = 'idil.hall.booking.payment.wizard'
    _description = 'Add Payment to Hall Booking'

    booking_id = fields.Many2one('idil.hall.booking', string='Hall Booking', required=True)
    payment_method_id = fields.Many2one('idil.payment.method', string='Payment Method', required=True)
    payment_date = fields.Date(string='Payment Date', default=fields.Date.today, required=True)
    payment_amount = fields.Float(string='Payment Amount', required=True)

    @api.model
    def default_get(self, fields):
        """Set the default booking_id in the wizard."""
        res = super(HallBookingPaymentWizard, self).default_get(fields)
        booking_id = self.env.context.get('active_id')
        res['booking_id'] = booking_id
        return res

    def action_add_payment(self):
        """Action to add a new payment to the hall booking."""
        if not self.booking_id:
            raise UserError('Booking not found.')

        # Create a new payment record
        payment = self.env['idil.hall.booking.payment'].create({
            'booking_id': self.booking_id.id,
            'payment_method_id': self.payment_method_id.id,
            'payment_date': self.payment_date,
            'amount': self.payment_amount,
            'payment_reference': 'Additional Payment for Booking {}'.format(self.booking_id.name),
        })
