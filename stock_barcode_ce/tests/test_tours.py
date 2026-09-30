from odoo import Command
from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestStockBarcodeTours(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        admin = env.ref("base.user_admin")
        admin.group_ids |= env.ref("stock.group_stock_multi_locations")
        cls.wh = env["stock.warehouse"].search([("company_id", "=", env.company.id)], limit=1)
        cls.wh.code = "WHT"
        env["stock.bin.generator"].create({
            "warehouse_id": cls.wh.id, "parent_location_id": cls.wh.lot_stock_id.id,
            "zones": "A", "racks": 1, "levels": 1, "bins": 1}).action_generate()
        cls.bin = env["stock.location"].search([("barcode", "=", "WHT-A-01-1-01")])
        cls.cola = env["product.product"].create({"name": "Tour Cola", "is_storable": True, "barcode": "6901234567892"})

    def _picking(self, ptype, name, qty):
        picking = self.env["stock.picking"].create({
            "name": name,
            "picking_type_id": ptype.id,
            "location_id": ptype.default_location_src_id.id,
            "location_dest_id": ptype.default_location_dest_id.id,
            "move_ids": [Command.create({
                "product_id": self.cola.id, "product_uom_qty": qty,
                "location_id": ptype.default_location_src_id.id,
                "location_dest_id": ptype.default_location_dest_id.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        return picking

    def test_receipt_tour(self):
        picking = self._picking(self.wh.in_type_id, "BCTOUR/IN/001", 2)
        self.start_tour("/odoo/action-stock_barcode_ce.action_stock_barcode_ce_main", "stock_barcode_ce_receipt_tour", login="admin")
        self.assertEqual(picking.state, "done")
        self.assertEqual(self.cola.with_context(location=self.bin.id).qty_available, 2)
        crackers = self.env["product.product"].search([("barcode", "=", "6901234567809")])
        self.assertEqual(crackers.name, "Tour Crackers")
        self.assertEqual(picking.move_ids.filtered(lambda m: m.product_id == crackers).quantity, 1)

    def test_inventory_tour(self):
        self.env["stock.quant"]._update_available_quantity(self.cola, self.bin, 5)
        self.start_tour("/odoo/action-stock_barcode_ce.action_stock_barcode_ce_main", "stock_barcode_ce_inventory_tour", login="admin")
        self.assertEqual(self.cola.with_context(location=self.bin.id).qty_available, 7)

    def test_delivery_list_tour(self):
        self.env["stock.quant"]._update_available_quantity(self.cola, self.wh.lot_stock_id, 5)
        self.wh.out_type_id.create_backorder = "ask"
        picking = self._picking(self.wh.out_type_id, "BCTOUR/OUT/001", 3)
        self.start_tour("/odoo/action-stock_barcode_ce.action_stock_barcode_ce_main", "stock_barcode_ce_delivery_list_tour", login="admin")
        self.assertEqual(picking.state, "done")
        self.assertEqual(picking.move_ids.quantity, 1)
        backorder = self.env["stock.picking"].search([("backorder_id", "=", picking.id)])
        self.assertEqual(backorder.move_ids.product_uom_qty, 2)

    def test_operator_tour(self):
        operator = new_test_user(self.env, "bc_op_tour", password="bc_op_tour",
                                 groups="stock_barcode_ce.group_barcode_operator")
        self.wh.in_type_id.write({"bc_scan_only": True, "create_backorder": "ask"})
        picking = self._picking(self.wh.in_type_id, "BCTOUR/IN/OP1", 3)
        self.start_tour("/odoo", "stock_barcode_ce_operator_tour", login="bc_op_tour")
        self.assertEqual(picking.state, "done")
        self.assertEqual(picking.move_ids.quantity, 1)
        log_users = self.env["stock.barcode.scan.log"].search([("picking_id", "=", picking.id)]).user_id
        self.assertEqual(log_users, operator)

    def test_offline_tour(self):
        picking = self._picking(self.wh.in_type_id, "BCTOUR/IN/OFF1", 2)
        self.start_tour("/odoo/action-stock_barcode_ce.action_stock_barcode_ce_main", "stock_barcode_ce_offline_tour", login="admin")
        self.assertEqual(picking.state, "done")
        self.assertEqual(picking.move_ids.quantity, 2)
        events = self.env["stock.barcode.scan.event"].search([("picking_id", "=", picking.id)])
        self.assertEqual(sum(events.mapped("qty")), 2, "each offline scan counted exactly once")
        self.assertEqual(len(set(events.mapped("scan_uuid"))), 2)

    def test_p1_tour(self):
        self.env["stock.scrap.reason.tag"].create({"name": "Damaged"})
        self.env["stock.quant"]._update_available_quantity(self.cola, self.wh.lot_stock_id, 10)
        out = self._picking(self.wh.out_type_id, "BCTOUR/OUT/DONE", 3)
        out.move_ids.quantity = 3
        out.move_ids.picked = True
        out.button_validate()
        self.assertEqual(out.state, "done")
        self.start_tour("/odoo/action-stock_barcode_ce.action_stock_barcode_ce_main", "stock_barcode_ce_p1_tour", login="admin")
        self.assertEqual(self.env["stock.scrap"].search([("product_id", "=", self.cola.id)]).scrap_qty, 2)
        ret = self.env["stock.picking"].search([("return_id", "=", out.id)])
        self.assertEqual(sum(ret.move_line_ids.mapped("bc_qty")), 1)

    def test_request_tour(self):
        new_test_user(self.env, "bc_req_tour", password="bc_req_tour", groups="stock_barcode_ce.group_barcode_operator")
        self._picking(self.wh.in_type_id, "BCTOUR/IN/REQ", 1)
        self.start_tour("/odoo", "stock_barcode_ce_request_tour", login="bc_req_tour")
        self.assertTrue(self.env["product.barcode.request"].search([("barcode", "=", "6901234567809")]))
