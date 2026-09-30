from odoo import Command
from odoo.tests import Form, HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSaleBarcode(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Scan Customer"})
        cls.cola = cls.env["product.product"].create({
            "name": "Cola", "is_storable": True, "barcode": "6901234567892", "list_price": 3.5,
            "invoice_policy": "delivery"})
        dozen = cls.env.ref("uom.product_uom_dozen")
        cls.env["product.uom"].create({"product_id": cls.cola.id, "uom_id": dozen.id, "barcode": "16901234567899"})
        wh = cls.env["stock.warehouse"].search([("company_id", "=", cls.env.company.id)], limit=1)
        cls.env["stock.quant"]._update_available_quantity(cls.cola, wh.lot_stock_id, 100)

    def test_scan_into_quotation(self):
        with Form(self.env["sale.order"]) as so_form:
            so_form.partner_id = self.partner
            so_form._barcode_scanned = "6901234567892"
            so_form._barcode_scanned = "6901234567892"
            so_form._barcode_scanned = "16901234567899"
        order = so_form.record
        self.assertEqual(len(order.order_line), 1)
        self.assertEqual(order.order_line.product_uom_qty, 14)
        self.assertEqual(order.order_line.price_unit, 3.5)

    def test_unknown_barcode_warning(self):
        order = self.env["sale.order"].create({"partner_id": self.partner.id})
        res = order.on_barcode_scanned("0000000")
        self.assertIn("warning", res)

    def test_delivery_then_invoice(self):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [Command.create({"product_id": self.cola.id, "product_uom_qty": 2})]})
        order.action_confirm()
        picking = order.picking_ids
        ctx = {}
        for _i in range(2):
            ctx = picking.bc_scan("6901234567892", ctx)["ctx"]
        res = picking.bc_validate()
        self.assertTrue(res["done"])
        self.assertEqual(len(res["next_actions"]), 1)
        action = res["next_actions"][0]["action"]
        wiz = self.env["sale.advance.payment.inv"].with_context(action["context"]).create({})
        wiz.create_invoices()
        self.assertEqual(order.invoice_ids.amount_untaxed, 7.0)


@tagged("post_install", "-at_install")
class TestSaleBarcodeTour(HttpCase):
    def test_sale_form_scan_tour(self):
        self.env["product.product"].create({"name": "Tour Cola", "barcode": "6901234567892", "list_price": 3.5})
        self.env["res.partner"].create({"name": "Tour Customer"})
        self.start_tour("/odoo/action-sale.action_quotations_with_onboarding/new", "sale_barcode_ce_tour", login="admin")
        order = self.env["sale.order"].search([("partner_id.name", "=", "Tour Customer")])
        self.assertEqual(order.order_line.product_uom_qty, 2)
