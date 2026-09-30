from odoo import models
from odoo.addons.product.report.product_label_report import _prepare_data


class ReportThermalProductLabel(models.AbstractModel):
    _name = "report.product_barcode_quick.report_product_label_thermal"
    _description = "Thermal product label"

    def _get_report_values(self, docids, data):
        values = _prepare_data(self.env, docids, data)
        values["thermal_format"] = data.get("thermal_format", "th40x30")
        return values
