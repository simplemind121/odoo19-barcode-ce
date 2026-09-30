from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .barcode_tools import ALLOWED_INSTORE_PREFIXES


class ResCompany(models.Model):
    _inherit = "res.company"

    bcq_instore_prefix = fields.Char(
        "In-store Barcode Prefix", default="20", size=2,
        help="EAN-13 prefix used for barcodes generated in Odoo. 20 and 24-29 are reserved by GS1 "
             "for in-store use; 21-23 are used by Odoo for weight/discount/price barcodes.")
    bcq_strict_gtin = fields.Boolean(
        "Validate EAN/UPC Check Digit", default=True,
        help="Refuse numeric product barcodes of 8, 12, 13 or 14 digits whose check digit is wrong.")

    @api.constrains("bcq_instore_prefix")
    def _check_bcq_instore_prefix(self):
        for company in self:
            if company.bcq_instore_prefix and company.bcq_instore_prefix not in ALLOWED_INSTORE_PREFIXES:
                raise ValidationError(_(
                    "The in-store barcode prefix must be one of %s.", ", ".join(ALLOWED_INSTORE_PREFIXES)))
