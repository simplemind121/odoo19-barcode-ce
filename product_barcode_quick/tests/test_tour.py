from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestProductScanTour(HttpCase):
    def test_product_scan_tour(self):
        self.env["product.product"].create({"name": "Tour Cola", "barcode": "6901234567892", "list_price": 3.5})
        self.start_tour("/odoo/action-product_barcode_quick.action_product_scan", "product_barcode_quick_tour", login="admin")
        created = self.env["product.product"].search([("barcode", "=", "6901234567809")])
        self.assertEqual(created.name, "Tour Tea")
