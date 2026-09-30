from odoo import api, fields, models


class StockBarcodeScanEvent(models.Model):
    """Quantity events of the scanner.

    Scanning never updates a shared row: each scan inserts one event and the
    scanned quantity of a move line is the sum of its events. Inserts do not
    conflict, so several people can scan the same transfer at the same time.
    """

    _name = "stock.barcode.scan.event"
    _description = "Barcode scan quantity event"
    _order = "id"
    _log_access = True

    move_line_id = fields.Many2one("stock.move.line", required=True, index=True, ondelete="cascade", readonly=True)
    picking_id = fields.Many2one("stock.picking", index=True, readonly=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", readonly=True, index=True)
    qty = fields.Float(digits="Product Unit", readonly=True, required=True)
    kind = fields.Selection([
        ("scan", "Scan"),
        ("manual", "Typed quantity"),
        ("transfer", "Moved to another line"),
        ("package", "Whole package"),
        ("migrated", "Migrated from version 1"),
    ], default="scan", required=True, readonly=True)
    user_id = fields.Many2one("res.users", required=True, readonly=True, default=lambda self: self.env.uid, index=True)
    device = fields.Char(readonly=True)
    scan_uuid = fields.Char("Client scan id", readonly=True, index=True)
    company_id = fields.Many2one("res.company", required=True, readonly=True, default=lambda self: self.env.company)

    @api.model
    def _bc_push(self, move_line, delta):
        """Insert one event for `move_line` (sudo: operators only have read access)."""
        if not delta:
            return self.browse()
        meta = self.env.context.get("bc_event") or {}
        return self.sudo().create({
            "move_line_id": move_line.id,
            "picking_id": move_line.picking_id.id,
            "product_id": move_line.product_id.id,
            "qty": delta,
            "kind": meta.get("kind", "scan"),
            "user_id": self.env.uid,
            "device": (self.env.context.get("bc_device") or "")[:120],
            "scan_uuid": meta.get("uuid"),
            "company_id": (move_line.company_id or self.env.company).id,
        })
