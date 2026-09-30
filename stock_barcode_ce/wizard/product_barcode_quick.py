from odoo import fields, models


class ProductBarcodeQuick(models.TransientModel):
    _inherit = "product.barcode.quick"

    is_storable = fields.Boolean("Track Inventory", default=True)
    tracking = fields.Selection([
        ("none", "No tracking"), ("lot", "By lots"), ("serial", "By unique serial number")],
        default="none", required=True)

    def _prepare_template_vals(self):
        vals = super()._prepare_template_vals()
        vals["is_storable"] = self.is_storable
        vals["tracking"] = self.tracking if self.is_storable else "none"
        return vals
