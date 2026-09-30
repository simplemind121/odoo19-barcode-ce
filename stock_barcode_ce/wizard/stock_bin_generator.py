from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockBinGenerator(models.TransientModel):
    """Create a zone / rack / level / bin location tree with barcodes."""

    _name = "stock.bin.generator"
    _description = "Generate storage bins"

    warehouse_id = fields.Many2one("stock.warehouse", required=True,
                                   default=lambda self: self.env["stock.warehouse"].search(
                                       [("company_id", "=", self.env.company.id)], limit=1))
    parent_location_id = fields.Many2one("stock.location", "Parent location", required=True,
                                         domain="[('usage', 'in', ['internal', 'view'])]")
    zones = fields.Char("Zones", required=True, default="A", help="Comma separated zone codes, e.g. A,B,C")
    racks = fields.Integer("Racks per zone", default=1, required=True)
    levels = fields.Integer("Levels per rack", default=1, required=True)
    bins = fields.Integer("Bins per level", default=1, required=True)
    separator = fields.Char(default="-", required=True)
    preview = fields.Char(compute="_compute_preview")
    total = fields.Integer(compute="_compute_preview")

    @api.onchange("warehouse_id")
    def _onchange_warehouse_id(self):
        if self.warehouse_id:
            self.parent_location_id = self.warehouse_id.lot_stock_id

    def _zone_codes(self):
        return [z.strip().upper() for z in (self.zones or "").split(",") if z.strip()]

    def _bin_code(self, zone, rack, level, bin_no):
        sep = self.separator
        return sep.join([zone, "%02d" % rack, str(level), "%02d" % bin_no])

    @api.depends("zones", "racks", "levels", "bins", "separator", "warehouse_id")
    def _compute_preview(self):
        for wiz in self:
            zones = wiz._zone_codes()
            wiz.total = len(zones) * max(wiz.racks, 0) * max(wiz.levels, 0) * max(wiz.bins, 0)
            if zones and wiz.racks > 0 and wiz.levels > 0 and wiz.bins > 0:
                first = wiz._bin_code(zones[0], 1, 1, 1)
                wiz.preview = "%s%s%s" % (wiz.warehouse_id.code or "", wiz.separator, first)
            else:
                wiz.preview = False

    def action_generate(self):
        self.ensure_one()
        if self.racks < 1 or self.levels < 1 or self.bins < 1 or not self._zone_codes():
            raise UserError(_("Zones, racks, levels and bins must all be set."))
        if self.total > 5000:
            raise UserError(_("That would create %s bins; generate them in smaller chunks (max 5000).", self.total))
        if not self.env.user.has_group("stock.group_stock_multi_locations"):
            self.env["res.config.settings"].create({"group_stock_multi_locations": True}).execute()
        Location = self.env["stock.location"]
        company = self.warehouse_id.company_id
        sep = self.separator
        wh_code = self.warehouse_id.code or ""

        def get_or_create(name, parent, usage, barcode=False):
            loc = Location.search([("name", "=", name), ("location_id", "=", parent.id)], limit=1)
            if not loc:
                loc = Location.create({"name": name, "location_id": parent.id, "usage": usage,
                                       "company_id": company.id, "barcode": barcode})
            elif barcode and not loc.barcode:
                loc.barcode = barcode
            return loc

        created = Location
        for zone in self._zone_codes():
            zone_loc = get_or_create(zone, self.parent_location_id, "view")
            for rack in range(1, self.racks + 1):
                rack_name = sep.join([zone, "%02d" % rack])
                rack_loc = get_or_create(rack_name, zone_loc, "view")
                for level in range(1, self.levels + 1):
                    level_name = sep.join([rack_name, str(level)])
                    level_loc = get_or_create(level_name, rack_loc, "view")
                    for bin_no in range(1, self.bins + 1):
                        code = self._bin_code(zone, rack, level, bin_no)
                        barcode = sep.join([wh_code, code]) if wh_code else code
                        created |= get_or_create(code, level_loc, "internal", barcode)
        return {
            "type": "ir.actions.act_window",
            "name": _("Generated bins"),
            "res_model": "stock.location",
            "view_mode": "list,form",
            "domain": [("id", "in", created.ids)],
            "target": "current",
        }
