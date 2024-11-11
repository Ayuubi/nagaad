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

    # Route to fetch products (all products or a single product by ID)
    @http.route('/api/products', type='http', auth='public', methods=['GET'], csrf=False)
    def get_products(self, **kwargs):
        try:
            _logger.info("Fetching products from Odoo.")
            # Initialize the domain for searching products
            domain = []
            product_id = kwargs.get('id')  # Get the 'id' query parameter for a specific product

            if product_id:
                product = request.env['product.product'].sudo().browse(int(product_id))
                if not product.exists():
                    _logger.warning(f"Product with ID {product_id} not found.")
                    return Response(json.dumps({'error': 'Product not found'}), status=404, content_type='application/json')
                
                # Prepare data for that specific product, including image URL
                category_name = product.categ_id.name if product.categ_id else "Uncategorized"
                product_data = {
                    'id': product.id,
                    'title': product.name,
                    'price': product.sale_price,
                    'Type': category_name,
                    'image_url': product.image_url  # Add image URL to response
                }
                _logger.info(f"Returning data for product ID {product_id}")
                return Response(json.dumps(product_data), content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})

            # Handle search by various parameters
            title = kwargs.get('title')
            price = kwargs.get('price')
            product_types = kwargs.get('type')  # Now this can accept multiple types

            if title:
                domain.append(('name', 'ilike', title))  # Search by title (case-insensitive)

            if price:
                try:
                    price_value = float(price)  # Convert price to float
                    domain.append(('sale_price', '=', price_value))  # Search by exact price
                except ValueError:
                    _logger.error("Invalid price format provided.")
                    return Response(json.dumps({'error': 'Invalid price format'}), status=400, content_type='application/json')

            if product_types:
                # Split the types by comma and create a domain condition for each type
                types_list = [ptype.strip() for ptype in product_types.split(',')]
                domain.append(('categ_id.name', 'in', types_list))  # Search by multiple types

            products = request.env['product.product'].sudo().search(domain)
            products_data = []
            all_types = set()  # Initialize an empty set to store unique types across all products

            for product in products:
                category_name = product.categ_id.name if product.categ_id else "Uncategorized"
                all_types.add(category_name)

                products_data.append({
                    'id': product.id,
                    'title': product.name,  # 'name' field from your model
                    'price': product.sale_price,  # 'sale_price' from your model
                    'Type': category_name,  # Use category name for type
                    'image_url': product.image_url  # Add image URL to each product in the list
                })

            _logger.info("Returning list of products with unique types.")
            # Return the unique types in the response along with product data
            return Response(
                json.dumps({
                    'products': products_data, 
                    'unique_types': list(all_types),  # Return unique types separately
                    'total': len(products_data)
                }), 
                content_type='application/json', 
                headers={'Access-Control-Allow-Origin': '*'}
            )
        except Exception as e:
            _logger.error(f"Error fetching products: {str(e)}")
            return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')

    # Route to save all products to Firebase in the required format
    @http.route('/api/save_all_products_to_firebase', type='json', auth='public', methods=['POST'], csrf=False)
    def save_all_products_to_firebase(self, **kwargs):
        try:
            _logger.info("Starting to fetch products from Odoo's product.product model")
            products = request.env['product.product'].sudo().search([('available_in_pos', '=', True)])
            _logger.info(f"Fetched {len(products)} products from Odoo.")

            products_data = []

            for product in products:
                _logger.info(f"Processing product ID: {product.id}")

                # Get product category name
                category_name = product.categ_id.name if product.categ_id else "Uncategorized"
                # Get POS categories for the product
                pos_category_rel_records = request.env['pos.category'].sudo().search([
                    ('product_tmpl_id', '=', product.product_tmpl_id.id)
                ])
            
                pos_category_names = [category.name for category in pos_category_rel_records] if pos_category_rel_records else ["Uncategorized"]

                transformed_data = {
                    'id': product.id,
                    'description': product.name,
                    'name': product.name,
                    'image': product.image_url,
                    'price': product.lst_price,
                    'type': pos_category_names,  # Use a list with the single category name
                    'url': product.image_url
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
