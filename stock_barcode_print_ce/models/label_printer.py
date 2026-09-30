import base64
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BarcodeLabelAgent(models.Model):
    """A small program running in the warehouse network that polls Odoo for print jobs
    (outgoing HTTPS only: no port to open on the warehouse side)."""

    _name = "barcode.label.agent"
    _description = "Label print agent"

    name = fields.Char(required=True)
    token = fields.Char(required=True, copy=False, readonly=True, groups="stock.group_stock_manager",
                        default=lambda self: secrets.token_urlsafe(24))
    last_seen = fields.Datetime(readonly=True)
    printer_ids = fields.One2many("barcode.label.printer", "agent_id")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    active = fields.Boolean(default=True)

    def action_regenerate_token(self):
        for agent in self:
            agent.token = secrets.token_urlsafe(24)

    @api.model
    def _by_token(self, token):
        if not token or len(token) < 20:
            return self.browse()
        return self.sudo().search([("token", "=", token), ("active", "=", True)], limit=1)


class BarcodeLabelPrinter(models.Model):
    _name = "barcode.label.printer"
    _description = "Thermal label printer"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    agent_id = fields.Many2one("barcode.label.agent", required=True, ondelete="restrict")
    target = fields.Char(
        required=True, default="tcp://192.168.1.100:9100",
        help="Where the agent sends the data: tcp://IP:9100 (network printer), cups:QUEUE (Linux/macOS), "
             "win:PRINTER NAME (Windows), file:/path (test).")
    language = fields.Selection([("tspl", "TSPL (TSC, Gprinter, Xprinter, HPRT...)"), ("zpl", "ZPL (Zebra)")],
                                default="tspl", required=True)
    dpi = fields.Selection([("203", "203 dpi"), ("300", "300 dpi")], default="203", required=True)
    width_mm = fields.Float("Label width (mm)", default=40, required=True)
    height_mm = fields.Float("Label height (mm)", default=30, required=True)
    gap_mm = fields.Float("Gap (mm)", default=2)
    darkness = fields.Integer(default=16, help="0-30")
    tspl_invert = fields.Boolean("Invert text bitmap (TSPL)", help="Tick if text prints as a black block with white letters.")
    show_price = fields.Boolean("Price on product labels", default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True)
    active = fields.Boolean(default=True)

    @api.model
    def _default_for_user(self):
        printer = self.env.user.bc_label_printer_id
        if printer and printer.active:
            return printer
        return self.search([("company_id", "in", [self.env.company.id, False])], limit=1)

    def _print(self, contents, name):
        """contents: list of (content dict, copies). Queues one job."""
        self.ensure_one()
        data = self.env["barcode.label.render"].render(self, contents)
        if not data:
            raise UserError(_("Nothing to print."))
        count = sum(c for _x, c in contents)
        return self.env["barcode.label.job"].sudo().create({
            "printer_id": self.id,
            "name": name,
            "data": base64.b64encode(data),
            "label_count": count,
            "user_id": self.env.uid,
        })

    def action_test_print(self):
        self.ensure_one()
        content = {"lines": [(_("Test label %s", self.name), "title"), ("中文 English 123", "sub")],
                   "barcode": "6901234567892"}
        self._print([(content, 1)], _("Test label"))
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"message": _("Test label sent to the agent queue."), "type": "success"}}


class BarcodeLabelJob(models.Model):
    _name = "barcode.label.job"
    _description = "Label print job"
    _order = "id desc"

    name = fields.Char()
    printer_id = fields.Many2one("barcode.label.printer", required=True, ondelete="cascade", index=True)
    agent_id = fields.Many2one(related="printer_id.agent_id", store=True, index=True)
    data = fields.Binary(attachment=False)
    label_count = fields.Integer()
    state = fields.Selection([("queued", "Queued"), ("sent", "Sent to agent"), ("done", "Printed"),
                              ("error", "Error")], default="queued", index=True)
    error = fields.Char()
    user_id = fields.Many2one("res.users")
    sent_date = fields.Datetime()
    done_date = fields.Datetime()

    def action_retry(self):
        self.write({"state": "queued", "error": False})

    @api.model
    def _gc_old_jobs(self):
        limit = fields.Datetime.subtract(fields.Datetime.now(), days=30)
        self.search([("create_date", "<", limit), ("state", "in", ["done", "error"])]).unlink()
        # jobs claimed by an agent that never answered: make them printable again
        stale = fields.Datetime.subtract(fields.Datetime.now(), minutes=5)
        self.search([("state", "=", "sent"), ("sent_date", "<", stale)]).write({"state": "queued"})


class ResUsers(models.Model):
    _inherit = "res.users"

    bc_label_printer_id = fields.Many2one("barcode.label.printer", "Default label printer")
