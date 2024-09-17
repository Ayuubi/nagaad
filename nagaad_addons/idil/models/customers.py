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
    image = fields.Binary(string="Image")
