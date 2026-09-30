from odoo import _, api, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .barcode_security import bc_guard, bc_is_supervisor, bc_require_supervisor


class StockScrap(models.Model):
    _inherit = "stock.scrap"

    @api.model
    def _bc_scrap_ctx(self, ctx):
        ctx = dict(ctx or {})
        return {k: ctx.get(k) or False for k in ("location_id", "product_id", "lot_id", "pending_lot")}

    @api.model
    def bc_scrap_state(self, ctx=None, feedback=None):
        self = bc_guard(self)
        ctx = self._bc_scrap_ctx(ctx)
        loc = self.env["stock.location"].browse(ctx["location_id"]) if ctx["location_id"] else self.env["stock.location"]
        product = self.env["product.product"].browse(ctx["product_id"]) if ctx["product_id"] else self.env["product.product"]
        lot = self.env["stock.lot"].browse(ctx["lot_id"]) if ctx["lot_id"] else self.env["stock.lot"]
        available = None
        if product and loc:
            available = self.env["stock.quant"]._get_available_quantity(product, loc, lot_id=lot or None, strict=bool(lot))
        return {
            "ctx": ctx,
            "location": loc.display_name if loc else "",
            "product": product.display_name if product else "",
            "uom": product.uom_id.name if product else "",
            "tracking": product.tracking if product else "none",
            "lot": lot.name if lot else "",
            "available": available,
            "reasons": [{"id": r.id, "name": r.name} for r in self.env["stock.scrap.reason.tag"].search([])],
            "is_supervisor": bc_is_supervisor(self.env),
            "feedback": feedback or False,
        }

    @api.model
    def bc_scrap_scan(self, barcode, ctx=None):
        self = bc_guard(self)
        ctx = self._bc_scrap_ctx(ctx)
        res = self.env["stock.barcode.resolver"].resolve(barcode)
        fb = None
        if res.get("location"):
            if res["location"].usage != "internal":
                fb = {"level": "danger", "message": _("%s is not a stock location.", res["location"].display_name)}
            else:
                ctx["location_id"] = res["location"].id
                fb = {"level": "success", "message": _("Scrap from %s", res["location"].display_name)}
        elif res.get("product") or res.get("gs1"):
            product = res.get("product")
            lot = res.get("lot") if res.get("lot") and len(res["lot"]) == 1 else None
            if not product:
                fb = {"level": "danger", "message": _("Unknown barcode: %s", barcode)}
            else:
                ctx.update(product_id=product.id, lot_id=lot.id if lot else False)
                fb = {"level": "success", "message": product.display_name}
                if product.tracking != "none" and not lot:
                    fb = {"level": "warning", "message": _("%s is tracked: scan its lot/serial number.", product.display_name)}
        elif ctx.get("product_id"):
            product = self.env["product.product"].browse(ctx["product_id"])
            lot = self.env["stock.lot"].search([("name", "=", res["barcode"]), ("product_id", "=", product.id)], limit=1)
            if lot:
                ctx["lot_id"] = lot.id
                fb = {"level": "success", "message": _("Lot %s", lot.name)}
        if not fb:
            fb = {"level": "danger", "message": _("Unknown barcode: %s", barcode)}
        self.env["stock.barcode.scan.log"]._bc_write("scan", barcode=res.get("barcode"), resolved_type="scrap",
                                                     level=fb["level"], message=fb["message"],
                                                     product_id=ctx.get("product_id") or False,
                                                     location_id=ctx.get("location_id") or False)
        return self.bc_scrap_state(ctx, fb)

    @api.model
    def bc_scrap_confirm(self, ctx=None, qty=1.0, reason_ids=None):
        self = bc_guard(self)
        ctx = self._bc_scrap_ctx(ctx)
        try:
            with self.env.cr.savepoint():
                bc_require_supervisor(self.env, _("scrap products"))
                if not ctx["product_id"]:
                    raise UserError(_("Scan the product to scrap."))
                product = self.env["product.product"].browse(ctx["product_id"])
                if product.tracking != "none" and not ctx["lot_id"]:
                    raise UserError(_("Scan the lot/serial number to scrap."))
                location = self.env["stock.location"].browse(ctx["location_id"]) if ctx["location_id"] else \
                    self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1).lot_stock_id
                scrap = self.create({
                    "product_id": product.id,
                    "product_uom_id": product.uom_id.id,
                    "scrap_qty": qty,
                    "location_id": location.id,
                    "lot_id": ctx["lot_id"] or False,
                    "scrap_reason_tag_ids": [(6, 0, reason_ids or [])],
                })
                if not scrap.check_available_qty():
                    raise UserError(_("Only %(qty)s %(uom)s of %(product)s available in %(loc)s.",
                                      qty=self.env["stock.quant"]._get_available_quantity(
                                          product, location, lot_id=scrap.lot_id or None, strict=bool(scrap.lot_id)),
                                      uom=product.uom_id.name, product=product.display_name, loc=location.display_name))
                scrap.do_scrap()
        except (UserError, ValidationError, AccessError) as e:
            return self.bc_scrap_state(ctx, {"level": "danger", "message": e.args[0]})
        self.env["stock.barcode.scan.log"]._bc_write("validate", resolved_type="scrap", level="success",
                                                     message=_("Scrapped %s", scrap.name), product_id=product.id,
                                                     location_id=location.id, quantity=qty,
                                                     lot_name=scrap.lot_id.name or "")
        return self.bc_scrap_state({"location_id": ctx["location_id"]},
                                   {"level": "success", "message": _("%(qty)s %(uom)s of %(product)s scrapped (%(ref)s)",
                                                                     qty=qty, uom=product.uom_id.name,
                                                                     product=product.display_name, ref=scrap.name),
                                    "done": True})
