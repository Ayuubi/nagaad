from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ProjectProcurementPlan(models.Model):
    _name = 'idil.project.procurement'
    _description = 'Project Procurement Plan'

    project_id = fields.Many2one('idil.project', string="Project", required=True, ondelete="cascade")
    item = fields.Char(string="Item Description", required=True)
    vendor_id = fields.Many2one('res.partner', string="Vendor", domain=[('supplier_rank', '>', 0)])
    quantity = fields.Float(string="Quantity", required=True)
    expected_date = fields.Date(string="Expected Delivery Date")
    status = fields.Selection([
        ('pending', 'Pending'),
        ('ordered', 'Ordered'),
        ('delivered', 'Delivered')
    ], default='pending', string="Status")
