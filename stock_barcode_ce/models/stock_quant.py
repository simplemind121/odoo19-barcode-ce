from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .barcode_security import bc_guard, bc_is_supervisor, bc_require_supervisor


class StockQuant(models.Model):
    _inherit = "stock.quant"

    # Counting session = quants with inventory_quantity_set by the current user.

    @api.model
    def _bc_inv_clean_ctx(self, ctx):
        ctx = dict(ctx or {})
        return {
            "location_id": ctx.get("location_id") or False,
            "package_id": ctx.get("package_id") or False,
            "pending_product_id": ctx.get("pending_product_id") or False,
            "last_quant_id": ctx.get("last_quant_id") or False,
            "all_users": bool(ctx.get("all_users")) and bc_is_supervisor(self.env),
        }

    @api.model
    def _bc_inv_default_location(self):
        warehouse = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        return warehouse.lot_stock_id

    @api.model
    def _bc_my_counted(self, all_users=False):
        """Counts of the current user; supervisors can review everybody's counts."""
        user_domain = [] if all_users else [("user_id", "=", self.env.uid)]
        return self.search(user_domain + [
            ("inventory_quantity_set", "=", True),
            ("location_id.usage", "in", ["internal", "transit"]),
            ("company_id", "in", self.env.companies.ids),
        ])

    @api.model
    def bc_inv_state(self, ctx=None, feedback=None):
        self = bc_guard(self)
        ctx = self._bc_inv_clean_ctx(ctx)
        location = self.env["stock.location"].browse(ctx["location_id"]) if ctx["location_id"] else self.env["stock.location"]
        counted = self._bc_my_counted(ctx.get("all_users"))
        expected = self.browse()
        if location:
            expected = self.search([
                ("location_id", "=", location.id), ("quantity", "!=", 0),
                ("id", "not in", counted.ids)])

        def row(q, is_counted):
            return {
                "id": q.id,
                "product_id": q.product_id.id,
                "product": q.product_id.display_name,
                "barcode": q.product_id.barcode or "",
                "tracking": q.product_id.tracking,
                "lot": q.lot_id.name or "",
                "package": q.package_id.name or "",
                "location": q.location_id.display_name,
                "location_id": q.location_id.id,
                "uom": q.product_uom_id.name,
                "quantity": q.quantity,
                "counted": q.inventory_quantity if is_counted else 0.0,
                "is_counted": is_counted,
                "diff": (q.inventory_quantity - q.quantity) if is_counted else 0.0,
                "user": q.user_id.name or "",
            }

        return {
            "ctx": dict(ctx, location_name=location.display_name if location else "",
                        package_name=self.env["stock.package"].browse(ctx["package_id"]).name if ctx["package_id"] else "",
                        pending_product_name=self.env["product.product"].browse(ctx["pending_product_id"]).display_name
                        if ctx["pending_product_id"] else ""),
            "counted": [row(q, True) for q in counted.sorted(lambda q: (q.location_id.complete_name, q.product_id.display_name))],
            "expected": [row(q, False) for q in expected.sorted(lambda q: q.product_id.display_name)],
            "feedback": feedback or False,
            "is_supervisor": bc_is_supervisor(self.env),
            "can_create_product": self.env(su=False)["product.template"].has_access("create"),
        }

    @api.model
    def bc_inv_scan(self, barcode, ctx=None):
        self = bc_guard(self)
        ctx = self._bc_inv_clean_ctx(ctx)
        res = self.env["stock.barcode.resolver"].resolve(barcode)
        try:
            with self.env.cr.savepoint():
                feedback = self._bc_inv_dispatch(res, ctx)
        except (UserError, ValidationError, AccessError) as e:
            feedback = {"level": "danger", "message": e.args[0] if e.args else str(e)}
        quant = self.browse(feedback.get("quant_id") or []).exists()
        self._bc_inv_log("inv_scan", feedback, quant, barcode=res.get("barcode"),
                         resolved_type=self.env["stock.barcode.resolver"]._type_of(res),
                         quantity=(res.get("qty") or 1.0) if quant else 0.0,
                         location_id=ctx.get("location_id") or False)
        return self.bc_inv_state(ctx, feedback)

    @api.model
    def _bc_inv_log(self, operation, feedback, quant=None, **vals):
        if quant:
            vals.setdefault("product_id", quant.product_id.id)
            vals.setdefault("lot_name", quant.lot_id.name or "")
            vals.setdefault("location_id", quant.location_id.id)
            vals.setdefault("package_name", quant.package_id.name or "")
            vals.setdefault("quant_id", quant.id)
        if feedback:
            vals.setdefault("level", feedback.get("level") if feedback.get("level") in ("success", "info", "warning", "danger") else "info")
            vals.setdefault("message", feedback.get("message"))
        self.env["stock.barcode.scan.log"]._bc_write(operation, **vals)

    @api.model
    def _bc_inv_dispatch(self, res, ctx):
        if res.get("command"):
            if res["command"] in ("O-BTN.VALIDATE", "O-CMD.VALIDATE", "O-BTN.APPLY"):
                bc_require_supervisor(self.env, _("apply inventory counts"))
                count = self._bc_inv_apply()
                return {"level": "success", "message": _("%s count(s) applied", count)}
            if res["command"] in ("O-BTN.DISCARD", "O-CMD.DISCARD", "O-CMD.RESET"):
                ctx.update(location_id=False, package_id=False, pending_product_id=False)
                return {"level": "info", "message": _("Scan context cleared.")}
            return {"level": "warning", "message": _("Unknown command %s", res["command"])}
        if res.get("location"):
            loc = res["location"]
            if loc.usage not in ("internal", "transit"):
                return {"level": "danger", "message": _("%s is not a stock location.", loc.display_name)}
            ctx["location_id"] = loc.id
            ctx["package_id"] = False
            return {"level": "success", "message": _("Counting in %s", loc.display_name)}
        if res.get("gs1"):
            if res.get("location"):
                ctx["location_id"] = res["location"].id
            if res.get("unknown_product"):
                return {"level": "danger", "message": _("Unknown product GTIN %s", res["unknown_product"]),
                        "unknown_barcode": str(res["unknown_product"]).lstrip("0")}
            if res.get("product"):
                return self._bc_inv_count(res["product"], res.get("qty") or 1.0, ctx,
                                          lot=res.get("lot"), lot_name=None if res.get("lot") else res.get("lot_name"),
                                          expiration_date=res.get("expiration_date"))
        if res.get("package") or res.get("package_name"):
            package = res.get("package") or self.env["stock.package"].create({"name": res["package_name"]})
            if package.quant_ids and not ctx.get("pending_product_id"):
                # count the whole package as it is
                for quant in package.quant_ids:
                    quant.with_context(inventory_mode=True).write({"inventory_quantity": quant.quantity})
                    quant.write({"user_id": self.env.uid, "inventory_quantity_set": True})
                ctx["location_id"] = package.location_id.id
                return {"level": "success", "message": _("Package %s counted as complete", package.name)}
            ctx["package_id"] = package.id
            return {"level": "success", "message": _("Counting into package %s", package.name)}
        if res.get("product"):
            lot = res.get("lot") if res.get("lot") and len(res["lot"]) == 1 else None
            return self._bc_inv_count(res["product"], res.get("qty") or 1.0, ctx, lot=lot)
        if res.get("unknown") and ctx.get("pending_product_id"):
            product = self.env["product.product"].browse(ctx["pending_product_id"])
            return self._bc_inv_count(product, 1.0, ctx, lot_name=res["barcode"])
        return {"level": "danger", "message": _("Unknown barcode: %s", res["barcode"]), "unknown_barcode": res["barcode"]}

    @api.model
    def _bc_inv_count(self, product, qty, ctx, lot=None, lot_name=None, expiration_date=None):
        if not product.is_storable:
            return {"level": "danger", "message": _("%s is not tracked in inventory.", product.display_name)}
        location = self.env["stock.location"].browse(ctx["location_id"]) if ctx.get("location_id") else self._bc_inv_default_location()
        ctx["location_id"] = location.id
        if product.tracking != "none" and not lot and not lot_name:
            ctx["pending_product_id"] = product.id
            return {"level": "warning", "need_lot": True,
                    "message": _("%s is tracked: scan its lot/serial number.", product.display_name)}
        ctx["pending_product_id"] = False
        if lot_name:
            lot = self.env["stock.lot"].search([
                ("name", "=", lot_name), ("product_id", "=", product.id),
                ("company_id", "in", [self.env.company.id, False])], limit=1)
            if not lot:
                vals = {"name": lot_name, "product_id": product.id, "company_id": self.env.company.id}
                if expiration_date and "expiration_date" in self.env["stock.lot"]._fields:
                    vals["expiration_date"] = fields.Datetime.to_datetime(expiration_date)
                lot = self.env["stock.lot"].create(vals)
        if product.tracking == "serial":
            qty = 1.0
        package = self.env["stock.package"].browse(ctx["package_id"]) if ctx.get("package_id") else self.env["stock.package"]
        quant = self.search([
            ("product_id", "=", product.id), ("location_id", "=", location.id),
            ("lot_id", "=", lot.id if lot else False), ("package_id", "=", package.id or False),
            ("owner_id", "=", False)], limit=1)
        if not quant:
            quant = self.with_context(inventory_mode=True).create({
                "product_id": product.id,
                "location_id": location.id,
                "lot_id": lot.id if lot else False,
                "package_id": package.id or False,
                "inventory_quantity": 0.0,
            })
        if product.tracking == "serial" and quant.inventory_quantity_set and quant.inventory_quantity >= 1:
            return {"level": "danger", "message": _("Serial number %s has already been counted.", lot.name)}
        new_qty = (quant.inventory_quantity if quant.inventory_quantity_set else 0.0) + qty
        quant.with_context(inventory_mode=True).write({"inventory_quantity": new_qty})
        quant.write({"inventory_quantity_set": True, "user_id": self.env.uid})
        ctx["last_quant_id"] = quant.id
        return {"level": "success", "quant_id": quant.id,
                "message": _("%(product)s: %(qty)s counted in %(loc)s", product=product.display_name,
                             qty=new_qty, loc=location.display_name)}

    @api.model
    def bc_inv_set_qty(self, quant_id, qty, ctx=None):
        self = bc_guard(self)
        quant = self.browse(quant_id).exists()
        if quant:
            self._bc_inv_log("inv_set_qty", {"level": "success", "message": ""}, quant, quantity=max(qty, 0.0),
                             old_quantity=quant.inventory_quantity if quant.inventory_quantity_set else 0.0)
            if quant.product_id.tracking == "serial" and qty > 1:
                return self.bc_inv_state(ctx, {"level": "danger", "message": _("A serial number can only be counted once.")})
            quant.with_context(inventory_mode=True).write({"inventory_quantity": max(qty, 0.0)})
            quant.write({"inventory_quantity_set": True, "user_id": self.env.uid})
        return self.bc_inv_state(ctx, {"level": "success", "message": _("Quantity updated")})

    @api.model
    def bc_inv_clear(self, quant_id, ctx=None):
        self = bc_guard(self)
        quant = self.browse(quant_id).exists()
        if quant:
            self._bc_inv_log("inv_clear", {"level": "info", "message": ""}, quant,
                             old_quantity=quant.inventory_quantity)
            quant.action_clear_inventory_quantity()
        return self.bc_inv_state(ctx, {"level": "info", "message": _("Count removed")})

    @api.model
    def bc_inv_zero_uncounted(self, ctx=None):
        self = bc_guard(self)
        ctx = self._bc_inv_clean_ctx(ctx)
        if not bc_is_supervisor(self.env):
            return self.bc_inv_state(ctx, {"level": "danger", "message": _("Only a barcode supervisor can set uncounted products to zero.")})
        if not ctx["location_id"]:
            return self.bc_inv_state(ctx, {"level": "warning", "message": _("Scan a location first.")})
        quants = self.search([
            ("location_id", "=", ctx["location_id"]), ("quantity", "!=", 0),
            ("inventory_quantity_set", "=", False)])
        for quant in quants:
            quant.with_context(inventory_mode=True).write({"inventory_quantity": 0.0})
            quant.write({"inventory_quantity_set": True, "user_id": self.env.uid})
        fb = {"level": "warning", "message": _("%s uncounted line(s) set to 0", len(quants))}
        self._bc_inv_log("inv_zero", fb, location_id=ctx["location_id"], quantity=len(quants))
        return self.bc_inv_state(ctx, fb)

    @api.model
    def _bc_inv_apply(self, all_users=False):
        quants = self._bc_my_counted(all_users)
        if not quants:
            raise UserError(_("Nothing has been counted yet."))
        count = len(quants)
        quants.with_context(inventory_name=_("Barcode count"))._apply_inventory()
        return count

    @api.model
    def bc_inv_apply(self, ctx=None):
        self = bc_guard(self)
        try:
            with self.env.cr.savepoint():
                bc_require_supervisor(self.env, _("apply inventory counts"))
                count = self._bc_inv_apply(self._bc_inv_clean_ctx(ctx)["all_users"])
        except (UserError, ValidationError, AccessError) as e:
            fb = {"level": "danger", "message": e.args[0]}
            self._bc_inv_log("inv_apply", fb)
            return self.bc_inv_state(ctx, fb)
        fb = {"level": "success", "message": _("%s count(s) applied", count), "applied": True}
        self._bc_inv_log("inv_apply", fb, quantity=count)
        return self.bc_inv_state(ctx, fb)
