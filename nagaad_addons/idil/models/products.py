from odoo import models, fields, api

class Product(models.Model):
    _name = 'my_product.product'
    _description = 'Product'

    name = fields.Char(string='Product Name', required=True)
    internal_reference = fields.Char(string='Internal Reference', required=True)
    category_id = fields.Many2one('product.category', string='Product Category')
    available_in_pos = fields.Boolean(string='Available in POS', default=True)
    pos_categ_ids = fields.Many2many('pos.category', string='POS Categories')
    detailed_type = fields.Selection([
        ('consu', 'Consumable'),
        ('service', 'Service')
    ], string='Product Type', default='consu', required=True,
        help='A storable product is a product for which you manage stock. The Inventory app has to be installed.\n'
             'A consumable product is a product for which stock is not managed.\n'
             'A service is a non-material product you provide.')

    sale_price = fields.Float(string='Sales Price', required=True)
    uom_id = fields.Many2one('idil.unit.measure', string='Unit of Measure')
    income_account_id = fields.Many2one(
        'idil.chart.account',
        string='Income Account',
        help='Account to report Sales Income',
        required=True,
        domain="[('code', 'like', '4')]"  # Domain to filter accounts starting with '4'
    )

    image_url = fields.Char(string='Image URL')  # New field to store the image URL instead of binary

    @api.model
    def create(self, vals):
        if 'internal_reference' not in vals or not vals['internal_reference']:
            # Generate the next internal reference
            last_product = self.search([], order='id desc', limit=1)
            if last_product:
                # Assuming the internal reference is a numeric value
                last_id = int(last_product.internal_reference) if last_product.internal_reference.isdigit() else 0
                vals['internal_reference'] = str(last_id + 1)
            else:
                vals['internal_reference'] = '1'  # Start from 1 if no product exists

        res = super(Product, self).create(vals)
        res._sync_with_odoo_product()
        return res

    def write(self, vals):
        res = super(Product, self).write(vals)
        self._sync_with_odoo_product()
        return res

    def _sync_with_odoo_product(self):
        ProductProduct = self.env['product.product']
        for product in self:
            odoo_product = ProductProduct.search([('default_code', '=', product.internal_reference)], limit=1)
            product_data = {
                'my_product_id': product.id,
                'name': product.name,
                'default_code': product.internal_reference,
                'type': product.detailed_type,
                'list_price': product.sale_price,
                'standard_price': product.sale_price,
                'categ_id': product.category_id.id,
                'pos_categ_ids': product.pos_categ_ids,
                'uom_id': product.uom_id.id if product.uom_id else 1,
                'available_in_pos': product.available_in_pos,
                'image_url': product.image_url,  # Using image URL instead of binary image
            }

            if not odoo_product:
                odoo_product = ProductProduct.create(product_data)
            else:
                odoo_product.write(product_data)

# Extend the `product.product` model with an `image_url` field in the same file
class ProductProduct(models.Model):
    _inherit = 'product.product'

    image_url = fields.Char(string='Image URL')  # New field to store the image URL
