from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ProductBarcodeQuick(models.TransientModel):
    """Minimal product creation form, opened when an unknown code is scanned."""

    _name = "product.barcode.quick"
    _description = "Create product from barcode"

    barcode = fields.Char(required=False)
    name = fields.Char("Product Name", required=True)
    default_code = fields.Char("Internal Reference")
    list_price = fields.Float("Sales Price", digits="Product Price", default=0.0)
    standard_price = fields.Float("Cost", digits="Product Price", default=0.0)
    categ_id = fields.Many2one(
        "product.category", "Category",
        default=lambda self: self.env.ref("product.product_category_goods", raise_if_not_found=False)
        or self.env["product.category"].search([], limit=1))
    uom_id = fields.Many2one("uom.uom", "Unit", default=lambda self: self.env.ref("uom.product_uom_unit"))
    image_1920 = fields.Image("Image", max_width=1920, max_height=1920)
    sale_ok = fields.Boolean("Can be Sold", default=True)
    purchase_ok = fields.Boolean("Can be Purchased", default=True)
    barcode_warning = fields.Char(compute="_compute_barcode_warning")
    print_label = fields.Boolean("Print a label after creation")

    @api.depends("barcode")
    def _compute_barcode_warning(self):
        from ..models.barcode_tools import gtin_is_valid, is_gtin_like
        for wiz in self:
            code = (wiz.barcode or "").strip()
            wiz.barcode_warning = False
            if code and is_gtin_like(code) and not gtin_is_valid(code):
                wiz.barcode_warning = _("Check digit is wrong: this does not look like a valid EAN/UPC.")
            elif code and self.env["product.product"]._bcq_barcode_in_use(code):
                wiz.barcode_warning = _("This barcode is already used by another product.")

    def action_generate_barcode(self):
        self.ensure_one()
        self.barcode = self.env["product.product"]._bcq_next_instore_barcode()
        return self._reopen()

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "name": _("New product"),
            "context": self.env.context,
        }

    def _prepare_template_vals(self):
        self.ensure_one()
        return {
            "name": self.name,
            "barcode": (self.barcode or "").strip() or False,
            "default_code": self.default_code,
            "list_price": self.list_price,
            "standard_price": self.standard_price,
            "categ_id": self.categ_id.id,
            "uom_id": self.uom_id.id,
            "image_1920": self.image_1920,
            "sale_ok": self.sale_ok,
            "purchase_ok": self.purchase_ok,
            "type": "consu",
        }

    def _create_product(self):
        self.ensure_one()
        code = (self.barcode or "").strip()
        if code and self.env["product.product"]._bcq_barcode_in_use(code):
            raise UserError(_("Barcode %s is already used by another product.", code))
        template = self.env["product.template"].create(self._prepare_template_vals())
        return template.product_variant_id

    def action_create(self):
        product = self._create_product()
        if self.print_label:
            return self.env["product.label.layout"].create({
                "product_ids": [(6, 0, product.ids)],
                "print_format": "th40x30",
                "custom_quantity": 1,
            }).process()
        return {
            "type": "ir.actions.act_window_close",
            "infos": {"bcq_product_id": product.id},
        }

    def action_create_and_open(self):
        product = self._create_product()
        return {
            "type": "ir.actions.act_window",
            "res_model": "product.template",
            "res_id": product.product_tmpl_id.id,
            "view_mode": "form",
            "target": "current",
        }
