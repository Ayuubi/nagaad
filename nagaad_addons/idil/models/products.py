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

class ProductProduct(models.Model):
    _inherit = 'product.product'

    image_url = fields.Char(string='Image URL')

    @api.model
    def create(self, vals):
        product = super(ProductProduct, self).create(vals)
        product._save_pos_product_to_firebase(product)
        return product

    def write(self, vals):
        res = super(ProductProduct, self).write(vals)
        self._save_pos_product_to_firebase(self)
        return res

    def _save_pos_product_to_firebase(self, product):
        """Save a single POS product to the 'menu' collection in Firebase with matching fields and values."""
        data = {
            'description': product.name or '',  # Use product name for description
            'id': product.id,
            'image': product.image_url or False,  # Use URL if available, otherwise False
            'name': product.name,
            'price': product.list_price or 0,  # Default to 0 if no price is set
            'type': product.categ_id.name if product.categ_id else 'All',  # Default to 'All' if no category
            'url': product.image_url or False,  # URL if available, otherwise False
        }
        _logger.info("Saving POS product to Firebase in 'menu' collection: %s", data)
        db.collection('menu').document(str(product.id)).set(data)

    def push_all_pos_products_to_firebase(self):
        """Push all POS products to Firebase under the 'menu' collection with the specified fields."""
        batch = db.batch()
        products = self.search([('available_in_pos', '=', True)])  # Only POS products
        for product in products:
            data = {
                'description': product.name or '',
                'id': product.id,
                'image': product.image_url or False,
                'name': product.name,
                'price': product.list_price or 0,
                'type': product.categ_id.name if product.categ_id else 'All',
                'url': product.image_url or False,
            }
            doc_ref = db.collection('menu').document(str(product.id))
            batch.set(doc_ref, data)
        
        batch.commit()
        _logger.info("All POS products have been pushed to Firebase under the 'menu' collection.")
