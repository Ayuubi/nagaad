from odoo import models, fields, api
from odoo.exceptions import ValidationError


class Product(models.Model):
    _name = 'my_product.product'
    _description = 'Product'
    _inherit = ['mail.thread', 'mail.activity.mixin']  # optional for chatter
    _rec_name = 'name'

    # 👇 new field for multi-company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        domain=lambda self: [('id', 'in', self.env.companies.ids)],  # only allowed companies
        index=True
    )
    name = fields.Char(string='Product Name', required=True)
    internal_reference = fields.Char(string='Internal Reference', required=True)
    category_id = fields.Many2one('product.category', string='Product Category')

    available_in_pos = fields.Boolean(string='Available in POS', default=True)
    pos_categ_ids = fields.Many2many('pos.category', string='POS Categories')

    detailed_type = fields.Selection([
        ('consu', 'Consumable'),
        ('service', 'Service')
    ], string='Product Type', default='consu', required=True)

    sale_price = fields.Float(string='Sales Price', required=True)
    cost = fields.Float(string='Sales cost Price', required=True)
    stock_quantity = fields.Float(string="Available Stock")

    uom_id = fields.Many2one('idil.unit.measure', string='Unit of Measure')
    income_account_id = fields.Many2one(
        'idil.chart.account',
        string='Income Account',
        required=True,
        domain="[('code', '=like', '4%'), ('company_id', '=', company_id)]",
    )

    image_1920 = fields.Binary(string='Image')
    image_url = fields.Char(string='Image URL')



    _sql_constraints = [
        ('ref_company_unique',
         'unique(internal_reference, company_id)',
         'The internal reference must be unique per company!')
    ]

    @api.model
    def create(self, vals):
        if 'internal_reference' not in vals or not vals['internal_reference']:
            last_product = self.search(
                [('company_id', '=', vals.get('company_id') or self.env.company.id)],
                order='id desc', limit=1
            )
            if last_product and last_product.internal_reference.isdigit():
                vals['internal_reference'] = str(int(last_product.internal_reference) + 1)
            else:
                vals['internal_reference'] = '1'
        res = super().create(vals)
        res._sync_with_odoo_product()
        return res

    def write(self, vals):
        res = super().write(vals)
        self._sync_with_odoo_product()
        return res

    def _sync_with_odoo_product(self):
        ProductProduct = self.env['product.product']
        for product in self:
            odoo_product = ProductProduct.search([
                ('default_code', '=', product.internal_reference),
                ('company_id', '=', product.company_id.id)
            ], limit=1)

            vals = {
                'my_product_id': product.id,
                'name': product.name,
                'default_code': product.internal_reference,
                'type': product.detailed_type,
                'list_price': product.sale_price,
                'standard_price': product.sale_price,
                'categ_id': product.category_id.id,
                'pos_categ_ids': [(6, 0, product.pos_categ_ids.ids)],
                'uom_id': 1,
                'available_in_pos': product.available_in_pos,
                'image_1920': product.image_1920,
                'company_id': product.company_id.id,
            }
            if odoo_product:
                odoo_product.write(vals)
            else:
                ProductProduct.create(vals)
