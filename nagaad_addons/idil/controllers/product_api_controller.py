from odoo import http
from odoo.http import request, Response
import json


class ProductAPIController(http.Controller):

    # GET all products
    @http.route('/api/products/get_products', type='http', auth='public', methods=['GET'], csrf=False)
    def get_products(self, **kwargs):
        try:
            products = request.env['my_product.product'].sudo().search([])
            products_data = []
            for product in products:
                products_data.append({
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
            return Response(json.dumps(products_data), content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})
        except Exception as e:
            return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')

    # GET single product by ID
    @http.route('/api/products/get_product/<int:product_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def get_product(self, product_id, **kwargs):
        try:
            product = request.env['my_product.product'].sudo().browse(product_id)
            if not product.exists():
                return Response(json.dumps({'error': 'Product not found'}), status=404, content_type='application/json')

            product_data = {
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
            }
            return Response(json.dumps(product_data), content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})
        except Exception as e:
            return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')

    # POST to create a new product
    @http.route('/api/products/create_product', type='json', auth='public', methods=['POST'], csrf=False)
    def create_product(self, **post):
        try:
            # Validate mandatory fields
            required_fields = ['name', 'internal_reference', 'sale_price', 'uom_id', 'category_id']
            missing_fields = [field for field in required_fields if field not in post]
            if missing_fields:
                return Response(json.dumps({'error': f'Missing required fields: {", ".join(missing_fields)}'}), status=400, content_type='application/json')

            # Validate foreign key relations
            category = request.env['my_product.category'].sudo().browse(post.get('category_id'))
            if not category.exists():
                return Response(json.dumps({'error': 'Invalid category ID'}), status=400, content_type='application/json')

            uom = request.env['uom.uom'].sudo().browse(post.get('uom_id'))
            if not uom.exists():
                return Response(json.dumps({'error': 'Invalid UOM ID'}), status=400, content_type='application/json')

            # Create a new product
            product = request.env['my_product.product'].sudo().create({
                'name': post.get('name'),
                'internal_reference': post.get('internal_reference'),
                'category_id': post.get('category_id'),
                'available_in_pos': post.get('available_in_pos', False),
                'pos_categ_ids': [(6, 0, post.get('pos_categ_ids', []))],
                'detailed_type': post.get('detailed_type', 'consu'),
                'sale_price': post.get('sale_price'),
                'uom_id': post.get('uom_id'),
                'income_account_id': post.get('income_account_id'),
                'image_1920': base64.b64decode(post.get('image_1920')) if post.get('image_1920') else None,  # Handle image decoding
            })
            return Response(json.dumps({'success': True, 'product_id': product.id}), status=201, content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})
        except Exception as e:
            return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')

    # PUT to update an existing product
    @http.route('/api/products/update_product/<int:product_id>', type='json', auth='public', methods=['PUT'], csrf=False)
    def update_product(self, product_id, **post):
        try:
            product = request.env['my_product.product'].sudo().browse(product_id)
            if not product.exists():
                return Response(json.dumps({'error': 'Product not found'}), status=404, content_type='application/json')

            # Update the product with the provided JSON data
            product.write({
                'name': post.get('name'),
                'internal_reference': post.get('internal_reference'),
                'category_id': post.get('category_id'),
                'available_in_pos': post.get('available_in_pos'),
                'pos_categ_ids': [(6, 0, post.get('pos_categ_ids', []))],
                'detailed_type': post.get('detailed_type'),
                'sale_price': post.get('sale_price'),
                'uom_id': post.get('uom_id'),
                'income_account_id': post.get('income_account_id'),
                'image_1920': base64.b64decode(post.get('image_1920')) if post.get('image_1920') else None  # Handle image decoding
            })
            return Response(json.dumps({'success': True}), status=200, content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})
        except Exception as e:
            return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')

    # DELETE to remove an existing product
    @http.route('/api/products/delete_product/<int:product_id>', type='json', auth='public', methods=['DELETE'], csrf=False)
    def delete_product(self, product_id, **kwargs):
        try:
            product = request.env['my_product.product'].sudo().browse(product_id)
            if not product.exists():
                return Response(json.dumps({'error': 'Product not found'}), status=404, content_type='application/json')

            product.unlink()
            return Response(json.dumps({'success': True}), status=200, content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})
        except Exception as e:
            return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')
