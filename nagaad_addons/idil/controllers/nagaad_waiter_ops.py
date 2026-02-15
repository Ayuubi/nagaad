# -*- coding: utf-8 -*-
import datetime
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


def force_session(sid):
    """Keep as-is (optional). You are using auth='none' and passing user_id anyway."""
    if sid:
        request.session.sid = sid


def _get_uid(user_id=None):
    """Single source of truth for UID in all endpoints."""
    try:
        uid = int(user_id or request.session.uid or 0)
    except Exception:
        uid = 0
    return uid


def _line_env(uid):
    """
    ✅ Critical fix:
    Always do ORM operations with sudo() for access BUT with_user(uid) for tracking,
    so create_uid/write_uid are stamped correctly by Odoo (no SQL needed).
    """
    return request.env["idil.customer.place.order.line"].sudo().with_user(uid)


def _order_env(uid):
    """Same rule for orders when we need write_uid stamping."""
    return request.env["idil.customer.place.order"].sudo().with_user(uid)


class NagaadWaiterOps(http.Controller):

    @http.route("/nagaad/api/get_waiter_orders", type="json", auth="none", csrf=False, cors="*")
    def get_waiter_orders(self, user_id=None, session_id=None, **kwargs):
        force_session(session_id)
        uid = _get_uid(user_id)
        if not uid:
            return {"status": "error", "message": "Unauthorized"}

        _logger.warning("🔍 WAITER FETCH: uid=%s (SID=%s)", uid, session_id)

        try:
            # Keep your business logic/domain as-is
            domain = [
                # '|', ('waiter_id', '=', int(uid)), ('create_uid', '=', int(uid)),
                ("state", "in", ["draft", "confirmed"])
            ]

            total_matches = request.env["idil.customer.place.order"].sudo().search_count(domain)
            _logger.warning("📊 Orders Found for UID %s: %s", uid, total_matches)

            orders = request.env["idil.customer.place.order"].sudo().search(domain, order="create_date desc")

            product_list = request.env["my_product.product"].sudo().search_read(
                [("available_in_pos", "=", True)],
                ["id", "name", "sale_price"],
                limit=1000,
            )

            orders_by_date = {}
            for o in orders:
                if not o.create_date:
                    continue
                try:
                    d = o.create_date.strftime("%Y-%m-%d")
                except Exception:
                    d = str(o.create_date)[:10]

                orders_by_date.setdefault(d, [])

                lines = []
                for l in o.order_lines:
                    lines.append({
                        "id": l.id,
                        "product_id": [l.product_id.id, l.product_id.name],
                        "quantity": l.quantity,
                        "kitchen_printed_qty": l.kitchen_printed_qty,
                        "sale_price": l.sale_price,
                        "line_total": l.line_total,
                        "menu_name": l.menu_name,
                        "status": l.status,
                    })

                orders_by_date[d].append({
                    "id": o.id,
                    "name": o.name,
                    "state": o.state,
                    "customer_id": [o.customer_id.id, o.customer_id.name],
                    "waiter_id": [o.waiter_id.id, o.waiter_id.name],
                    "order_mode": o.order_mode,
                    "table_no": o.table_no,
                    "total_price": o.total_price,
                    "create_date": str(o.create_date),
                    "lines": lines,
                })

            return {"status": "success", "orders_by_date": orders_by_date, "product_list": product_list}

        except Exception as e:
            _logger.exception("❌ get_waiter_orders Error")
            return {"status": "error", "message": str(e)}

    @http.route("/nagaad/api/update_order_line", type="json", auth="none", csrf=False, cors="*")
    def update_order_line(self, line_id, quantity, user_id=None, session_id=None, **kwargs):
        force_session(session_id)
        uid = _get_uid(user_id)
        if not uid:
            return {"status": "error", "message": "Unauthorized"}

        try:
            # Ensure env user is set early
            request.update_env(user=uid)

            line = request.env["idil.customer.place.order.line"].sudo().browse(int(line_id))
            if not line.exists():
                return {"status": "error", "message": "Line not found"}

            if line.order_id.state != "draft":
                return {"status": "error", "message": "Cannot edit confirmed orders."}

            # ✅ Correct stamping (no SQL)
            env_line = _line_env(uid)
            env_line.browse(line.id).write({"quantity": float(quantity)})

            return {"status": "success"}

        except Exception as e:
            _logger.exception("❌ update_order_line Error")
            return {"status": "error", "message": str(e)}

    @http.route("/nagaad/api/delete_order_line", type="json", auth="none", csrf=False, cors="*")
    def delete_order_line(self, line_id, user_id=None, session_id=None, **kwargs):
        force_session(session_id)
        uid = _get_uid(user_id)
        if not uid:
            return {"status": "error", "message": "Unauthorized"}

        try:
            request.update_env(user=uid)

            line = request.env["idil.customer.place.order.line"].sudo().browse(int(line_id))
            if not line.exists():
                return {"status": "error", "message": "Line not found"}

            if line.order_id.state != "draft":
                return {"status": "error", "message": "Cannot delete items from confirmed orders."}

            # ✅ Correct stamping (unlink executed as uid)
            env_line = _line_env(uid)
            env_line.browse(line.id).unlink()

            return {"status": "success"}

        except Exception as e:
            _logger.exception("❌ delete_order_line Error")
            return {"status": "error", "message": str(e)}

    @http.route("/nagaad/api/add_order_line", type="json", auth="none", csrf=False, cors="*")
    def add_order_line(self, order_id, product_id, quantity, user_id=None, session_id=None, **kwargs):
        force_session(session_id)
        uid = _get_uid(user_id)
        if not uid:
            return {"status": "error", "message": "Unauthorized"}

        _logger.warning("🧾 ADD LINE: params=%s uid=%s sid=%s",
                        {"order_id": order_id, "product_id": product_id, "quantity": quantity}, uid, session_id)

        try:
            request.update_env(user=uid)

            oid = int(order_id)
            pid = int(product_id)
            qty = float(quantity)

            order = request.env["idil.customer.place.order"].sudo().browse(oid)
            if not order.exists():
                return {"status": "error", "message": "Order not found"}

            if order.state != "draft":
                return {"status": "error", "message": "Cannot edit confirmed orders."}

            # Use sudo() for access rights (Avoids "read access" errors)
            Line = request.env["idil.customer.place.order.line"].sudo()
            existing = Line.search([("order_id", "=", order.id), ("product_id", "=", pid)], limit=1)

            if existing:
                existing.write({
                    "quantity": (existing.quantity or 0.0) + qty,
                    "kitchen_printed_qty": (existing.kitchen_printed_qty or 0.0) + qty,
                    "status": "add",
                })
                # FORCE update write_uid (fix for attribution when using sudo)
                request.env.cr.execute("UPDATE idil_customer_place_order_line SET write_uid=%s WHERE id=%s", (uid, existing.id))
            else:
                line = Line.create({
                    "order_id": order.id,
                    "product_id": pid,
                    "quantity": qty,
                    "kitchen_printed_qty": qty,
                    "status": "add",
                })
                # FORCE update create_uid and write_uid (fix for attribution when using sudo)
                request.env.cr.execute("UPDATE idil_customer_place_order_line SET create_uid=%s, write_uid=%s WHERE id=%s", (uid, uid, line.id))
                request.env.cr.commit()
                
            return {"status": "success"}

        except Exception as e:
            _logger.exception("❌ add_order_line Error")
            return {"status": "error", "message": str(e)}

    @http.route("/nagaad/api/confirm_print", type="json", auth="none", csrf=False, cors="*")
    def confirm_print(self, order_id, user_id=None, session_id=None, **kwargs):
        force_session(session_id)
        uid = _get_uid(user_id)
        if not uid:
            return {"status": "error", "message": "Unauthorized"}

        try:
            request.update_env(user=uid)

            order = request.env["idil.customer.place.order"].sudo().browse(int(order_id))
            if not order.exists():
                return {"status": "error", "message": "Order not found"}

            # Use sudo() to guarantee write access (Avoids permission errors for waiters)
            Line = request.env["idil.customer.place.order.line"].sudo()
            lines = Line.search([("order_id", "=", order.id)])

            for line in lines:
                updated = False
                if (line.kitchen_printed_qty or 0.0) > 0:
                    line.write({"kitchen_printed_qty": 0.0, "status": "normal"})
                    updated = True
                elif line.status == "add":
                    line.write({"status": "normal"})
                    updated = True

                if updated:
                    # FORCE update write_uid (fix attribution)
                    request.env.cr.execute("UPDATE idil_customer_place_order_line SET write_uid=%s WHERE id=%s", (uid, line.id))

            return {"status": "success"}

        except Exception as e:
            _logger.exception("❌ confirm_print Error")
            return {"status": "error", "message": str(e)}

    @http.route("/nagaad/api/get_kitchen_orders", type="json", auth="none", csrf=False, cors="*")
    def get_kitchen_orders(self, user_id=None, session_id=None, **kwargs):
        force_session(session_id)
        uid = _get_uid(user_id)
        if not uid:
            return {"status": "error", "message": "Unauthorized"}

        _logger.warning("🔍 KITCHEN FETCH: uid=%s (SID=%s)", uid, session_id)

        try:
            orders = request.env["idil.customer.place.order"].sudo().search_read(
                [("state", "!=", "confirmed")],
                ["id", "customer_id", "order_lines", "create_date", "state", "total_price", "order_mode", "table_no",
                 "waiter_id"],
                order="id desc",
                limit=100,
            )

            # Keep your current output format
            for o in orders:
                line_ids = o.get("order_lines") or []
                lines = request.env["idil.customer.place.order.line"].sudo().search_read(
                    [("id", "in", line_ids)],
                    ["id", "product_id", "quantity", "sale_price", "line_total", "menu_name"],
                )
                o["lines"] = lines

            return {"status": "success", "orders": orders}

        except Exception as e:
            _logger.exception("❌ get_kitchen_orders Error")
            return {"status": "error", "message": str(e)}

    @http.route("/nagaad/api/confirm_order", type="json", auth="none", csrf=False, cors="*")
    def confirm_order(self, order_id, user_id=None, session_id=None, **kwargs):
        force_session(session_id)
        uid = _get_uid(user_id)
        if not uid:
            return {"status": "error", "message": "Unauthorized"}

        try:
            request.update_env(user=uid)

            order = request.env["idil.customer.place.order"].sudo().browse(int(order_id))
            if not order.exists():
                return {"status": "error", "message": "Order not found"}

            # DR: Receivable (keep your logic)
            creator_emp = request.env["idil.employee"].sudo().search(
                [("user_id", "=", order.waiter_id.id or order.create_uid.id)],
                limit=1,
            )
            receivable_id = creator_emp.receivable_account_id.id
            if not receivable_id:
                return {"status": "error", "message": "Account Error: Order creator has no receivable account."}

            booking = request.env["idil.transaction_booking"].sudo().create({
                "customer_id": order.customer_id.id,
                "sale_order_id": order.id,
                "bank_reff": 0,
                "reffno": order.name or str(order.id),
                "amount": order.total_price,
                "trx_date": datetime.date.today(),
            })

            request.env["idil.transaction_bookingline"].sudo().create({
                "transaction_booking_id": booking.id,
                "account_number": receivable_id,
                "transaction_type": "dr",
                "dr_amount": order.total_price,
                "cr_amount": 0,
                "bank_reff": 0,
            })

            for line in order.order_lines:
                income_id = line.product_id.income_account_id.id
                if not income_id:
                    raise Exception(f"Income account missing for product: {line.product_id.name}")
                request.env["idil.transaction_bookingline"].sudo().create({
                    "transaction_booking_id": booking.id,
                    "account_number": income_id,
                    "transaction_type": "cr",
                    "dr_amount": 0,
                    "cr_amount": line.line_total,
                    "product_id": line.product_id.id,
                    "bank_reff": 0,
                })

            # ✅ Ensure write_uid is the real uid when confirming
            # Use sudo() for access, then SQL for attribution
            order.sudo().write({
                "state": "confirmed",
                "confirmed_by": uid,
                "confirmed_at": datetime.datetime.now(),
            })
            
            # FORCE update write_uid just in case
            request.env.cr.execute("UPDATE idil_customer_place_order SET write_uid=%s WHERE id=%s", (uid, order.id))
            
            request.env.cr.commit()

            return {"status": "success"}

        except Exception as e:
            request.env.cr.rollback()
            _logger.exception("❌ confirm_order Error")
            return {"status": "error", "message": str(e)}
