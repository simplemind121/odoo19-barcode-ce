from odoo import _, api, fields, models


class ProductBarcodeRequest(models.Model):
    """An unknown code scanned by someone who cannot create products.
    Closed automatically when a product gets that barcode."""

    _name = "product.barcode.request"
    _description = "Request to create a product for a scanned barcode"
    _order = "state, id desc"

    barcode = fields.Char(required=True, index=True, readonly=True)
    user_id = fields.Many2one("res.users", "Requested by", readonly=True, default=lambda self: self.env.uid)
    origin = fields.Char("Where", readonly=True, help="Transfer or screen where the code was scanned")
    note = fields.Char()
    count = fields.Integer("Times scanned", default=1, readonly=True)
    state = fields.Selection([("open", "To create"), ("done", "Created"), ("cancel", "Ignored")],
                             default="open", index=True)
    product_id = fields.Many2one("product.product", readonly=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    @api.model
    def bcq_request(self, barcode, origin=None, note=None):
        """Callable by any internal user (the scanner calls it for users without product rights)."""
        code = (barcode or "").strip()
        if not code:
            return {"level": "danger", "message": _("Empty barcode")}
        existing = self.env["product.product"].sudo().search([("barcode", "=", code)], limit=1)
        if existing:
            return {"level": "info", "message": _("%s already exists: scan it again.", existing.display_name)}
        Request = self.sudo()
        req = Request.search([("barcode", "=", code), ("state", "=", "open")], limit=1)
        if req:
            req.count += 1
        else:
            req = Request.create({"barcode": code, "origin": origin, "note": note, "user_id": self.env.uid})
        return {"level": "success", "request_id": req.id,
                "message": _("Request sent: a product manager will create %s.", code)}

    def action_create_product(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "product.barcode.quick",
            "view_mode": "form",
            "target": "new",
            "name": _("New product"),
            "context": {"default_barcode": self.barcode},
        }

    def action_ignore(self):
        self.write({"state": "cancel"})

    @api.model
    def _bcq_close_for(self, products):
        codes = {p.barcode: p for p in products if p.barcode}
        if not codes:
            return
        for req in self.sudo().search([("barcode", "in", list(codes)), ("state", "=", "open")]):
            req.write({"state": "done", "product_id": codes[req.barcode].id})
