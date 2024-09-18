from odoo import models, fields, api
from odoo.exceptions import ValidationError


class HallSchedule(models.Model):
    _name = 'idil.hall.schedule'
    _description = 'Hall Schedule'

    hall_id = fields.Many2one('idil.hall', string='Hall', required=True)
    start_time = fields.Datetime(string='Start Time', required=True)
    end_time = fields.Datetime(string='End Time', required=True)
    status = fields.Selection([
        ('available', 'Available'),
        ('maintenance', 'Maintenance')
    ], string='Status', default='available')

    @api.constrains('start_time', 'end_time', 'status')
    def _check_time(self):
        """ Ensure that the end time is after the start time when status is 'maintenance'. """
        for schedule in self:
            if schedule.status == 'maintenance' and schedule.start_time and schedule.end_time:
                if schedule.start_time >= schedule.end_time:
                    raise ValidationError("End time must be after the start time for maintenance.")

    @api.model
    def create(self, vals):
        """ Create the schedule and update the hall availability if the status is 'available'. """
        # Call the original create method to create the schedule
        schedule = super(HallSchedule, self).create(vals)

        # If the status is 'available', update the hall's availability
        if schedule.status == 'available':
            schedule.hall_id.availability = 'available'

        if schedule.status == 'maintenance':
            schedule.hall_id.availability = 'maintenance'
        return schedule

    @api.model
    def write(self, vals):
        """ Ensure that when the status is set to 'available',
        the corresponding hall's availability is also updated. """
        result = super(HallSchedule, self).write(vals)
        for schedule in self:
            if vals.get('status') == 'available':
                schedule.hall_id.availability = 'available'

            if schedule.status == 'maintenance':
                schedule.hall_id.availability = 'maintenance'
        return result
