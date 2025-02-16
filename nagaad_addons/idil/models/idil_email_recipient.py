from odoo import models, fields


class EmailRecipient(models.Model):
    _name = 'idil.email.recipient'
    _description = 'Email Recipients for Reports'

    name = fields.Char(string="Recipient Name", required=True)
    email = fields.Char(string="Email Address", required=True)
    active = fields.Boolean(string="Active", default=True)
