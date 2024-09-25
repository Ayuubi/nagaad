from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class AccountHeader(models.Model):
    _name = 'idil.chart.account.header'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Idil Chart of Accounts Header'

    code = fields.Char(string='Header Code', required=True)
    name = fields.Char(string='Header Name', required=True)

    sub_header_ids = fields.One2many('idil.chart.account.subheader', 'header_id', string='Sub Headers')


class IncomeReportCurrencyWizard(models.TransientModel):
    _name = 'report.income.currency.wizard'
    _description = 'Currency Selection Wizard for Income Reports'

    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  help='Select the currency for the Income report.')
    report_date = fields.Date(string="Report Date", required=True,
                              default=fields.Date.context_today,
                              help="Select the date for which the Income report is to be generated.")

    def generate_income_report(self):
        self.ensure_one()
        data = {
            'currency_id': self.currency_id.id,
            'report_date': self.report_date  # Pass the selected date to the report
        }
        context = dict(self.env.context, currency_id=self.currency_id.id)
        return {
            'type': 'ir.actions.report',
            'report_name': 'idil.report_income_statement_template',
            'report_type': 'qweb-html',
            'context': context,
            'data': data
        }


class AccountSubHeader(models.Model):
    _name = 'idil.chart.account.subheader'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Idil Chart of Accounts Sub Header'

    sub_header_code = fields.Char(string='Sub Header Code', required=True)
    name = fields.Char(string='Sub Header Name', required=True)
    header_id = fields.Many2one('idil.chart.account.header', string='Header')
    account_ids = fields.One2many('idil.chart.account', 'subheader_id', string='Accounts')

    @api.constrains('sub_header_code')
    def _check_subheader_code_length(self):
        for subheader in self:
            if len(subheader.sub_header_code) != 6:
                raise ValidationError("Sub Header Code must be 6 characters long.")

    @api.constrains('sub_header_code', 'header_id')
    def _check_subheader_assignment(self):
        for subheader in self:
            header_code = subheader.header_id.code[:3]
            subheader_code = subheader.sub_header_code[:3]
            if not subheader_code.startswith(header_code):
                raise ValidationError("The first three digits of Sub Header Code must match the Header Code.")


class Account(models.Model):
    _name = 'idil.chart.account'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Idil Chart of Accounts'

    SIGN_SELECTION = [
        ('Dr', 'Dr'),
        ('Cr', 'Cr'),

    ]

    FINANCIAL_REPORTING_SELECTION = [
        ('BS', 'Balance Sheet'),
        ('PL', 'Profit and Loss'),
    ]
    account_type = [
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank'),
        ('payable', 'Account Payable'),
        ('receivable', 'Account Receivable'),
        ('COGS', 'COGS'),
        ('kitchen', 'kitchen'),
        ('Owners Equity', 'Owners Equity'),
    ]

    code = fields.Char(string='Account Code', required=True, tracking=True)
    name = fields.Char(string='Account Name', required=True, tracking=True)
    sign = fields.Selection(
        SIGN_SELECTION,
        string='Account Sign',
        compute='_compute_account_sign',
        store=True,
        tracking=True)
    FinancialReporting = fields.Selection(
        FINANCIAL_REPORTING_SELECTION,
        string='Financial Reporting',
        compute='_compute_financial_reporting',
        store=True,
        tracking=True
    )
    account_type = fields.Selection(
        account_type,
        string='Account Type',
        store=True,
        tracking=True
    )
    subheader_id = fields.Many2one('idil.chart.account.subheader', string='Sub Header', required=True, tracking=True)

    subheader_code = fields.Char(related='subheader_id.sub_header_code', string='Sub Header Code', readonly=True)
    subheader_name = fields.Char(related='subheader_id.name', string='Sub Header Name', readonly=True)
    header_code = fields.Char(related='subheader_id.header_id.code', string='Header Code', readonly=True)

    header_name = fields.Char(related='subheader_id.header_id.name', string='Header Name', readonly=True, store=True)
    # Add currency field
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)

    balance = fields.Float(string='Current Balance', compute='_compute_balance', store=True)

    transaction_bookingline_ids = fields.One2many(
        'idil.transaction_bookingline', 'account_number', string='Transaction Booking Lines'
    )

    @api.model
    def get_balance_sheet_data(self):
        """
        Dynamically fetch and calculate the balances for assets, liabilities, and equity,
        using only accounts where FinancialReporting is 'BS', showing only accounts with non-zero balances.
        Ensures that total liabilities + equity ± net profit/loss reflects non-zero values.
        """

        # Get today's date
        today = fields.Date.context_today(self)

        # If as_of_date is not provided, use today's date
        as_of_date = self.env.context.get('as_of_date', today)
        company = self.env.company  # Get the current company

        result = {
            'headers': [],
            'profit_loss': 0.0,
            'total_liabilities': 0.0,
            'total_equity': 0.0,  # Store total equity (without profit/loss adjustment)
            'total_owners_equity': 0.0,  # Store total equity after adjusting with profit/loss
            'total_liabilities_equity': 0.0,  # Store total of liabilities and equity adjusted by profit/loss
            'as_of_date': as_of_date,  # Pass as_of_date to the template
            'company': company  # Pass the company data to the template

        }

        # Fetching only accounts with FinancialReporting = 'BS'
        account_obj = self.env['idil.chart.account']
        bs_accounts = account_obj.search([('FinancialReporting', '=', 'BS')])

        # Group accounts by their header and subheader
        account_header_obj = self.env['idil.chart.account.header']
        headers = account_header_obj.search([])  # Get all headers

        for header in headers:
            header_data = {
                'header_name': header.name,
                'subheaders': [],
                'header_total': 0.0  # To store the total for this header
            }

            for subheader in header.sub_header_ids:
                subheader_data = {
                    'sub_header_name': subheader.name,
                    'accounts': [],
                    'subheader_total': 0.0
                }

                # Fetch only accounts under this subheader and FinancialReporting = 'BS'
                for account in subheader.account_ids.filtered(lambda a: a.FinancialReporting == 'BS'):
                    balance = self._compute_account_balance(account)

                    # Only add the account if its balance is non-zero
                    if balance != 0.0:
                        subheader_data['accounts'].append({
                            'account_name': account.name,
                            'balance': balance,
                        })
                        subheader_data['subheader_total'] += balance

                if subheader_data[
                    'accounts']:  # Only append subheader if it has relevant accounts with non-zero balance
                    header_data['header_total'] += subheader_data['subheader_total']
                    header_data['subheaders'].append(subheader_data)

            if header_data['subheaders']:
                if header.name == 'Liabilities':
                    result['total_liabilities'] += header_data['header_total']
                elif header.name == "Owner's Equity":
                    result['total_equity'] += header_data['header_total']

                result['headers'].append(header_data)

        # Compute Profit/Loss for Income and Expense accounts (starting with '4' and '5')
        income_accounts = account_obj.search([('code', 'like', '4%')])  # Income accounts
        expense_accounts = account_obj.search([('code', 'like', '5%')])  # Expense accounts

        total_income = sum(self._compute_account_balance(account) for account in income_accounts)
        total_expenses = sum(self._compute_account_balance(account) for account in expense_accounts)

        result['profit_loss'] = total_income - total_expenses

        # Calculate total owner's equity (equity + profit/loss)
        result['total_owners_equity'] = result['total_equity'] + result['profit_loss']

        # Calculate total liabilities + owner's equity
        result['total_liabilities_equity'] = result['total_liabilities'] + result['total_owners_equity']

        return result

    def _compute_account_balance(self, account):
        """
        Compute the balance of an account as sum(debit) - sum(credit)
        """
        moves = self.env['idil.transaction_bookingline'].search([('account_number', '=', account.id)])
        debit = sum(moves.mapped('dr_amount'))
        credit = sum(moves.mapped('cr_amount'))
        return abs(debit - credit)

    @api.depends('transaction_bookingline_ids.dr_amount', 'transaction_bookingline_ids.cr_amount')
    def _compute_balance(self):
        for account in self:
            # Clear the balance before calculation
            account.balance = 0
            debit_sum = sum(
                account.transaction_bookingline_ids.filtered(lambda l: l.transaction_type == 'dr').mapped('dr_amount'))
            credit_sum = sum(
                account.transaction_bookingline_ids.filtered(lambda l: l.transaction_type == 'cr').mapped('cr_amount'))
            account.balance = debit_sum - credit_sum

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        if 'balance' in fields:
            fields.remove('balance')
        res = super(Account, self).read_group(domain, fields, groupby, offset, limit, orderby, lazy)
        if 'balance' not in fields:
            fields.append('balance')
        if 'balance' in fields:
            for line in res:
                if '__domain' in line:
                    accounts = self.search(line['__domain'])
                    # Ensure balances are computed
                    accounts._compute_balance()
                    balance = sum(account.balance for account in accounts)
                    line['balance'] = balance
        return res

    @api.model
    def read(self, fields=None, load='_classic_read'):
        res = super(Account, self).read(fields, load)
        for record in self:
            record._compute_balance()
        return res

    def name_get(self):
        result = []
        for record in self:
            name = f"{record.name} ({record.currency_id.name})"
            result.append((record.id, name))
        return result

    @api.depends('code')
    def _compute_account_sign(self):
        for account in self:
            if account.code:
                first_digit = account.code[0]
                # Determine sign based on the first digit of the account code
                if first_digit in ['1', '5', '6', '8']:  # Dr accounts
                    account.sign = 'Dr'
                elif first_digit in ['2', '3', '4', '7', '9']:  # Cr accounts
                    account.sign = 'Cr'
                else:
                    account.sign = False
            else:
                account.sign = False

    @api.depends('code')
    def _compute_financial_reporting(self):
        for account in self:
            if account.code:
                first_digit = account.code[0]
                # Determine financial reporting based on the first digit of the account code
                if first_digit in ['1', '2', '3']:  # Assuming 1, 2, 3 represent BS, adjust as needed
                    account.FinancialReporting = 'BS'
                elif first_digit in ['4', '5', '6', '7', '8', '9']:  # Assuming 4, 5 represent PL, adjust as needed
                    account.FinancialReporting = 'PL'
                else:
                    account.FinancialReporting = False
            else:
                account.FinancialReporting = False

    def get_balance_as_of_date(self, date):
        self.ensure_one()  # Ensures this is called on a single record
        transactions = self.env['idil.transaction_bookingline'].search([
            ('account_number', '=', self.id),
            ('transaction_date', '<=', date)  # Filter transactions up to the specified date
        ])
        debit = sum(transaction.dr_amount for transaction in transactions if transaction.transaction_type == 'dr')
        credit = sum(transaction.cr_amount for transaction in transactions if transaction.transaction_type == 'cr')
        return abs(debit - credit)


class AccountBalanceReport(models.TransientModel):
    _name = 'idil.account.balance.report'
    _description = 'Account Balance Report'

    type = fields.Char(string="Type")
    subtype = fields.Char(string="subtype")
    account_name = fields.Char(string="Account Name")
    # account_code = fields.Char(string="Account Code")
    account_id = fields.Many2one('idil.chart.account', string="Account", store=True)
    balance = fields.Float(compute='_compute_balance', store=True)
    currency_id = fields.Many2one('res.currency', string='Currency', related='account_id.currency_id', store=True,
                                  readonly=True)

    @api.depends('account_id')
    def _compute_balance(self):
        for report in self:
            # Initialize balance to 0 for each report entry
            report.balance = 0
            # Find transactions related to this account_code
            transactions = self.env['idil.transaction_bookingline'].search(
                [('account_number', '=', report.account_id.id)])
            debit = sum(transactions.filtered(lambda r: r.transaction_type == 'dr').mapped('dr_amount'))
            credit = sum(transactions.filtered(lambda r: r.transaction_type == 'cr').mapped('cr_amount'))
            # Calculate balance
            report.balance = abs(debit - credit)

    @api.model
    def generate_account_balances_report(self):
        self.search([]).unlink()  # Clear existing records to avoid stale data

        account_balances = self._get_account_balances()
        for balance in account_balances:
            self.create({
                'type': balance['type'],
                'subtype': balance['subtype'],
                'account_name': balance['account_name'],
                'account_id': balance['account_id'],

            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Account Balances',
            'view_mode': 'tree',
            'res_model': 'idil.account.balance.report',
            'domain': [('balance', '<>', 0)],  # Ensures only accounts with non-zero balances are shown
            'context': {'group_by': ['type', 'subtype']},
            'target': 'new',
        }

    def _get_account_balances(self):
        account_balances = []
        accounts = self.env['idil.chart.account'].search([])

        for account in accounts:
            account_balances.append({
                'type': account.header_name,
                'subtype': account.subheader_name,
                'account_name': account.name,
                'account_id': account.id,
            })
        return account_balances
