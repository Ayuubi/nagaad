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
        ('booked', 'Booked'),
        ('maintenance', 'Maintenance')
    ], string='Availability')

    income_account_id = fields.Many2one(
        'idil.chart.account',
        string='Income Account',
        help='Account to report Sales Income',
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
