# models/customer_place_order.py
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class CustomerPlaceOrder(models.Model):
    _name = "idil.customer.place.order"
    _description = "Customer Place Order"
    _inherit = ["mail.thread", "mail.activity.mixin"]   # ⬅️ add this

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

    # NEW: who took the order
    waiter_id = fields.Many2one(
        "res.users",
        string="Waiter",
        required=True,
        default=lambda self: self.env.user,
        help="User who placed/submitted the order."
    )

    # NEW: dine mode + table number
    order_mode = fields.Selection(
        [
            ("dine_in", "Dine-In"),
            ("takeaway", "Takeaway"),
        ],
        string="Order Mode",
        required=True,
        default="dine_in",
    )
    table_no = fields.Char(
        string="Table",
        help="Table number for dine-in orders. Leave blank for takeaway."
    )

    order_lines = fields.One2many(
        "idil.customer.place.order.line", "order_id", string="Order Lines"
    )
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("cancel", "Cancelled") ,("closed", "Closed") ],
        default="draft",
    )

    # Rollups
    total_quantity = fields.Float(
        string="Total Quantity", compute="_compute_rollups", store=True
    )
    total_price = fields.Monetary(
        string="Total Price",
        compute="_compute_rollups",
        store=True,
        currency_field="currency_id"
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
    confirmed_by = fields.Many2one(
        "res.users",
        string="Confirmed By",
        readonly=True,
        tracking=True,  # ✅ show in chatter
    )
    confirmed_at = fields.Datetime(
        string="Confirmed At",
        readonly=True,
        tracking=True,  # ✅ show in chatter
    )
    # --- Add inside class CustomerPlaceOrder(models.Model): ---

    # Payment tracking on place order (no sale order involved)
    paid_amount = fields.Float(string="Paid Amount", default=0.0, tracking=True)
    balance_due = fields.Float(string="Balance Due", compute="_compute_payment_progress", store=True)
    payment_status = fields.Selection(
        [("pending", "Pending"), ("partial_paid", "Partially Paid"), ("paid", "Paid")],
        default="pending",
        tracking=True,
    )
    # 🔹 New field: serial number per day
    sl = fields.Char(
        string="Daily Serial",
        copy=False,
        index=True,
        readonly=True,
        help="Daily running number (001, 002, ...) reset every day."
    )

    @api.depends("total_price", "paid_amount")
    def _compute_payment_progress(self):
        for rec in self:
            total = rec.total_price or 0.0
            paid = rec.paid_amount or 0.0
            due = max(total - paid, 0.0)
            rec.balance_due = due
            if due <= 0:
                rec.payment_status = "paid"
            elif paid > 0:
                rec.payment_status = "partial_paid"
            else:
                rec.payment_status = "pending"

    def _generate_order_reference(self):
        seq = self.env["ir.sequence"].next_by_code("idil.customer.place.order.sequence")
        return seq or "ORDER"

    @api.depends(
        "order_lines.quantity",
        "order_lines.sale_price",
        "order_lines.line_total",
        "order_lines.status",
    )
    def _compute_rollups(self):
        for order in self:
            qty_sum = 0.0
            total_sum = 0.0
            for l in order.order_lines:
                if l.status != "removed":  # exclude removed lines from totals
                    qty_sum += l.quantity or 0.0
                    total_sum += l.line_total or 0.0
            order.total_quantity = qty_sum
            order.total_price = total_sum

    @api.constrains("order_mode", "table_no")
    def _check_table_for_dinein(self):
        for rec in self:
            if rec.order_mode == "dine_in" and not rec.table_no:
                raise ValidationError("Table is required for Dine-In orders.")

    @api.model
    def create(self, vals):
        # Prevent multiple concurrent drafts per customer
        # existing = self.search(
        #     [("customer_id", "=", vals.get("customer_id")), ("state", "=", "draft")],
        #     limit=1,
        # )
        # if existing:
        #     raise UserError(
        #         "This customer already has an active draft order. "
        #         "Please edit the existing order or change its state first."
        #     )
        # Ensure waiter defaults if client didn't pass it
        if not vals.get("waiter_id"):
            vals["waiter_id"] = self.env.user.id
        # Auto-clear table if takeaway
        if vals.get("order_mode") == "takeaway":
            vals["table_no"] = False

        # 🔹 assign daily sequence if not already passed
        if not vals.get("sl"):
            vals["sl"] = self.env["ir.sequence"].next_by_code(
                "idil.customer.place.order.sl"
            )
        return super().create(vals)

    def write(self, vals):
        # If switching to takeaway, clear table
        if vals.get("order_mode") == "takeaway":
            vals["table_no"] = False
        return super().write(vals)

    def action_confirm(self):
        for order in self:
            if getattr(order, "state", False) == "confirmed":
                # already confirmed; nothing to do
                continue

            # (optional) maker–checker enforcement can remain elsewhere; this focuses only on booking
            amount = self._compute_order_amount_fallback(order)

            # Try to get trx_source from the order if you have it; otherwise leave False
            trx_source_id = False
            if hasattr(order, "trx_source_id") and order.trx_source_id:
                trx_source_id = order.trx_source_id.id

            # Create the header booking
            transaction_booking = self.env["idil.transaction_booking"].create(
                {
                    "customer_id": order.customer_id.id,
                    "cusotmer_sale_order_id": order.id,  # (kept as spelled in your schema)
                    "trx_source_id": trx_source_id,
                    "reffno": getattr(order, "name", str(order.id)),
                    "Sales_order_number": order.id,
                    "payment_method": "bank_transfer",
                    "payment_status": "pending",
                    "trx_date": fields.Date.context_today(self),
                    "amount": amount,
                }
            )

            # Create booking lines for each order line (COGS vs Inventory)
            if not order.order_lines:
                # If you expect at least one line, you can raise; otherwise just skip
                pass

            for line in order.order_lines:
                product = line.product_id
                if not product:
                    raise UserError(_("Order line without product cannot be booked."))

                # Validate accounts exist
                if not getattr(product, "account_cogs_id", False):
                    raise UserError(
                        _("COGS account is missing for product: %s") % (product.display_name or product.name))
                if not getattr(product, "asset_account_id", False):
                    raise UserError(_("Inventory (asset) account is missing for product: %s") % (
                            product.display_name or product.name))

                qty = getattr(line, "quantity", 0.0) or 0.0
                unit_cost = self._product_cost(product)
                product_cost_amount = qty * unit_cost

                # DR: COGS
                self.env["idil.transaction_bookingline"].create(
                    {
                        "transaction_booking_id": transaction_booking.id,
                        "description": f"Sales Order -- Expanses COGS account for - {product.name}",
                        "product_id": product.id,
                        "account_number": product.account_cogs_id.id,
                        "transaction_type": "dr",
                        "dr_amount": product_cost_amount,
                        "cr_amount": 0.0,
                        "transaction_date": fields.Date.context_today(self),
                    }
                )

                # CR: Inventory (asset)
                self.env["idil.transaction_bookingline"].create(
                    {
                        "transaction_booking_id": transaction_booking.id,
                        "description": f"Sales Inventory account for - {product.name}",
                        "product_id": product.id,
                        "account_number": product.asset_account_id.id,
                        "transaction_type": "cr",
                        "dr_amount": 0.0,
                        "cr_amount": product_cost_amount,
                        "transaction_date": fields.Date.context_today(self),
                    }
                )

            # Finally, mark the order as confirmed + audit fields
            order.write(
                {
                    "state": "confirmed",
                    "confirmed_by": self.env.uid,
                    "confirmed_at": fields.Datetime.now(),
                }
            )

        return True


class CustomerPlaceOrderLine(models.Model):
    _name = "idil.customer.place.order.line"
    _description = "Customer Place Order Line"

    order_id = fields.Many2one(
        "idil.customer.place.order", string="Customer Order", required=True, ondelete="cascade"
    )
    product_id = fields.Many2one("my_product.product", string="Product", required=True)
    quantity = fields.Float(string="Quantity", default=1.0)

    # NEW: snapshot menu/category (first POS category of the product)
    menu_id = fields.Many2one(
        "pos.category",
        string="Menu",
        help="Snapshot of the product's primary POS category at the time of ordering."
    )
    menu_name = fields.Char(
        string="Menu Name",
        help="Snapshot of menu name to keep a stable label even if the category is later renamed."
    )

    # Snapshot pricing
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

    status = fields.Selection(
        [
            ("normal", "Normal"),
            ("removed", "Removed"),
            ("add", "Add"),
        ],
        default="normal",
        string="Status",
        tracking=True,
        help="Normal: existing line; Removed: excluded from totals; Add: newly added line.",
    )

    # Currency (inherit from order)
    currency_id = fields.Many2one(
        'res.currency',
        related="order_id.currency_id",
        store=True,
        readonly=True,
    )

    @api.depends("quantity", "sale_price", "status")
    def _compute_line_total(self):
        for line in self:
            if line.status == "removed":
                line.line_total = 0.0
            else:
                qty = line.quantity or 0.0
                price = line.sale_price or 0.0
                line.line_total = qty * price

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            # default quantity and snapshot the current product price
            self.quantity = 1.0
            self.sale_price = self.product_id.sale_price or 0.0
            # set menu snapshot from first POS category
            first_cat = (self.product_id.pos_categ_ids and self.product_id.pos_categ_ids[:1]) or False
            self.menu_id = first_cat and first_cat.id or False
            self.menu_name = self.menu_id and self.menu_id.name or False

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

            # Menu snapshot if not provided
            if not vals.get("menu_id"):
                first_cat = (prod.pos_categ_ids and prod.pos_categ_ids[:1]) or False
                if first_cat:
                    vals["menu_id"] = first_cat.id
                    vals["menu_name"] = first_cat.name

        # If client sent menu_id but not menu_name, snapshot name
        if vals.get("menu_id") and not vals.get("menu_name"):
            cat = self.env["pos.category"].browse(vals["menu_id"])
            vals["menu_name"] = cat.name

        return super().create(vals)

    def write(self, vals):
        # If product changed and sale_price not explicitly provided, resnap it
        if "product_id" in vals and "sale_price" not in vals:
            prod = self.env["my_product.product"].browse(vals["product_id"])
            vals["sale_price"] = prod.sale_price or 0.0
            # refresh menu snapshot if client didn't send it
            if "menu_id" not in vals:
                first_cat = (prod.pos_categ_ids and prod.pos_categ_ids[:1]) or False
                vals["menu_id"] = first_cat and first_cat.id or False
                if vals["menu_id"]:
                    vals["menu_name"] = self.env["pos.category"].browse(vals["menu_id"]).name

        # If menu_id changed but no menu_name, keep snapshot
        if "menu_id" in vals and "menu_name" not in vals and vals["menu_id"]:
            cat = self.env["pos.category"].browse(vals["menu_id"])
            vals["menu_name"] = cat.name

        return super().write(vals)
