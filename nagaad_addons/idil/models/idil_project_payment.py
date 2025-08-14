from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ProjectPayment(models.Model):
    _name = 'idil.project.payment'
    _description = 'Project Payment Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Payment Reference", required=True, copy=False, default="New")
    project_id = fields.Many2one('idil.project', string="Project", required=True, ondelete="cascade", tracking=True)
    payment_date = fields.Date(string="Payment Date", default=fields.Date.context_today, required=True)
    amount = fields.Monetary(string="Amount Received", required=True, tracking=True)
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )
    # Adding payment method field
    payment_method_id = fields.Many2one('idil.payment.method', string='Payment Method', required=True)
    # Account Number Field (related to the selected Payment Method)
    account_number = fields.Char(string='Account Number', compute='_compute_account_number', store=True)
    # Add these to ProjectPayment class
    project_code = fields.Char(related='project_id.code', string='Project Code', store=True)
    project_total_cost = fields.Monetary(related='project_id.total_cost', string='Total Cost', store=True)
    project_amount = fields.Monetary(related='project_id.project_amount', string='Project Amount', store=True)

    project_estimated_profit = fields.Monetary(related='project_id.estimated_profit', string='Estimated Profit',
                                               store=True)
    project_currency_id = fields.Many2one(related='project_id.currency_id', string='Project Currency', store=True)
    project_cash_account_id = fields.Many2one(related='project_id.cost_account_id', string='Cost Account', store=True)
    project_profit_account_id = fields.Many2one(related='project_id.profit_account_id', string='Profit Account',
                                                store=True)

    notes = fields.Text(string="Notes")

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
    ], string="Status", default="draft", tracking=True)

    @api.depends('payment_method_id')
    def _compute_account_number(self):
        for record in self:
            if record.payment_method_id:
                record.account_number = record.payment_method_id.account_number.name
            else:
                record.account_number = ''

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('idil.project.payment') or 'New'
        return super().create(vals)

    def action_confirm_payment(self):
        for payment in self:
            if payment.state != 'draft':
                continue
            payment._create_payment_booking()
            payment.state = 'confirmed'

    def _create_payment_booking(self):
        """Create accounting booking for the payment"""
        # Create transaction booking
        booking_vals = {
            'transaction_number': self.env['ir.sequence'].next_by_code('idil.transaction.booking') or 'New',
            'reffno': self.name,
            'trx_date': self.payment_date,
            'payment_method': 'cash',  # or 'bank' or as required
            'amount': self.amount,
        }
        booking = self.env['idil.transaction_booking'].create(booking_vals)

        # Debit: Cash/Bank account from project
        cost_account = self.payment_method_id.account_number.id
        if not cost_account:
            raise UserError(_("Please set a Cash/Bank Account on the project: %s" % self.project_id.name))

        self.env['idil.transaction_bookingline'].create({
            'transaction_booking_id': booking.id,
            'description': f'Debit for project payment: {self.project_id.name}',
            'item_id': False,
            'account_number': cost_account,
            'transaction_type': 'dr',
            'dr_amount': self.amount,
            'cr_amount': 0,
            'transaction_date': self.payment_date,
        })

        # Credit: Profit/Income/Receivable account from project
        profit_account = self.project_id.profit_account_id
        if not profit_account:
            raise UserError(_("Please set a Profit/Receivable Account on the project: %s" % self.project_id.name))

        self.env['idil.transaction_bookingline'].create({
            'transaction_booking_id': booking.id,
            'description': f'Credit for project payment: {self.project_id.name}',
            'item_id': False,
            'account_number': profit_account.id,
            'transaction_type': 'cr',
            'cr_amount': self.amount,
            'dr_amount': 0,
            'transaction_date': self.payment_date,
        })
