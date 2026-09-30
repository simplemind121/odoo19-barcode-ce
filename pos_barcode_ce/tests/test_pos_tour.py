from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon


@tagged("post_install", "-at_install")
class TestPosBarcodeCE(TestPointOfSaleHttpCommon):

    def test_create_unknown_product_from_scan(self):
        # product creation from the POS needs product create rights (Product > Manager group)
        self.pos_admin.group_ids |= self.env.ref("product.group_product_manager")
        self.main_pos_config.with_user(self.pos_admin).open_ui()
        self.start_tour("/pos/ui/%d" % self.main_pos_config.id, "pos_barcode_ce_create_unknown", login="pos_admin")
        product = self.env["product.product"].search([("barcode", "=", "6901234567809")])
        self.assertEqual(product.name, "POS Scanned Snack")
        self.assertTrue(product.available_in_pos)
