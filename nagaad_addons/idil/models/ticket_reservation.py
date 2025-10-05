from odoo import api, fields, models, _
from odoo.exceptions import UserError


class TravelTicketReservation(models.Model):
    _name = "travel.ticket.reservation"
    _description = "Travel Ticket Reservation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    # Core fields
    # 👇 new field for multi-company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        domain=lambda self: [('id', 'in', self.env.companies.ids)],  # only allowed companies
        index=True
    )

    name = fields.Char(string="Reservation No", default="New", copy=False, required=True, tracking=True)
    trip_type = fields.Selection(
        [("one_way", "One Way"), ("round_trip", "Round Trip"), ("multi_city", "Multi City")],
        string="Trip Type", default="one_way", required=True, tracking=True
    )

    passenger_name = fields.Char(string="Passenger Name", required=True, tracking=True)
    passport_no = fields.Char(string="Passport No", tracking=True)
    passport_country = fields.Char(string="Issued Passport Country", tracking=True)
    contact_no = fields.Char(string="Contact No", tracking=True)

    airline_id = fields.Many2one("res.partner", string="Company Name (Airline)", tracking=True)
    user_id = fields.Many2one("res.users", string="Sales Person", default=lambda self: self.env.user, tracking=True, )

    from_city = fields.Char(string="From (Departure City)", required=True, tracking=True)
    to_city = fields.Char(string="To (Destination City)", required=True, tracking=True)

    departure_date = fields.Date(string="Departure Date", tracking=True)
    departure_time = fields.Char(string="Departure Time", tracking=True)
    arrival_date = fields.Date(string="Arrival Date", tracking=True)
    arrival_time = fields.Char(string="Arrival Time", tracking=True)

    ticket_type = fields.Selection(
        [("economy", "Economy"), ("business", "Business"), ("first", "First Class")],
        string="Ticket Type", default="economy", tracking=True
    )

    reservation_status = fields.Selection(
        [("confirmed", "Confirmed"), ("pending", "Pending"), ("canceled", "Canceled")],
        string="Reservation Status", default="pending", tracking=True
    )

    screen_status = fields.Selection(
        [("draft", "Draft"), ("approved", "Approved"), ("canceled", "Canceled")],
        string="Screen Status", default="draft", tracking=True
    )

    description = fields.Text(string="Description")
    attachment_file = fields.Binary(string="Attachment")
    attachment_filename = fields.Char(string="Attachment Filename")

    # ---------- Invoicing fields ----------
    customer_id = fields.Many2one(
        "idil.customer.registration", string="Customer", required=True,
        domain=lambda self: [('company_id', 'in', self.env.companies.ids)]
    )

    product_id = fields.Many2one("my_product.product", string="Product",
                                 help="Service product used in the invoice line (must have an income account).",
                                 domain=lambda self: [('company_id', 'in', self.env.companies.ids)])
    currency_id = fields.Many2one(
        "res.currency", string="Currency",
        default=lambda self: self.env.company.currency_id, required=True
    )
    ticket_fee = fields.Monetary(string="Ticket Fee", currency_field="currency_id", tracking=True)

    invoice_id = fields.Many2one("idil.invoice", string="Invoice", readonly=True, copy=False)
    invoice_state = fields.Selection(
        [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")],
        string="Invoice Status",
        readonly=True,
        compute="_compute_invoice_state",
        store=False,
    )

    # ---------- Sequencing ----------
    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("travel.ticket.reservation") or "New"
        return super().create(vals)

    # ---------- Status actions ----------
    def action_approve(self):
        self.write({"screen_status": "approved"})

    def action_cancel(self):
        self.write({"screen_status": "canceled", "reservation_status": "canceled"})

    def action_set_draft(self):
        self.write({"screen_status": "draft"})

    # ---------- Invoice actions ----------
    # ---------- Invoice state mapper ----------
    def _compute_invoice_state(self):
        """
        Map idil.invoice.state to reservation-friendly labels:
          draft  -> pending
          posted -> approved
          cancel -> rejected
        """
        map_state = {"draft": "pending", "posted": "approved", "cancel": "rejected"}
        for rec in self:
            rec.invoice_state = map_state.get(rec.invoice_id.state, False) if rec.invoice_id else False

    # ---------- Invoice actions (use idil.invoice) ----------
    def action_create_invoice(self):
        """
        Create an IDIL custom invoice (idil.invoice) with 1 line using product_id and ticket_fee.
        Requires: customer_id, product_id, ticket_fee > 0.
        """
        for rec in self:
            if rec.invoice_id:
                raise UserError(_("An invoice already exists for this reservation."))

            if not rec.customer_id:
                raise UserError(_("Please set the Customer to invoice."))
            if not rec.product_id:
                raise UserError(_("Please set the Service Product for invoicing."))
            if not rec.ticket_fee or rec.ticket_fee <= 0:
                raise UserError(_("Ticket Fee must be greater than zero."))

            inv_vals = {
                "company_id": rec.company_id.id,
                "customer_id": rec.customer_id.id,
                "currency_id": rec.currency_id.id,
                "invoice_date": fields.Date.context_today(self),
                "ref": _("Reservation: %s") % (rec.name or ""),
                "line_ids": [(0, 0, {
                    "product_id": rec.product_id.id,
                    "name": _("Ticket: %(res)s | %(from)s → %(to)s") % {
                        "res": rec.name or "",
                        "from": rec.from_city or "",
                        "to": rec.to_city or "",
                    },
                    "quantity": 1.0,
                    "price_unit": rec.ticket_fee,
                    # Optional: "tax_percent": 5.0,
                })],
            }
            invoice = self.env["idil.invoice"].create(inv_vals)
            rec.invoice_id = invoice.id

        return self.action_view_invoice()

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_("No invoice linked yet."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Invoice"),
            "res_model": "idil.invoice",
            "view_mode": "form",
            "res_id": self.invoice_id.id,
            "target": "current",
        }

    def action_print_invoice_pdf(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_("No invoice linked yet."))
        return self.invoice_id.action_print_pdf()
