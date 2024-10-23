from odoo import http
from odoo.http import request, Response
import json
import base64

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
                
                # Prepare data for that specific product
                pos_categories = set(product.pos_categ_ids.mapped('name'))
                product_data = {
                    'id': product.id,
                    'title': product.name,
                    'price': product.sale_price,
                    'category': product.category_id.name if product.category_id else '',
                    'Type': list(pos_categories),
                    'available_in_pos': product.available_in_pos,
                    'uom': product.uom_id.name if product.uom_id else ''
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
                    'category': product.category_id.name if product.category_id else '',  # 'category_id' from your model
                    'available_in_pos': product.available_in_pos,  # 'available_in_pos' from your model
                    'uom': product.uom_id.name if product.uom_id else ''  # 'uom_id' field from your model
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
