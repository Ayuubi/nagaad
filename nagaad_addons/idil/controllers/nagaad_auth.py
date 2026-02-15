from odoo import http, fields
from odoo.http import request
import logging
import json

_logger = logging.getLogger(__name__)

class NagaadAuth(http.Controller):

    @http.route('/nagaad/api/get_users_by_company', type='json', auth='none', csrf=False, cors='*')
    def get_users_by_company(self, company_id=None, **kwargs):
        try:
           domain = []
           if company_id:
               domain = [('company_ids', 'in', [int(company_id)])]
           
           users = request.env['res.users'].sudo().search_read(
               domain,
               ['id', 'name', 'login', 'image_1920'],
               order='name asc'
           )
           return {'status': 'success', 'users': users}
        except Exception as e:
           return {'status': 'error', 'message': str(e)}

    @http.route('/nagaad/api/login', type='json', auth='none', csrf=False, cors='*')
    def login(self, db, login, password, **kwargs):
        _logger.warning("🔐 LOGIN ATTEMPT: db=%s login=%s", db, login)
        try:
            request.session.authenticate(db, login, password)
            uid = request.session.uid
            session_id = request.session.sid
            
            _logger.warning("✅ LOGIN SUCCESS: uid=%s db=%s", uid, getattr(request.session, 'db', 'NONE'))
            user = request.env['res.users'].sudo().browse(uid)
            
            # Get allowed companies
            companies = []
            for c in user.company_ids:
                companies.append({
                    'id': c.id,
                    'name': c.name,
                    'currency_id': [c.currency_id.id, c.currency_id.name]
                })

            return {
                'status': 'success',
                'uid': uid,
                'session_id': session_id,
                'name': user.name,
                'username': user.login,
                'company_id': user.company_id.id,
                'company_name': user.company_id.name,
                'companies': companies,
                'image_1920': user.image_1920,
            }
        except Exception as e:
            import traceback
            _logger.error("❌ Login Fail TRACEBACK: %s\n%s", str(e), traceback.format_exc())
            return {'status': 'error', 'message': str(e)}

    @http.route('/nagaad/api/register_device', type='json', auth='public', csrf=False, cors='*')
    def register_device(self, device_data, **kwargs):
        _logger.info("📱 Register Device Called. Data: %s", device_data)
        try:
            Device = request.env['idil.mobile.device'].sudo()
            # Use explicit user_id from payload if provided (robustness), else fallback to session uid
            uid = device_data.get('user_id') or request.uid
            
            # If public user (None or public ID), abort logging
            if not uid:
                 return {'status': 'error', 'message': 'Missing user_id for registration'}
            
            d_id = device_data.get('device_id')
            if not d_id:
                return {'status': 'error', 'message': 'Device ID required'}

            vals = {
                'name': device_data.get('name'),
                'device_id': d_id,
                'platform': device_data.get('platform'),
                'app_version': device_data.get('app_version'),
                'last_lat': device_data.get('lat'),
                'last_long': device_data.get('long'),
                'ip_address': request.httprequest.remote_addr,
                'user_id': int(uid),
                'last_login': fields.Datetime.now(),
            }

            existing = Device.search([('device_id', '=', d_id)], limit=1)
            
            log_vals = {
                'user_id': int(uid),
                'ip_address': request.httprequest.remote_addr,
                'lat': device_data.get('lat'),
                'long': device_data.get('long'),
                'platform': device_data.get('platform'),
                'app_version': device_data.get('app_version'),
                'login_time': fields.Datetime.now()
            }

            if existing:
                if existing.state == 'blocked':
                    return {'status': 'error', 'message': 'This device has been blocked by admin.'}
                
                vals['login_count'] = existing.login_count + 1
                existing.write(vals)
                log_vals['device_ref_id'] = existing.id
                _logger.info("Creating Log for Existing Device: %s", log_vals)
                request.env['idil.mobile.device.log'].sudo().create(log_vals)
                return {'status': 'success', 'message': 'Device updated'}
            else:
                vals['device_id'] = device_data.get('device_id')
                vals['login_count'] = 1
                new_device = Device.create(vals)
                log_vals['device_ref_id'] = new_device.id
                _logger.info("Creating Log for New Device: %s", log_vals)
                request.env['idil.mobile.device.log'].sudo().create(log_vals)
                return {'status': 'success', 'message': 'Device registered'}

        except Exception as e:
            _logger.error("Device Register Error: %s", str(e))
            return {'status': 'error', 'message': str(e)}
