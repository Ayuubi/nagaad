from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ProjectSchedule(models.Model):
    _name = 'idil.project.schedule'
    _description = 'Project Schedule'

    project_id = fields.Many2one('idil.project', string="Project", required=True, ondelete="cascade")
    activity_name = fields.Char(string="Activity", required=True)
    start_date = fields.Date(string="Start Date", required=True)
    end_date = fields.Date(string="End Date", required=True)
    responsible_id = fields.Many2one('res.users', string="Responsible")

    @api.constrains('start_date', 'end_date')
    def _check_schedule_dates(self):
        for rec in self:
            if rec.start_date > rec.end_date:
                raise ValidationError("Schedule end date must be after the start date.")
