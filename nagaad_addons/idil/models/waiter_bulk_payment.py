from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero


class WaiterBulkPayment(models.Model):
    _name = "idil.waiter.bulk.payment"
    _description = "Bulk Waiter Receive Payment"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    _order = "id desc"

    name = fields.Char(string="Reference", default="New", readonly=True, copy=False)
    date = fields.Date(default=fields.Date.context_today, string="Date", tracking=True)

    waiter_id = fields.Many2one(
        "res.users",
        string="Waiter",
        required=True,
        help="Collect payments for this waiter's confirmed place-orders.",
        tracking=True,
    )

    amount_to_receive = fields.Float(string="Total Amount to Receive", required=True)
    payment_method_ids = fields.One2many(
        "idil.waiter.bulk.payment.method",
        "bulk_payment_id",
        string="Payment Methods",
    )
    payment_methods_total = fields.Float(
        string="Payment Methods Total", compute="_compute_payment_methods_total"
    )

    line_ids = fields.One2many(
        "idil.waiter.bulk.payment.line",
        "bulk_payment_id",
        string="Allocations",
    )

    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed")],
        default="draft",
        tracking=True,
    )

    # Waiter totals (based on confirmed place orders)
    waiter_due_amount = fields.Float(
        string="Total Due on Confirmed Orders", compute="_compute_waiter_due", store=False
    )
    waiter_due_count = fields.Integer(
        string="# Confirmed Orders with Balance", compute="_compute_waiter_due", store=False
    )
    # In class WaiterBulkPayment(models.Model):

    # Forward balance = due on confirmed place-orders with order_date < today
    waiter_forward_due_amount = fields.Float(
        string="Forward Balance (Before Today)",
        compute="_compute_waiter_forward_due",
        store=False,
    )
    waiter_forward_due_count = fields.Integer(
        string="# Forward Orders (Before Today)",
        compute="_compute_waiter_forward_due",
        store=False,
    )
    # --- Today metrics ---
    waiter_sales_today_count = fields.Integer(
        string="Sales Today (Count)",
        compute="_compute_today_and_total_due",
        store=False,
    )
    waiter_sales_today_amount = fields.Float(
        string="Sales Today (Amount)",
        compute="_compute_today_and_total_due",
        store=False,
    )
    waiter_due_today_amount = fields.Float(
        string="Due Today (Amount)",
        compute="_compute_today_and_total_due",
        store=False,
    )

    # --- Grand total due (forward + today) ---
    waiter_total_due_amount = fields.Float(
        string="Total Due (Forward + Today)",
        compute="_compute_today_and_total_due",
        store=False,
    )
    # In class WaiterBulkPayment(models.Model):

    waiter_due_after_payment = fields.Float(
        string="Due After This Payment",
        compute="_compute_due_after_payment",
        store=False,
    )

    company_id = fields.Many2one("res.company", default=lambda s: s.env.company, required=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True, readonly=True)

    # ----------------- Computes & Constraints -----------------
    # Still inside WaiterBulkPayment(models.Model)
    @api.depends("waiter_total_due_amount", "amount_to_receive")
    def _compute_due_after_payment(self):
        for rec in self:
            total_pending = rec.waiter_total_due_amount or 0.0
            receiving = rec.amount_to_receive or 0.0
            rec.waiter_due_after_payment = max(total_pending - receiving, 0.0)

    @api.depends("waiter_id")
    def _compute_today_and_total_due(self):
        for rec in self:
            rec.waiter_sales_today_count = 0
            rec.waiter_sales_today_amount = 0.0
            rec.waiter_due_today_amount = 0.0
            rec.waiter_total_due_amount = (rec.waiter_forward_due_amount or 0.0)

            if not rec.waiter_id:
                continue

            # Define [start_of_today, start_of_tomorrow)
            today = fields.Date.context_today(rec)
            start_of_today = fields.Datetime.to_datetime(today)  # 00:00 local
            start_of_tomorrow = start_of_today + timedelta(days=1)

            # All confirmed orders for this waiter that happened today
            todays_pos = rec.env["idil.customer.place.order"].search([
                ("waiter_id", "=", rec.waiter_id.id),
                ("state", "=", "confirmed"),
                ("order_date", ">=", start_of_today),
                ("order_date", "<", start_of_tomorrow),
            ])

            # Count + amount (total price) for today
            rec.waiter_sales_today_count = len(todays_pos)
            rec.waiter_sales_today_amount = sum((po.total_price or 0.0) for po in todays_pos)

            # Today's DUE amount (not paid yet, for today's confirmed orders)
            due_today = 0.0
            for po in todays_pos:
                total = po.total_price or 0.0
                paid = po.paid_amount or 0.0
                rem = total - paid
                if rem > 0:
                    due_today += rem

            rec.waiter_due_today_amount = due_today

            # Grand total due = forward (already computed) + today due
            rec.waiter_total_due_amount = (rec.waiter_forward_due_amount or 0.0) + due_today

    @api.depends("waiter_id")
    def _compute_waiter_forward_due(self):
        for rec in self:
            if not rec.waiter_id:
                rec.waiter_forward_due_amount = 0.0
                rec.waiter_forward_due_count = 0
                continue

            # "Today" in the user's context; convert to a datetime at 00:00
            # Anything strictly earlier than this is "before today"
            today = fields.Date.context_today(rec)
            start_of_today = fields.Datetime.to_datetime(today)

            pos = rec.env["idil.customer.place.order"].search([
                ("waiter_id", "=", rec.waiter_id.id),
                ("state", "=", "confirmed"),
                ("order_date", "<", start_of_today),  # strictly before today
            ])

            total_forward_due = 0.0
            forward_cnt = 0
            for po in pos:
                total = po.total_price or 0.0
                paid = po.paid_amount or 0.0
                due = total - paid
                if due > 0:
                    total_forward_due += due
                    forward_cnt += 1

            rec.waiter_forward_due_amount = total_forward_due
            rec.waiter_forward_due_count = forward_cnt

    @api.depends("payment_method_ids.payment_amount")
    def _compute_payment_methods_total(self):
        for rec in self:
            rec.payment_methods_total = sum(x.payment_amount for x in rec.payment_method_ids)

    @api.depends("waiter_id")
    def _compute_waiter_due(self):
        for rec in self:
            if not rec.waiter_id:
                rec.waiter_due_amount = 0.0
                rec.waiter_due_count = 0
                continue

            pos = rec.env["idil.customer.place.order"].search([
                ("waiter_id", "=", rec.waiter_id.id),
                ("state", "=", "confirmed"),
            ])
            dued = 0.0
            cnt = 0
            for po in pos:
                total = po.total_price or 0.0
                paid = po.paid_amount or 0.0
                due = total - paid
                if due > 0:
                    dued += due
                    cnt += 1
            rec.waiter_due_amount = dued
            rec.waiter_due_count = cnt

    @api.constrains("amount_to_receive", "waiter_id")
    def _check_amount_not_exceed_due(self):
        for rec in self:
            if not rec.waiter_id or rec.amount_to_receive <= 0:
                continue
            pos = rec.env["idil.customer.place.order"].search([
                ("waiter_id", "=", rec.waiter_id.id),
                ("state", "=", "confirmed"),
            ])
            total_due = 0.0
            for po in pos:
                total_due += max((po.total_price or 0.0) - (po.paid_amount or 0.0), 0.0)

            if rec.amount_to_receive > total_due + 0.01:
                raise ValidationError(
                    f"Amount to Receive ({rec.amount_to_receive}) cannot exceed waiter total due ({total_due})."
                )

    @api.constrains("payment_method_ids")
    def _check_at_least_one_method(self):
        for rec in self:
            if not rec.payment_method_ids:
                raise ValidationError("Add at least one payment method.")

    @api.constrains("amount_to_receive", "payment_method_ids")
    def _check_methods_equal_amount(self):
        for rec in self:
            if rec.payment_method_ids:
                total = sum(m.payment_amount for m in rec.payment_method_ids)
                if abs(total - rec.amount_to_receive) > 0.01:
                    raise ValidationError("Sum of payment methods must equal Total Amount to Receive.")

    # ----------------- Allocation (onchange) -----------------
    @api.onchange("waiter_id", "amount_to_receive")
    def _onchange_allocate_lines(self):
        self.line_ids = [(5, 0, 0)]
        if not self.waiter_id:
            return

        pos = self.env["idil.customer.place.order"].search(
            [("waiter_id", "=", self.waiter_id.id), ("state", "=", "confirmed")],
            order="order_date asc"
        )

        remaining = max(self.amount_to_receive or 0.0, 0.0)
        new_lines = []
        for po in pos:
            total = po.total_price or 0.0
            paid = po.paid_amount or 0.0
            due = max(total - paid, 0.0)
            if due <= 0:
                continue

            to_pay = min(due, remaining) if remaining > 0 else 0.0
            new_lines.append((0, 0, {
                "place_order_id": po.id,
                "order_date": po.order_date,
                "customer_id": po.customer_id.id if po.customer_id else False,
                "total_amount": total,
                "paid_amount": paid,
                "remaining_amount": due,
                "paid_now": to_pay,
            }))
            if remaining > 0:
                remaining -= to_pay

        self.line_ids = new_lines

    # ----------------- Confirm -----------------
    def action_confirm(self):
        for rec in self:
            if rec.state != "draft":
                continue
            if rec.amount_to_receive <= 0:
                raise UserError("Amount to Receive must be greater than zero.")
            if not rec.line_ids:
                raise UserError("Nothing to allocate. Select a waiter and amount first.")
            if not rec.payment_method_ids:
                raise UserError("Add at least one payment method.")

            # 1) Resolve waiter -> employee -> receivable (asset) account
            employee = rec.env["idil.employee"].search([("user_id", "=", rec.waiter_id.id)], limit=1)
            if not employee:
                raise UserError(f"No employee record linked to waiter {rec.waiter_id.name}.")
            waiter_rec_acct = employee.receivable_account_id
            if not waiter_rec_acct:
                raise UserError(f"Receivable Account is not set on employee {employee.name}.")

            # 2) Transaction source
            trx_source = rec.env["idil.transaction.source"].search(
                [("name", "=", "Bulk Waiter Payment")], limit=1
            )
            if not trx_source:
                raise UserError("Transaction source 'Bulk Waiter Payment' not found.")

            # 3) Create ONE booking header for this bulk payment
            trx_booking = rec.env["idil.transaction_booking"].create({
                "order_number": rec.name or "/",
                "trx_source_id": trx_source.id,
                "bank_reff": 0,
                "payment_method": "other",
                "customer_id": False,  # dedicated clearing if your model requires
                "reffno": rec.name,
                "payment_status": "partial_paid",  # informational; allocations drive per-order status
                "trx_date": fields.Datetime.now(),
                "amount": rec.amount_to_receive,
            })

            # 4) DR each payment method account by its assigned amount
            methods_total = 0.0
            for method in rec.payment_method_ids:
                pay_acct = method.payment_account_id
                amt = method.payment_amount or 0.0
                if not pay_acct:
                    raise UserError("Payment method missing account.")
                if amt <= 0:
                    continue
                methods_total += amt

                rec.env["idil.transaction_bookingline"].create({
                    "transaction_booking_id": trx_booking.id,
                    "transaction_type": "dr",
                    "bank_reff": 0,
                    "account_number": pay_acct.id,
                    "dr_amount": amt,
                    "cr_amount": 0.0,
                    "transaction_date": fields.Datetime.now(),
                    "description": f"Bulk Waiter Payment - {rec.name} (DR {pay_acct.name})",
                })

            # Safety: methods must equal header amount (you already constrain elsewhere)
            if abs(methods_total - (rec.amount_to_receive or 0.0)) > 0.01:
                raise UserError("Payment methods total must equal Amount to Receive.")

            # 5) CR waiter receivable (asset) full amount (reduces AR)
            rec.env["idil.transaction_bookingline"].create({
                "transaction_booking_id": trx_booking.id,
                "transaction_type": "cr",
                "bank_reff": 0,
                "account_number": waiter_rec_acct.id,
                "dr_amount": 0.0,
                "cr_amount": rec.amount_to_receive,
                "transaction_date": fields.Datetime.now(),
                "description": f"Bulk Waiter Payment - {rec.name} (CR Waiter AR {waiter_rec_acct.name})",
            })

            # 6) Allocate to place orders (update paid_amounts) + mark as paid when settled
            alloc_lines = rec.line_ids.filtered(lambda l: l.remaining_amount > 0)
            remaining_pool = rec.amount_to_receive

            fully_settled = []  # for summary message
            partially_paid = []  # for summary message

            for line in alloc_lines:
                if remaining_pool <= 0:
                    break

                po = line.place_order_id
                if not po:
                    continue

                total = po.total_price or 0.0
                paid = po.paid_amount or 0.0
                due = max(total - paid, 0.0)
                if due <= 0:
                    continue

                to_pay = min(due, remaining_pool)

                # Update place order payment progress
                new_paid = paid + to_pay
                po.write({"paid_amount": new_paid})  # compute updates balance/status

                remaining = max(total - new_paid, 0.0)
                # NEW: explicitly mark as paid + chatter when fully settled (currency aware)
                if float_is_zero(remaining, precision_rounding=po.currency_id.rounding):
                    # ✅ mark as fully paid + closed
                    po.write({
                        "payment_status": "paid",
                        "state": "closed",
                    })

                    po.message_post(body=f"Order fully settled by Bulk Waiter Payment <b>{rec.name}</b>.")
                    fully_settled.append(f"{po.name}: {to_pay:.2f}")
                else:
                    partially_paid.append(f"{po.name}: {to_pay:.2f} (remain {remaining:.2f})")

                # Mirror on allocation line
                line.paid_now += to_pay
                line.paid_amount = new_paid
                line.remaining_amount = remaining

                remaining_pool -= to_pay

            if remaining_pool > 0:
                raise UserError(f"{remaining_pool:.2f} remains unallocated. Adjust allocations or amount.")

            # 7) finalize record
            rec.state = "confirmed"

            # 8) Post a compact summary to the bulk payment chatter
            summary_lines = []
            if fully_settled:
                summary_lines.append("<b>Fully settled</b>: " + ", ".join(fully_settled))
            if partially_paid:
                summary_lines.append("<b>Partially paid</b>: " + "; ".join(partially_paid))
            summary_html = "<br/>".join(summary_lines) or "No orders were affected."
            rec.message_post(body=(
                f"<b>Bulk payment confirmed.</b><br/>"
                f"Amount received: <b>{rec.amount_to_receive:.2f}</b><br/>{summary_html}"
            ))

    # ----------------- Sequence & Guards -----------------
    @api.model
    def create(self, vals):
        if vals.get("name", "New") == "New":
            vals["name"] = self.env["ir.sequence"].next_by_code("idil.waiter.bulk.payment.seq") or "WBP/0001"
        return super().create(vals)

    def write(self, vals):
        for rec in self:
            if rec.state == "confirmed":
                forbidden = set(vals.keys()) - {"message_follower_ids"}
                if forbidden:
                    raise ValidationError("This record is confirmed and cannot be modified.")
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.state == "confirmed":
                raise ValidationError("Confirmed bulk payments cannot be deleted.")
        return super().unlink()


class WaiterBulkPaymentLine(models.Model):
    _name = "idil.waiter.bulk.payment.line"
    _description = "Bulk Waiter Payment Allocation Line"

    bulk_payment_id = fields.Many2one("idil.waiter.bulk.payment", string="Bulk Payment", ondelete="cascade")

    place_order_id = fields.Many2one("idil.customer.place.order", string="Place Order", required=True)
    order_date = fields.Datetime(related="place_order_id.order_date", store=True)
    customer_id = fields.Many2one(related="place_order_id.customer_id", store=True, readonly=True)

    total_amount = fields.Float(string="Order Total", store=True)
    paid_amount = fields.Float(string="Already Paid", store=True)
    remaining_amount = fields.Float(string="Remaining", store=True)
    paid_now = fields.Float(string="Pay Now", store=True)

    currency_id = fields.Many2one("res.currency", related="bulk_payment_id.currency_id", store=True, readonly=True)

    @api.onchange("place_order_id")
    def _onchange_place_order_id(self):
        po = self.place_order_id
        if po:
            total = po.total_price or 0.0
            paid = po.paid_amount or 0.0
            due = max(total - paid, 0.0)
            self.total_amount = total
            self.paid_amount = paid
            self.remaining_amount = due
            self.paid_now = 0.0
        else:
            self.total_amount = 0.0
            self.paid_amount = 0.0
            self.remaining_amount = 0.0
            self.paid_now = 0.0


class WaiterBulkPaymentMethod(models.Model):
    _name = "idil.waiter.bulk.payment.method"
    _description = "Bulk Waiter Payment Method"

    bulk_payment_id = fields.Many2one("idil.waiter.bulk.payment", string="Bulk Payment", ondelete="cascade")
    payment_account_id = fields.Many2one(
        "idil.chart.account",
        string="Payment Account",
        required=True,
        domain=[("account_type", "in", ["cash", "bank_transfer", "sales_expense"])],
    )
    payment_amount = fields.Float(string="Amount", required=True)
    note = fields.Char(string="Memo/Reference")
