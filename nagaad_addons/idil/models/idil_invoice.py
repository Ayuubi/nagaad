from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class IdilInvoice(models.Model):
    _name = "idil.invoice"
    _description = "IDIL Invoice"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    # --- Core / Company ---
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        domain=lambda self: [("id", "in", self.env.companies.ids)],
        index=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True,
    )

    # --- Identity ---
    name = fields.Char(string="Invoice No", default="New", required=True, copy=False, tracking=True)
    customer_id = fields.Many2one(
        "idil.customer.registration",
        string="Customer",
        required=True,
        domain=lambda self: [("company_id", "in", self.env.companies.ids)],
        tracking=True,
    )
    invoice_date = fields.Date(string="Invoice Date", default=fields.Date.context_today, tracking=True)
    ref = fields.Char(string="Reference", tracking=True)
    narration = fields.Text(string="Notes")

    # --- Relations ---
    line_ids = fields.One2many("idil.invoice.line", "invoice_id", string="Invoice Lines", copy=True)
    reservation_ids = fields.One2many("travel.ticket.reservation", "invoice_id", string="Reservations", readonly=True)

    # --- Amounts ---
    amount_untaxed = fields.Monetary(string="Untaxed", currency_field="currency_id", compute="_compute_amounts",
                                     store=True)
    amount_tax = fields.Monetary(string="Tax", currency_field="currency_id", compute="_compute_amounts", store=True)
    amount_total = fields.Monetary(string="Total", currency_field="currency_id", compute="_compute_amounts", store=True)

    # --- Status ---
    state = fields.Selection(
        [("draft", "Draft"), ("posted", "Posted"), ("cancel", "Canceled")],
        string="Status",
        default="draft",
        tracking=True,
    )

    # --- Audit ---
    user_id = fields.Many2one("res.users", string="Salesperson", default=lambda self: self.env.user, tracking=True)

    _sql_constraints = [
        ("name_unique", "unique(name, company_id)", "Invoice number must be unique per company."),
    ]

    @api.depends("line_ids.subtotal", "line_ids.tax_amount")
    def _compute_amounts(self):
        for inv in self:
            untaxed = sum(inv.line_ids.mapped("subtotal"))
            tax = sum(inv.line_ids.mapped("tax_amount"))
            inv.amount_untaxed = untaxed
            inv.amount_tax = tax
            inv.amount_total = untaxed + tax

    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("idil.invoice") or "New"
        return super().create(vals)

    # --- Business actions ---
    def action_post(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Add at least one invoice line before posting."))
            if any(l.quantity <= 0 for l in rec.line_ids):
                raise ValidationError(_("Invoice lines must have quantity > 0."))
            rec.state = "posted"

            # OPTIONAL: hook into your custom booking/ledger here
            # self._create_custom_booking(rec)

        return True

    def action_reset_to_draft(self):
        self.write({"state": "draft"})
        return True

    def action_cancel(self):
        self.write({"state": "cancel"})
        return True

    # Example booking hook you can adapt to your existing models
    def _create_custom_booking(self, invoice):
        """
        Wire this to your own models (e.g., idil.transaction_booking, lines, etc.)
        """
        # Example pseudo:
        # booking = self.env["idil.transaction_booking"].create({
        #     "company_id": invoice.company_id.id,
        #     "date": invoice.invoice_date,
        #     "reference": invoice.name,
        #     "customer_id": invoice.customer_id.id,
        #     "currency_id": invoice.currency_id.id,
        #     "amount": invoice.amount_total,
        # })
        # for line in invoice.line_ids:
        #     self.env["idil.transaction_bookingline"].create({
        #         "booking_id": booking.id,
        #         "product_id": line.product_id.id,
        #         "description": line.name,
        #         "quantity": line.quantity,
        #         "price_unit": line.price_unit,
        #         "amount": line.total,
        #     })
        return True

    # --- Printing ---
    def action_print_pdf(self):
        self.ensure_one()
        # Fast path: use the report action we just created
        return self.env.ref("idil.report_idil_invoice_pdf").report_action(self)

    def _get_report_base_filename(self):
        """Controls the filename when user clicks Download in the viewer."""
        self.ensure_one()
        safe = (self.name or "Invoice").replace("/", "-")
        return safe


class IdilInvoiceLine(models.Model):
    _name = "idil.invoice.line"
    _description = "IDIL Invoice Line"
    _order = "id asc"

    invoice_id = fields.Many2one("idil.invoice", string="Invoice", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="invoice_id.company_id", store=True)
    currency_id = fields.Many2one(related="invoice_id.currency_id", store=True)

    product_id = fields.Many2one(
        "my_product.product",
        string="Product",
        required=True,
        domain=lambda self: [("company_id", "in", self.env.companies.ids)],
    )
    name = fields.Char(string="Description")
    quantity = fields.Float(string="Qty", default=1.0)
    price_unit = fields.Monetary(string="Unit Price", currency_field="currency_id")
    tax_percent = fields.Float(string="Tax %", digits=(16, 2), default=0.0)

    subtotal = fields.Monetary(string="Subtotal", currency_field="currency_id", compute="_compute_totals", store=True)
    tax_amount = fields.Monetary(string="Tax Amount", currency_field="currency_id", compute="_compute_totals",
                                 store=True)
    total = fields.Monetary(string="Total", currency_field="currency_id", compute="_compute_totals", store=True)

    @api.depends("quantity", "price_unit", "tax_percent")
    def _compute_totals(self):
        for line in self:
            qty = max(line.quantity or 0.0, 0.0)
            price = line.price_unit or 0.0
            subtotal = qty * price
            tax = subtotal * (line.tax_percent or 0.0) / 100.0
            line.subtotal = subtotal
            line.tax_amount = tax
            line.total = subtotal + tax

    @api.constrains("quantity", "price_unit", "tax_percent")
    def _check_values(self):
        for l in self:
            if l.quantity <= 0:
                raise ValidationError(_("Quantity must be greater than zero."))
            if l.price_unit < 0:
                raise ValidationError(_("Unit Price cannot be negative."))
            if l.tax_percent < 0:
                raise ValidationError(_("Tax % cannot be negative."))
