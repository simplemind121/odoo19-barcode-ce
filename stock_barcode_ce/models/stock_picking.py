from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

from .barcode_security import bc_guard, bc_is_supervisor, bc_require_supervisor

CTX_KEYS = (
    "source_location_id", "dest_location_id", "result_package_id",
    "pending_line_ids", "last_line_id", "pending_product_id",
)


def _clean_ctx(ctx):
    ctx = dict(ctx or {})
    out = {k: ctx.get(k) or False for k in CTX_KEYS}
    out["pending_line_ids"] = list(ctx.get("pending_line_ids") or [])
    return out


class StockPicking(models.Model):
    _inherit = "stock.picking"

    # ==================================================================
    # Public API (called by the client action). Batches reuse the same
    # engine through `_bc_*` helpers operating on several pickings.
    # ==================================================================
    def bc_get_state(self, ctx=None):
        return bc_guard(self)._bc_state(_clean_ctx(ctx))

    def bc_scan(self, barcode, ctx=None, uuid=None):
        return bc_guard(self)._bc_scan_idempotent(barcode, _clean_ctx(ctx), uuid)

    def bc_set_qty(self, line_id, qty, ctx=None):
        rec = bc_guard(self).with_context(bc_event={"kind": "manual"})
        return rec._bc_notify_after(rec._bc_set_qty(line_id, qty, _clean_ctx(ctx)))

    def bc_set_move_qty(self, move_id, qty, ctx=None):
        rec = bc_guard(self).with_context(bc_event={"kind": "manual"})
        return rec._bc_notify_after(rec._bc_set_move_qty(move_id, qty, _clean_ctx(ctx)))

    def bc_add_product(self, product_id, qty=1.0, ctx=None):
        rec = bc_guard(self).with_context(bc_event={"kind": "manual"})
        return rec._bc_notify_after(rec._bc_add_product(product_id, qty, _clean_ctx(ctx)))

    def bc_put_in_pack(self, ctx=None):
        rec = bc_guard(self)
        return rec._bc_notify_after(rec._bc_put_in_pack_api(_clean_ctx(ctx)))

    def bc_validate(self, force=False, backorder=None, expired_ok=False):
        rec = bc_guard(self)
        if expired_ok:
            if not bc_is_supervisor(rec.env):
                return {"level": "danger", "message": _("Only a barcode supervisor can validate expired lots.")}
            rec = rec.with_context(skip_expired=True)
        res = rec._bc_validate(force=force, backorder=backorder)
        rec._bc_notify()
        return res

    # ------------------------------------------------------------------
    # idempotency, live updates, presence
    # ------------------------------------------------------------------
    def _bc_scan_idempotent(self, barcode, ctx, uuid=None):
        Log = self.env["stock.barcode.scan.log"]
        if uuid and Log._bc_seen(uuid):
            # re-sent after a network failure: already counted
            return self._bc_state(ctx, self._bc_feedback("info", _("Already recorded."), duplicate=True))
        rec = self.with_context(bc_event={"kind": "scan", "uuid": uuid})
        return rec._bc_notify_after(rec._bc_scan(barcode, ctx))

    @api.model
    def _bc_channel(self, record):
        return "stock_barcode_ce.%s.%s" % (record._name, record.id)

    def _bc_notify(self):
        """Tell the other scanners of these transfers to refresh (payload holds no business data)."""
        Bus = self.env["bus.bus"].sudo()
        payload = {"user_id": self.env.uid, "user": self.env.user.name, "device": self.env.context.get("bc_device") or ""}
        for picking in self:
            Bus._sendone(self._bc_channel(picking), "stock_barcode_ce/update", dict(payload, picking_id=picking.id))
        for batch in self.batch_id:
            Bus._sendone(self._bc_channel(batch), "stock_barcode_ce/update", dict(payload, batch_id=batch.id))

    def _bc_notify_after(self, state):
        self._bc_notify()
        return state

    def _bc_presence(self):
        """Other users who scanned these transfers in the last 2 minutes."""
        since = fields.Datetime.subtract(fields.Datetime.now(), minutes=2)
        domain = [("create_date", ">=", since), ("user_id", "!=", self.env.uid)]
        domain += ["|", ("picking_id", "in", self.ids), ("batch_id", "in", self.batch_id.ids)] if self.batch_id else [("picking_id", "in", self.ids)]
        groups = self.env["stock.barcode.scan.log"].sudo()._read_group(domain, ["user_id"], ["create_date:max"])
        now = fields.Datetime.now()
        return [{"user": user.name, "seconds": int((now - last).total_seconds())} for user, last in groups]


    # ------------------------------------------------------------------
    # rules & logging helpers
    # ------------------------------------------------------------------
    def _bc_rule(self, name):
        """True when the rule is enabled on any operation type of the pickings."""
        return any(p.picking_type_id[name] for p in self)

    def _bc_manual_allowed(self):
        return not self._bc_rule("bc_scan_only") or bc_is_supervisor(self.env)

    def _bc_log(self, operation, feedback=None, **vals):
        pickings = self
        if len(pickings) == 1:
            vals.setdefault("picking_id", pickings.id)
        elif pickings[:1].batch_id:
            vals.setdefault("batch_id", pickings[:1].batch_id.id)
        vals.setdefault("picking_type_id", pickings[:1].picking_type_id.id)
        if feedback:
            vals.setdefault("level", feedback.get("level") if feedback.get("level") in ("success", "info", "warning", "danger") else "info")
            vals.setdefault("message", feedback.get("message"))
        self.env["stock.barcode.scan.log"]._bc_write(operation, **vals)

    def _bc_add_product(self, product_id, qty, ctx):
        product = self.env["product.product"].browse(product_id)
        if not self._bc_manual_allowed():
            feedback = self._bc_feedback("danger", _("This operation must be scanned: adding products by hand is not allowed."))
        else:
            try:
                with self.env.cr.savepoint():
                    feedback = self._bc_process_product(product, qty or 1.0, ctx)
            except (UserError, ValidationError) as e:
                feedback = self._bc_feedback("danger", e.args[0] if e.args else str(e))
        self._bc_log("add_product", feedback, product_id=product.id, quantity=qty or 1.0)
        return self._bc_state(ctx, feedback)

    def _bc_put_in_pack_api(self, ctx):
        feedback = self._bc_put_in_pack(ctx)
        self._bc_log("pack", feedback)
        return self._bc_state(ctx, feedback)

    def bc_print(self, what="operations"):
        self = bc_guard(self)
        self.ensure_one()
        xmlid = {
            "operations": "stock.action_report_picking",
            "delivery": "stock.action_report_delivery",
            "labels": False,
        }.get(what, "stock.action_report_picking")
        if what == "labels":
            products = self.move_ids.product_id
            return {
                "type": "ir.actions.act_window",
                "res_model": "product.label.layout",
                "views": [(False, "form")],
                "target": "new",
                "name": _("Print labels"),
                "context": {
                    "default_product_ids": products.ids,
                    "default_move_ids": self.move_ids.ids,
                    "default_move_quantity": "move",
                    "default_print_format": "th40x30",
                },
            }
        return self.env.ref(xmlid).report_action(self, config=False)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _bc_open_pickings(self):
        return self.filtered(lambda p: p.state not in ("done", "cancel"))

    def _bc_uses_lots(self, product):
        if product.tracking == "none":
            return False
        types = self.picking_type_id
        return any(t.use_create_lots or t.use_existing_lots for t in types)

    def _bc_is_receipt(self):
        return all(p.picking_type_code == "incoming" for p in self)

    @api.model
    def _bc_feedback(self, level, message, **extra):
        res = {"level": level, "message": message}
        res.update(extra)
        return res

    # ------------------------------------------------------------------
    # state
    # ------------------------------------------------------------------
    def _bc_state(self, ctx, feedback=None, action=None):
        pickings = self
        first = pickings[:1]
        lines_by_move = []
        prec = self.env["decimal.precision"].precision_get("Product Unit")
        moves = pickings.move_ids.filtered(lambda m: m.state != "cancel").sorted(lambda m: (m.picking_id.id, m.sequence, m.id))
        total_demand = total_done = 0.0
        for move in moves:
            lines = []
            for ml in move.move_line_ids.sorted("id"):
                lines.append({
                    "id": ml.id,
                    "reserved": ml.quantity if ml.state != "done" else ml.quantity,
                    "bc_qty": ml.quantity if move.state == "done" else ml.bc_qty,
                    "lot": ml.lot_id.name or ml.lot_name or "",
                    "location": ml.location_id.display_name,
                    "location_id": ml.location_id.id,
                    "location_dest": ml.location_dest_id.display_name,
                    "location_dest_id": ml.location_dest_id.id,
                    "package": ml.package_id.name or "",
                    "result_package": ml.result_package_id.name or "",
                    "dest_confirmed": ml.bc_dest_confirmed,
                })
            done = sum(line["bc_qty"] for line in lines)
            demand = move.product_uom_qty
            total_demand += demand
            total_done += done
            product = move.product_id
            pack_codes = []
            if "product.uom" in self.env:
                for pack in self.env["product.uom"].search([("product_id", "=", product.id), ("barcode", "!=", False)]):
                    pack_codes.append([pack.barcode, pack.uom_id._compute_quantity(1.0, product.uom_id)])
            lines_by_move.append({
                "move_id": move.id,
                "pack_codes": pack_codes,
                "picking": move.picking_id.name,
                "product_id": product.id,
                "product": product.display_name,
                "barcode": product.barcode or "",
                "default_code": product.default_code or "",
                "tracking": product.tracking if pickings._bc_uses_lots(product) else "none",
                "uom": move.product_uom.name,
                "demand": demand,
                "done": done,
                "complete": float_compare(done, demand, precision_digits=prec) >= 0 and demand > 0,
                "over": float_compare(done, demand, precision_digits=prec) > 0,
                "lines": lines,
            })
        loc = lambda rec: {"id": rec.id, "name": rec.display_name} if rec else False  # noqa: E731
        state = {
            "model": self._name,
            "ids": pickings.ids,
            "name": ", ".join(pickings.mapped("name")),
            "state": first.state if len(pickings) == 1 else ("done" if all(p.state == "done" for p in pickings) else "assigned"),
            "code": first.picking_type_code,
            "picking_type": first.picking_type_id.display_name,
            "partner": first.partner_id.display_name or "",
            "origin": first.origin or "",
            "location": loc(first.location_id),
            "location_dest": loc(first.location_dest_id),
            "moves": lines_by_move,
            "total_demand": total_demand,
            "total_done": total_done,
            "ctx": self._bc_ctx_display(ctx),
            "feedback": feedback or False,
            "action": action or False,
            "multi_location": self.env.user.has_group("stock.group_stock_multi_locations"),
            "use_packages": self.env.user.has_group("stock.group_tracking_lot"),
            "show_lots": self.env.user.has_group("stock.group_production_lot"),
            "is_supervisor": bc_is_supervisor(self.env),
            "can_create_product": self.env(su=False)["product.template"].has_access("create"),
            "uid": self.env.uid,
            "presence": pickings._bc_presence(),
            "channels": [self._bc_channel(p) for p in pickings] + [self._bc_channel(b) for b in pickings.batch_id],
            "rules": {
                "manual_allowed": pickings._bc_manual_allowed(),
                "require_source": pickings._bc_rule("bc_require_source"),
                "require_dest": pickings._bc_rule("bc_require_dest"),
                "require_pack": pickings._bc_rule("bc_require_pack"),
            },
        }
        return state

    def _bc_ctx_display(self, ctx):
        out = dict(ctx)
        Location = self.env["stock.location"]
        if ctx.get("source_location_id"):
            out["source_location_name"] = Location.browse(ctx["source_location_id"]).display_name
        if ctx.get("dest_location_id"):
            out["dest_location_name"] = Location.browse(ctx["dest_location_id"]).display_name
        if ctx.get("result_package_id"):
            out["result_package_name"] = self.env["stock.package"].browse(ctx["result_package_id"]).name
        if ctx.get("pending_product_id"):
            out["pending_product_name"] = self.env["product.product"].browse(ctx["pending_product_id"]).display_name
        # drop ids of lines that no longer exist
        existing = self.env["stock.move.line"].browse(ctx.get("pending_line_ids") or []).exists()
        out["pending_line_ids"] = existing.ids
        return out

    # ------------------------------------------------------------------
    # scanning
    # ------------------------------------------------------------------
    def _bc_scan(self, barcode, ctx):
        pickings = self._bc_open_pickings()
        if not pickings:
            return self._bc_state(ctx, self._bc_feedback("warning", _("This transfer is already done.")))
        res = self.env["stock.barcode.resolver"].resolve(barcode)
        try:
            with self.env.cr.savepoint():
                feedback, action = pickings._bc_dispatch(res, ctx)
        except (UserError, ValidationError) as e:
            feedback, action = self._bc_feedback("danger", e.args[0] if e.args else str(e)), None
        line = self.env["stock.move.line"].browse(feedback.get("line_id") or []).exists()
        pickings._bc_log(
            "scan", feedback,
            barcode=res.get("barcode"),
            resolved_type=self.env["stock.barcode.resolver"]._type_of(res),
            product_id=(line.product_id or (res.get("product") if res.get("product") and len(res["product"]) == 1 else self.env["product.product"])).id,
            lot_name=(line.lot_id.name or line.lot_name) if line else (res.get("lot_name") or ""),
            location_id=(line.location_dest_id if line and line.bc_dest_confirmed else line.location_id).id if line else (res.get("location") or self.env["stock.location"]).id,
            quantity=(res.get("qty") or 1.0) if line else 0.0,
            move_line_id=line.id,
        )
        return self._bc_state(ctx, feedback, action)

    def _bc_dispatch(self, res, ctx):
        """Returns (feedback, action)."""
        if res.get("command"):
            return self._bc_command(res["command"], ctx)
        if res.get("gs1"):
            return self._bc_process_gs1(res, ctx), None
        if res.get("picking") or res.get("batch"):
            rec = res.get("picking") or res.get("batch")
            if rec in (self | self.batch_id):
                return self._bc_feedback("info", _("You are already in %s.", rec.name)), None
            return self._bc_feedback("info", _("Opening %s", rec.name), open={
                "model": rec._name, "id": rec.id}), None
        if res.get("location"):
            return self._bc_process_location(res["location"], ctx), None
        if res.get("product"):
            lot = res.get("lot") if res.get("lot") and len(res["lot"]) == 1 else None
            return self._bc_process_product(res["product"], res.get("qty") or 1.0, ctx, lot=lot), None
        if res.get("package") or res.get("package_name"):
            return self._bc_process_package(res.get("package"), res.get("package_name"), ctx), None
        if res.get("lot"):
            return self._bc_feedback("warning", _("Several products use lot %s: scan the product first.", res["barcode"])), None
        if res.get("picking_type"):
            return self._bc_feedback("warning", _("This is an operation type barcode.")), None
        # unknown code: it may be a new lot/serial for the product waiting for one
        if ctx.get("pending_product_id"):
            product = self.env["product.product"].browse(ctx["pending_product_id"])
            return self._bc_process_product(product, 1.0, ctx, lot_name=res["barcode"]), None
        return self._bc_feedback(
            "danger", _("Unknown barcode: %s", res["barcode"]), unknown_barcode=res["barcode"]), None

    # ------------------------------------------------------------------
    def _bc_command(self, command, ctx):
        if command in ("O-BTN.VALIDATE", "O-CMD.VALIDATE"):
            result = self._bc_validate()
            return self._bc_feedback(result.get("level", "success"), result.get("message", "")), result
        if command in ("O-BTN.DISCARD", "O-CMD.DISCARD", "O-CMD.RESET"):
            for key in CTX_KEYS:
                ctx[key] = [] if key == "pending_line_ids" else False
            return self._bc_feedback("info", _("Scan context cleared.")), None
        if command in ("O-BTN.PACK", "O-CMD.PACK"):
            return self._bc_put_in_pack(ctx), None
        if command in ("O-BTN.PRINT-OP", "O-CMD.PRINT"):
            return self._bc_feedback("info", _("Printing operations")), {"client": "do_action", "action": self[:1].bc_print("operations")}
        if command in ("O-BTN.PRINT-SLIP",):
            return self._bc_feedback("info", _("Printing delivery slip")), {"client": "do_action", "action": self[:1].bc_print("delivery")}
        if command in ("O-CMD.MAIN-MENU", "O-BTN.MAIN-MENU"):
            return self._bc_feedback("info", ""), {"client": "main_menu"}
        return self._bc_feedback("warning", _("Unknown command %s", command)), None

    # ------------------------------------------------------------------
    def _bc_process_location(self, location, ctx):
        src_ok = any(location._child_of(p.location_id) for p in self)
        dest_ok = any(location._child_of(p.location_dest_id) for p in self)
        pending = self.env["stock.move.line"].browse(ctx.get("pending_line_ids") or []).exists().filtered(
            lambda ml: ml.bc_qty > 0 and not ml.bc_dest_confirmed)
        is_receipt = self._bc_is_receipt()
        if location.usage == "view":
            return self._bc_feedback("danger", _("%s is a view location; scan a storable location.", location.display_name))
        if dest_ok and (pending or is_receipt or not src_ok):
            if pending:
                self._bc_apply_destination(pending, location)
                ctx["pending_line_ids"] = []
                ctx["dest_location_id"] = False
                return self._bc_feedback("success", _("%(count)s line(s) will be put in %(loc)s",
                                                      count=len(pending), loc=location.display_name))
            ctx["dest_location_id"] = location.id
            return self._bc_feedback("success", _("Destination: %s", location.display_name))
        if src_ok:
            ctx["source_location_id"] = location.id
            return self._bc_feedback("success", _("Picking from %s", location.display_name))
        return self._bc_feedback("danger", _("%s is not a valid location for this operation.", location.display_name))

    def _bc_apply_destination(self, lines, location):
        self = self.with_context(bc_event=dict(self.env.context.get("bc_event") or {}, kind="transfer"))
        lines = lines.with_env(self.env)
        MoveLine = self.env["stock.move.line"]
        for ml in lines:
            if float_compare(ml.bc_qty, ml.quantity, precision_rounding=ml.product_uom_id.rounding) < 0 and not ml.bc_created:
                # split the scanned part from the reserved/suggested line
                new = ml.copy({
                    "quantity": 0.0,
                    "bc_qty": ml.bc_qty,
                    "bc_created": True,
                    "move_id": ml.move_id.id,
                    "picking_id": ml.picking_id.id,
                    "location_dest_id": location.id,
                    "bc_dest_confirmed": True,
                    "lot_id": ml.lot_id.id,
                    "lot_name": ml.lot_name,
                })
                ml._bc_set(0.0)
                MoveLine |= new
            else:
                ml.write({"location_dest_id": location.id, "bc_dest_confirmed": True})
        return MoveLine

    # ------------------------------------------------------------------
    def _bc_process_gs1(self, res, ctx):
        messages = []
        if res.get("location"):
            fb = self._bc_process_location(res["location"], ctx)
            messages.append(fb["message"])
            if fb["level"] == "danger":
                return fb
        if res.get("package") or res.get("package_name"):
            if not res.get("product"):
                return self._bc_process_package(res.get("package"), res.get("package_name"), ctx)
            fb = self._bc_process_package(res.get("package"), res.get("package_name"), ctx, as_destination=True)
            messages.append(fb["message"])
        if res.get("unknown_product"):
            return self._bc_feedback("danger", _("Unknown product GTIN %s", res["unknown_product"]),
                                     unknown_barcode=str(res["unknown_product"]).lstrip("0"))
        if res.get("product"):
            fb = self._bc_process_product(
                res["product"], res.get("qty") or 1.0, ctx,
                lot=res.get("lot"), lot_name=None if res.get("lot") else res.get("lot_name"),
                expiration_date=res.get("expiration_date"))
            if messages and fb["level"] == "success":
                fb["message"] = " / ".join(messages + [fb["message"]])
            return fb
        if res.get("location_dest"):
            return self._bc_process_location(res["location_dest"], ctx)
        return self._bc_feedback("success", " / ".join(messages) or _("GS1 barcode read"))

    # ------------------------------------------------------------------
    def _bc_process_package(self, package, package_name, ctx, as_destination=False):
        Package = self.env["stock.package"]
        if package and not as_destination and package.quant_ids and any(
                package.location_id._child_of(p.location_id) for p in self):
            return self._bc_take_package(package, ctx)
        if not package:
            package = Package.create({"name": package_name})
        ctx["result_package_id"] = package.id
        pending = self.env["stock.move.line"].browse(ctx.get("pending_line_ids") or []).exists().filtered(
            lambda ml: ml.bc_qty > 0 and not ml.result_package_id)
        if pending:
            pending.result_package_id = package
        return self._bc_feedback("success", _("Packing into %s", package.name))

    def _bc_take_package(self, package, ctx):
        """Move a whole existing package (all its content)."""
        MoveLine = self.env["stock.move.line"]
        lines = self.move_line_ids.filtered(lambda ml: ml.package_id == package and ml.state not in ("done", "cancel"))
        if not lines:
            for quant in package.quant_ids.filtered(lambda q: q.quantity > 0):
                move = self.move_ids.filtered(
                    lambda m: m.product_id == quant.product_id and m.state not in ("done", "cancel"))[:1]
                if not move:
                    raise UserError(_("Package %(pack)s contains %(product)s which is not part of this operation.",
                                      pack=package.name, product=quant.product_id.display_name))
                lines |= MoveLine.create({
                    "move_id": move.id,
                    "picking_id": move.picking_id.id,
                    "product_id": quant.product_id.id,
                    "product_uom_id": quant.product_id.uom_id.id,
                    "location_id": quant.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                    "lot_id": quant.lot_id.id,
                    "package_id": package.id,
                    "quantity": quant.quantity,
                    "bc_created": True,
                    "company_id": move.company_id.id,
                })
        lines = lines.with_context(bc_event=dict(self.env.context.get("bc_event") or {}, kind="package"))
        for ml in lines:
            ml.write({"bc_qty": ml.quantity, "result_package_id": package.id, "is_entire_pack": True})
        ctx["pending_line_ids"] = list(set(ctx.get("pending_line_ids", [])) | set(lines.ids))
        ctx["last_line_id"] = lines[-1:].id
        return self._bc_feedback("success", _("Whole package %s scanned", package.name))

    # ------------------------------------------------------------------
    def _bc_process_product(self, product, qty, ctx, lot=None, lot_name=None, expiration_date=None):
        pickings = self._bc_open_pickings()
        if not product:
            return self._bc_feedback("danger", _("Unknown product"))
        if product.type != "consu":
            return self._bc_feedback("danger", _("%s is not a goods product.", product.display_name))
        if (pickings._bc_rule("bc_require_source") and not ctx.get("source_location_id")
                and any(p.picking_type_code != "incoming" for p in pickings)
                and self.env.user.has_group("stock.group_stock_multi_locations")):
            return self._bc_feedback("danger", _("Scan the source location first."))
        uses_lots = pickings._bc_uses_lots(product)
        if uses_lots and not lot and not lot_name:
            ctx["pending_product_id"] = product.id
            return self._bc_feedback(
                "warning",
                _("%s is tracked: scan its serial number.", product.display_name) if product.tracking == "serial"
                else _("%s is tracked: scan its lot number.", product.display_name),
                need_lot=True)
        ctx["pending_product_id"] = False
        if lot_name and uses_lots:
            existing = self.env["stock.lot"].search([
                ("name", "=", lot_name), ("product_id", "=", product.id),
                ("company_id", "in", [self.env.company.id, False])], limit=1)
            if existing:
                lot, lot_name = existing, None
            elif not any(p.picking_type_id.use_create_lots for p in pickings):
                return self._bc_feedback("danger", _("Lot/serial %s does not exist for this product.", lot_name))
        if lot and lot.product_id != product:
            return self._bc_feedback("danger", _("Lot %(lot)s belongs to %(product)s.", lot=lot.name, product=lot.product_id.display_name))
        if product.tracking == "serial" and uses_lots:
            if float_compare(qty, 1.0, precision_digits=2) != 0:
                qty = 1.0
            serial = lot.name if lot else lot_name
            dup = pickings.move_line_ids.filtered(
                lambda ml: ml.bc_qty > 0 and ml.product_id == product and (ml.lot_id.name or ml.lot_name) == serial)
            if dup:
                return self._bc_feedback("danger", _("Serial number %s has already been scanned.", serial))
        if not uses_lots:
            lot = lot_name = None

        line = pickings._bc_find_line(product, qty, ctx, lot=lot, lot_name=lot_name)
        if not line:
            line = pickings._bc_create_line(product, ctx, lot=lot, lot_name=lot_name)
        line._bc_add(qty)
        vals = {}
        if lot and not line.lot_id:
            vals["lot_id"] = lot.id
        if lot_name and not line.lot_name and not line.lot_id:
            vals["lot_name"] = lot_name
        if expiration_date and "expiration_date" in line._fields and (lot_name or not line.lot_id):
            vals["expiration_date"] = fields.Datetime.to_datetime(expiration_date)
        if ctx.get("dest_location_id") and not line.bc_dest_confirmed:
            vals["location_dest_id"] = ctx["dest_location_id"]
            vals["bc_dest_confirmed"] = True
        if ctx.get("result_package_id") and not line.result_package_id:
            vals["result_package_id"] = ctx["result_package_id"]
        if vals:
            line.write(vals)
        ctx["last_line_id"] = line.id
        if not line.bc_dest_confirmed and line.id not in ctx["pending_line_ids"]:
            ctx["pending_line_ids"].append(line.id)
        move = line.move_id
        done = sum(move.move_line_ids.mapped("bc_qty"))
        if pickings._bc_rule("bc_block_over") and float_compare(
                done, move.product_uom_qty, precision_rounding=move.product_uom.rounding) > 0:
            raise UserError(_("%(product)s: only %(demand)s expected, you cannot scan more.",
                              product=product.display_name, demand=move.product_uom_qty))
        if move.product_uom_qty and float_compare(done, move.product_uom_qty, precision_rounding=move.product_uom.rounding) > 0:
            level, msg = "warning", _("%(product)s: %(done)s scanned, more than the %(demand)s expected",
                                     product=product.display_name, done=done, demand=move.product_uom_qty)
        elif not move.product_uom_qty:
            level, msg = "warning", _("%s is not expected in this operation; it has been added.", product.display_name)
        else:
            level, msg = "success", _("%(product)s %(done)s / %(demand)s", product=product.display_name,
                                      done=done, demand=move.product_uom_qty)
        return self._bc_feedback(level, msg, line_id=line.id)

    def _bc_find_line(self, product, qty, ctx, lot=None, lot_name=None):
        lines = self.move_line_ids.filtered(
            lambda ml: ml.product_id == product and ml.state not in ("done", "cancel") and ml.move_id)
        if ctx.get("source_location_id"):
            lines = lines.filtered(lambda ml: ml.location_id.id == ctx["source_location_id"])
        if ctx.get("dest_location_id"):
            lines = lines.filtered(lambda ml: not ml.bc_dest_confirmed or ml.location_dest_id.id == ctx["dest_location_id"])
        else:
            lines = lines.filtered(lambda ml: not ml.bc_dest_confirmed)
        if lot or lot_name:
            name = lot.name if lot else lot_name
            same_lot = lines.filtered(lambda ml: (ml.lot_id and ml.lot_id.name == name) or ml.lot_name == name)
            if product.tracking == "serial":
                return same_lot.filtered(lambda ml: ml.bc_qty == 0)[:1]
            candidates = same_lot
        else:
            candidates = lines

        def remaining(ml):
            return float_compare(ml.bc_qty + qty, ml.quantity, precision_rounding=ml.product_uom_id.rounding) <= 0

        line = candidates.filtered(remaining)[:1]
        if line:
            return line
        # A lot-less line from which nothing was scanned can take the lot (receipts).
        if lot or lot_name:
            already = candidates.filtered(lambda ml: ml.bc_qty > 0)[-1:]
            if already and product.tracking == "lot":
                return already
            free = lines.filtered(lambda ml: not ml.lot_id and not ml.lot_name and ml.bc_qty == 0)
            if free and product.tracking == "lot":
                ml = free[0]
                if float_compare(ml.quantity, qty, precision_rounding=ml.product_uom_id.rounding) > 0:
                    return False  # keep the remaining quantity as a suggestion: new line
                return ml
            return candidates.filtered(lambda ml: ml.bc_qty > 0)[-1:]
        # all fulfilled: add to the last scanned line (over-quantity)
        return candidates.filtered(lambda ml: ml.bc_qty > 0)[-1:] or candidates[:1]

    def _bc_create_line(self, product, ctx, lot=None, lot_name=None):
        MoveLine = self.env["stock.move.line"]
        pickings = self._bc_open_pickings()
        move = pickings.move_ids.filtered(
            lambda m: m.product_id == product and m.state not in ("done", "cancel"))[:1]
        if not move:
            if pickings._bc_rule("bc_block_extra"):
                raise UserError(_("%s is not part of this operation.", product.display_name))
            if len(pickings) > 1:
                raise UserError(_("%s is not part of this batch.", product.display_name))
            picking = pickings
            move = self.env["stock.move"].create({
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": 0.0,
                "picking_id": picking.id,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
                "company_id": picking.company_id.id,
                "picking_type_id": picking.picking_type_id.id,
            })
            if picking.state == "draft":
                picking.action_confirm()
            else:
                move._action_confirm()
        src = ctx.get("source_location_id")
        location = self.env["stock.location"].browse(src) if src else move.location_id
        if not src and lot and move.picking_code != "incoming":
            quant = self.env["stock.quant"].search([
                ("product_id", "=", product.id), ("lot_id", "=", lot.id),
                ("location_id", "child_of", move.location_id.id), ("quantity", ">", 0)], limit=1)
            if quant:
                location = quant.location_id
        dest = move.location_dest_id
        if ctx.get("dest_location_id"):
            dest = self.env["stock.location"].browse(ctx["dest_location_id"])
        else:
            dest = dest._get_putaway_strategy(product, quantity=1)
        return MoveLine.create({
            "move_id": move.id,
            "picking_id": move.picking_id.id,
            "product_id": product.id,
            "product_uom_id": move.product_uom.id,
            "location_id": location.id,
            "location_dest_id": dest.id,
            "quantity": 0.0,
            "lot_id": lot.id if lot else False,
            "lot_name": lot_name or False,
            "bc_created": True,
            "company_id": move.company_id.id,
        })

    # ------------------------------------------------------------------
    def _bc_set_qty(self, line_id, qty, ctx):
        line = self.env["stock.move.line"].browse(line_id).exists()
        if not line or line.picking_id not in self:
            return self._bc_state(ctx, self._bc_feedback("danger", _("Line not found.")))
        if not self._bc_manual_allowed():
            fb = self._bc_feedback("danger", _("This operation must be scanned: typing quantities is not allowed."))
            self._bc_log("set_qty", fb, move_line_id=line.id, product_id=line.product_id.id, quantity=qty or 0.0,
                         old_quantity=line.bc_qty)
            return self._bc_state(ctx, fb)
        self._bc_log("set_qty", self._bc_feedback("success", _("Quantity updated")), move_line_id=line.id,
                     product_id=line.product_id.id, lot_name=line.lot_id.name or line.lot_name or "",
                     quantity=qty or 0.0, old_quantity=line.bc_qty)
        qty = max(qty or 0.0, 0.0)
        if line.product_id.tracking == "serial" and self._bc_uses_lots(line.product_id) and qty > 1:
            return self._bc_state(ctx, self._bc_feedback("danger", _("A serial number line can only hold 1 unit.")))
        if qty == 0 and line.bc_created and float_is_zero(line.quantity, precision_rounding=line.product_uom_id.rounding):
            line.unlink()
        else:
            line._bc_set(qty)
            if qty and line.id not in ctx["pending_line_ids"] and not line.bc_dest_confirmed:
                ctx["pending_line_ids"].append(line.id)
        return self._bc_state(ctx, self._bc_feedback("success", _("Quantity updated")))

    def _bc_set_move_qty(self, move_id, qty, ctx):
        """Quick path: set the scanned quantity of a whole move (untracked products)."""
        move = self.env["stock.move"].browse(move_id).exists()
        if not move or move.picking_id not in self:
            return self._bc_state(ctx, self._bc_feedback("danger", _("Line not found.")))
        old = sum(move.move_line_ids.mapped("bc_qty"))
        if not self._bc_manual_allowed():
            fb = self._bc_feedback("danger", _("This operation must be scanned: typing quantities is not allowed."))
            self._bc_log("set_qty", fb, product_id=move.product_id.id, quantity=qty or 0.0, old_quantity=old)
            return self._bc_state(ctx, fb)
        if self._bc_rule("bc_block_over") and float_compare(
                qty or 0.0, move.product_uom_qty, precision_rounding=move.product_uom.rounding) > 0:
            fb = self._bc_feedback("danger", _("%(product)s: only %(demand)s expected.",
                                               product=move.product_id.display_name, demand=move.product_uom_qty))
            return self._bc_state(ctx, fb)
        self._bc_log("set_qty", self._bc_feedback("success", _("Quantity updated")), product_id=move.product_id.id,
                     quantity=qty or 0.0, old_quantity=old)
        if self._bc_uses_lots(move.product_id):
            return self._bc_state(ctx, self._bc_feedback("warning", _("Scan lots/serials for tracked products.")))
        lines = move.move_line_ids.filtered(lambda ml: not ml.bc_dest_confirmed)
        remaining = max(qty, 0.0) - sum(move.move_line_ids.filtered("bc_dest_confirmed").mapped("bc_qty"))
        if not lines:
            lines = self._bc_create_line(move.product_id, ctx)
        for ml in lines:
            take = min(remaining, ml.quantity) if ml != lines[-1] else remaining
            ml._bc_set(max(take, 0.0))
            remaining -= ml.bc_qty
        return self._bc_state(ctx, self._bc_feedback("success", _("Quantity updated")))

    # ------------------------------------------------------------------
    def _bc_put_in_pack(self, ctx):
        lines = self.move_line_ids.filtered(
            lambda ml: ml.bc_qty > 0 and not ml.result_package_id and ml.state not in ("done", "cancel"))
        if not lines:
            return self._bc_feedback("warning", _("Nothing to pack: scan products first."))
        package = self.env["stock.package"].create({})
        lines.write({"result_package_id": package.id})
        ctx["result_package_id"] = False
        return self._bc_feedback("success", _("%(count)s line(s) packed in %(pack)s", count=len(lines), pack=package.name),
                                 package_id=package.id)

    # ------------------------------------------------------------------
    def _bc_prepare_validation(self, force=False):
        """Copy scanned quantities into Odoo's quantity/picked fields.
        Returns False when nothing was scanned (and force is not set)."""
        pickings = self._bc_open_pickings()
        lines = pickings.move_line_ids.filtered(lambda ml: ml.state not in ("done", "cancel"))
        scanned = lines.filtered(lambda ml: ml.bc_qty > 0)
        if not scanned:
            if not force:
                return False
            # Validate everything as reserved, like the standard button.
            return True
        moves_scanned = scanned.move_id
        # 1. release lines that were not scanned (frees their reservation first)
        not_scanned = lines - scanned
        to_unlink = not_scanned.filtered(lambda ml: ml.bc_created or ml.move_id in moves_scanned)
        to_unlink.unlink()
        # 2. apply scanned quantities
        for ml in scanned:
            ml.write({"quantity": ml.bc_qty, "picked": True})
        # moves with lines left and not scanned stay un-picked => backorder
        return True

    def _bc_check_rules_before_validate(self, force=False):
        """Raise UserError when an enabled rule is not satisfied."""
        pickings = self._bc_open_pickings()
        scanned = pickings.move_line_ids.filtered(lambda ml: ml.bc_qty > 0 and ml.state not in ("done", "cancel"))
        if force and pickings._bc_rule("bc_scan_only"):
            bc_require_supervisor(self.env, _("validate quantities that were not scanned"))
        if not scanned:
            return
        if pickings._bc_rule("bc_require_dest") and self.env.user.has_group("stock.group_stock_multi_locations"):
            missing = scanned.filtered(lambda ml: ml.picking_code != "outgoing" and not ml.bc_dest_confirmed
                                       and ml.picking_type_id.bc_require_dest)
            if missing:
                raise UserError(_("Scan the destination location of: %s", ", ".join(missing.product_id.mapped("display_name"))))
        if pickings._bc_rule("bc_require_pack"):
            missing = scanned.filtered(lambda ml: not ml.result_package_id and ml.picking_type_id.bc_require_pack)
            if missing:
                raise UserError(_("Put these products in a pack before validating: %s",
                                  ", ".join(missing.product_id.mapped("display_name"))))

    def _bc_validate(self, force=False, backorder=None):
        res = self._bc_validate_inner(force=force, backorder=backorder)
        self._bc_log("validate", {"level": res.get("level") if not res.get("done") else "success",
                                  "message": (res.get("message") or "") + (" [force]" if force else "")})
        return res

    def _bc_expired_question(self):
        """product_expiry asks for a confirmation in a backend wizard; the scanner asks itself."""
        if self.env.context.get("skip_expired") or not hasattr(self, "_check_expired_lots"):
            return None
        if not self._check_expired_lots():
            return None
        import datetime
        now = datetime.datetime.now()
        lots = self.move_line_ids.filtered(
            lambda ml: ml.lot_id.product_expiry_alert or (ml.removal_date and ml.removal_date <= now)).lot_id
        return {"level": "warning", "confirm": "expired", "allowed": bc_is_supervisor(self.env),
                "lots": lots.mapped("display_name"),
                "message": _("Expired lots in this transfer: %s", ", ".join(lots.mapped("name")))}

    def bc_create_return(self):
        """Create the return of a done transfer; the returned quantities are then scanned."""
        rec = bc_guard(self)
        rec.ensure_one()
        if rec.state != "done":
            raise UserError(_("Only done transfers can be returned."))
        wizard = rec.env["stock.return.picking"].with_context(active_id=rec.id, active_ids=rec.ids,
                                                               active_model="stock.picking").create({})
        if not wizard.product_return_moves:
            raise UserError(_("Nothing left to return on %s.", rec.name))
        for line in wizard.product_return_moves:
            if not line.quantity:
                line.quantity = line.move_id.quantity
        action = wizard.action_create_returns()
        new = rec.env["stock.picking"].browse(action["res_id"])
        rec._bc_log("scan", {"level": "success", "message": _("Return %s created", new.name)},
                    resolved_type="return")
        return {"id": new.id, "name": new.name}

    def _bc_backorder_question(self):
        """The scanner asks about backorders itself (no wizard: operators have no backend access)."""
        pickings = self._bc_check_backorder_needed()
        if not pickings:
            return None
        return {"level": "warning", "confirm": "backorder", "pickings": pickings.mapped("name"),
                "message": _("Some products were not fully processed. Create a backorder for the rest?")}

    def _bc_check_backorder_needed(self):
        return self._check_backorder()

    def _bc_validate_context(self, backorder):
        ctx = {"skip_backorder": True}
        if backorder is False:
            ctx["picking_ids_not_to_backorder"] = self.ids
        return ctx

    def _bc_validate_inner(self, force=False, backorder=None):
        pickings = self._bc_open_pickings()
        if not pickings:
            return {"level": "info", "message": _("Already done."), "done": True}
        try:
            with self.env.cr.savepoint():
                pickings._bc_check_rules_before_validate(force=force)
                if not pickings._bc_prepare_validation(force=force):
                    return {"level": "warning", "confirm": "nothing_scanned",
                            "allowed": pickings._bc_manual_allowed(),
                            "message": _("Nothing has been scanned. Validate all the reserved quantities?")}
                expired = pickings._bc_expired_question()
                if expired:
                    return expired
                if backorder is None:
                    if force:
                        # validating everything as reserved: same as Odoo's picked logic
                        pickings.move_ids.filtered(lambda m: m.state not in ("done", "cancel") and m.quantity).picked = True
                    question = pickings._bc_backorder_question()
                    if question:
                        question["force"] = force
                        return question
                result = pickings.with_context(**pickings._bc_validate_context(backorder))._bc_call_validate()
        except (UserError, ValidationError, AccessError) as e:
            return {"level": "danger", "message": e.args[0] if e.args else str(e)}
        if isinstance(result, dict):
            return {"level": "info", "message": "", "action": result}
        return self._bc_after_validate()

    def _bc_call_validate(self):
        return self.button_validate()

    def _bc_after_validate(self):
        done = all(p.state == "done" for p in self)
        backorders = self.env["stock.picking"].search([("backorder_id", "in", self.ids)])
        res = {
            "level": "success" if done else "warning",
            "message": _("Validated") if done else _("Not validated"),
            "done": done,
            "backorders": [{"id": b.id, "name": b.name} for b in backorders],
            "next_actions": self._bc_next_actions(),
        }
        return res

    def _bc_next_actions(self):
        """Hook for sale/purchase integration: buttons shown after validation."""
        return []

    # ==================================================================
    # Barcode app entry points
    # ==================================================================
    @api.model
    def bc_home_scan(self, barcode):
        self = bc_guard(self)
        res = self.env["stock.barcode.resolver"].resolve(barcode)
        self.env["stock.barcode.scan.log"]._bc_write(
            "home_scan", barcode=res.get("barcode"), resolved_type=self.env["stock.barcode.resolver"]._type_of(res),
            level="success" if not res.get("unknown") else "warning")
        if res.get("picking"):
            return {"open": "picking", "id": res["picking"].id}
        if res.get("batch"):
            return {"open": "batch", "id": res["batch"].id}
        if res.get("picking_type"):
            return {"open": "picking_type", "id": res["picking_type"].id}
        if res.get("location"):
            return {"open": "inventory", "location_id": res["location"].id}
        if res.get("product"):
            return {"open": "product", "barcode": res["barcode"]}
        if res.get("command") in ("O-CMD.MAIN-MENU", "O-BTN.MAIN-MENU"):
            return {"open": "home"}
        return {"open": False, "message": _("No transfer, operation type, location or product found for %s", res["barcode"])}

    def action_open_barcode_ce(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "stock_barcode_ce.main",
            "name": _("Barcode"),
            "params": {"open": "picking", "id": self.id},
        }

    def action_open_barcode_ce_batch(self):
        return self.action_open_barcode_ce()
