from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class NagaadPosController(http.Controller):

    @http.route('/nagaad/api/ping', type='json', auth='public', csrf=False)
    def ping(self):
        return {'status': 'success', 'message': 'Odoo API is online!'}

    @http.route('/nagaad/api/get_pos_data', type='json', auth='public', csrf=False)
    def get_pos_data(self, **kwargs):
        """
        ROBUST: Fetches master data using manual recordset counting.
        """
        try:
            # 1. Fetch Customers
            customers = request.env['idil.customer.registration'].sudo().search_read(
                [], ['id', 'name'], limit=200
            )

            # 2. Fetch Categories and count them manually (Bypasses read_group errors)
            products = request.env['my_product.product'].sudo().search([('available_in_pos', '=', True)])
            all_cats = products.mapped('pos_categ_ids')

            categories = []
            seen_ids = set()
            for cat in all_cats:
                if cat.id not in seen_ids:
                    # Filter products in memory - very fast in Python
                    count = len(products.filtered(lambda p: cat.id in p.pos_categ_ids.ids))
                    categories.append({
                        'id': cat.id,
                        'name': cat.name,
                        'count': count
                    })
                    seen_ids.add(cat.id)

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
    def get_products(self, category_id=None, **kwargs):
        """
        FIXED: Using 'image_1920' as defined in your model.
        """
        try:
            domain = [('available_in_pos', '=', True)]
            if category_id:
                domain.append(('pos_categ_ids', 'in', [int(category_id)]))

            # We use image_1920 since image_128 doesn't exist on your model
            products = request.env['my_product.product'].sudo().search_read(
                domain,
                ['id', 'name', 'pos_categ_ids', 'sale_price', 'image_1920'],
                order='name asc'
            )

            return {'status': 'success', 'products': products}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    @http.route('/nagaad/api/submit_order', type='json', auth='public', csrf=False)
    def submit_order(self, order_data, **kwargs):
        try:
            lines = []
            for line in order_data.get('order_lines', []):
                lines.append((0, 0, {
                    'product_id': line.get('product_id'),
                    'quantity': line.get('quantity'),
                    'sale_price': line.get('sale_price'),
                    'menu_id': line.get('menu_id'),
                    'menu_name': line.get('menu_name'),
                    'status': 'normal',
                }))

            vals = {
                'customer_id': order_data.get('customer_id'),
                'waiter_id': order_data.get('waiter_id'),
                'order_mode': order_data.get('order_mode'),
                'table_no': order_data.get('table_no'),
                'order_lines': lines,
            }

            res = request.env['idil.customer.place.order'].sudo().create(vals)
            return {'status': 'success', 'order_id': res.id}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}