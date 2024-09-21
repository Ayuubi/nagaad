from odoo import http
from odoo.http import request, Response
import json


class ItemAPIController(http.Controller):

    # GET all items
    @http.route('/api/items', type='http', auth='public', methods=['GET'], csrf=False)
    def get_items(self, **kwargs):
        items = request.env['idil.item'].sudo().search([])
        items_data = []
        for item in items:
            items_data.append({
                'id': item.id,
                'name': item.name,
                'description': item.description,
                'item_type': item.item_type,
                'quantity': item.quantity,
                'purchase_date': item.purchase_date,
                'expiration_date': item.expiration_date,
                'cost_price': item.cost_price,
                'total_price': item.total_price,
                'days_until_expiration': item.days_until_expiration,
            })
        return Response(json.dumps(items_data), content_type='application/json')

    # GET single item by ID
    @http.route('/api/items/<int:item_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def get_item(self, item_id, **kwargs):
        item = request.env['idil.item'].sudo().browse(item_id)
        if not item:
            return Response(json.dumps({'error': 'Item not found'}), status=404, content_type='application/json')
        
        item_data = {
            'id': item.id,
            'name': item.name,
            'description': item.description,
            'item_type': item.item_type,
            'quantity': item.quantity,
            'purchase_date': item.purchase_date,
            'expiration_date': item.expiration_date,
            'cost_price': item.cost_price,
            'total_price': item.total_price,
            'days_until_expiration': item.days_until_expiration,
        }
        return Response(json.dumps(item_data), content_type='application/json')

    # POST to create a new item
    @http.route('/api/items', type='json', auth='public', methods=['POST'], csrf=False)
    def create_item(self, **post):
        try:
            # Create a new item using the provided JSON data
            item = request.env['idil.item'].sudo().create({
                'name': post.get('name'),
                'description': post.get('description'),
                'item_type': post.get('item_type'),
                'quantity': post.get('quantity'),
                'purchase_date': post.get('purchase_date'),
                'expiration_date': post.get('expiration_date'),
                'cost_price': post.get('cost_price'),
                'item_category_id': post.get('item_category_id'),
                'unitmeasure_id': post.get('unitmeasure_id'),
                'min': post.get('min'),
                'purchase_account_id': post.get('purchase_account_id'),
                'asset_account_id': post.get('asset_account_id'),
            })
            return json.dumps({'success': True, 'item_id': item.id})
        except Exception as e:
            return json.dumps({'error': str(e)})

    # PUT to update an existing item
    @http.route('/api/items/<int:item_id>', type='json', auth='public', methods=['PUT'], csrf=False)
    def update_item(self, item_id, **post):
        item = request.env['idil.item'].sudo().browse(item_id)
        if not item:
            return json.dumps({'error': 'Item not found'})
        
        try:
            # Update the item with the provided JSON data
            item.write({
                'name': post.get('name'),
                'description': post.get('description'),
                'item_type': post.get('item_type'),
                'quantity': post.get('quantity'),
                'purchase_date': post.get('purchase_date'),
                'expiration_date': post.get('expiration_date'),
                'cost_price': post.get('cost_price'),
                'item_category_id': post.get('item_category_id'),
                'unitmeasure_id': post.get('unitmeasure_id'),
                'min': post.get('min'),
                'purchase_account_id': post.get('purchase_account_id'),
                'asset_account_id': post.get('asset_account_id'),
            })
            return json.dumps({'success': True})
        except Exception as e:
            return json.dumps({'error': str(e)})

    # DELETE to remove an existing item
    @http.route('/api/items/<int:item_id>', type='json', auth='public', methods=['DELETE'], csrf=False)
    def delete_item(self, item_id, **kwargs):
        item = request.env['idil.item'].sudo().browse(item_id)
        if not item:
            return json.dumps({'error': 'Item not found'})
        
        try:
            item.unlink()
            return json.dumps({'success': True})
        except Exception as e:
            return json.dumps({'error': str(e)})


