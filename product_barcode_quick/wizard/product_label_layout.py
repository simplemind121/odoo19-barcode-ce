from odoo import api, fields, models

THERMAL_FORMATS = {
    "th40x30": "product_barcode_quick.report_product_label_th40x30",
    "th50x30": "product_barcode_quick.report_product_label_th50x30",
    "th60x40": "product_barcode_quick.report_product_label_th60x40",
}


class ProductLabelLayout(models.TransientModel):
    _inherit = "product.label.layout"

    print_format = fields.Selection(selection_add=[
        ("th40x30", "Thermal label 40 x 30 mm"),
        ("th50x30", "Thermal label 50 x 30 mm"),
        ("th60x40", "Thermal label 60 x 40 mm"),
    ], ondelete={"th40x30": "set default", "th50x30": "set default", "th60x40": "set default"})
    thermal_show_price = fields.Boolean("Show price on thermal label", default=True)

    @api.depends("print_format")
    def _compute_dimensions(self):
        thermal = self.filtered(lambda w: w.print_format in THERMAL_FORMATS)
        for wizard in thermal:
            wizard.columns, wizard.rows = 1, 1
        return super(ProductLabelLayout, self - thermal)._compute_dimensions()

    def _prepare_report_data(self):
        xml_id, data = super()._prepare_report_data()
        if self.print_format in THERMAL_FORMATS:
            xml_id = THERMAL_FORMATS[self.print_format]
            data["price_included"] = self.thermal_show_price
            data["thermal_format"] = self.print_format
        return xml_id, data
