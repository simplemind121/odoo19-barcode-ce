from odoo import _, models


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "barcodes.barcode_events_mixin"]

    def on_barcode_scanned(self, barcode):
        if self.state not in ("draft", "sent"):
            return {"warning": {"title": _("Order locked"), "message": _("Only quotations can be edited by scanning.")}}
        product, qty, _uom, _parsed = self.env["product.product"].bcq_find_by_barcode(barcode)
        if not product:
            return {"warning": {
                "title": _("Unknown barcode"),
                "message": _("No product with barcode %s. Create it from Barcode > Scan products.", barcode)}}
        if not product.sale_ok:
            return {"warning": {"title": _("Not sellable"), "message": _("%s cannot be sold.", product.display_name)}}
        qty = qty or 1.0
        line = self.order_line.filtered(lambda l: l.product_id == product and not l.display_type)[:1]
        if line:
            line.product_uom_qty += qty
        else:
            self.order_line += self.env["sale.order.line"].new({
                "order_id": self.id,
                "product_id": product.id,
                "product_uom_qty": qty,
                "sequence": max(self.order_line.mapped("sequence") or [10]) + 1,
            })
        return None


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _bc_next_actions(self):
        actions = super()._bc_next_actions()
        orders = self.sale_id.filtered(lambda so: so.invoice_status == "to invoice")
        for order in orders:
            action = self.env["ir.actions.actions"]._for_xml_id("sale.action_view_sale_advance_payment_inv")
            action["context"] = {"active_model": "sale.order", "active_ids": order.ids, "active_id": order.id}
            actions.append({"label": _("Create invoice for %s", order.name), "action": action})
        return actions
