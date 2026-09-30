from odoo import api, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.product_barcode_quick.models.barcode_tools import gtin_candidates

COMMAND_PREFIXES = ("O-BTN.", "O-CMD.")


class StockBarcodeResolver(models.AbstractModel):
    """Turns a raw scanned string into typed records.

    The result is a dict that may contain:
      command, picking, batch, picking_type, location, location_dest,
      product (+ qty), lot / lot_name, package / package_name,
      expiration_date, gs1 (bool), barcode.
    """

    _name = "stock.barcode.resolver"
    _description = "Stock barcode resolver"

    @api.model
    def resolve(self, barcode, allowed=None):
        """:param allowed: optional set of result keys the caller is interested in,
        used to give priority to the relevant record types."""
        code = (barcode or "").strip()
        res = {"barcode": code}
        if not code:
            return res
        if code.upper().startswith(COMMAND_PREFIXES):
            res["command"] = code.upper()
            return res
        company = self.env.company

        # GS1-128 aggregate codes (only when the company uses a GS1 nomenclature)
        nomenclature = company.nomenclature_id
        if nomenclature and nomenclature.is_gs1_nomenclature:
            try:
                parsed = nomenclature.parse_barcode(code)
            except (UserError, ValidationError):
                parsed = None
            if isinstance(parsed, list) and parsed and (
                    len(parsed) > 1 or parsed[0]["type"] != "product" or len(code) > 14):
                gs1 = self._resolve_gs1(parsed)
                if gs1:
                    gs1["barcode"] = code
                    return gs1

        # Transfers and batches by reference
        Picking = self.env["stock.picking"]
        picking = Picking.search([("name", "=", code)], limit=1)
        if picking:
            res["picking"] = picking
            return res
        if "stock.picking.batch" in self.env:
            batch = self.env["stock.picking.batch"].search([("name", "=", code)], limit=1)
            if batch:
                res["batch"] = batch
                return res
        picking_type = self.env["stock.picking.type"].search(
            [("barcode", "=", code), ("company_id", "in", [company.id, False])], limit=1)
        if picking_type:
            res["picking_type"] = picking_type
            return res
        location = self.env["stock.location"].search(
            [("barcode", "=", code), ("company_id", "in", [company.id, False])], limit=1)
        if location:
            res["location"] = location
            return res
        product, qty, _uom, _parsed = self.env["product.product"].bcq_find_by_barcode(code)
        if product:
            res["product"] = product
            if qty:
                res["qty"] = qty
            return res
        lots = self.env["stock.lot"].search([("name", "=", code), ("company_id", "in", [company.id, False])], limit=2)
        if lots:
            res["lot"] = lots
            if len(lots) == 1:
                res["product"] = lots.product_id
            return res
        package = self.env["stock.package"].search([("name", "=", code)], limit=1)
        if package:
            res["package"] = package
            return res
        # Unknown code that looks like a package according to the nomenclature
        if nomenclature and not nomenclature.is_gs1_nomenclature:
            parsed = nomenclature.parse_barcode(code)
            if isinstance(parsed, dict) and parsed.get("type") == "package":
                res["package_name"] = code
                return res
        # Otherwise it may be a new lot/serial name: the caller decides.
        res["unknown"] = True
        return res

    @api.model
    def _type_of(self, res):
        for key in ("command", "gs1", "picking", "batch", "picking_type", "location", "product", "lot",
                    "package", "package_name", "unknown"):
            if res.get(key):
                return key
        return ""

    @api.model
    def _resolve_gs1(self, parsed):
        data = {"gs1": True}
        Product = self.env["product.product"]
        for part in parsed:
            kind, value = part["type"], part["value"]
            if kind == "product" and "product" not in data:
                product = Product.search([("barcode", "in", gtin_candidates(value))], limit=1)
                if not product and "product.uom" in self.env:
                    pack = self.env["product.uom"].search([("barcode", "in", gtin_candidates(value))], limit=1)
                    if pack:
                        product = pack.product_id
                        data["pack_qty"] = pack.uom_id._compute_quantity(1.0, product.uom_id)
                data["product"] = product
                data["gtin"] = value
            elif kind == "lot":
                data["lot_name"] = value
            elif kind == "quantity":
                data["qty"] = value
            elif kind in ("expiration_date", "use_date"):
                data.setdefault("expiration_date", value)
            elif kind == "package":
                package = self.env["stock.package"].search([("name", "=", value)], limit=1)
                if package:
                    data["package"] = package
                else:
                    data["package_name"] = value
            elif kind in ("location", "location_dest"):
                loc = self.env["stock.location"].search([("barcode", "=", value)], limit=1)
                if loc:
                    data[kind] = loc
        if "product" in data and not data["product"]:
            data["unknown_product"] = data.pop("gtin", True)
            data.pop("product")
        if data.get("lot_name") and data.get("product"):
            lot = self.env["stock.lot"].search([
                ("name", "=", data["lot_name"]), ("product_id", "=", data["product"].id),
                ("company_id", "in", [self.env.company.id, False])], limit=1)
            if lot:
                data["lot"] = lot
        if data.get("pack_qty"):
            data["qty"] = (data.get("qty") or 1) * data.pop("pack_qty")
        return data if len(data) > 1 else None
