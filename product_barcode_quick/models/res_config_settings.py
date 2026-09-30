from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    bcq_instore_prefix = fields.Char(related="company_id.bcq_instore_prefix", readonly=False)
    bcq_strict_gtin = fields.Boolean(related="company_id.bcq_strict_gtin", readonly=False)
