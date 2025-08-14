from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ProjectTask(models.Model):
    _name = 'idil.project.task'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Project Task'

    name = fields.Char(string="Task Name", required=True, tracking=True)
    project_id = fields.Many2one('idil.project', string="Project", required=True, ondelete="cascade", tracking=True)
    parent_task_id = fields.Many2one('idil.project.task', string="Parent Task", tracking=True)
    milestone = fields.Boolean(string="Is Milestone?", tracking=True)
    start_date = fields.Date(string="Start Date", tracking=True)
    end_date = fields.Date(string="End Date", tracking=True)
    assigned_to = fields.Many2one('res.users', string="Assigned To", tracking=True)
    status = fields.Selection([
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('done', 'Done')
    ], string="Status", default="not_started", tracking=True)
    description = fields.Text(string="Description", tracking=True)

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.start_date > rec.end_date:
                raise ValidationError("End Date cannot be earlier than Start Date.")

    def set_to_in_progress(self):
        for task in self:
            task.status = 'in_progress'

    def set_to_done(self):
        for task in self:
            task.status = 'done'
