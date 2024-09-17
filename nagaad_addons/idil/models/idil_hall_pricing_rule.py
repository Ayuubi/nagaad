from odoo import models, fields, api


class HallPricingRule(models.Model):
    _name = 'idil.hall.pricing.rule'
    _description = 'Hall Pricing Rule'

    rule_name = fields.Char(string='Rule Name', required=True)
    day_of_week = fields.Selection([
        ('0', 'Sunday'),
        ('1', 'Monday'),
        ('2', 'Tuesday'),
        ('3', 'Wednesday'),
        ('4', 'Thursday'),
        ('5', 'Friday'),
        ('6', 'Saturday')
    ], string='Day of the Week', required=True)
    start_time = fields.Datetime(string='Start Time', required=True)
    end_time = fields.Datetime(string='End Time', required=True)
    discount_percentage = fields.Float(string='Discount Percentage', required=True)
    special_conditions = fields.Text(string='Special Conditions')

    @api.constrains('start_time', 'end_time')
    def _check_time(self):
        """ Ensure that the end time is after the start time. """
        for rule in self:
            if rule.start_time >= rule.end_time:
                raise models.ValidationError("End time must be after the start time.")
