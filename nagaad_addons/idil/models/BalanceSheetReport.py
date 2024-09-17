from odoo import models, fields, api


class BalanceSheetReport(models.TransientModel):
    _name = 'idil.balance.sheet.report'
    _description = 'Balance Sheet Report'

    type = fields.Char(string="Type")
    subtype = fields.Char(string="Subtype")
    account_name = fields.Char(string="Account Name")
    account_code = fields.Char(string="Account Code")
    balance = fields.Float(string="Balance")
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    category = fields.Selection([
        ('asset', 'Asset'),
        ('liability', 'Liability'),
        ('equity', 'Equity')
    ], string='Category')

    def _get_account_balances(self):
        account_balances = []
        accounts = self.env['idil.chart.account'].search([])

        categories = {
            '1': 'asset',
            '2': 'liability',
            '3': 'equity',
        }

        totals = {
            'asset': 0,
            'liability': 0,
            'equity': 0,
        }

        expense_accounts = self.env['idil.chart.account'].search([('code', '=like', '5%')])
        profit_accounts = self.env['idil.chart.account'].search([('code', '=like', '4%')])

        total_expense = 0
        total_profit = 0

        for expense_account in expense_accounts:
            expense_debit = sum(self.env['idil.transaction_bookingline'].search(
                [('account_number', '=', expense_account.id), ('transaction_type', '=', 'dr')]).mapped('dr_amount'))
            expense_credit = sum(self.env['idil.transaction_bookingline'].search(
                [('account_number', '=', expense_account.id), ('transaction_type', '=', 'cr')]).mapped('cr_amount'))

            total_expense += expense_debit - expense_credit

        for profit_account in profit_accounts:
            profit_debit = sum(self.env['idil.transaction_bookingline'].search(
                [('account_number', '=', profit_account.id), ('transaction_type', '=', 'dr')]).mapped('dr_amount'))
            profit_credit = sum(self.env['idil.transaction_bookingline'].search(
                [('account_number', '=', profit_account.id), ('transaction_type', '=', 'cr')]).mapped('cr_amount'))

            total_profit += profit_credit - profit_debit

        net_profit = total_profit - total_expense

        for account in accounts:
            debit = sum(self.env['idil.transaction_bookingline'].search(
                [('account_number', '=', account.id), ('transaction_type', '=', 'dr')]).mapped('dr_amount'))
            credit = sum(self.env['idil.transaction_bookingline'].search(
                [('account_number', '=', account.id), ('transaction_type', '=', 'cr')]).mapped('cr_amount'))

            balance = debit - credit
            category = categories.get(account.code[0], 'unknown')

            if category in totals:
                totals[category] += balance

            account_balances.append({
                'type': account.header_name,
                'subtype': account.subheader_name,
                'account_name': account.name,
                'account_code': account.code,
                'balance': balance,
                'currency_id': account.currency_id.id,
                'category': category,
            })

        # Add the net profit to the equity category
        account_balances.append({
            'type': 'Equity',
            'subtype': 'Net Profit',
            'account_name': 'Net Profit',
            'account_code': '',
            'balance': net_profit,
            'currency_id': self.env.company.currency_id.id,
            'category': 'equity',
        })

        return account_balances

    def generate_balance_sheet_report(self):
        account_balances = self._get_account_balances()
        asset_accounts = [acc for acc in account_balances if acc['category'] == 'asset']
        liability_accounts = [acc for acc in account_balances if acc['category'] == 'liability']
        equity_accounts = [acc for acc in account_balances if acc['category'] == 'equity']

        asset_total = sum(acc['balance'] for acc in asset_accounts)
        liability_total = sum(acc['balance'] for acc in liability_accounts)
        equity_total = sum(acc['balance'] for acc in equity_accounts)

        # Extract Net Profit (assuming it's the last equity account added)
        net_profit = equity_accounts[-1]['balance'] if equity_accounts and equity_accounts[-1][
            'subtype'] == 'Net Profit' else 0

        # Encapsulate data in a dictionary under 'doc'
        report_data = {
            'doc': {
                'asset_accounts': asset_accounts,
                'liability_accounts': liability_accounts,
                'equity_accounts': equity_accounts,
                'asset_total': asset_total,
                'liability_total': liability_total,
                'equity_total': equity_total,
                'net_profit': net_profit,  # Pass net profit to the template
                'currency_id': self.env.company.currency_id,  # Ensure currency is passed
            }
        }

        return self.env.ref('idil.report_balance_sheet').report_action(self, data=report_data)
