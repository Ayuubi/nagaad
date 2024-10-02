from odoo import http
from odoo.http import request, Response

class ItemAPIController(http.Controller):

    @http.route('/api/items', type='json', auth='public', methods=['GET'], csrf=False)
    def get_items(self, **kwargs):
        """Fetch all items"""
        items = request.env['idil.item'].sudo().search([])
        item_data = items.read(['name', 'description', 'quantity', 'cost_price', 'purchase_date'])
        return {'status': 200, 'items': item_data}

    @http.route('/api/items/<int:item_id>', type='json', auth='public', methods=['GET'], csrf=False)
    def get_item(self, item_id, **kwargs):
        """Fetch a single item by ID"""
        item = request.env['idil.item'].sudo().browse(item_id)
        if not item.exists():
            return {'status': 404, 'message': 'Item not found'}
        item_data = item.read(['name', 'description', 'quantity', 'cost_price', 'purchase_date'])[0]
        return {'status': 200, 'item': item_data}

    @http.route('/api/items', type='json', auth='public', methods=['POST'], csrf=False)
    def create_item(self, **kwargs):
        """Create a new item"""
        try:
            item_data = {
                'name': kwargs.get('name'),
                'description': kwargs.get('description'),
                'quantity': kwargs.get('quantity'),
                'cost_price': kwargs.get('cost_price'),
                'purchase_date': kwargs.get('purchase_date'),
                'expiration_date': kwargs.get('expiration_date'),
                'item_category_id': kwargs.get('item_category_id'),
                'unitmeasure_id': kwargs.get('unitmeasure_id'),
                'min': kwargs.get('min'),
                'purchase_account_id': kwargs.get('purchase_account_id'),
                'asset_account_id': kwargs.get('asset_account_id'),
            }
            new_item = request.env['idil.item'].sudo().create(item_data)
            return {'status': 201, 'message': 'Item created', 'item_id': new_item.id}
        except Exception as e:
            return {'status': 400, 'message': str(e)}

    @http.route('/api/items/<int:item_id>', type='json', auth='public', methods=['PUT'], csrf=False)
    def update_item(self, item_id, **kwargs):
        """Update an existing item"""
        item = request.env['idil.item'].sudo().browse(item_id)
        if not item.exists():
            return {'status': 404, 'message': 'Item not found'}
        try:
            item_data = {
                'name': kwargs.get('name'),
                'description': kwargs.get('description'),
                'quantity': kwargs.get('quantity'),
                'cost_price': kwargs.get('cost_price'),
                'purchase_date': kwargs.get('purchase_date'),
                'expiration_date': kwargs.get('expiration_date'),
                'item_category_id': kwargs.get('item_category_id'),
                'unitmeasure_id': kwargs.get('unitmeasure_id'),
                'min': kwargs.get('min'),
                'purchase_account_id': kwargs.get('purchase_account_id'),
                'asset_account_id': kwargs.get('asset_account_id'),
            }
            item.sudo().write(item_data)
            return {'status': 200, 'message': 'Item updated'}
        except Exception as e:
            return {'status': 400, 'message': str(e)}

    @http.route('/api/items/<int:item_id>', type='json', auth='public', methods=['DELETE'], csrf=False)
    def delete_item(self, item_id, **kwargs):
        """Delete an item"""
        item = request.env['idil.item'].sudo().browse(item_id)
        if not item.exists():
            return {'status': 404, 'message': 'Item not found'}
        try:
            item.sudo().unlink()
            return {'status': 200, 'message': 'Item deleted'}
        except Exception as e:
            return {'status': 400, 'message': str(e)}
