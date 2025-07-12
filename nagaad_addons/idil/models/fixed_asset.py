from odoo import models, fields, api
from odoo.exceptions import ValidationError


class IdilFixedAsset(models.Model):
    _name = "idil.fixed.asset"
    _description = "Fixed Asset"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Asset Name", required=True, tracking=True)
    asset_code = fields.Char(string="Asset Code", tracking=True)
    model = fields.Char(string="Model")
    serial_number = fields.Char(string="Serial Number")
    acquisition_date = fields.Date(string="Date of Acquisition", required=True)
    invoice_reference = fields.Char(string="Invoice / PO Reference")
    supplier_id = fields.Many2one("res.partner", string="Supplier")
    purchase_value = fields.Float(string="Invoice Value", required=True)

    # Asset Category and Depreciation Method
    category_id = fields.Many2one("idil.fixed.asset.category", string="Asset Category", required=True)
    depreciation_method = fields.Selection(related="category_id.depreciation_method", store=True)

    # Accounting Fields
    fixed_asset_account_id = fields.Many2one("account.account", string="Fixed Asset GL Account", required=True)
    accumulated_depreciation_account_id = fields.Many2one("account.account", string="Accumulated Depreciation GL")
    depreciation_expense_account_id = fields.Many2one("account.account", string="Depreciation Expense GL")

    # Depreciation Setup
    useful_life = fields.Integer(string="Useful Life (Months)", required=True)
    salvage_value = fields.Float(string="Salvage Value", default=0.0)
    depreciation_start_date = fields.Date(string="Depreciation Start Date")

    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('sold', 'Sold'),
        ('written_off', 'Written Off'),
    ], default='draft', tracking=True)

    def action_activate_asset(self):
        for asset in self:
            if not asset.depreciation_start_date:
                raise ValidationError("Please set Depreciation Start Date.")
            asset.state = 'active'
class IdilFixedAssetCategory(models.Model):
    _name = "idil.fixed.asset.category"
    _description = "Fixed Asset Category"

    name = fields.Char(string="Category Name", required=True)
    depreciation_method = fields.Selection([
        ('straight_line', 'Straight Line'),
        ('declining_balance', 'Declining Balance')
    ], string="Depreciation Method", required=True)
