from odoo import http
from odoo.http import request
import base64

class ProductAPIManager(http.Controller):

    @http.route('/api/product/get_products', type='json', auth='public', methods=['GET'], csrf=False)
    def get_products(self):
        try:
            products = request.env['my_product.product'].search([])
            product_list = []
            for product in products:
                product_list.append({
                    'id': product.id,
                    'name': product.name,
                    'internal_reference': product.internal_reference,
                    'category_id': product.category_id.id if product.category_id else None,
                    'available_in_pos': product.available_in_pos,
                    'pos_categ_ids': product.pos_categ_ids.ids,
                    'detailed_type': product.detailed_type,
                    'sale_price': product.sale_price,
                    'uom_id': product.uom_id.id if product.uom_id else None,
                    'income_account_id': product.income_account_id.id if product.income_account_id else None,
                    'image_1920': base64.b64encode(product.image_1920).decode('utf-8') if product.image_1920 else None  # Handle image encoding
                })
            return {'status': 200, 'data': product_list}
        except Exception as e:
            return {'status': 500, 'message': str(e)}

    @http.route('/api/product/create_product', type='json', auth='public', methods=['POST'], csrf=False)
    def create_product(self, **kwargs):
        try:
            # Validation for required fields
            if not kwargs.get('name'):
                return {'status': 400, 'message': 'Product name is required'}

            vals = {
                'name': kwargs.get('name'),
                'internal_reference': kwargs.get('internal_reference'),
                'category_id': kwargs.get('category_id'),
                'available_in_pos': kwargs.get('available_in_pos'),
                'pos_categ_ids': [(6, 0, kwargs.get('pos_categ_ids', []))],
                'detailed_type': kwargs.get('detailed_type', 'consu'),
                'sale_price': kwargs.get('sale_price'),
                'uom_id': kwargs.get('uom_id'),
                'income_account_id': kwargs.get('income_account_id'),
                'image_1920': base64.b64decode(kwargs.get('image_1920')) if kwargs.get('image_1920') else None,  # Handle image decoding
            }
            product = request.env['my_product.product'].create(vals)
            return {'status': 200, 'message': 'Product created successfully', 'product_id': product.id}
        except Exception as e:
            return {'status': 500, 'message': str(e)}

    @http.route('/api/product/update_product/<int:product_id>', type='json', auth='public', methods=['PUT'], csrf=False)
    def update_product(self, product_id, **kwargs):
        try:
            product = request.env['my_product.product'].browse(product_id)
            if not product.exists():
                return {'status': 404, 'message': 'Product not found'}
            
            vals = {}
            if 'name' in kwargs:
                vals['name'] = kwargs.get('name')
            if 'internal_reference' in kwargs:
                vals['internal_reference'] = kwargs.get('internal_reference')
            if 'category_id' in kwargs:
                vals['category_id'] = kwargs.get('category_id')
            if 'available_in_pos' in kwargs:
                vals['available_in_pos'] = kwargs.get('available_in_pos')
            if 'pos_categ_ids' in kwargs:
                vals['pos_categ_ids'] = [(6, 0, kwargs.get('pos_categ_ids', []))]
            if 'detailed_type' in kwargs:
                vals['detailed_type'] = kwargs.get('detailed_type')
            if 'sale_price' in kwargs:
                vals['sale_price'] = kwargs.get('sale_price')
            if 'uom_id' in kwargs:
                vals['uom_id'] = kwargs.get('uom_id')
            if 'income_account_id' in kwargs:
                vals['income_account_id'] = kwargs.get('income_account_id')
            if 'image_1920' in kwargs:
                vals['image_1920'] = base64.b64decode(kwargs.get('image_1920')) if kwargs.get('image_1920') else None  # Handle image decoding
            
            product.write(vals)
            return {'status': 200, 'message': 'Product updated successfully'}
        except Exception as e:
            return {'status': 500, 'message': str(e)}

    @http.route('/api/product/delete_product/<int:product_id>', type='json', auth='public', methods=['DELETE'], csrf=False)
    def delete_product(self, product_id):
        try:
            product = request.env['my_product.product'].browse(product_id)
            if not product.exists():
                return {'status': 404, 'message': 'Product not found'}
            
            product.unlink()
            return {'status': 200, 'message': 'Product deleted successfully'}
        except Exception as e:
            return {'status': 500, 'message': str(e)}
