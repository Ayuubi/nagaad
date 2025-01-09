from odoo import models, fields, api


class Hall(models.Model):
    _name = 'idil.hall'
    _description = 'Hall Management'

    name = fields.Char(string='Hall Name', required=True)
    location = fields.Char(string='Location')
    capacity = fields.Integer(string='Capacity')
    price_per_hour = fields.Float(string='Price per Guest')
    facilities = fields.Many2many('idil.hall.facility', string='Facilities')
    availability = fields.Selection([
        ('available', 'Available'),
        ('maintenance', 'Maintenance')
    ], default='available', string='Availability')

    income_account_id = fields.Many2one(
        'idil.chart.account',
        string='Income Account',
        help='Account to report Hall Income',
        required=True,
        domain="[('code', 'like', '4')]"  # Domain to filter accounts starting with '4'
    )
    extra_income_account_id = fields.Many2one(
        'idil.chart.account',
        string='Extra Income Account',
        help='Account to report Extra Hall Income',
        required=True,
        domain="[('code', 'like', '4')]"  # Domain to filter accounts starting with '4'
    )
    Receivable_account_id = fields.Many2one(
        'idil.chart.account',
        string='Receivable Account',
        help='Account to report Receivable Amounts',
        required=True,
        domain="[('code', 'like', '1')]"  # Domain to filter accounts starting with '4'
    )
    facilities_display = fields.Char(
        string='Facilities Display',
        compute='_compute_facilities_display'
    )

    @api.depends('facilities')
    def _compute_facilities_display(self):
        for record in self:
            if record.facilities:
                record.facilities_display = ", ".join(record.facilities.mapped('name'))
            else:
                record.facilities_display = ''
