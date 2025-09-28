from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ProjectResourceAssignment(models.Model):
    _name = 'idil.project.resource'
    _description = 'Project Resource Assignment'

    # 👇 new field for multi-company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True
    )
    project_id = fields.Many2one('idil.project', string="Project", required=True, ondelete="cascade")
    employee_id = fields.Many2one('hr.employee', string="Employee", required=True)
    role = fields.Char(string="Role in Project")
    equipment = fields.Text(string="Allocated Equipment")
    material = fields.Text(string="Allocated Materials")
    assignment_date = fields.Date(string="Assignment Date", default=fields.Date.today)
