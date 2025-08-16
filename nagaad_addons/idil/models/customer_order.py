from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class CustomerPlaceOrder(models.Model):
    _name = "idil.customer.place.order"
    _description = "Customer Place Order"
    _order = "id desc"

    name = fields.Char(
        string="Order Reference",
        required=True,
        default=lambda self: self._generate_order_reference(),
    )
    customer_id = fields.Many2one(
        "idil.customer.registration", string="Customer", required=True
    )
    order_date = fields.Datetime(string="Order Date", default=fields.Datetime.now)
    order_lines = fields.One2many(
        "idil.customer.place.order.line", "order_id", string="Order Lines"
    )
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("cancel", "Cancelled")],
        default="draft",
    )
    total_quantity = fields.Float(
        string="Total Quantity", compute="_compute_total_quantity", store=True
    )
    # in idil.customer.place.order

    sale_order_id = fields.Many2one(
        "idil.customer.sale.order",  # ✅ not "idil.sale.order"
        string="Processed Sale Order",
        readonly=True,
    )

    def _generate_order_reference(self):
        """
        This method generates the order reference using a sequence and custom logic.
        You can customize it further to fit your needs (e.g., including the date, customer code, etc.).
        """
        sequence = self.env["ir.sequence"].next_by_code(
            "idil.customer.place.order.sequence"
        )
        return sequence or "ORDER"  # Fallback if no sequence is configured

    @api.depends("order_lines.quantity")
    def _compute_total_quantity(self):
        for order in self:
            order.total_quantity = sum(line.quantity for line in order.order_lines)

    @api.model
    def create(self, vals):
        # Prevent creation of a draft order if the customer already has an active draft order
        existing_draft_order = self.search(
            [
                ("customer_id", "=", vals.get("customer_id")),
                ("state", "=", "draft"),
            ],
            limit=1,
        )

        if existing_draft_order:
            raise UserError(
                "This customer already has an active draft order. Please edit the existing order or change its state before creating a new one."
            )

        return super(CustomerPlaceOrder, self).create(vals)


class CustomerPlaceOrderLine(models.Model):
    _name = "idil.customer.place.order.line"
    _description = "Customer Place Order Line"

    order_id = fields.Many2one(
        "idil.customer.place.order", string="Customer Order", required=True
    )
    product_id = fields.Many2one("my_product.product", string="Product", required=True)
    quantity = fields.Float(string="Quantity", default=1.0)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.quantity = 1.0

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError("Quantity must be greater than zero.")
