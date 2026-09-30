from odoo import Command
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPurchaseBarcode(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.vendor = cls.env["res.partner"].create({"name": "Scan Vendor"})
        cls.cola = cls.env["product.product"].create({
            "name": "Cola", "is_storable": True, "barcode": "6901234567892", "standard_price": 2.0,
            "purchase_method": "receive"})

    def test_scan_into_rfq(self):
        with Form(self.env["purchase.order"]) as po_form:
            po_form.partner_id = self.vendor
            for _i in range(3):
                po_form._barcode_scanned = "6901234567892"
        order = po_form.record
        self.assertEqual(order.order_line.product_qty, 3)

    def test_receipt_then_bill_matches_received_qty(self):
        order = self.env["purchase.order"].create({
            "partner_id": self.vendor.id,
            "order_line": [Command.create({"product_id": self.cola.id, "product_qty": 10, "price_unit": 2.0})]})
        order.button_confirm()
        picking = order.picking_ids
        ctx = {}
        for _i in range(6):
            ctx = picking.bc_scan("6901234567892", ctx)["ctx"]
        res = picking.bc_validate()
        self.assertEqual(res.get("confirm"), "backorder")
        res = picking.bc_validate(backorder=False)
        next_actions = res["next_actions"]
        self.assertEqual(len(next_actions), 1)
        na = next_actions[0]["action"]
        self.env[na["model"]].browse(na["res_id"]).action_create_invoice()
        bill = order.invoice_ids
        self.assertEqual(bill.invoice_line_ids.quantity, 6, "bill follows the scanned received quantity")
        self.assertEqual(bill.amount_untaxed, 12.0)
