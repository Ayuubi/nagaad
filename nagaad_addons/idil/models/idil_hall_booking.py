import base64
import io
import uuid
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from reportlab.platypus import Image
from reportlab.lib.pagesizes import landscape
from reportlab.platypus import SimpleDocTemplate
import logging

_logger = logging.getLogger(__name__)


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
    price_per_guest = fields.Float(string='Price per Guest', default=0.0)
    total_price = fields.Float(string='Total Price', compute='_compute_total_price', store=True)
    # Total amount paid will now be computed from the sum of payments
    amount = fields.Float(string='Advance Amount / Down Payment', store=True, default='')
    amount_paid = fields.Float(string='Amount Paid', default=0.0, compute='_compute_amount_paid', store=True)
    remaining_amount = fields.Float(string='Remaining Amount', default=0.0, store=True,
                                    compute='_compute_remaining_amount')
    # Adding payment method field
    payment_method_id = fields.Many2one('idil.payment.method', string='Payment Method', required=True)
    # Account Number Field (related to the selected Payment Method)
    account_number = fields.Char(string='Account Number', compute='_compute_account_number', store=True)
    payment_ids = fields.One2many('idil.hall.booking.payment', 'booking_id', string='Payments')
    status = fields.Selection([
        ('draft', 'Draft'),
        ('booked', 'Booked'),
        ('confirmed', 'Confirmed'),
        ('due', 'Due'),
        ('closed', 'Closed'),
        ('canceled', 'Canceled')
    ], string='Status', default='draft')
    hall_event_id = fields.Many2one('idil.hall_event_type', string='Choose Event Type')

    @api.model
    def read(self, fields=None, load='_classic_read'):
        """Override the read method to dynamically update the status field."""
        records = super(HallBooking, self).read(fields, load)
        current_time = datetime.now()  # Use Python's datetime module for current time

        # Collect IDs of records to update
        ids_to_update = []
        for record in records:
            if 'status' in record and 'end_time' in record:
                if record['status'] not in ['closed', 'canceled'] and record.get('end_time') and record[
                    'end_time'] < current_time:
                    ids_to_update.append(record['id'])

        # Perform a write operation for all expired bookings
        if ids_to_update:
            for record in records:
                if record.get('remaining_amount', 0) == 0:  # Access remaining_amount correctly
                    self.browse(ids_to_update).write({'status': 'closed'})
                else:
                    self.browse(ids_to_update).write({'status': 'due'})

        return records

    # Method to compute remaining amount
    @api.depends('total_price', 'amount')
    def _compute_remaining_amount(self):
        for record in self:
            if record.amount == 0:
                record.remaining_amount = record.total_price  # If amount is zero, remaining is total price
            else:
                record.remaining_amount = record.total_price - record.amount  # Else, calculate as usual

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

        # Check for overlapping bookings
        start_time = vals.get('start_time')
        end_time = vals.get('end_time')

        overlapping_bookings = self.env['idil.hall.booking'].search([
            ('hall_id', '=', vals.get('hall_id')),
            ('status', 'in', ['booked', 'confirmed']),
            ('start_time', '<', end_time),
            ('end_time', '>', start_time)
        ])

        if overlapping_bookings:
            raise ValidationError(
                "The selected hall is already booked during the specified time. "
                "Please choose a different time or hall."
            )

        # Check if the number of guests is valid
        if 'no_of_guest' not in vals or vals.get('no_of_guest') <= 0:
            raise UserError("Please insert a valid number of guests.")

        if vals.get('name', 'New') == 'New':
            unique_id = uuid.uuid4().hex[:6].upper()  # Short unique ID
            vals['name'] = 'HB-' + datetime.now().strftime('%d%m%Y') + '-' + unique_id

        # Create the booking record
        booking = super(HallBooking, self).create(vals)

        if 0 < booking.remaining_amount < booking.total_price:
            booking.status = 'booked'
        elif booking.remaining_amount == booking.total_price:
            booking.status = 'draft'
        elif booking.remaining_amount == 0 and booking.total_price == booking.amount_paid:
            booking.status = 'confirmed'

        # Create a payment entry if there is an amount to pay
        if booking.amount > 0:
            if booking.amount <= booking.total_price:
                self.env['idil.hall.booking.payment'].create({
                    'booking_id': booking.id,
                    'payment_date': fields.Date.today(),
                    'amount': booking.amount,
                    'payment_method_id': booking.payment_method_id.id,
                    'payment_reference': 'Initial Payment for Booking {}'.format(booking.name),
                })
            else:
                raise ValidationError(
                    f"The amount exceeds the total price. Please pay the total price amount: {booking.total_price}.")

        # Create the transaction after booking
        if booking.amount == 0:
            booking._create_transaction()

        return booking

    def _create_transaction(self):
        """Create a transaction based on the total price, amount paid, and remaining amount."""
        total_price = self.total_price
        amount_paid = self.amount
        remaining_amount = self.total_price - self.amount
        # Fetch the trx source record for "Salary Advance Expense"
        hall_booking_trx_source = self.env['idil.transaction.source'].search([
            ('name', '=', 'hall booking')  # Assuming the type is COGS, adjust based on your setup
        ], limit=1)

        # Create the main transaction record
        transaction = self.env['idil.transaction_booking'].create({
            'transaction_number': self.env['ir.sequence'].next_by_code('idil.transaction_booking'),
            'hall_booking_id': self.id,
            'trx_source_id': hall_booking_trx_source.id,
            'reffno': self.name,
            'customer_id': self.customer_id.id,
            'trx_date': fields.Date.today(),
            'amount': total_price,
            'payment_method': 'cash',  # Assuming cash payment
        })

        # Create the credit line for the income (total price)
        self.env['idil.transaction_bookingline'].create({
            'transaction_booking_id': transaction.id,
            'hall_booking_id': self.id,
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
                'hall_booking_id': self.id,
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
                'hall_booking_id': self.id,
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

    @api.depends('no_of_guest', 'hall_id', 'price_per_guest')
    def _compute_total_price(self):
        for booking in self:
            if booking.price_per_guest == 0:
                if booking.no_of_guest and booking.hall_id:
                    booking.total_price = booking.no_of_guest * booking.hall_id.price_per_hour
            elif booking.price_per_guest > 0:
                booking.total_price = booking.no_of_guest * booking.price_per_guest

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
        if 'amount' in vals:
            for record in self:
                if record.amount != vals['amount']:
                    raise ValidationError(
                        "You cannot modify the 'Advance Amount / Down Payment' "
                        "field after the booking has been created.")

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

                # Set the status and hall availability based on the amount, remaining amount, and current date

                if 0 < booking.remaining_amount < booking.total_price:
                    booking.status = 'booked'
                elif booking.remaining_amount == booking.total_price:
                    booking.status = 'draft'
                elif booking.remaining_amount == 0:
                    booking.status = 'confirmed'

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
                    'hall_booking_id': self.id,
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

    def generate_confirmation_slip_pdf(self):
        """Generate the payment slip for the selected employee."""
        for record in self:
            if not record.name:
                raise ValidationError("Booking must be selected to generate the payment slip.")
            return self.generate_salary_report_pdf(booking_id=record.id)

    def generate_salary_report_pdf(self, booking_id=None, export_type="pdf"):
        """Generate and download the latest salary payment report."""
        _logger.info("Starting salary report generation...")
        where_clauses = []
        params = []

        if booking_id:
            where_clauses.append("hb.id = %s")
            params.append(booking_id)

        where_clause = " AND ".join(
            where_clauses) if where_clauses else "1=1"  # Default condition to avoid syntax errors

        query = f"""
                    SELECT  
                        cr.name AS customer_name,
                        cr.phone AS customer_phone,
                        hb.name AS booking_name,
                        hb.booking_date,
                        hb.start_time,
                        hb.end_time,
                        hb.no_of_guest,
                        hb.status,
                        hb.amount_paid,
                        hb.remaining_amount,
                        hb.total_price,
                        CASE 
                            WHEN hb.price_per_guest = 0 THEN h.price_per_hour
                            ELSE hb.price_per_guest
                        END AS effective_price,
                        h.name as hall_name,
                        hv.name as event_type
                    FROM 
                        idil_hall_booking hb
                    INNER JOIN 
                        idil_customer_registration cr
                    ON 
                        hb.customer_id = cr.id
                    INNER JOIN 
                        idil_hall h
                    ON 
                        h.id = hb.hall_id
                    inner join idil_hall_event_type hv
                    on hv.id=hb.hall_event_id
                    WHERE
                         {where_clause};

            """
        _logger.info(f"Executing query: {query} with params: {params}")
        self.env.cr.execute(query, tuple(params))
        results = self.env.cr.fetchall()
        _logger.info(f"Query results: {results}")

        if not results:
            raise ValidationError("No payment records found for the selected employee.")

        record = results[0]
        report_data = {

            'client_name': record[0],
            'client_phone': record[1],
            'booking_name': record[2],
            'booking_date': record[3],
            'start_time': record[4],
            'end_time': record[5],
            'no_of_guest': record[6],
            'status': record[7],
            'amount_paid': record[8],
            'remaining_amount': record[9],
            'total_price': record[10],
            'effective_price': record[11],
            'hall_name': record[12],
            'event_type': record[13],
        }

        company = self.env.company  # Fetch active company details

        if export_type == "pdf":
            _logger.info("Generating PDF...")
            output = io.BytesIO()
            doc = SimpleDocTemplate(output, pagesize=landscape(letter))
            elements = []

            styles = getSampleStyleSheet()
            title_style = styles['Title']
            normal_style = styles['Normal']

            # Center alignment for the company information
            centered_style = styles['Title'].clone('CenteredStyle')
            centered_style.alignment = TA_CENTER
            centered_style.fontSize = 14
            centered_style.leading = 20

            normal_centered_style = styles['Normal'].clone('NormalCenteredStyle')
            normal_centered_style.alignment = TA_CENTER
            normal_centered_style.fontSize = 10
            normal_centered_style.leading = 12

            # Header with Company Name, Address, and Logo
            if company.logo:
                logo = Image(io.BytesIO(base64.b64decode(company.logo)), width=60, height=60)
                logo.hAlign = 'CENTER'  # Center-align the logo
                elements.append(logo)

            # Add company name and address
            elements.append(Paragraph(f"<b>{company.name}</b>", centered_style))
            elements.append(
                Paragraph(f"{company.street}, {company.city}, {company.country_id.name}", normal_centered_style))
            elements.append(Paragraph(f"Phone: {company.phone} | Email: {company.email}", normal_centered_style))
            elements.append(Spacer(1, 12))

            # Unified Table: Employee Details and Payment Section
            payment_table_data = [
                # Header for Payment Slip Voucher
                ["", "Hall Booking Confirmation SLIP VOUCHER", ""],  # Title row spanning multiple columns
                ["Client Details", "", "", ""],  # Sub-header for Employee Details

                # 'client_name': record[0],'client_phone': record[1],'booking_date': record[2].strftime('%Y-%m-%d'),
                # 'start_time': record[3],'end_time': record[4],'no_of_guest': record[5],'status': record[6],
                # 'amount_paid': record[7],'remaining_amount': record[8],'total_price': record[9],
                #
                # Employee Details Rows
                ["Client Name", report_data['client_name'], "Booking Date", report_data['booking_date']],
                ["Client Phone", report_data['client_phone'], "Reff No", report_data['booking_name']],
                ["Hall Name", report_data['hall_name'], "Booking Status", report_data['status']],

                # Header for Earnings and Deductions
                ["", "Payment Details", "", ""],

                # Payment Details Rows
                ["No of Guests", f"${report_data['no_of_guest']:,.2f}", "Due Amount",
                 f"${report_data['remaining_amount']:,.2f}"],
                ["Price per Guest", f"${report_data['effective_price']:,.2f}", "Event Type",
                 f"{report_data['event_type']}"],
                ["Gross Total", f"${report_data['no_of_guest'] * report_data['effective_price']:,.2f}",
                 "Booking Start Date",
                 f"${report_data['start_time']}"],
                # Net Pay Row
                ["Advance/Paid Amount",
                 f"${(report_data['amount_paid']):,.2f}",
                 "Booking End Date", f"${report_data['end_time']}"]
            ]

            # Define the table layout and styling
            payment_table_layout = Table(payment_table_data, colWidths=[150, 200, 150, 200])
            payment_table_layout.setStyle(TableStyle([
                # Title Row Styling
                ('SPAN', (1, 0), (2, 0)),  # Span the title row across multiple columns
                ('ALIGN', (1, 0), (2, 0), 'CENTER'),
                ('FONTNAME', (1, 0), (2, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (1, 0), (2, 0), 14),
                ('TEXTCOLOR', (1, 0), (2, 0), colors.HexColor("#B6862D")),
                ('BOTTOMPADDING', (1, 0), (2, 0), 12),

                # Employee Details Header Styling
                ('SPAN', (0, 1), (3, 1)),  # Span Employee Details header
                ('BACKGROUND', (0, 1), (3, 1), colors.HexColor("#B6862D")),
                ('TEXTCOLOR', (0, 1), (3, 1), colors.white),
                ('ALIGN', (0, 1), (3, 1), 'CENTER'),
                ('FONTNAME', (0, 1), (3, 1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 1), (3, 1), 12),
                ('BOTTOMPADDING', (0, 1), (3, 1), 8),

                # Employee Details Rows Styling
                ('BACKGROUND', (0, 2), (-1, 4), colors.HexColor("#F0F0F0")),
                ('ALIGN', (0, 2), (-1, 4), 'LEFT'),
                ('FONTNAME', (0, 2), (-1, 4), 'Helvetica'),
                ('FONTSIZE', (0, 2), (-1, 4), 10),
                ('LEFTPADDING', (0, 2), (-1, 4), 10),

                # Highlight "Due Amount" in red
                ('TEXTCOLOR', (3, 6), (3, 6), colors.red),  # Specify the exact cell for "Due Amount"

                # Earnings and Deductions Header Styling
                ('BACKGROUND', (0, 5), (-1, 5), colors.HexColor("#B6862D")),
                ('TEXTCOLOR', (0, 5), (-1, 5), colors.white),
                ('ALIGN', (0, 5), (-1, 5), 'CENTER'),
                ('FONTNAME', (0, 5), (-1, 5), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 5), (-1, 5), 12),
                ('BOTTOMPADDING', (0, 5), (-1, 5), 8),

                # Payment Details Rows Styling
                ('ALIGN', (1, 6), (1, -1), 'RIGHT'),
                ('ALIGN', (3, 6), (3, -1), 'RIGHT'),
                ('FONTNAME', (0, 6), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 6), (-1, -1), 10),
                ('GRID', (0, 2), (-1, -1), 0.5, colors.grey),
            ]))
            elements.extend([payment_table_layout, Spacer(1, 12)])  # Add table to the document

            # Payment Signature Section
            hr_name = self.env.user.name  # Fetch the current HR (user) name
            client_name = report_data['client_name']  # Employee name from the report data

            signature_table = [
                [f"Prepared by (Admin): {hr_name}", "______________________", f"Paid by (Client): {client_name}",
                 "______________________"],
            ]
            signature_table_layout = Table(signature_table, colWidths=[200, 150, 200, 150])
            signature_table_layout.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ALIGN', (1, 1), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ]))
            elements.extend([signature_table_layout, Spacer(1, 24)])

            # Footer
            current_datetime = fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            footer = Paragraph(f"<b>Generated by:</b> {self.env.user.name} | <b>Date:</b> {current_datetime}",
                               normal_style)
            elements.append(footer)

            # Build PDF
            try:
                doc.build(elements)
            except Exception as e:
                _logger.error(f"Error building PDF: {e}")
                raise

            # Save PDF as attachment and provide download link
            output.seek(0)
            attachment = self.env['ir.attachment'].create({
                'name': 'Hall Booking Slip.pdf',
                'type': 'binary',
                'datas': base64.b64encode(output.read()),
                'mimetype': 'application/pdf',
            })
            output.close()
            _logger.info(f"PDF successfully generated: Attachment ID {attachment.id}")

            return {
                'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % attachment.id,
                'target': 'new',
            }

        return report_data


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

            # Set the status and hall availability based on the amount, remaining amount, and current date

            if 0 < booking.remaining_amount < booking.total_price:
                booking.status = 'booked'
            elif booking.remaining_amount == booking.total_price:
                booking.status = 'draft'
            elif booking.remaining_amount == 0:
                booking.status = 'confirmed'

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
            # Fetch the trx source record for "Salary Advance Expense"
            hall_booking_trx_source = self.env['idil.transaction.source'].search([
                ('name', '=', 'hall booking')  # Assuming the type is COGS, adjust based on your setup
            ], limit=1)

            transaction = self.env['idil.transaction_booking'].create({
                'transaction_number': self.env['ir.sequence'].next_by_code('idil.transaction_booking'),
                'reffno': booking.name,
                'trx_source_id': hall_booking_trx_source.id,
                'hall_booking_id': self.booking_id.id,
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
                'hall_booking_id': self.booking_id.id,
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
                'hall_booking_id': self.booking_id.id,
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
                'hall_booking_id': self.booking_id.id,
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

            # Set the status and hall availability based on the amount, remaining amount, and current date

            if 0 < booking.remaining_amount < booking.total_price:
                booking.status = 'booked'
            elif booking.remaining_amount == booking.total_price:
                booking.status = 'draft'
            elif booking.remaining_amount == 0:
                booking.status = 'confirmed'

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
                'hall_booking_id': self.booking_id.id,
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
                    'hall_booking_id': self.booking_id.id,
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

            # Set the status and hall availability based on the amount, remaining amount, and current date
            current_date = fields.Date.today()
            start_date = fields.Date.to_date(booking.start_time)

            if 0 < booking.remaining_amount < booking.total_price:
                booking.status = 'booked'
            elif booking.remaining_amount == booking.total_price:
                booking.status = 'draft'
            elif booking.remaining_amount == 0:
                booking.status = 'confirmed'

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
                    'hall_booking_id': self.booking_id.id,
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

        # Calculate the due amount
        due_amount = self.booking_id.total_price - sum(
            payment.amount for payment in self.booking_id.payment_ids
        )

        # Check if the payment amount exceeds the due amount
        if self.payment_amount > due_amount:
            raise UserError(
                f"The payment amount exceeds the due amount. "
                f"Due amount: {due_amount:.2f}, Payment amount: {self.payment_amount:.2f}."
            )
        # Create a new payment record
        payment = self.env['idil.hall.booking.payment'].create({
            'booking_id': self.booking_id.id,
            'payment_method_id': self.payment_method_id.id,
            'payment_date': self.payment_date,
            'amount': self.payment_amount,
            'payment_reference': 'Additional Payment for Booking {}'.format(self.booking_id.name),
        })


class IdilEmployeePosition(models.Model):
    _name = 'idil.hall_event_type'
    _description = 'Hall Event Type'
    _order = 'name'

    name = fields.Char(required=True)
