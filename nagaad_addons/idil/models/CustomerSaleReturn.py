# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class CustomerSaleReturn(models.Model):
    _name = "idil.customer.sale.return"
    _description = "Customer Sale Return"
    _order = "id desc"

    name = fields.Char(string="Return Reference", default="New", readonly=True)

    customer_id = fields.Many2one(
        "idil.customer.registration", string="Customer", required=True
    )
    sale_order_id = fields.Many2one(
        "idil.customer.sale.order",
        string="Sale Order",
    )

    return_date = fields.Date(default=fields.Date.context_today, string="Return Date")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        string="Status",
    )

    return_lines = fields.One2many(
        "idil.customer.sale.return.line", "return_id", string="Return Lines", copy=True
    )

    # Currency fields
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        required=True,
        default=lambda self: self.env["res.currency"].search([("name", "=", "SL")], limit=1),
        readonly=True,
    )
    rate = fields.Float(
        string="Exchange Rate",
        compute="_compute_exchange_rate",
        store=True,
        readonly=True,
    )
    total_return = fields.Float(
        string="Total Return Amount",
        compute="_compute_total_return",
        store=True,
        readonly=True,
    )

    # ----- COMPUTES -----
    @api.depends("return_lines.total_amount")
    def _compute_total_return(self):
        for rec in self:
            rec.total_return = sum(line.total_amount for line in rec.return_lines)

    @api.depends("currency_id")
    def _compute_exchange_rate(self):
        for order in self:
            if order.currency_id:
                rate = self.env["res.currency.rate"].search(
                    [
                        ("currency_id", "=", order.currency_id.id),
                        ("name", "=", fields.Date.today()),
                        ("company_id", "=", self.env.company.id),
                    ],
                    limit=1,
                )
                order.rate = rate.rate if rate else 0.0
            else:
                order.rate = 0.0

    # ----- DEFAULTING / CREATE -----
    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("idil.customer.sale.return") or "New"
        return super().create(vals)

    # ----- ONCHANGE -----
    @api.onchange("sale_order_id")
    def _onchange_sale_order_id(self):
        """Prefill lines from the selected sale order; returnable qty is computed anyway."""
        if not self.sale_order_id:
            self.return_lines = [(5, 0, 0)]
            return

        self.return_lines = [(5, 0, 0)]  # Clear lines
        lines = []
        for so_line in self.sale_order_id.order_lines:
            # Previously confirmed returns for this SO line
            prev_return_lines = self.env["idil.customer.sale.return.line"].search(
                [
                    ("sale_order_line_id", "=", so_line.id),
                    ("return_id.state", "=", "confirmed"),
                ]
            )
            total_prev_returned = sum(r.return_quantity for r in prev_return_lines)
            returnable_qty = max((so_line.quantity or 0.0) - total_prev_returned, 0.0)

            lines.append(
                (
                    0,
                    0,
                    {
                        "sale_order_line_id": so_line.id,
                        "product_id": so_line.product_id.id,
                        "original_quantity": so_line.quantity,
                        "price_unit": so_line.price_unit,
                        # This is computed, but we also seed a value for the UI
                        "returnable_quantity": returnable_qty,
                    },
                )
            )
        self.return_lines = lines

    # ----- PROCESS -----
    def action_process(self):
        for rec in self:
            # No returns for opening balance sale orders
            if rec.sale_order_id and getattr(rec.sale_order_id, "customer_opening_balance_id", False):
                raise ValidationError("You cannot process a return for an opening balance sale order.")

            if rec.state != "draft":
                raise ValidationError("Only draft returns can be processed.")

            trx_source = self.env["idil.transaction.source"].search([("name", "=", "Sale Return")], limit=1)
            if not trx_source:
                raise ValidationError("Transaction source 'Sale Return' not found.")

            for line in rec.return_lines:
                if line.return_quantity <= 0:
                    # Skip blank lines
                    continue

                if line.return_quantity > line.original_quantity:
                    raise ValidationError(
                        f"Return quantity for '{line.product_id.name}' exceeds the original sold quantity."
                    )

                # 1) Stock update
                product = line.product_id
                # Custom field in your system:
                product.stock_quantity += line.return_quantity

                # 2) Stock movement (in)
                self.env["idil.product.movement"].create(
                    {
                        "product_id": product.id,
                        "movement_type": "in",
                        "quantity": line.return_quantity,
                        "date": fields.Datetime.now(),
                        "source_document": f"Customer Sale Return: {rec.name}",
                        "customer_id": rec.customer_id.id,
                    }
                )

                # 3) Reverse accounting (create a reversed booking per line)
                original_line = line.sale_order_line_id
                original_booking = self.env["idil.transaction_booking"].search(
                    [("cusotmer_sale_order_id", "=", rec.sale_order_id.id)], limit=1
                )
                if not original_booking:
                    raise ValidationError("Original transaction not found.")

                # Line amount to reverse
                line_amount = (original_line.price_unit or 0.0) * (line.return_quantity or 0.0)

                # Cost in BOM currency or product currency
                bom_currency = product.bom_id.currency_id if product.bom_id else product.currency_id
                amount_in_bom_currency = (product.cost or 0.0) * (line.return_quantity or 0.0)
                if bom_currency.name == "USD":
                    product_cost_amount = amount_in_bom_currency * (rec.rate or 0.0)
                else:
                    product_cost_amount = amount_in_bom_currency

                reversed_booking = self.env["idil.transaction_booking"].create(
                    {
                        "transaction_number": self.env["idil.transaction_booking"]._get_next_transaction_number(),
                        "trx_source_id": trx_source.id,
                        "customer_id": rec.customer_id.id,
                        "reffno": rec.name,
                        "trx_date": rec.return_date,
                        "amount": line_amount,
                        "amount_paid": 0.0,
                        "remaining_amount": 0.0,
                        "payment_status": "paid",
                        "customer_sales_return_id": line.id,
                    }
                )

                # COGS reversal (credit COGS)
                self.env["idil.transaction_bookingline"].create(
                    {
                        "transaction_booking_id": reversed_booking.id,
                        "description": f"Reversal of -- COGS for - {product.name}",
                        "product_id": product.id,
                        "account_number": product.account_cogs_id.id,
                        "transaction_type": "cr",
                        "dr_amount": 0.0,
                        "cr_amount": product_cost_amount,
                        "transaction_date": rec.return_date,
                        "company_id": self.env.company.id,
                        "customer_sales_return_id": line.id,
                    }
                )
                # Inventory asset back (debit asset)
                self.env["idil.transaction_bookingline"].create(
                    {
                        "transaction_booking_id": reversed_booking.id,
                        "description": f"Reversal of -- Asset Inventory for - {product.name}",
                        "product_id": product.id,
                        "account_number": product.asset_account_id.id,
                        "transaction_type": "dr",
                        "dr_amount": product_cost_amount,
                        "cr_amount": 0.0,
                        "transaction_date": rec.return_date,
                        "company_id": self.env.company.id,
                        "customer_sales_return_id": line.id,
                    }
                )
                # Reverse receivable (credit AR on the SO account)
                self.env["idil.transaction_bookingline"].create(
                    {
                        "transaction_booking_id": reversed_booking.id,
                        "description": f"Reversal of -- Sales Receivable for - {product.name}",
                        "product_id": product.id,
                        "account_number": rec.sale_order_id.account_number.id,
                        "transaction_type": "cr",
                        "dr_amount": 0.0,
                        "cr_amount": line_amount,
                        "transaction_date": rec.return_date,
                        "company_id": self.env.company.id,
                        "customer_sales_return_id": line.id,
                    }
                )
                # Reverse revenue (debit revenue)
                self.env["idil.transaction_bookingline"].create(
                    {
                        "transaction_booking_id": reversed_booking.id,
                        "description": f"Reversal of -- Revenue - {product.name}",
                        "product_id": product.id,
                        "account_number": product.income_account_id.id,
                        "transaction_type": "dr",
                        "dr_amount": line_amount,
                        "cr_amount": 0.0,
                        "transaction_date": rec.return_date,
                        "company_id": self.env.company.id,
                        "customer_sales_return_id": line.id,
                    }
                )

                # Receipt adjustment guard
                if line_amount > 0:
                    receipt = self.env["idil.sales.receipt"].search(
                        [("cusotmer_sale_order_id", "=", rec.sale_order_id.id)], limit=1
                    )
                    if receipt and line_amount > receipt.remaining_amount:
                        raise ValidationError(
                            f"Return amount ({line_amount}) exceeds remaining amount ({receipt.remaining_amount}) on the receipt.\n"
                            f"Verify payment before proceeding."
                        )
                    if receipt:
                        new_due = max((receipt.due_amount or 0.0) - line_amount, 0.0)
                        new_remaining = max(new_due - (receipt.paid_amount or 0.0), 0.0)
                        receipt.write(
                            {
                                "due_amount": new_due,
                                "remaining_amount": new_remaining,
                                "payment_status": "paid" if new_remaining <= 0 else "pending",
                            }
                        )

            rec.state = "confirmed"

    # ----- WRITE (edit after confirm = rollback old effects, reprocess) -----
    def write(self, vals):
        for rec in self:
            if rec.state == "confirmed":
                # 1) Reverse prior effects from this return
                for line in rec.return_lines:
                    if line.return_quantity > 0:
                        line.product_id.stock_quantity -= line.return_quantity

                    self.env["idil.product.movement"].search(
                        [
                            ("customer_id", "=", rec.customer_id.id),
                            ("source_document", "=", f"Customer Sale Return: {rec.name}"),
                            ("product_id", "=", line.product_id.id),
                        ]
                    ).unlink()

                    bookings = self.env["idil.transaction_booking"].search(
                        [("customer_sales_return_id", "=", line.id)]
                    )
                    for booking in bookings:
                        booking.booking_lines.unlink()
                        booking.unlink()

                # 2) Restore receipt totals
                if rec.total_return > 0:
                    receipt = self.env["idil.sales.receipt"].search(
                        [("cusotmer_sale_order_id", "=", rec.sale_order_id.id)], limit=1
                    )
                    if receipt:
                        receipt.write(
                            {
                                "due_amount": (receipt.due_amount or 0.0) + rec.total_return,
                                "remaining_amount": (receipt.remaining_amount or 0.0) + rec.total_return,
                                "payment_status": "paid" if (receipt.remaining_amount or 0.0) <= 0 else "pending",
                            }
                        )

                # 3) Force back to draft while we write new values
                vals = dict(vals or {})
                vals["state"] = "draft"

                res = super(CustomerSaleReturn, rec).write(vals)

                # 4) Re-run process with updated values
                rec.action_process()
                continue

            # If not confirmed, just write
            super(CustomerSaleReturn, rec).write(vals)
        return True

    # ----- UNLINK -----
    def unlink(self):
        for rec in self:
            if rec.state == "confirmed":
                # Restore receipt before deletion
                if rec.total_return > 0:
                    receipt = self.env["idil.sales.receipt"].search(
                        [("cusotmer_sale_order_id", "=", rec.sale_order_id.id)], limit=1
                    )
                    if receipt:
                        receipt.write(
                            {
                                "due_amount": (receipt.due_amount or 0.0) + rec.total_return,
                                "remaining_amount": (receipt.remaining_amount or 0.0) + rec.total_return,
                                "payment_status": "paid" if (receipt.remaining_amount or 0.0) <= 0 else "pending",
                            }
                        )

                # Reverse stock/movements/bookings
                for line in rec.return_lines:
                    if line.return_quantity > 0:
                        line.product_id.stock_quantity -= line.return_quantity

                    self.env["idil.product.movement"].search(
                        [
                            ("customer_id", "=", rec.customer_id.id),
                            ("source_document", "=", f"Customer Sale Return: {rec.name}"),
                            ("product_id", "=", line.product_id.id),
                        ]
                    ).unlink()

                    bookings = self.env["idil.transaction_booking"].search(
                        [("customer_sales_return_id", "=", line.id)]
                    )
                    for booking in bookings:
                        booking.booking_lines.unlink()
                        booking.unlink()

        return super(CustomerSaleReturn, self).unlink()


class CustomerSaleReturnLine(models.Model):
    _name = "idil.customer.sale.return.line"
    _description = "Customer Sale Return Line"
    _order = "id desc"

    return_id = fields.Many2one(
        "idil.customer.sale.return",
        string="Sale Return",
        required=True,
        ondelete="cascade",
    )
    sale_order_line_id = fields.Many2one(
        "idil.customer.sale.order.line", string="Original Order Line", store=True
    )
    product_id = fields.Many2one("my_product.product", string="Product", required=True)

    original_quantity = fields.Float(string="Original Quantity", store=True)
    price_unit = fields.Float(string="Unit Price", store=True)

    # ✅ FIXED: separate computes, both non-stored, same compute_sudo (default False)
    returnable_quantity = fields.Float(
        string="Returnable Quantity",
        compute="_compute_returnable",
        store=False,
        compute_sudo=False,
    )
    previously_returned_quantity = fields.Float(
        string="Previously Returned",
        compute="_compute_prev_returned",
        store=False,
        compute_sudo=False,
    )

    return_quantity = fields.Float(string="Return Quantity")

    total_amount = fields.Float(
        string="Total Amount",
        compute="_compute_total_amount",
        store=True,
        readonly=True,
    )

    # ----- COMPUTES -----
    @api.depends("return_quantity", "price_unit")
    def _compute_total_amount(self):
        for line in self:
            line.total_amount = (line.return_quantity or 0.0) * (line.price_unit or 0.0)

    @api.depends("sale_order_line_id", "original_quantity", "return_id.state", "return_quantity")
    def _compute_returnable(self):
        for line in self:
            if not line.sale_order_line_id:
                line.returnable_quantity = 0.0
                continue

            domain = [
                ("sale_order_line_id", "=", line.sale_order_line_id.id),
                ("return_id.state", "=", "confirmed"),
            ]
            if line.id and isinstance(line.id, int):
                domain.append(("id", "!=", line.id))

            prev_returns = self.env["idil.customer.sale.return.line"].search(domain)
            total_prev = sum(prev.return_quantity for prev in prev_returns)
            line.returnable_quantity = max((line.original_quantity or 0.0) - total_prev, 0.0)

    @api.depends("sale_order_line_id", "return_id.state", "return_quantity")
    def _compute_prev_returned(self):
        for line in self:
            if not line.sale_order_line_id:
                line.previously_returned_quantity = 0.0
                continue

            domain = [
                ("sale_order_line_id", "=", line.sale_order_line_id.id),
                ("return_id.state", "=", "confirmed"),
            ]
            if line.id and isinstance(line.id, int):
                domain.append(("id", "!=", line.id))

            prev_returns = self.env["idil.customer.sale.return.line"].search(domain)
            line.previously_returned_quantity = sum(prev.return_quantity for prev in prev_returns)

    # ----- CONSTRAINTS -----
    @api.constrains("return_quantity", "returnable_quantity")
    def _check_return_quantity(self):
        for line in self:
            # Let empty lines be skipped by process; only error if user set a value <= 0
            if line.return_quantity is not None and line.return_quantity <= 0:
                raise ValidationError(
                    f"Return quantity for product '{line.product_id.name}' must be greater than 0."
                )
            if line.return_quantity and line.return_quantity > (line.returnable_quantity or 0.0):
                raise ValidationError(
                    f"Return quantity for product '{line.product_id.name}' cannot exceed "
                    f"available returnable quantity ({line.returnable_quantity})."
                )
