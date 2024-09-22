from odoo import http
from odoo.http import request, Response
import json


class ItemAPIController(http.Controller):

    # GET all items
    @http.route('/api/items/get_items', type='http', auth='public', methods=['GET'], csrf=False)
    def get_items(self, **kwargs):
        try:
            items = request.env['idil.item'].sudo().search([])
            items_data = []
            for item in items:
                items_data.append({
                    'id': item.id,
                    'name': item.name,
                    'description': item.description,
                    'item_type': item.item_type,
                    'quantity': item.quantity,
                    'purchase_date': item.purchase_date.strftime('%Y-%m-%d') if item.purchase_date else None,
                    'expiration_date': item.expiration_date.strftime('%Y-%m-%d') if item.expiration_date else None,
                    'cost_price': item.cost_price,
                    'total_price': item.total_price,
                    'days_until_expiration': item.days_until_expiration,
                })
            return Response(json.dumps(items_data), content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})
        except Exception as e:
            return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')

    # GET single item by ID
    @http.route('/api/items/get_item/<int:item_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def get_item(self, item_id, **kwargs):
        try:
            item = request.env['idil.item'].sudo().browse(item_id)
            if not item.exists():
                return Response(json.dumps({'error': 'Item not found'}), status=404, content_type='application/json')

            item_data = {
                'id': item.id,
                'name': item.name,
                'description': item.description,
                'item_type': item.item_type,
                'quantity': item.quantity,
                'purchase_date': item.purchase_date.strftime('%Y-%m-%d') if item.purchase_date else None,
                'expiration_date': item.expiration_date.strftime('%Y-%m-%d') if item.expiration_date else None,
                'cost_price': item.cost_price,
                'total_price': item.total_price,
                'days_until_expiration': item.days_until_expiration,
            }
            return Response(json.dumps(item_data), content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})
        except Exception as e:
            return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')

    # POST to create a new item
    @http.route('/api/items/create_item', type='json', auth='public', methods=['POST'], csrf=False)
    def create_item(self, **post):
        try:
            # Validate mandatory fields
            required_fields = ['name', 'item_type', 'quantity', 'purchase_date', 'expiration_date', 'cost_price',
                               'item_category_id', 'unitmeasure_id', 'min', 'purchase_account_id', 'asset_account_id']
            missing_fields = [field for field in required_fields if field not in post]
            if missing_fields:
                return Response(json.dumps({'error': f'Missing required fields: {", ".join(missing_fields)}'}), status=400, content_type='application/json')

            # Validate foreign key relations
            category = request.env['idil.item.category'].sudo().browse(post.get('item_category_id'))
            if not category.exists():
                return Response(json.dumps({'error': 'Invalid item category ID'}), status=400, content_type='application/json')

            purchase_account = request.env['idil.chart.account'].sudo().browse(post.get('purchase_account_id'))
            if not purchase_account.exists():
                return Response(json.dumps({'error': 'Invalid purchase account ID'}), status=400, content_type='application/json')

            asset_account = request.env['idil.chart.account'].sudo().browse(post.get('asset_account_id'))
            if not asset_account.exists():
                return Response(json.dumps({'error': 'Invalid asset account ID'}), status=400, content_type='application/json')

            # Create a new item
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
            return Response(json.dumps({'success': True, 'item_id': item.id}), status=201, content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})
        except Exception as e:
            return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')

    # PUT to update an existing item
    @http.route('/api/items/update_item/<int:item_id>', type='json', auth='public', methods=['PUT'], csrf=False)
    def update_item(self, item_id, **post):
        try:
            item = request.env['idil.item'].sudo().browse(item_id)
            if not item.exists():
                return Response(json.dumps({'error': 'Item not found'}), status=404, content_type='application/json')

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
            return Response(json.dumps({'success': True}), status=200, content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})
        except Exception as e:
            return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')

    # DELETE to remove an existing item
    @http.route('/api/items/delete_item/<int:item_id>', type='json', auth='public', methods=['DELETE'], csrf=False)
    def delete_item(self, item_id, **kwargs):
        try:
            item = request.env['idil.item'].sudo().browse(item_id)
            if not item.exists():
                return Response(json.dumps({'error': 'Item not found'}), status=404, content_type='application/json')

            item.unlink()
            return Response(json.dumps({'success': True}), status=200, content_type='application/json', headers={'Access-Control-Allow-Origin': '*'})
        except Exception as e:
            return Response(json.dumps({'error': str(e)}), status=500, content_type='application/json')
