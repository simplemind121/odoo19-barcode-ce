from odoo import _, models


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["purchase.order", "barcodes.barcode_events_mixin"]

    def on_barcode_scanned(self, barcode):
        if self.state not in ("draft", "sent"):
            return {"warning": {"title": _("Order locked"), "message": _("Only requests for quotation can be edited by scanning.")}}
        product, qty, _uom, _parsed = self.env["product.product"].bcq_find_by_barcode(barcode)
        if not product:
            return {"warning": {
                "title": _("Unknown barcode"),
                "message": _("No product with barcode %s. Create it from Barcode > Scan products.", barcode)}}
        if not product.purchase_ok:
            return {"warning": {"title": _("Not purchasable"), "message": _("%s cannot be purchased.", product.display_name)}}
        qty = qty or 1.0
        line = self.order_line.filtered(lambda l: l.product_id == product and not l.display_type)[:1]
        if line:
            line.product_qty += qty
        else:
            self.order_line += self.env["purchase.order.line"].new({
                "order_id": self.id,
                "product_id": product.id,
                "product_qty": qty,
                "sequence": max(self.order_line.mapped("sequence") or [10]) + 1,
            })
        return None


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _bc_next_actions(self):
        actions = super()._bc_next_actions()
        orders = self.purchase_id.filtered(lambda po: po.invoice_status == "to invoice")
        for order in orders:
            actions.append({
                "label": _("Create bill for %s", order.name),
                "action": {
                    "type": "ir.actions.server_call",  # handled client side via orm
                    "model": "purchase.order",
                    "method": "action_create_invoice",
                    "res_id": order.id,
                },
            })
        return actions
