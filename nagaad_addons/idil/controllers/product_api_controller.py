from odoo import http
from odoo.http import request
import json



class ProductAPIManager(http.Controller):
    
    @http.route('/product_api_manager/products', type='json', auth='user', methods=['GET'], csrf=False)
    def get_products(self):
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
                'image_1920': product.image_1920
            })
        return {'status': 200, 'data': product_list}

    @http.route('/product_api_manager/products', type='json', auth='user', methods=['POST'], csrf=False)
    def create_product(self, **kwargs):
        try:
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
                'image_1920': kwargs.get('image_1920'),
            }
            product = request.env['my_product.product'].create(vals)
            return {'status': 200, 'message': 'Product created successfully', 'product_id': product.id}
        except Exception as e:
            return {'status': 500, 'message': str(e)}

    @http.route('/product_api_manager/products/<int:product_id>', type='json', auth='user', methods=['PUT'], csrf=False)
    def update_product(self, product_id, **kwargs):
        try:
            product = request.env['my_product.product'].browse(product_id)
            if not product.exists():
                return {'status': 404, 'message': 'Product not found'}
            
            vals = {
                'name': kwargs.get('name'),
                'internal_reference': kwargs.get('internal_reference'),
                'category_id': kwargs.get('category_id'),
                'available_in_pos': kwargs.get('available_in_pos'),
                'pos_categ_ids': [(6, 0, kwargs.get('pos_categ_ids', []))],
                'detailed_type': kwargs.get('detailed_type'),
                'sale_price': kwargs.get('sale_price'),
                'uom_id': kwargs.get('uom_id'),
                'income_account_id': kwargs.get('income_account_id'),
                'image_1920': kwargs.get('image_1920'),
            }
            product.write(vals)
            return {'status': 200, 'message': 'Product updated successfully'}
        except Exception as e:
            return {'status': 500, 'message': str(e)}

    @http.route('/product_api_manager/products/<int:product_id>', type='json', auth='user', methods=['DELETE'], csrf=False)
    def delete_product(self, product_id):
        try:
            product = request.env['my_product.product'].browse(product_id)
            if not product.exists():
                return {'status': 404, 'message': 'Product not found'}
            
            product.unlink()
            return {'status': 200, 'message': 'Product deleted successfully'}
        except Exception as e:
            return {'status': 500, 'message': str(e)}
