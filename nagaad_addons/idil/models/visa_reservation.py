from odoo import fields, models


class TravelVisaReservation(models.Model):
    _name = "travel.visa.reservation"
    _description = "Visa Reservation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    # Reservation No (manual)
    name = fields.Char(string="Reservation No", required=True, tracking=True)

    # Applicant details
    applicant_name = fields.Char(string="Applicant Name", required=True, tracking=True)
    passport_no = fields.Char(string="Passport No", tracking=True)
    passport_country = fields.Char(string="Issued Passport Country", tracking=True)
    contact_no = fields.Char(string="Contact No", tracking=True)

    # Visa details
    destination_country = fields.Char(string="Destination Country", tracking=True)
    visa_type = fields.Selection(
        [("tourist", "Tourist"), ("business", "Business"),
         ("student", "Student"), ("work", "Work")],
        string="Visa Type", default="tourist", tracking=True
    )
    visa_duration = fields.Char(string="Visa Duration", help="e.g., 30 days, 6 months", tracking=True)
    application_date = fields.Date(string="Application Date", tracking=True)
    visa_expiry_date = fields.Date(string="Visa Expiry Date", tracking=True)

    status = fields.Selection(
        [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
        string="Status", default="pending", tracking=True
    )

    # Fees & agency
    visa_fee = fields.Float(string="Visa Fee (USD)", tracking=True)
    agency_id = fields.Many2one("res.partner", string="Company/Agency Name", tracking=True)

    # Notes & attachment
    remarks = fields.Text(string="Remarks / Notes")
    attachment_file = fields.Binary(string="Attachment")
    attachment_filename = fields.Char(string="Attachment Filename")
