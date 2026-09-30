from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .barcode_tools import gtin_candidates, gtin_is_valid, is_gtin_like, make_ean13


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        self.env["product.barcode.request"]._bcq_close_for(products)
        return products

    def write(self, vals):
        res = super().write(vals)
        if vals.get("barcode"):
            self.env["product.barcode.request"]._bcq_close_for(self)
        return res

    @api.model
    def bcq_can_create(self):
        return self.env["product.template"].has_access("create")

    @api.constrains("barcode")
    def _check_bcq_barcode_digit(self):
        for product in self:
            code = product.barcode
            company = product.company_id or self.env.company
            if code and company.bcq_strict_gtin and is_gtin_like(code) and not gtin_is_valid(code):
                raise ValidationError(_(
                    "Barcode %(code)s of %(product)s has a wrong check digit. Check the digits, "
                    "or disable the check in Settings if the code is not an EAN/UPC.",
                    code=code, product=product.display_name))

    # ------------------------------------------------------------------
    # In-store barcode generation
    # ------------------------------------------------------------------
    @api.model
    def _bcq_next_instore_barcode(self, company=None):
        company = company or self.env.company
        prefix = company.bcq_instore_prefix or "20"
        seq = self.env["ir.sequence"].sudo().with_company(company)
        for _attempt in range(1000):
            number = seq.next_by_code("product_barcode_quick.instore")
            if not number:
                raise UserError(_("The in-store barcode sequence is missing."))
            body = (prefix + number.rjust(10, "0")[-10:])
            code = make_ean13(body)
            if not self._bcq_barcode_in_use(code):
                return code
        raise UserError(_("Could not find a free in-store barcode."))

    @api.model
    def _bcq_barcode_in_use(self, code):
        Product = self.with_context(active_test=False)
        if Product.search_count([("barcode", "=", code)], limit=1):
            return True
        if "product.uom" in self.env and self.env["product.uom"].sudo().search_count(
                [("barcode", "=", code)], limit=1):
            return True
        return False

    def action_bcq_generate_barcode(self):
        for product in self:
            if product.barcode:
                continue
            product.barcode = self._bcq_next_instore_barcode(product.company_id or self.env.company)
        return True

    # ------------------------------------------------------------------
    # Lookup used by the scan screens
    # ------------------------------------------------------------------
    @api.model
    def bcq_find_by_barcode(self, barcode):
        """Return (product, qty, uom, parsed) for a scanned code.

        Handles plain barcodes, GTIN padding variants, packaging (product.uom)
        barcodes, GS1-128 and weight/price embedded EAN-13 of the company
        nomenclature. `qty` is None when the code carries no quantity.
        """
        Product = self.env["product.product"]
        code = (barcode or "").strip()
        if not code:
            return Product, None, None, {}
        # 1. direct match
        product = Product.search([("barcode", "in", gtin_candidates(code))], limit=1)
        if product:
            return product, None, None, {}
        # 2. packaging barcode
        if "product.uom" in self.env:
            pack = self.env["product.uom"].search([("barcode", "in", gtin_candidates(code))], limit=1)
            if pack:
                return pack.product_id, pack.uom_id._compute_quantity(1.0, pack.product_id.uom_id), None, {}
        # 3. nomenclature parsing (GS1 / weight / price)
        nomenclature = self.env.company.nomenclature_id
        if nomenclature:
            try:
                parsed = nomenclature.parse_barcode(code)
            except (UserError, ValidationError):
                parsed = None
            if isinstance(parsed, list):  # GS1
                data = {}
                for part in parsed:
                    data.setdefault(part["type"], part)
                prod = data.get("product")
                if prod:
                    product = Product.search([("barcode", "in", gtin_candidates(prod["value"]))], limit=1)
                    qty = data.get("quantity", {}).get("value")
                    return product, qty, None, data
            elif isinstance(parsed, dict) and parsed.get("type") in ("weight", "price", "product") \
                    and parsed.get("base_code") != code:
                product = Product.search([("barcode", "=", parsed["base_code"])], limit=1)
                if product:
                    qty = parsed["value"] if parsed["type"] == "weight" else None
                    return product, qty, None, parsed
        return Product, None, None, {}

    @api.model
    def bcq_lookup(self, barcode):
        """JSON helper for the scan screen."""
        product, qty, _uom, _parsed = self.bcq_find_by_barcode(barcode)
        if not product:
            code = (barcode or "").strip()
            return {
                "found": False,
                "barcode": code,
                "gtin_like": is_gtin_like(code),
                "gtin_valid": gtin_is_valid(code),
            }
        return {"found": True, "product": product._bcq_card_data(), "qty": qty}

    def _bcq_card_data(self):
        self.ensure_one()
        data = {
            "id": self.id,
            "tmpl_id": self.product_tmpl_id.id,
            "display_name": self.display_name,
            "barcode": self.barcode or "",
            "default_code": self.default_code or "",
            "list_price": self.lst_price,
            "currency_symbol": self.currency_id.symbol or "",
            "uom": self.uom_id.name,
            "categ": self.categ_id.display_name,
            "write_date": fields.Datetime.to_string(self.write_date),
        }
        if "qty_available" in self._fields:
            data["qty_available"] = self.qty_available
        return data


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def action_bcq_generate_barcode(self):
        for template in self:
            if len(template.product_variant_ids) == 1:
                template.product_variant_ids.action_bcq_generate_barcode()
            else:
                template.product_variant_ids.filtered(lambda p: not p.barcode).action_bcq_generate_barcode()
        return True
