from odoo import models, fields


class MobileDevice(models.Model):
    _name = 'idil.mobile.device'
    _description = 'Registered Mobile Devices'
    _order = 'last_login desc'

    name = fields.Char(string='Device Name', required=True)
    device_id = fields.Char(string='Device ID', required=True, index=True, help="Unique hardware ID")
    user_id = fields.Many2one('res.users', string='Last User')
    ip_address = fields.Char(string='Last IP Address')
    platform = fields.Char(string='Platform', help="e.g. Android 13")
    app_version = fields.Char(string='App Version')
    last_login = fields.Datetime(string='Last Activity', default=fields.Datetime.now)
    
    login_count = fields.Integer(string='Login Count', default=0)
    last_lat = fields.Char(string='Latitude')
    last_long = fields.Char(string='Longitude')
    
    state = fields.Selection([
        ('allowed', 'Allowed'),
        ('blocked', 'Blocked')
    ], string='Status', default='allowed', required=True)

    log_ids = fields.One2many('idil.mobile.device.log', 'device_ref_id', string='Login History')

    _sql_constraints = [
        ('unique_device_id', 'unique(device_id)', 'This device is already registered.')
    ]

    def action_block(self):
        self.state = 'blocked'

    def action_allow(self):
        self.state = 'allowed'


class MobileDeviceLog(models.Model):
    _name = 'idil.mobile.device.log'
    _description = 'Device Login Audit'
    _order = 'login_time desc'

    device_ref_id = fields.Many2one('idil.mobile.device', string='Device', ondelete='cascade', required=True)
    user_id = fields.Many2one('res.users', string='User', required=True)
    login_time = fields.Datetime(string='Login Time', default=fields.Datetime.now, required=True)
    ip_address = fields.Char(string='IP Address')
    lat = fields.Char(string='Latitude')
    long = fields.Char(string='Longitude')
    platform = fields.Char(string='Platform')
    app_version = fields.Char(string='App Version')

    map_link = fields.Char(string="Google Map", compute="_compute_map_link")

    def _compute_map_link(self):
        for record in self:
            if record.lat and record.long:
                record.map_link = f"https://www.google.com/maps?q={record.lat},{record.long}"
            else:
                record.map_link = False
