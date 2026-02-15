from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class NagaadPosData(http.Controller):

    @http.route('/nagaad/api/get_pos_data', type='json', auth='public', csrf=False)
    def get_pos_data(self, **kwargs):
        """
        OPTIMIZED: Uses SQL/read_group to count categories instead of load all products.
        """
        try:
            # 1. Fetch Customers
            customers = request.env['idil.customer.registration'].sudo().search_read(
                [], ['id', 'name'], limit=20000
            )

            # 2. Optimized Category Counting
            Product = request.env['my_product.product'].sudo()
            domain = [('available_in_pos', '=', True)]
            
            # Group by category to get counts efficiently
            # We assume 'pos_categ_ids' is the field linking product to POS category
            # This returns [{'pos_categ_ids': (id, name), 'pos_categ_ids_count': X}, ...]
            groups = Product.read_group(domain, ['pos_categ_ids'], ['pos_categ_ids'])
            
            categories = []
            for g in groups:
                if g['pos_categ_ids']:
                    # read_group returns (id, name) tuple for m2o/m2m grouped fields
                    cat_id = g['pos_categ_ids'][0]
                    cat_name = g['pos_categ_ids'][1]
                    count = g['pos_categ_ids_count']
                    
                    categories.append({
                        'id': cat_id,
                        'name': cat_name,
                        'count': count
                    })

            categories.sort(key=lambda x: x['name'])

            return {
                'status': 'success',
                'customers': customers,
                'categories': categories
            }
        except Exception as e:
            _logger.error("POS API Error: %s", str(e))
            return {'status': 'error', 'message': str(e)}

    @http.route('/nagaad/api/get_products', type='json', auth='public', csrf=False)
    def get_products(self, category_id=None, last_sync=None, limit=None, offset=0, **kwargs):
        """
        Updated to support Delta Sync (last_sync) and Pagination.
        """
        try:
            domain = [('available_in_pos', '=', True)]
            
            if category_id:
                domain.append(('pos_categ_ids', 'in', [int(category_id)]))
            
            # Delta Sync: Only fetch products modified since last_sync
            if last_sync:
                # expecting ISO format or similar, but simplified here
                domain.append(('write_date', '>', last_sync))

            limit_val = int(limit) if limit else None
            offset_val = int(offset) if offset else 0

            # Optimizing: Fetch smaller image if available, else standard
            # Assuming 'image_1920' is heavy, check if 'image_128' or 'image_256' exists in model
            # For now keeping per user request: image_1920
            fields = ['id', 'name', 'pos_categ_ids', 'sale_price', 'image_1920', 'write_date']
            
            products = request.env['my_product.product'].sudo().search_read(
                domain,
                fields,
                order='name asc',
                limit=limit_val,
                offset=offset_val
            )

            return {
                'status': 'success', 
                'products': products,
                'count': len(products)
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
