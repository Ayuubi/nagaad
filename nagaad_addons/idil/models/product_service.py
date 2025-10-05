from odoo import models, fields


class ProductService(models.Model):
    _name = "idil.product.service"
    _description = "Product and Service Master"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    # 👇 new field for multi-company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        domain=lambda self: [('id', 'in', self.env.companies.ids)],  # only allowed companies
        index=True
    )
    item_type = fields.Selection([
        ('product', 'Product'),
        ('service', 'Service'),
    ], string="Item Type", required=True, tracking=True)

    # Common fields
    name = fields.Char(string="Product / Service Name", required=True, tracking=True)
    sale_price = fields.Float(string='Sales Price', required=True)
    cost = fields.Float(string='Cost Price', required=True)
    quantity = fields.Float(string="Available Stock")
    uom_id = fields.Many2one('idil.unit.measure', string='Unit of Measure')


    image = fields.Binary(string="Image")

    # Accounting fields (dynamic visibility)
    asset_account_id = fields.Many2one('idil.chart.account', string="Asset Account (Inventory)", tracking=True)
    purchase_account_id = fields.Many2one('idil.chart.account', string="Purchase Account", tracking=True)
    income_account_id = fields.Many2one('idil.chart.account', string="Income Account", tracking=True)
