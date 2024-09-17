from odoo import models, fields


class HallFacility(models.Model):
    _name = 'idil.hall.facility'
    _description = 'Hall Facility'

    name = fields.Char(string='Facility Name', required=True)
    description = fields.Text(string='Description')
    price = fields.Float(string='Additional Price')
