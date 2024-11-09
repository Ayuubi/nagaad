from odoo import models, fields, api
import firebase_admin
from firebase_admin import credentials, firestore
import logging

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    cred = credentials.Certificate('/mnt/extra-addons/nagad-f6ebd-firebase-adminsdk-thdw2-8bda9a1d9f.json')
    firebase_admin.initialize_app(cred)
db = firestore.client()

_logger = logging.getLogger(__name__)

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
        help='A consumable product is a product for which stock is not managed.\n'
             'A service is a non-material product you provide.')

    sale_price = fields.Float(string='Sales Price', required=True)
    uom_id = fields.Many2one('idil.unit.measure', string='Unit of Measure')
    income_account_id = fields.Many2one(
        'idil.chart.account',
        string='Income Account',
        help='Account to report Sales Income',
        required=True,
        domain="[('code', 'like', '4')]"
    )

    image_url = fields.Char(string='Image URL')

    @api.model
    def create(self, vals):
        if 'internal_reference' not in vals or not vals['internal_reference']:
            last_product = self.search([], order='id desc', limit=1)
            if last_product:
                last_id = int(last_product.internal_reference) if last_product.internal_reference.isdigit() else 0
                vals['internal_reference'] = str(last_id + 1)
            else:
                vals['internal_reference'] = '1'

        product = super(Product, self).create(vals)
        product._save_product_to_firebase(product)  # Save to Firebase
        return product

    def write(self, vals):
        res = super(Product, self).write(vals)
        self._sync_with_odoo_product()
        return res

    def _sync_with_odoo_product(self):
        ProductProduct = self.env['product.product']
        for product in self:
            odoo_product = ProductProduct.search([('default_code', '=', product.internal_reference)], limit=1)
            if not odoo_product:
                odoo_product = ProductProduct.create({
                    'my_product_id': product.id,
                    'name': product.name,
                    'default_code': product.internal_reference,
                    'type': product.detailed_type,
                    'list_price': product.sale_price,
                    'standard_price': product.sale_price,
                    'categ_id': product.category_id.id,
                    'pos_categ_ids': product.pos_categ_ids,
                    'uom_id': 1,
                    'available_in_pos': product.available_in_pos,
                    'image_url': product.image_url,
                })
            else:
                odoo_product.write({
                    'my_product_id': product.id,
                    'name': product.name,
                    'default_code': product.internal_reference,
                    'type': product.detailed_type,
                    'list_price': product.sale_price,
                    'standard_price': product.sale_price,
                    'categ_id': product.category_id.id,
                    'pos_categ_ids': product.pos_categ_ids,
                    'uom_id': 1,
                    'available_in_pos': product.available_in_pos,
                    'image_url': product.image_url,
                })

    def _save_product_to_firebase(self, product):
        """Save a single product to Firebase, customized to the 'menu' collection."""
        data = {
            'name': product.name,
            'description': product.name,  # Duplicate of name
            'price': product.sale_price,  # Keeping sale_price as a float
            'type': product.category_id.name if product.category_id else '',  # Saving category name as type
            'image': product.image_url,  # URL of the product image
        }
        _logger.info("Saving product to Firebase: %s", data)
        db.collection('menu').document(str(product.id)).set(data)

    def push_all_products_to_firebase(self):
        """Push all existing products to Firebase."""
        batch = db.batch()
        products = self.search([])  # Fetch all products
        for product in products:
            data = {
                'name': product.name,
                'description': product.name,
                'price': product.sale_price,
                'type': product.category_id.name if product.category_id else '',  # Saving category name as type
                'image': product.image_url,
            }
            doc_ref = db.collection('menu').document(str(product.id))
            batch.set(doc_ref, data)
        
        batch.commit()

# Extend the `product.product` model with an `image_url` field in the same file
class ProductProduct(models.Model):
    _inherit = 'product.product'

    image_url = fields.Char(string='Image URL')
