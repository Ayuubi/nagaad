from odoo import models, fields, api
from odoo.exceptions import ValidationError


class Project(models.Model):
    _name = 'idil.project'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Project Management'

    name = fields.Char(string="Project Name", required=True, tracking=True)
    code = fields.Char(string="Project Code", required=True, copy=False, tracking=True)
    client_id = fields.Many2one('idil.customer.registration', string="Client", tracking=True)
    location = fields.Char(string="Location")
    category = fields.Selection([
        ('construction', 'Construction'),
        ('it', 'IT'),
        ('manufacturing', 'Manufacturing'),
        ('other', 'Other'),
    ], string="Category", tracking=True)

    start_date = fields.Date(string="Start Date", tracking=True)
    end_date = fields.Date(string="End Date", tracking=True)

    project_amount = fields.Monetary(string="Project Amount", tracking=True)
    total_cost = fields.Monetary(string="Total Cost Estimate", tracking=True)
    estimated_profit = fields.Monetary(
        string="Estimated Revenue",
        compute="_compute_estimated_profit",
        store=True,
        tracking=True
    )
    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  default=lambda self: self.env.company.currency_id)

    status = fields.Selection([
        ('draft', 'Draft'),
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', string="Status", tracking=True)

    project_manager_id = fields.Many2one('res.users', string="Project Manager", tracking=True)
    description = fields.Text(string="Project Description")

    charter_file = fields.Binary(string="Project Charter")
    charter_filename = fields.Char(string="Filename")

    profit_account_id = fields.Many2one('idil.chart.account', string='Revenue Account',
                                        domain="[('code', 'like', '4%'), "
                                               "('currency_id', '=', currency_id)]", required=True, tracking=True)
    cost_account_id = fields.Many2one('idil.chart.account', string='Cost Account',
                                      domain="[('code', 'like', '5%'), "
                                             "('currency_id', '=', currency_id)]", required=True)
    payment_ids = fields.One2many('idil.project.payment', 'project_id', string='Payments')

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.start_date > rec.end_date:
                raise ValidationError("End Date cannot be earlier than Start Date.")

    @api.depends('project_amount', 'total_cost')
    def _compute_estimated_profit(self):
        for rec in self:
            rec.estimated_profit = (rec.project_amount or 0.0) - (rec.total_cost or 0.0)
