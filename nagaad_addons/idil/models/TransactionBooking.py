import base64
import io
from datetime import datetime, date
import xlsxwriter
from xlrd.xlsx import ET
from odoo import models, fields, api, exceptions, _
from odoo.exceptions import UserError, ValidationError
from datetime import date
import re
import logging

_logger = logging.getLogger(__name__)


class TransactionBooking(models.Model):
    _name = 'idil.transaction_booking'
    _description = 'Transaction Booking'

    # Primary Key Fields
    transaction_number = fields.Integer(string='Transaction Number')
    reffno = fields.Char(string='Reference Number')  # Consider renaming for clarity
    journal_entry_id = fields.Many2one('idil.journal.entry', string='Journal Entry')
    vendor_id = fields.Many2one('idil.vendor.registration', string='Vendor')
    vendor_phone = fields.Char(related='vendor_id.phone', string='Vendor Phone', readonly=True)
    vendor_email = fields.Char(related='vendor_id.email', string='Vendor Email', readonly=True)
    customer_id = fields.Many2one('idil.customer.registration', string='Customer')
    employee_id = fields.Many2one('idil.employee', string='Employee')
    sales_person_id = fields.Many2one('idil.sales.sales_personnel', string='Sales Person')
    # Add a field to link to the SaleOrder. This assumes you have a unique identifier (like an ID) for SaleOrder.
    sale_order_id = fields.Many2one('idil.sale.order', string='Linked Sale Order', ondelete='cascade')
    order_number = fields.Char(string='Order Number')
    Sales_order_number = fields.Char(string='Sales Order Number')
    payment_method = fields.Selection(
        [('cash', 'Cash'), ('ap', 'A/P'), ('bank_transfer', 'Bank Transfer'), ('other', 'Other'),
         ('opening_balance', 'opening_balance'),
         ('internal', 'Internal')],
        string='Payment Method'
    )
    pos_payment_method = fields.Many2one('pos.payment.method', string='POS Payment Method')
    payment_status = fields.Selection(
        [('pending', 'Pending'), ('paid', 'Paid'), ('partial_paid', 'Partial Paid')],
        string='Payment Status',
        help='Description or additional information about the payment status.'
    )
    trx_date = fields.Date(string='Transaction Date', default=lambda self: fields.Date.today())
    # amount = fields.Float(string='Amount')
    trx_source_id = fields.Many2one(
        'idil.transaction.source',
        string='Transaction Source',
        help="Select the transaction source."
    )
    # Secondary Key Fields
    employee_salary_advance_id = fields.Many2one(
        'idil.employee.salary.advance', string='Employee Salary Advance', ondelete='cascade'
    )
    # Secondary Key Fields
    employee_salary_id = fields.Many2one(
        'idil.employee.salary', string='Employee Salary', ondelete='cascade'
    )
    # Secondary Key Fields
    hall_booking_id = fields.Many2one(
        'idil.hall.booking', string='Hall Booking ID', ondelete='cascade'
    )
    amount = fields.Float(string='Amount', compute='_compute_amount', store=True)
    amount_paid = fields.Float(string='Amount Paid')
    remaining_amount = fields.Float(string='Remaining Amount', store=True)
    debit_total = fields.Float(string='Total Debit', compute='_compute_debit_credit_total', store=True)
    credit_total = fields.Float(string='Total Credit', compute='_compute_debit_credit_total', store=True)
    booking_lines = fields.One2many(
        'idil.transaction_bookingline', 'transaction_booking_id', string='Transaction Lines'
    )
    # Add a Many2one field to select a cash account
    cash_account_id = fields.Many2one(
        'idil.chart.account',
        string='Cash Account',
        domain=[('account_type', '=', 'cash')],
        help="Select the cash account for transactions."
    )
    vendor_transactions = fields.One2many(
        'idil.vendor_transaction', 'transaction_booking_id', string='Vendor Transactions', ondelete='cascade'
    )

    sales_payment_id = fields.Many2one(
        'account.payment',
        string='Sales Payment',
        ondelete='cascade',  # <-- when account.payment is deleted, delete this record too
        oldname='sale_payment_id',  # keep if you previously renamed the column
        index=True,
    )

    # Add a Many2one field to link to PurchaseOrder
    purchase_order_id = fields.Many2one('idil.purchase_order', string='Linked Purchase Order', ondelete='cascade')
    bulk_payment_id = fields.Many2one(
        'idil.vendor.bulk.payment',
        string='Related Bulk Payment',
        ondelete='cascade'
    )

    bank_reff = fields.Char(
        string='Bank Reference', required=True, tracking=True
    )
    sales_payment_id = fields.Many2one(
        "idil.sales.payment",
        string="Sales Payment",
        ondelete="cascade"
    )
    customer_opening_balance_id = fields.Many2one(
        "idil.customer.opening.balance.line",
        string="Opening Balance",
        ondelete="cascade",
    )

    @api.constrains('amount_paid')
    def _check_amount_paid(self):
        if self.env.context.get('skip_validations'):
            return
        for record in self:
            if record.amount_paid > record.amount:
                raise ValidationError(
                    "The paid amount cannot be greater than the balance.\nBalance: %s\nAmount Needed to Pay: %s" % (
                        record.amount, record.amount_paid))

    @api.onchange('amount_paid')
    def _onchange_amount_paid(self):
        if self.env.context.get('skip_validations'):
            return
        if self.amount_paid > self.amount:
            raise ValidationError(
                "The paid amount cannot be greater than the balance.\nBalance: %s\nAmount Needed to Pay: %s" % (
                    self.amount, self.amount_paid))

    def action_pay(self):
        for record in self:
            if not record.cash_account_id:
                raise ValidationError("Select Cash account")
            if record.amount_paid > record.amount:
                raise ValidationError("The payment amount cannot exceed the current balance.")

            # Create two transaction booking lines or update
            cr_account = record.sales_person_id.account_receivable_id.id
            dr_account = record.cash_account_id.id
            if cr_account and dr_account:
                # Find existing transaction booking lines

                existing_lines = self.env['idil.transaction_bookingline'].search([
                    ('transaction_booking_id', '=', record.id),
                    ('transaction_booking_id.payment_status', '!=', 'pending'),
                ])
                # Update existing lines or create them if they don't exist
                for line in existing_lines:
                    if line.description == "Receipt":
                        if line.transaction_type == 'cr':
                            line.cr_amount = record.amount_paid
                        elif line.transaction_type == 'dr':
                            line.dr_amount = record.amount_paid

                if not existing_lines:
                    # Create credit transaction booking line
                    self.env['idil.transaction_bookingline'].create({
                        'transaction_booking_id': record.id,
                        'description': 'Receipt',
                        'transaction_type': 'cr',
                        'cr_amount': record.amount_paid,
                        'dr_amount': 0,
                        'account_number': cr_account,
                    })

                    # Create debit transaction booking line
                    self.env['idil.transaction_bookingline'].create({
                        'transaction_booking_id': record.id,
                        'description': 'Receipt',
                        'transaction_type': 'dr',
                        'cr_amount': 0,
                        'dr_amount': record.amount_paid,
                        'account_number': dr_account,
                    })

                update_vals = {
                    'trx_source_id': 3,  # New trx_source_id value
                }

                # Update payment status based on remaining amount
                if record.remaining_amount == 0:
                    record.payment_status = 'paid'
                else:
                    record.payment_status = 'partial_paid'

                record.amount_paid = record.amount_paid
                record.remaining_amount = record.remaining_amount
                # Write the changes to the database
                record.write(update_vals)
            else:
                # Log an error or handle the case where accounts are not properly set
                _logger.error(f"Accounts not properly set for transaction booking {record.id}.")

    @api.depends('booking_lines.dr_amount', 'booking_lines.cr_amount')
    def _compute_debit_credit_total(self):
        for record in self:
            record.debit_total = sum(line.dr_amount for line in record.booking_lines)
            record.credit_total = sum(line.cr_amount for line in record.booking_lines)

    @api.model
    def create(self, vals):
        # vals['reffno'] = self._generate_booking_reference(vals)
        vals['transaction_number'] = self._get_next_transaction_number()

        transaction_record = super(TransactionBooking, self).create(vals)

        return transaction_record

    def _get_next_transaction_number(self):
        max_transaction_number = self.env['idil.transaction_booking'].search([], order='transaction_number desc',
                                                                             limit=1).transaction_number or 0
        return max_transaction_number + 1

    def action_add_default_lines(self):
        for record in self:
            # Add a debit line
            self.env['idil.transaction_bookingline'].create({
                'transaction_booking_id': record.id,
                'transaction_type': 'dr',
                'dr_amount': 0.0,  # Default amount; adjust as necessary
                'cr_amount': 0.0,  # Ensured to be zero for debit line
                'description': 'Default debit line',
            })
            # Add a credit line
            self.env['idil.transaction_bookingline'].create({
                'transaction_booking_id': record.id,
                'transaction_type': 'cr',
                'dr_amount': 0.0,  # Ensured to be zero for credit line
                'cr_amount': 0.0,  # Default amount; adjust as necessary
                'description': 'Default credit line',
            })

    def update_related_booking_lines(self):
        for line in self.booking_lines:
            if line.transaction_type == 'dr':
                line.dr_amount = self.amount  # Update dr_amount to total sale order amount for debit lines
                line.cr_amount = 0
            elif line.transaction_type == 'cr':
                line.cr_amount = self.amount  # Update cr_amount to total sale order amount for credit lines
                line.dr_amount = 0


class TransactionBookingline(models.Model):
    _name = 'idil.transaction_bookingline'
    _description = 'Transaction Booking Line'

    # Secondary Key Fields
    transaction_booking_id = fields.Many2one(
        'idil.transaction_booking', string='Transaction Booking', ondelete='cascade'
    )
    # Secondary Key Fields
    hall_booking_id = fields.Many2one(
        'idil.hall.booking', string='Hall Booking ID', ondelete='cascade'
    )
    # Secondary Key Fields
    employee_salary_advance_id = fields.Many2one(
        'idil.employee.salary.advance', string='Employee Salary Advance', ondelete='cascade'
    )
    # Secondary Key Fields
    employee_salary_id = fields.Many2one(
        'idil.employee.salary', string='Employee Salary', ondelete='cascade'
    )
    sales_payment_id = fields.Many2one(
        'account.payment',
        string='Sales Payment',
        ondelete='cascade',  # <-- when account.payment is deleted, delete this record too
        oldname='sale_payment_id',  # keep if you previously renamed the column
        index=True,
    )

    # order_line = fields.Char(string='Order Line')
    order_line = fields.Integer(string='Order Line')

    description = fields.Char(string='Description')
    item_id = fields.Many2one('idil.item', string='Item')
    product_id = fields.Many2one('my_product.product', string='Product')

    account_number = fields.Many2one(
        'idil.chart.account', string='Account Number', required=True
    )
    account_display = fields.Char(string='Account Display', compute='_compute_account_display', store=True)

    transaction_type = fields.Selection(
        [('dr', 'Debit'), ('cr', 'Credit')], string='Transaction Type', required=True
    )
    dr_amount = fields.Float(string='Debit Amount')
    cr_amount = fields.Float(string='Credit Amount')
    transaction_date = fields.Date(string='Transaction Date', default=lambda self: fields.Date.today())
    vendor_payment_id = fields.Many2one('idil.vendor_payment', string='Vendor Payment', ondelete='cascade')
    currency_id = fields.Many2one('res.currency', string='Currency', related='account_number.currency_id', store=True,
                                  readonly=True)

    commission_payment_id = fields.Many2one('idil.commission.payment', string='Commission Payment', ondelete='cascade')
    hall_booking_payment_id = fields.Many2one(
        'idil.hall.booking.payment',
        string='Hall Booking Payment',
        ondelete='cascade'
    )
    bank_reff = fields.Char(
        string='Bank Reference', required=True, tracking=True
    )
    sales_payment_id = fields.Many2one(
        "idil.sales.payment",
        string="Sales Payment",
        ondelete="cascade"
    )
    customer_opening_balance_id = fields.Many2one(
        "idil.customer.opening.balance.line",
        string="Opening Balance",
        ondelete="cascade",
    )

    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)

    @api.depends('account_number')
    def _compute_account_display(self):
        for line in self:
            if line.account_number:
                line.account_display = (f"{line.account_number.code} - {line.account_number.name} "
                                        f"- {line.account_number.currency_id.name}")
            else:
                line.account_display = ""

    @api.model
    def compute_trial_balance(self, report_currency_id):
        self.env.cr.execute("""
                SELECT
                    tb.account_number,
                    ca.currency_id,
                    SUM(tb.dr_amount) AS dr_total,
                    SUM(tb.cr_amount) AS cr_total
                FROM
                    idil_transaction_bookingline tb
                JOIN idil_chart_account ca ON tb.account_number = ca.id
                JOIN idil_chart_account_subheader cb ON ca.subheader_id = cb.id
                JOIN idil_chart_account_header ch ON cb.header_id = ch.id
                WHERE
                    ca.currency_id = %s  -- Filter by selected report currency
                GROUP BY
                    tb.account_number, ca.currency_id, ch.code
                HAVING
                    SUM(tb.dr_amount) - SUM(tb.cr_amount) <> 0
                ORDER BY
                    ch.code
            """, (report_currency_id.id,))
        result = self.env.cr.dictfetchall()

        total_dr_balance = 0
        total_cr_balance = 0

        # Clear previous trial balance records
        self.env['idil.trial.balance'].search([]).unlink()

        for line in result:
            account = self.env['idil.chart.account'].browse(line['account_number'])
            # Compute the net balance for the account
            net_balance = line['dr_total'] - line['cr_total']

            if net_balance > 0:
                # Positive net balance indicates a debit balance
                dr_balance = net_balance
                cr_balance = 0
                total_dr_balance += dr_balance
            else:
                # Negative net balance indicates a credit balance
                dr_balance = 0
                cr_balance = abs(net_balance)
                total_cr_balance += cr_balance

            # Create the trial balance record
            self.env['idil.trial.balance'].create({
                'account_number': account.id,
                'header_name': account.header_name,
                'currency_id': line['currency_id'],
                'dr_balance': dr_balance,
                'cr_balance': cr_balance,
            })

        # Add a grand total row if a report currency is specified
        if report_currency_id:
            self.env['idil.trial.balance'].create({
                'account_number': None,
                'currency_id': report_currency_id.id,
                'dr_balance': total_dr_balance,
                'cr_balance': total_cr_balance,
                'label': 'Grand Total'
            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Trial Balance',
            'view_mode': 'tree',
            'res_model': 'idil.trial.balance',
            'target': 'new',
        }

    # @api.model
    # def compute_company_trial_balance(self, report_currency_id, company_id, as_of_date):
    #     self.env.cr.execute("""
    #             SELECT
    #                 tb.account_number,
    #                 ca.currency_id,
    #                 tb.company_id,
    #                 tb.transaction_date,  -- Include transaction date in the query
    #                 SUM(tb.dr_amount) AS dr_total,
    #                 SUM(tb.cr_amount) AS cr_total
    #             FROM
    #                 idil_transaction_bookingline tb
    #             JOIN idil_chart_account ca ON tb.account_number = ca.id
    #             JOIN idil_chart_account_subheader cb ON ca.subheader_id = cb.id
    #             JOIN idil_chart_account_header ch ON cb.header_id = ch.id
    #             WHERE
    #                 tb.company_id = %s  -- Filter by company
    #                 AND tb.transaction_date <= %s  -- Filter by as_of_date
    #                 AND ca.name != 'Exchange Clearing Account'  -- Exclude Exchange Clearing Account
    #
    #             GROUP BY
    #                 tb.account_number, ca.currency_id, tb.company_id, tb.transaction_date, ch.code
    #             HAVING
    #                 SUM(tb.dr_amount) - SUM(tb.cr_amount) <> 0
    #             ORDER BY
    #                 ch.code
    #         """, (company_id.id, as_of_date))
    #     result = self.env.cr.dictfetchall()
    #
    #     total_dr_balance = 0
    #     total_cr_balance = 0
    #
    #     # Clear previous trial balance records
    #     self.env['idil.company.trial.balance'].search([]).unlink()
    #
    #     usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
    #
    #     for line in result:
    #         account = self.env['idil.chart.account'].browse(line['account_number'])
    #         # Compute the net balance for the account
    #         dr_total = line['dr_total']
    #         cr_total = line['cr_total']
    #         transaction_date = line['transaction_date']
    #
    #         if line['currency_id'] != usd_currency.id:
    #             # Convert amounts to USD using the transaction date
    #             currency = self.env['res.currency'].browse(line['currency_id'])
    #             dr_total = currency._convert(dr_total, usd_currency, self.env.user.company_id, transaction_date)
    #             cr_total = currency._convert(cr_total, usd_currency, self.env.user.company_id, transaction_date)
    #
    #         net_balance = dr_total - cr_total
    #
    #         if net_balance > 0:
    #             # Positive net balance indicates a debit balance
    #             dr_balance = net_balance
    #             cr_balance = 0
    #             total_dr_balance += dr_balance
    #         else:
    #             # Negative net balance indicates a credit balance
    #             dr_balance = 0
    #             cr_balance = abs(net_balance)
    #             total_cr_balance += cr_balance
    #
    #         # Create the trial balance record
    #         self.env['idil.company.trial.balance'].create({
    #             'account_number': account.id,
    #             'header_name': account.header_name,
    #             'currency_id': usd_currency.id,
    #             'dr_balance': dr_balance,
    #             'cr_balance': cr_balance,
    #         })
    #
    #     # Add a grand total row
    #     self.env['idil.company.trial.balance'].create({
    #         'account_number': None,
    #         'currency_id': usd_currency.id,
    #         'dr_balance': total_dr_balance,
    #         'cr_balance': total_cr_balance,
    #         'label': 'Grand Total'
    #     })
    #
    #     return {
    #         'type': 'ir.actions.act_window',
    #         'name': 'Company Trial Balance',
    #         'view_mode': 'tree',
    #         'res_model': 'idil.company.trial.balance',
    #         'target': 'new',
    #     }
    @api.model
    def compute_company_trial_balance(self, report_currency_id, company_id, as_of_date):
        self.env.cr.execute("""
            SELECT
                tb.account_number,
                ca.currency_id,
                SUM(tb.dr_amount) AS dr_total,
                SUM(tb.cr_amount) AS cr_total
            FROM
                idil_transaction_bookingline tb
            JOIN idil_chart_account ca ON tb.account_number = ca.id
            WHERE
                tb.company_id = %s  -- Filter by company
                AND tb.transaction_date <= %s  -- Filter by as_of_date
                AND ca.name != 'Exchange Clearing Account'  -- Exclude Exchange Clearing Account
            GROUP BY
                tb.account_number,ca.code, ca.currency_id
            HAVING
                SUM(tb.dr_amount) - SUM(tb.cr_amount) <> 0  -- Exclude accounts with zero net balance
            ORDER BY
                ca.code
        """, (company_id.id, as_of_date))

        result = self.env.cr.dictfetchall()

        total_dr_balance = 0
        total_cr_balance = 0

        # Clear previous trial balance records
        self.env['idil.company.trial.balance'].search([]).unlink()

        usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)

        for line in result:
            account = self.env['idil.chart.account'].browse(line['account_number'])
            dr_total = line['dr_total']
            cr_total = line['cr_total']

            # Convert amounts to USD using the as_of_date
            if line['currency_id'] != usd_currency.id:
                currency = self.env['res.currency'].browse(line['currency_id'])
                dr_total = currency._convert(dr_total, usd_currency, self.env.user.company_id, as_of_date)
                cr_total = currency._convert(cr_total, usd_currency, self.env.user.company_id, as_of_date)

            # Calculate the net balance
            net_balance = dr_total - cr_total

            if net_balance > 0:
                # Positive net balance indicates a debit balance
                dr_balance = net_balance
                cr_balance = 0
                total_dr_balance += dr_balance
            else:
                # Negative net balance indicates a credit balance
                dr_balance = 0
                cr_balance = abs(net_balance)
                total_cr_balance += cr_balance

            # Create the trial balance record
            self.env['idil.company.trial.balance'].create({
                'account_number': account.id,
                'header_name': account.header_name,
                'currency_id': usd_currency.id,
                'dr_balance': dr_balance,
                'cr_balance': cr_balance,
            })

        # Add a grand total row
        self.env['idil.company.trial.balance'].create({
            'account_number': None,
            'currency_id': usd_currency.id,
            'dr_balance': total_dr_balance,
            'cr_balance': total_cr_balance,
            'label': 'Grand Total'
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Company Trial Balance',
            'view_mode': 'tree',
            'res_model': 'idil.company.trial.balance',
            'target': 'new',
        }

    def compute_income_statement(self, company_id, from_date, to_date):
        # Retrieve USD currency
        usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)

        # Clear previous report data
        self.env['idil.income.statement.report'].search([]).unlink()

        # Define account types for income (starting with '4') and expenses (starting with '5' or '6')
        profit_accounts = self.env['idil.chart.account'].search([('code', '=like', '4%')])
        expense_accounts = self.env['idil.chart.account'].search(
            ['|', ('code', '=like', '5%'), ('code', '=like', '6%')])

        total_income = 0
        total_expenses = 0

        # Compute total income (accounts starting with '4')
        for account in profit_accounts:
            self.env.cr.execute("""
                SELECT
                    SUM(tb.cr_amount) - SUM(tb.dr_amount) AS total
                FROM
                    idil_transaction_bookingline tb
                WHERE
                    tb.company_id = %s AND tb.account_number = %s
                    AND tb.transaction_date BETWEEN %s AND %s
                GROUP BY
                    tb.account_number
                HAVING
                    SUM(tb.cr_amount) - SUM(tb.dr_amount) != 0
                """, (company_id.id, account.id, from_date, to_date))

            result = self.env.cr.fetchone()
            amount = result[0] if result else 0

            # Convert amount to USD if necessary
            if account.currency_id.id != usd_currency.id:
                amount = account.currency_id._convert(amount, usd_currency, self.env.user.company_id,
                                                      fields.Date.today())

            # Only create a report entry if the amount is non-zero
            if amount != 0:
                # Accumulate total income
                total_income += amount

                # Create report entry for each profit account
                self.env['idil.income.statement.report'].create({
                    'account_number': account.id,
                    'amount': amount,
                    'currency_id': usd_currency.id,
                })

        # Add subtotal for income only if there are any
        if total_income != 0:
            self.env['idil.income.statement.report'].create({
                'account_number': None,
                'account_type': 'Income Subtotal',
                'amount': total_income,
                'currency_id': usd_currency.id,
            })

        # Compute total expenses (accounts starting with '5' and '6')
        for account in expense_accounts:
            self.env.cr.execute("""
                SELECT
                    SUM(tb.dr_amount) - SUM(tb.cr_amount) AS total
                FROM
                    idil_transaction_bookingline tb
                WHERE
                    tb.company_id = %s AND tb.account_number = %s
                    AND tb.transaction_date BETWEEN %s AND %s
                GROUP BY
                    tb.account_number
                HAVING
                    SUM(tb.dr_amount) - SUM(tb.cr_amount) != 0
                """, (company_id.id, account.id, from_date, to_date))

            result = self.env.cr.fetchone()
            amount = result[0] if result else 0

            # Convert amount to USD if necessary
            if account.currency_id.id != usd_currency.id:
                amount = account.currency_id._convert(amount, usd_currency, self.env.user.company_id,
                                                      fields.Date.today())

            # Only create a report entry if the amount is non-zero
            if amount != 0:
                # Accumulate total expenses
                total_expenses += amount

                # Create report entry for each expense account
                self.env['idil.income.statement.report'].create({
                    'account_number': account.id,
                    'amount': amount,
                    'currency_id': usd_currency.id,
                })

        # Add subtotal for expenses only if there are any
        if total_expenses != 0:
            self.env['idil.income.statement.report'].create({
                'account_number': None,
                'account_type': 'Expense Subtotal',
                'amount': total_expenses,
                'currency_id': usd_currency.id,
            })

        # Calculate and add gross profit (total income - total expenses)
        gross_profit = total_income - total_expenses
        self.env['idil.income.statement.report'].create({
            'account_number': None,
            'account_type': 'Gross Profit',
            'amount': gross_profit,
            'currency_id': usd_currency.id,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Income Statement',
            'view_mode': 'tree',
            'res_model': 'idil.income.statement.report',
            'target': 'new',
        }


class IncomeStatementReport(models.TransientModel):
    _name = 'idil.income.statement.report'
    _description = 'Income Statement Report'

    account_number = fields.Many2one('idil.chart.account', string='Account Number')
    account_type = fields.Char(string='Description')
    amount = fields.Float(string='Amount')
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    label = fields.Char(string='Label')


class IncomeStatementWizard(models.TransientModel):
    _name = 'idil.income.statement.wizard'
    _description = 'Income Statement Wizard'

    company_id = fields.Many2one('res.company', string='Company', required=True)
    from_date = fields.Date(string='From Date', required=True)
    to_date = fields.Date(string='To Date', required=True)

    def action_compute_income_statement(self):
        self.ensure_one()
        # Pass the company, from_date, and to_date to the compute method
        action = self.env['idil.transaction_bookingline'].compute_income_statement(
            self.company_id, self.from_date, self.to_date
        )
        return action


class CompanyTrialBalance(models.Model):
    _name = 'idil.company.trial.balance'
    _description = 'Company Trial Balance'

    account_number = fields.Many2one('idil.chart.account', string='Account Number')
    header_name = fields.Char(string='Account Type')
    dr_balance = fields.Float(string='Dr', digits=(16, 3))
    cr_balance = fields.Float(string='Cr', digits=(16, 3))
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    label = fields.Char(string='Label', compute='_compute_label')
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    @api.depends('account_number', 'dr_balance', 'cr_balance')
    def _compute_label(self):
        for record in self:
            if not record.account_number:
                record.label = 'Grand Total'
            else:
                record.label = ''


class CompanyTrialBalanceWizard(models.TransientModel):
    _name = 'idil.company.trial.balance.wizard'
    _description = 'Company Trial Balance Wizard'

    company_id = fields.Many2one('res.company', string='Company', required=True)
    as_of_date = fields.Date(string='As of Date', required=True)

    def action_compute_company_trial_balance(self):
        self.ensure_one()
        usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
        action = self.env['idil.transaction_bookingline'].compute_company_trial_balance(usd_currency, self.company_id,
                                                                                        self.as_of_date)
        action['context'] = {
            'default_name': f'Company Trial Balance for {self.company_id.name} as of {self.as_of_date}'}

        return action
