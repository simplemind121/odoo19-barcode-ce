from odoo import _, api, fields, models

from .barcode_security import bc_guard


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    bc_require_source = fields.Boolean(
        "Scan: source location required", help="Products can only be scanned after their source location (deliveries, internal transfers).")
    bc_require_dest = fields.Boolean(
        "Scan: destination location required", help="Every scanned line needs a scanned destination before validation.")
    bc_scan_only = fields.Boolean(
        "Scan: no typed quantities",
        help="Operators cannot type quantities, add products by hand or validate unscanned transfers. Supervisors can.")
    bc_require_pack = fields.Boolean("Scan: packing required", help="All scanned lines must be put in a pack before validation.")
    bc_block_extra = fields.Boolean("Scan: refuse products not in the transfer")
    bc_block_over = fields.Boolean("Scan: refuse quantities above demand")

    @api.model
    def bc_dashboard(self):
        self = bc_guard(self)
        types = self.search([
            ("active", "=", True), ("company_id", "in", self.env.companies.ids),
            ("code", "in", ["incoming", "outgoing", "internal"])])
        warehouses = {}
        for ptype in types.sorted(lambda t: (t.warehouse_id.sequence, t.warehouse_id.id, t.sequence, t.id)):
            wh = ptype.warehouse_id
            key = wh.id or 0
            if key not in warehouses:
                warehouses[key] = {"id": wh.id, "name": wh.name or _("No warehouse"), "code": wh.code or "", "types": []}
            warehouses[key]["types"].append({
                "id": ptype.id,
                "name": ptype.name,
                "code": ptype.code,
                "ready": ptype.count_picking_ready,
                "waiting": ptype.count_picking_waiting,
                "late": ptype.count_picking_late,
                "backorders": ptype.count_picking_backorders,
            })
        Batch = self.env["stock.picking.batch"]
        return {
            "warehouses": list(warehouses.values()),
            "batch_count": Batch.search_count([("state", "=", "in_progress"), ("is_wave", "=", False)]),
            "wave_count": Batch.search_count([("state", "=", "in_progress"), ("is_wave", "=", True)]),
            "is_supervisor": self.env.user.has_group("stock_barcode_ce.group_barcode_supervisor"),
            "counted_count": self.env["stock.quant"].search_count([
                ("inventory_quantity_set", "=", True), ("user_id", "=", self.env.uid)]),
        }

    def bc_pickings(self, search=""):
        self = bc_guard(self)
        self.ensure_one()
        domain = [("picking_type_id", "=", self.id), ("state", "in", ["draft", "confirmed", "waiting", "assigned"])]
        if search:
            domain += ["|", "|", ("name", "ilike", search), ("origin", "ilike", search), ("partner_id", "ilike", search)]
        pickings = self.env["stock.picking"].search(domain, order="state desc, scheduled_date asc, id asc", limit=200)
        today = fields.Datetime.now()
        return {
            "type": {"id": self.id, "name": self.display_name, "code": self.code},
            "pickings": [{
                "id": p.id,
                "name": p.name,
                "partner": p.partner_id.display_name or "",
                "origin": p.origin or "",
                "state": p.state,
                "state_label": dict(p._fields["state"]._description_selection(self.env)).get(p.state),
                "scheduled_date": fields.Datetime.to_string(p.scheduled_date) if p.scheduled_date else "",
                "late": bool(p.scheduled_date and p.scheduled_date < today),
                "lines": len(p.move_ids),
            } for p in pickings],
        }

    def bc_new_picking(self):
        self = bc_guard(self)
        self.ensure_one()
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.id,
            "location_id": self.default_location_src_id.id,
            "location_dest_id": self.default_location_dest_id.id,
        })
        return picking.id

    @api.model
    def bc_batches(self, is_wave=False):
        self = bc_guard(self)
        batches = self.env["stock.picking.batch"].search(
            [("state", "in", ["draft", "in_progress"]), ("is_wave", "=", bool(is_wave))], order="scheduled_date, id", limit=200)
        return [{
            "id": b.id,
            "name": b.name,
            "state": b.state,
            "user": b.user_id.name or "",
            "picking_type": b.picking_type_id.display_name or "",
            "count": len(b.picking_ids),
        } for b in batches]

    @api.model
    def action_redirect_to_barcode_installation(self):
        # Community "install the barcode app" link now opens this module.
        return self.env["ir.actions.actions"]._for_xml_id("stock_barcode_ce.action_stock_barcode_ce_main")
