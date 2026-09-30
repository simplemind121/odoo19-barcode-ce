from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.product_barcode_quick.models.barcode_tools import gtin_is_valid, is_gtin_like

CATEGORIES = [
    ("invalid_digit", "Wrong EAN/UPC check digit"),
    ("nomenclature", "Read as something else by the barcode rules"),
    ("duplicate", "Same code used twice"),
    ("missing", "Product without barcode"),
    ("location_missing", "Storable location without barcode"),
]


class StockBarcodeHealth(models.TransientModel):
    """Audit of existing barcode data before enabling strict scanning."""

    _name = "stock.barcode.health"
    _description = "Barcode data check"

    line_ids = fields.One2many("stock.barcode.health.line", "health_id", readonly=True)
    summary = fields.Text(readonly=True)
    include_missing = fields.Boolean("List products without barcode", default=True)

    def action_run(self):
        self.ensure_one()
        self.line_ids.unlink()
        self.env["stock.barcode.health.line"].create(self._collect())
        counts = defaultdict(int)
        for line in self.line_ids:
            counts[line.category] += 1
        labels = dict(self.env["stock.barcode.health.line"]._fields["category"]._description_selection(self.env))
        self.summary = "\n".join("%s: %s" % (labels[c], counts[c]) for c, _l in CATEGORIES if counts[c]) \
            or _("No problem found.")
        return self._reopen()

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
            "name": _("Barcode data check"),
        }

    def _collect(self):
        rows = []
        company = self.env.company
        nomenclature = company.nomenclature_id
        products = self.env["product.product"].with_context(active_test=True).search(
            [("type", "=", "consu"), "|", ("company_id", "=", False), ("company_id", "=", company.id)])
        by_code = defaultdict(list)
        for product in products:
            code = product.barcode
            if not code:
                if self.include_missing:
                    rows.append({"health_id": self.id, "category": "missing", "product_id": product.id,
                                 "detail": _("No barcode")})
                continue
            by_code[code].append(("product", product))
            if is_gtin_like(code) and not gtin_is_valid(code):
                rows.append({"health_id": self.id, "category": "invalid_digit", "product_id": product.id,
                             "barcode": code, "detail": _("Check digit does not match")})
            if nomenclature:
                try:
                    parsed = nomenclature.parse_barcode(code)
                except (UserError, ValidationError):
                    parsed = None
                kind = None
                if isinstance(parsed, dict):
                    if parsed.get("type") not in ("product", "error", None) or parsed.get("base_code") != code:
                        kind = parsed.get("type")
                elif isinstance(parsed, list) and parsed and parsed[0].get("type") != "product":
                    kind = parsed[0].get("type")
                if kind:
                    rows.append({"health_id": self.id, "category": "nomenclature", "product_id": product.id,
                                 "barcode": code,
                                 "detail": _("Barcode rules read it as \"%s\": POS and scanners may not find the product", kind)})
        if "product.uom" in self.env:
            for pack in self.env["product.uom"].search([("barcode", "!=", False)]):
                by_code[pack.barcode].append(("packaging", pack.product_id))
        for loc in self.env["stock.location"].search([("barcode", "!=", False), ("company_id", "in", [company.id, False])]):
            by_code[loc.barcode].append(("location", loc))
        for code, owners in by_code.items():
            if len(owners) > 1:
                names = ", ".join("%s %s" % (kind, rec.display_name) for kind, rec in owners)
                product = next((rec for kind, rec in owners if rec._name == "product.product"), self.env["product.product"])
                location = next((rec for kind, rec in owners if rec._name == "stock.location"), self.env["stock.location"])
                rows.append({"health_id": self.id, "category": "duplicate", "product_id": product.id,
                             "location_id": location.id, "barcode": code, "detail": names})
        if self.env.user.has_group("stock.group_stock_multi_locations"):
            for loc in self.env["stock.location"].search([
                    ("usage", "=", "internal"), ("barcode", "=", False), ("company_id", "=", company.id)]):
                rows.append({"health_id": self.id, "category": "location_missing", "location_id": loc.id,
                             "detail": loc.complete_name})
        return rows

    def action_generate_missing(self):
        lines = self.line_ids.filtered(lambda l: l.category == "missing" and l.product_id and not l.product_id.barcode)
        lines.product_id.action_bcq_generate_barcode()
        return self.action_run()


class StockBarcodeHealthLine(models.TransientModel):
    _name = "stock.barcode.health.line"
    _description = "Barcode data check line"
    _order = "category, id"

    health_id = fields.Many2one("stock.barcode.health", required=True, ondelete="cascade")
    category = fields.Selection(CATEGORIES, required=True)
    product_id = fields.Many2one("product.product")
    location_id = fields.Many2one("stock.location")
    barcode = fields.Char()
    detail = fields.Char()
