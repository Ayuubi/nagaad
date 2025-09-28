from odoo import api, models, fields


class UnitMeasure(models.Model):
    _name = 'idil.unit.measure'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Unit of Measure'

    name = fields.Char(string='Name', required=True, tracking=True)
    description = fields.Char(string='Description', tracking=True)
    is_base_uom = fields.Boolean(string='Is Base UOM', default=False, tracking=True)
    related_uom_ids = fields.One2many(
        'idil.unit.measure.relation',
        'base_uom_id',
        string='Related UOMs'
    )


class UnitMeasureRelation(models.Model):
    _name = 'idil.unit.measure.relation'
    _description = 'Unit of Measure Relation'

    base_uom_id = fields.Many2one('idil.unit.measure', string='Base UOM', required=True, ondelete='cascade')
    related_uom_id = fields.Many2one('idil.unit.measure', string='Related UOM', required=True, ondelete='cascade')
    conversion_factor = fields.Float(
        string='Conversion Factor',
        required=True,
        help='Factor to convert the related UOM to the base UOM'
    )
