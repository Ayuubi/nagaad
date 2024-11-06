from odoo import http
from odoo.http import request, Response
from firebase_admin import credentials, firestore, initialize_app, _apps
import json

# Firebase setup: initialize Firebase app only if it hasn't been initialized
if not _apps:
    cred = credentials.Certificate('/mnt/extra-addons/nagad-f6ebd-firebase-adminsdk-thdw2-8bda9a1d9f.json')
    initialize_app(cred)
db = firestore.client()

class ProductAPIController(http.Controller):
    
    # GET products (either all products or a single product by ID)
    @http.route('/api/products', type='http', auth='public', methods=['GET'], csrf=False)
    def get_products(self, **kwargs):
        try:
            # Initialize the domain for searching products
            domain = []
            product_id = kwargs.get('id')  # Get the 'id' query parameter for a specific product

            if product_id:
                product = request.env['my_product.product'].sudo().browse(int(product_id))
                if not product.exists():
                    return Response(json.dumps({'error': 'Product not found'}), status=404, content_type='application/json')
                
                # Prepare data for that specific product, including image URL
                pos_categories = set(product.pos_categ_ids.mapped('name'))
                product_data = {
                    'id': product.id,
                    'title': product.name,
                    'price': product.sale_price,
                    'Type': list(pos_categories),
                    'image_url': product.image_url  # Add image URL to response
                }
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
                    return Response(json.dumps({'error': 'Invalid price format'}), status=400, content_type='application/json')

            if product_types:
                # Split the types by comma and create a domain condition for each type
                types_list = [ptype.strip() for ptype in product_types.split(',')]
                domain.append(('pos_categ_ids.name', 'in', types_list))  # Search by multiple types

            products = request.env['my_product.product'].sudo().search(domain)
            products_data = []
            all_types = set()  # Initialize an empty set to store unique types across all products

            for product in products:
                pos_categories = set(product.pos_categ_ids.mapped('name'))  # Using a set to automatically remove duplicates
                all_types.update(pos_categories)  # Add product types to the overall set of types

                products_data.append({
                    'id': product.id,
                    'title': product.name,  # 'name' field from your model
                    'price': product.sale_price,  # 'sale_price' from your model
                    'Type': list(pos_categories),  # Convert set to list for JSON serialization
                    'image_url': product.image_url  # Add image URL to each product in the list
                })

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
            return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')

    # Route to save all products to Firebase in the required format
    class ProductAPIController(http.Controller):
    
    @http.route('/api/save_all_products_to_firebase', type='json', auth='public', methods=['POST'], csrf=False)
    def save_all_products_to_firebase(self, **kwargs):
        try:
            # Fetch all products from Odoo's product.product model
            products = request.env['product.product'].sudo().search([('available_in_pos', '=', True)])
            products_data = []

            # Iterate over each product to prepare and save it to Firebase
            for product in products:
                # Get product POS category
                pos_categories = [product.pos_categ_id.name] if product.pos_categ_id else []
                transformed_data = {
                    'id': product.id,
                    'description': product.name,
                    'name': product.name,
                    'image': product.image_url,
                    'price': product.lst_price,
                    'type': pos_categories,
                    'url': product.image_url
                }

                # Save the transformed product data to the 'menu' collection in Firebase
                db.collection('menu').document(str(product.id)).set(transformed_data)
                products_data.append(transformed_data)

            # Return a success response with a list of all products saved to Firebase
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
            return Response(
                json.dumps({'error': str(e)}),
                status=500,
                content_type='application/json'
            )
