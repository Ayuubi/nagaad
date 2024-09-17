from odoo import models, fields


class HallPayment(models.Model):
    _name = 'idil.hall.payment'
    _description = 'Hall Booking Payment'

    booking_id = fields.Many2one('idil.hall.booking', string='Hall Booking', required=True)
    payment_date = fields.Datetime(string='Payment Date', default=fields.Datetime.now, required=True)
    amount = fields.Float(string='Amount Paid', required=True)
    payment_status = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('partial', 'Partial'),
        ('paid', 'Paid'),
    ], string='Payment Status', default='unpaid')

    def action_set_paid(self):
        """ Set the payment status to Paid """
        self.payment_status = 'paid'

    def action_set_partial(self):
        """ Set the payment status to Partial """
        self.payment_status = 'partial'
