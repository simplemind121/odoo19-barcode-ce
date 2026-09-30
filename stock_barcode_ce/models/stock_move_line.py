from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    bc_event_ids = fields.One2many("stock.barcode.scan.event", "move_line_id", "Scan events")
    bc_qty = fields.Float(
        "Scanned Quantity", digits="Product Unit", copy=False,
        compute="_compute_bc_qty", inverse="_inverse_bc_qty",
        help="Sum of the scan events of this line. Writing it records the difference as a new event.")
    bc_dest_confirmed = fields.Boolean("Destination scanned", copy=False)
    bc_created = fields.Boolean("Created by barcode", copy=False)

    @api.depends("bc_event_ids.qty")
    def _compute_bc_qty(self):
        real = self.filtered("id")
        totals = {}
        if real.ids:
            self.env["stock.barcode.scan.event"].flush_model(["move_line_id", "qty"])
            self.env.cr.execute(
                "SELECT move_line_id, SUM(qty) FROM stock_barcode_scan_event WHERE move_line_id IN %s GROUP BY move_line_id",
                [tuple(real.ids)])
            totals = dict(self.env.cr.fetchall())
        for line in self:
            line.bc_qty = totals.get(line.id, 0.0) if line.id else 0.0

    def _bc_db_qty(self):
        self.ensure_one()
        self.env["stock.barcode.scan.event"].flush_model(["move_line_id", "qty"])
        self.env.cr.execute("SELECT COALESCE(SUM(qty), 0) FROM stock_barcode_scan_event WHERE move_line_id = %s", [self.id])
        return self.env.cr.fetchone()[0]

    def _bc_add(self, delta):
        """Record `delta` scanned units without writing the move line row (no write_date
        update, hence no lock conflict when several people scan the same transfer)."""
        self.ensure_one()
        self.env["stock.barcode.scan.event"]._bc_push(self, delta)
        self.invalidate_recordset(["bc_qty"])

    def _bc_set(self, qty):
        self.ensure_one()
        self._bc_add((qty or 0.0) - self._bc_db_qty())

    def _inverse_bc_qty(self):
        Event = self.env["stock.barcode.scan.event"]
        for line in self:
            delta = (line.bc_qty or 0.0) - line._bc_db_qty()
            if abs(delta) > 1e-9:
                Event._bc_push(line, delta)
