from odoo import http
from odoo.http import request, Response
from firebase_admin import credentials, firestore, initialize_app, _apps
import json
import logging

# Setup logging for debugging
_logger = logging.getLogger(__name__)

# Firebase setup: initialize Firebase app only if it hasn't been initialized
if not _apps:
    try:
        _logger.info("Initializing Firebase app with provided credentials.")
        cred = credentials.Certificate('/mnt/extra-addons/nagad-f6ebd-firebase-adminsdk-thdw2-8bda9a1d9f.json')
        initialize_app(cred)
        _logger.info("Firebase app initialized successfully.")
    except Exception as e:
        _logger.error(f"Failed to initialize Firebase: {str(e)}")
db = firestore.client()

class ProductAPIController(http.Controller):

    @http.route('/api/get_all_products_from_odoo', type='http', auth='public', methods=['GET'], csrf=False)
    def get_all_products_from_odoo(self, **kwargs):
        try:
            _logger.info("Starting to fetch products from Odoo's product.product model with filters")

            # Extract filters from query parameters
            product_id = kwargs.get('id')
            name = kwargs.get('name')
            price = kwargs.get('price')
            category = kwargs.get('category')
            product_type = kwargs.get('type')

            # Build search domain
            domain = [('available_in_pos', '=', True)]
            if product_id:
                domain.append(('id', '=', int(product_id)))
            if name:
                domain.append(('name', 'ilike', name))
            if price:
                domain.append(('lst_price', '=', float(price)))
            if category:
                domain.append(('categ_id.name', 'ilike', category))
            # 'type' filter will be applied after querying products

            # Fetch products from Odoo
            products = request.env['product.product'].sudo().search(domain)
            _logger.info(f"Fetched {len(products)} products from Odoo based on filters.")

            products_data = []

            for product in products:
                _logger.info(f"Processing product ID: {product.id}")

                # Get product category name
                category_name = product.categ_id.name if product.categ_id and isinstance(product.categ_id.name, str) else "Uncategorized"

                # Fetch related POS categories using SQL query
                request.cr.execute('''
                    SELECT pc.name->>'en_US'
                    FROM pos_category_product_template_rel pl
                    JOIN pos_category pc ON pc.id = pl.pos_category_id
                    WHERE pl.product_template_id = %s
                ''', (product.product_tmpl_id.id,))
                pos_category_names = [row[0] for row in request.cr.fetchall()]

                # Use the first POS category if available, otherwise fallback to product category
                category_type = pos_category_names[0] if pos_category_names else category_name

                # Apply 'type' filter if specified and skip this product if it doesn't match
                if product_type and product_type != category_type:
                    continue

                transformed_data = {
                    'id': product.id,
                    'description': product.name,
                    'name': product.name,
                    'image': product.image_url,
                    'price': product.lst_price,
                    'type': category_type
                }

                products_data.append(transformed_data)

            _logger.info("Finished fetching products from Odoo.")

            return Response(
                json.dumps({
                    'status': 'success',
                    'message': f'{len(products_data)} products fetched from Odoo',
                    'products': products_data
                }),
                content_type='application/json',
                headers={'Access-Control-Allow-Origin': '*'}
            )

        except Exception as e:
            _logger.error(f"Error fetching products from Odoo: {str(e)}")
            return Response(
                json.dumps({'error': str(e)}),
                status=500,
                content_type='application/json'
            )

    @http.route('/api/save_all_products_to_firebase', type='json', auth='public', methods=['POST'], csrf=False)
    def save_all_products_to_firebase(self, **kwargs):
        try:
            _logger.info("Starting to fetch products from Odoo's product.product model")
            products = request.env['product.product'].sudo().search([('available_in_pos', '=', True)])
            _logger.info(f"Fetched {len(products)} products from Odoo.")

            products_data = []

            for product in products:
                _logger.info(f"Processing product ID: {product.id}")

                # Get product category name as a string
                category_name = product.categ_id.name if product.categ_id and isinstance(product.categ_id.name, str) else "Uncategorized"

                # Fetch related POS categories using SQL query
                request.cr.execute('''
                    SELECT pc.name->>'en_US'
                    FROM pos_category_product_template_rel pl
                    JOIN pos_category pc ON pc.id = pl.pos_category_id
                    WHERE pl.product_template_id = %s
                ''', (product.product_tmpl_id.id,))
                pos_category_names = [row[0] for row in request.cr.fetchall()]

                # Use the first POS category if available, otherwise fallback to product category
                category_type = pos_category_names[0] if pos_category_names else category_name

                transformed_data = {
                    'id': product.id,
                    'description': product.name,
                    'name': product.name,
                    'image': product.image_url,
                    'price': product.lst_price,
                    'type': category_type  # Save only the type value without the locale key
                }

                _logger.info(f"Attempting to save product ID {product.id} to Firebase.")
                db.collection('menu').document(str(product.id)).set(transformed_data)
                _logger.info(f"Successfully saved product ID {product.id} to Firebase.")
                products_data.append(transformed_data)

            _logger.info("Finished saving products to Firebase.")
            return Response(
                json.dumps({
                    'status': 'success',
                    'message': f'{len(products_data)} products saved to Firebase',
                    'products': products_data
                }),
                content_type='application/json',
                headers={'Access-Control-Allow-Origin': '*'}
            )

        except Exception as e:
            _logger.error(f"Error saving products to Firebase: {str(e)}")
            return Response(
                json.dumps({'error': str(e)}),
                status=500,
                content_type='application/json'
            )
