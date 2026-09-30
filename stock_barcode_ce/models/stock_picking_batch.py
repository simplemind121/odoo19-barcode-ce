from odoo import _, models

from .barcode_security import bc_guard
from .stock_picking import _clean_ctx


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    def _bc_pickings(self):
        self.ensure_one()
        return self.picking_ids.filtered(lambda p: p.state not in ("cancel",))

    def _bc_decorate(self, state):
        state.update({
            "model": self._name,
            "ids": self.ids,
            "name": self.name,
            "is_batch": True,
            "is_wave": self.is_wave,
            "state": "done" if self.state == "done" else state["state"],
        })
        return state

    def bc_get_state(self, ctx=None):
        self = bc_guard(self)
        return self._bc_decorate(self._bc_pickings()._bc_state(_clean_ctx(ctx)))

    def bc_scan(self, barcode, ctx=None, uuid=None):
        self = bc_guard(self)
        return self._bc_decorate(self._bc_pickings()._bc_scan_idempotent(barcode, _clean_ctx(ctx), uuid))

    def bc_set_qty(self, line_id, qty, ctx=None):
        self = bc_guard(self)
        pickings = self._bc_pickings().with_context(bc_event={"kind": "manual"})
        return self._bc_decorate(pickings._bc_notify_after(pickings._bc_set_qty(line_id, qty, _clean_ctx(ctx))))

    def bc_set_move_qty(self, move_id, qty, ctx=None):
        self = bc_guard(self)
        pickings = self._bc_pickings().with_context(bc_event={"kind": "manual"})
        return self._bc_decorate(pickings._bc_notify_after(pickings._bc_set_move_qty(move_id, qty, _clean_ctx(ctx))))

    def bc_add_product(self, product_id, qty=1.0, ctx=None):
        self = bc_guard(self)
        pickings = self._bc_pickings().with_context(bc_event={"kind": "manual"})
        return self._bc_decorate(pickings._bc_notify_after(pickings._bc_add_product(product_id, qty, _clean_ctx(ctx))))

    def bc_put_in_pack(self, ctx=None):
        self = bc_guard(self)
        pickings = self._bc_pickings()
        return self._bc_decorate(pickings._bc_notify_after(pickings._bc_put_in_pack_api(_clean_ctx(ctx))))

    def bc_print(self, what="operations"):
        self = bc_guard(self)
        self.ensure_one()
        if what == "operations":
            return self.env.ref("stock_picking_batch.action_report_picking_batch").report_action(self, config=False)
        return self._bc_pickings()[:1].bc_print(what)

    def bc_validate(self, force=False, backorder=None, expired_ok=False):
        self = bc_guard(self)
        self.ensure_one()
        if expired_ok:
            from .barcode_security import bc_is_supervisor
            if not bc_is_supervisor(self.env):
                return {"level": "danger", "message": _("Only a barcode supervisor can validate expired lots.")}
            self = self.with_context(skip_expired=True)
        res = self._bc_validate_batch(force, backorder)
        self._bc_pickings()._bc_notify()
        self._bc_pickings()._bc_log("validate", {
            "level": "success" if res.get("done") else res.get("level", "info"),
            "message": (res.get("message") or "") + (" [force]" if force else "")}, batch_id=self.id)
        return res

    def _bc_validate_batch(self, force=False, backorder=None):
        pickings = self._bc_pickings()._bc_open_pickings()
        if not pickings:
            return {"level": "info", "message": _("Already done."), "done": True}
        try:
            with self.env.cr.savepoint():
                pickings._bc_check_rules_before_validate(force=force)
                if not pickings._bc_prepare_validation(force=force):
                    return {"level": "warning", "confirm": "nothing_scanned",
                            "message": _("Nothing has been scanned. Validate all the reserved quantities?")}
                expired = pickings._bc_expired_question()
                if expired:
                    return expired
                if backorder is None:
                    question = pickings._bc_backorder_question()
                    if question:
                        question["force"] = force
                        return question
                result = self.with_context(**pickings._bc_validate_context(backorder)).action_done()
        except Exception as e:  # noqa: BLE001 - UserError/ValidationError message to the scanner
            from odoo.exceptions import AccessError, UserError, ValidationError
            if not isinstance(e, (UserError, ValidationError, AccessError)):
                raise
            return {"level": "danger", "message": e.args[0] if e.args else str(e)}
        if isinstance(result, dict):
            return {"level": "info", "message": "", "action": result}
        res = pickings._bc_after_validate()
        res["done"] = self.state == "done"
        return res

    def action_open_barcode_ce(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "stock_barcode_ce.main",
            "name": _("Barcode"),
            "params": {"open": "batch", "id": self.id},
        }
