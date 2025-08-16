# models/customer_place_order.py
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

    # Rollups
    total_quantity = fields.Float(
        string="Total Quantity", compute="_compute_rollups", store=True
    )
    total_price = fields.Monetary(
        string="Total Price", compute="_compute_rollups", store=True, currency_field="currency_id"
    )

    # Optional: company/currency if you have multi-company – adjust as needed
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        string="Company",
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        depends=['company_id'],
        store=True,
        readonly=True
    )

    sale_order_id = fields.Many2one(
        "idil.customer.sale.order",
        string="Processed Sale Order",
        readonly=True,
    )

    def _generate_order_reference(self):
        seq = self.env["ir.sequence"].next_by_code("idil.customer.place.order.sequence")
        return seq or "ORDER"

    @api.depends("order_lines.quantity", "order_lines.sale_price", "order_lines.line_total")
    def _compute_rollups(self):
        for order in self:
            qty_sum = 0.0
            total_sum = 0.0
            for l in order.order_lines:
                qty_sum += l.quantity or 0.0
                # line_total is computed on the line; using it avoids double rounding
                total_sum += l.line_total or 0.0
            order.total_quantity = qty_sum
            order.total_price = total_sum

    @api.model
    def create(self, vals):
        # Prevent multiple concurrent drafts per customer
        existing = self.search(
            [("customer_id", "=", vals.get("customer_id")), ("state", "=", "draft")],
            limit=1,
        )
        if existing:
            raise UserError(
                "This customer already has an active draft order. "
                "Please edit the existing order or change its state first."
            )
        return super().create(vals)


class CustomerPlaceOrderLine(models.Model):
    _name = "idil.customer.place.order.line"
    _description = "Customer Place Order Line"

    order_id = fields.Many2one(
        "idil.customer.place.order", string="Customer Order", required=True, ondelete="cascade"
    )
    product_id = fields.Many2one("my_product.product", string="Product", required=True)
    quantity = fields.Float(string="Quantity", default=1.0)

    # New snapshot fields
    sale_price = fields.Monetary(
        string="Sale Price",
        help="Unit sales price captured at the time of ordering.",
        currency_field="currency_id"
    )
    line_total = fields.Monetary(
        string="Line Total",
        compute="_compute_line_total",
        store=True,
        currency_field="currency_id",
    )

    # Currency (inherit from order)
    currency_id = fields.Many2one(
        'res.currency',
        related="order_id.currency_id",
        store=True,
        readonly=True,
    )

    @api.depends("quantity", "sale_price")
    def _compute_line_total(self):
        for line in self:
            qty = line.quantity or 0.0
            price = line.sale_price or 0.0
            line.line_total = qty * price

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            # default quantity and snapshot the current product price
            self.quantity = 1.0
            self.sale_price = self.product_id.sale_price or 0.0

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError("Quantity must be greater than zero.")

    @api.constrains("sale_price")
    def _check_sale_price(self):
        for line in self:
            if line.sale_price is not None and line.sale_price < 0:
                raise ValidationError("Sale price cannot be negative.")

    @api.model
    def create(self, vals):
        # Ensure sale_price is snapped even if not provided from the client
        if not vals.get("sale_price") and vals.get("product_id"):
            prod = self.env["my_product.product"].browse(vals["product_id"])
            vals["sale_price"] = prod.sale_price or 0.0
        return super().create(vals)

    def write(self, vals):
        # If product changed and sale_price not explicitly provided, resnap it
        if "product_id" in vals and "sale_price" not in vals:
            prod = self.env["my_product.product"].browse(vals["product_id"])
            vals["sale_price"] = prod.sale_price or 0.0
        return super().write(vals)
