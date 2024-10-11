from odoo import http
from odoo.http import request, Response
import json
import base64

class ProductAPIController(http.Controller):

    # GET all products with relevant fields from the Odoo model
    @http.route('/api/products/get_products', type='http', auth='public', methods=['GET'], csrf=False)
    def get_products(self, **kwargs):
        try:
            products = request.env['my_product.product'].sudo().search([])
            products_data = []
            for product in products:
                products_data.append({
                    'id': product.id,
                    'title': product.name,  # 'name' field from your model
                    'price': product.sale_price,  # 'sale_price' from your model
                    'category': product.category_id.name if product.category_id else '',  # 'category_id' from your model
                    'thumbnail': f"data:image/png;base64,{base64.b64encode(product.image_1920).decode('utf-8')}" if product.image_1920 else None,  # 'image_1920' as base64
                    'images': [
                        f"data:image/png;base64,{base64.b64encode(product.image_1920).decode('utf-8')}" if product.image_1920 else None  # Assuming one image for now
                    ],
                    'available_in_pos': product.available_in_pos,  # 'available_in_pos' from your model
                    'uom': product.uom_id.name if product.uom_id else ''  # 'uom_id' field from your model
                })
            return Response(json.dumps({'products': products_data, 'total': len(products_data)}), content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})
        except Exception as e:
            return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')

    # GET single product by ID with the relevant fields
    @http.route('/api/products/get_product/<int:product_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def get_product(self, product_id, **kwargs):
        try:
            product = request.env['my_product.product'].sudo().browse(product_id)
            if not product.exists():
                return Response(json.dumps({'error': 'Product not found'}), status=404, content_type='application/json')

            product_data = {
                'id': product.id,
                'title': product.name,
                'price': product.sale_price,
                'category': product.category_id.name if product.category_id else '',
                'thumbnail': f"data:image/png;base64,{base64.b64encode(product.image_1920).decode('utf-8')}" if product.image_1920 else None,
                'images': [
                    f"data:image/png;base64,{base64.b64encode(product.image_1920).decode('utf-8')}" if product.image_1920 else None
                ],
                'available_in_pos': product.available_in_pos,
                'uom': product.uom_id.name if product.uom_id else ''
            }
            return Response(json.dumps(product_data), content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})
        except Exception as e:
            return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')
