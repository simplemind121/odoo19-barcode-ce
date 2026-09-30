from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.stock_barcode_ce.models.barcode_security import bc_guard


def _no_printer(env):
    return {"level": "warning", "fallback": True,
            "message": env._("No label printer configured: using PDF instead.")}


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def bc_direct_print(self, kind="products"):
        rec = bc_guard(self)
        printer = rec.env["barcode.label.printer"].sudo()._default_for_user()
        if not printer:
            return _no_printer(rec.env)
        Render = rec.env["barcode.label.render"]
        contents = []
        if kind == "products":
            for move in rec.move_ids.filtered(lambda m: m.state != "cancel"):
                done = sum(move.move_line_ids.mapped("bc_qty")) if move.state != "done" else move.quantity
                copies = int(round(done or move.product_uom_qty))
                if copies and move.product_id.barcode:
                    contents.append((Render._content_product(move.product_id, printer.show_price), copies))
        elif kind == "lots":
            lots = rec.move_line_ids.filtered(lambda ml: ml.bc_qty > 0 or ml.state == "done").lot_id
            # lots typed on receipts only exist after validation
            contents = [(Render._content_lot(lot), 1) for lot in lots]
        elif kind == "packages":
            packs = rec.move_line_ids.result_package_id
            contents = [(Render._content_package(p), 1) for p in packs]
        if not contents:
            return {"level": "warning", "message": _("Nothing to print.")}
        job = printer._print(contents, "%s (%s)" % (", ".join(rec.mapped("name")), kind))
        return {"level": "success", "message": _("%(count)s label(s) sent to %(printer)s",
                                                 count=job.label_count, printer=printer.name)}


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    def bc_direct_print(self, kind="products"):
        rec = bc_guard(self)
        return rec.picking_ids.bc_direct_print(kind)


class ProductProduct(models.Model):
    _inherit = "product.product"

    def bc_direct_print(self, copies=1):
        printer = self.env["barcode.label.printer"].sudo()._default_for_user()
        if not printer:
            return _no_printer(self.env)
        Render = self.env["barcode.label.render"]
        contents = [(Render._content_product(p, printer.show_price), int(copies or 1)) for p in self if p.barcode]
        if not contents:
            return {"level": "warning", "message": _("These products have no barcode.")}
        job = printer._print(contents, _("Product labels"))
        return {"level": "success", "message": _("%(count)s label(s) sent to %(printer)s",
                                                 count=job.label_count, printer=printer.name)}


class _DirectPrintMixin(models.AbstractModel):
    _name = "barcode.label.direct.mixin"
    _description = "Direct label print for list views"

    def _bc_content(self, render):
        raise NotImplementedError

    def action_bc_direct_print(self):
        printer = self.env["barcode.label.printer"].sudo()._default_for_user()
        if not printer:
            raise UserError(self.env._("Configure a label printer first (Barcode > Configuration > Label printers)."))
        render = self.env["barcode.label.render"]
        job = printer._print([(rec._bc_content(render), 1) for rec in self], self._description)
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"type": "success", "message": self.env._("%(count)s label(s) sent to %(printer)s",
                                                                   count=job.label_count, printer=printer.name)}}


class StockLocation(models.Model):
    _name = "stock.location"
    _inherit = ["stock.location", "barcode.label.direct.mixin"]

    def _bc_content(self, render):
        return render._content_location(self)


class StockPackage(models.Model):
    _name = "stock.package"
    _inherit = ["stock.package", "barcode.label.direct.mixin"]

    def _bc_content(self, render):
        return render._content_package(self)


class StockLot(models.Model):
    _name = "stock.lot"
    _inherit = ["stock.lot", "barcode.label.direct.mixin"]

    def _bc_content(self, render):
        return render._content_lot(self)
