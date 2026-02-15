import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class NagaadOrder(http.Controller):

    # @http.route('/nagaad/api/submit_order', type='json', auth='public', csrf=False, cors='*')
    def submit_order(self, order_data, **kwargs):
        _logger.info("Received Order Submission: %s (Company ID: %s)", order_data, order_data.get('company_id'))
        try:
            # -------------------------
            # 1) Decide the REAL user
            # -------------------------
            # Option A: take from payload (recommended if your app sends it)
            real_uid = order_data.get('user_id')

            # Option B: fallback to waiter_id (works for your case)
            if not real_uid:
                real_uid = order_data.get('waiter_id')

            if not real_uid:
                return {'status': 'error', 'message': 'Missing user_id / waiter_id'}

            real_uid = int(real_uid)

            # -------------------------
            # 2) Determine company
            # -------------------------
            cid = order_data.get('company_id')

            if not cid:
                waiter = request.env['res.users'].sudo().browse(real_uid)
                if waiter.exists():
                    cid = waiter.company_id.id

            cid = int(cid or request.env.company.id)

            # -------------------------
            # 3) Build lines
            # -------------------------
            lines = []
            for line in (order_data.get('order_lines') or []):
                lines.append((0, 0, {
                    'product_id': line.get('product_id'),
                    'quantity': line.get('quantity'),
                    'sale_price': line.get('sale_price'),
                    'menu_id': line.get('menu_id'),
                    'menu_name': line.get('menu_name'),
                    'status': 'normal',
                    'kitchen_printed_qty': 0.0,
                }))

            # -------------------------
            # 4) Create as REAL user (NO sudo)
            # -------------------------
            vals = {
                'customer_id': order_data.get('customer_id'),
                'waiter_id': order_data.get('waiter_id'),
                'order_mode': order_data.get('order_mode'),
                'table_no': order_data.get('table_no'),
                'company_id': cid,
                'order_lines': lines,  # ✅ fixed key
            }

            _logger.info("🚀 Creating Order as UID=%s in Company=%s (Vals: %s)", real_uid, cid, vals)

            OrderModel = (
                request.env['idil.customer.place.order']
                .with_user(real_uid)  # ✅ makes create_uid = real_uid
                .with_company(cid)
                .with_context(allowed_company_ids=[cid], force_company=cid)
            )

            res = OrderModel.create(vals)

            _logger.info("✅ Order Created: ID=%s, Company=%s, create_uid=%s", res.id, cid, real_uid)
            return {'status': 'success', 'order_id': res.id}

        except Exception as e:
            _logger.exception("Submit Order Error")
            return {'status': 'error', 'message': str(e)}
