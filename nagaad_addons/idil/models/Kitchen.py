from odoo import models, fields


class Kitchen(models.Model):
    _name = 'idil.kitchen'
    _description = 'Kitchen'

    # 👇 new field for multi-company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        domain=lambda self: [('id', 'in', self.env.companies.ids)],  # only allowed companies
        index=True
    )
    name = fields.Char(string='Name')
    location = fields.Char(string='Location')
    contact_person = fields.Char(string='Contact Person')
    contact_email = fields.Char(string='Contact Email')
    contact_phone = fields.Char(string='Contact Phone')
    notes = fields.Text(string='Notes')

    inventory_account = fields.Many2one(
        'idil.chart.account',
        string='Inventory Account Number',
        domain="[('account_type', '=', 'kitchen'), ('company_id', '=', company_id)]"
        # Assuming 'kitchen' is a valid account_type value
    )
    is_event = fields.Boolean(string="Is Event?", help="Check this if the kitchen is associated with an event.")
