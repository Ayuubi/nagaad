from odoo import models, fields, api


class Customer(models.Model):
    _name = 'idil.customer.registration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Customer Registration'

    name = fields.Char(string='Name', required=True, tracking=True)
    type_id = fields.Many2one(comodel_name='idil.customer.type.registration', string='Customer Type',
                              help='Select type of registration')
    phone = fields.Char(string='Phone', required=True, tracking=True)
    email = fields.Char(string='Email', tracking=True)
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female')
    ], string='Gender', tracking=True)
    status = fields.Boolean(string='Status', tracking=True)
    active = fields.Boolean(string="Archive", default=True, tracking=True)
    # currency_id = fields.Many2one(
    #     "res.currency",
    #     string="Currency",
    #     default=lambda self: self.env.company.currency_id,
    # )
    # account_receivable_id = fields.Many2one(
    #     "idil.chart.account",
    #     string="Sales Receivable Account",
    #     domain="[('account_type', 'like', 'receivable'), ('code', 'like', '1%'), "
    #            "('currency_id', '=', currency_id)]",
    #     help="Select the receivable account for transactions.",
    #
    # )
    image = fields.Binary(string="Image")
