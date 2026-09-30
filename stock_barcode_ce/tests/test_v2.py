from odoo import Command
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestBarcodeV2(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wh = cls.env["stock.warehouse"].search([("company_id", "=", cls.env.company.id)], limit=1)
        cls.cola = cls.env["product.product"].create({"name": "Cola", "is_storable": True, "barcode": "6901234567892"})
        t = cls.wh.in_type_id
        cls.picking = cls.env["stock.picking"].create({
            "picking_type_id": t.id, "location_id": t.default_location_src_id.id,
            "location_dest_id": t.default_location_dest_id.id,
            "move_ids": [Command.create({"product_id": cls.cola.id, "product_uom_qty": 10,
                                         "location_id": t.default_location_src_id.id,
                                         "location_dest_id": t.default_location_dest_id.id})]})
        cls.picking.action_confirm()
        cls.operator = new_test_user(cls.env, "bc_v2_op", groups="stock_barcode_ce.group_barcode_operator")

    def test_scan_creates_events_not_row_updates(self):
        p = self.picking.with_context(bc_device="Android-v2")
        p.bc_scan("6901234567892", {}, uuid="u-1")
        p.bc_scan("6901234567892", {}, uuid="u-2")
        events = self.env["stock.barcode.scan.event"].search([("picking_id", "=", self.picking.id)])
        self.assertEqual(events.mapped("qty"), [1.0, 1.0])
        self.assertEqual(set(events.mapped("kind")), {"scan"})
        self.assertEqual(set(events.mapped("device")), {"Android-v2"})
        self.assertEqual(set(events.mapped("scan_uuid")), {"u-1", "u-2"})
        self.assertEqual(sum(self.picking.move_line_ids.mapped("bc_qty")), 2)

    def test_resent_scan_counted_once(self):
        self.picking.bc_scan("6901234567892", {}, uuid="same")
        state = self.picking.bc_scan("6901234567892", {}, uuid="same")
        self.assertTrue(state["feedback"].get("duplicate"))
        self.assertEqual(state["moves"][0]["done"], 1)

    def test_manual_quantity_is_an_event(self):
        state = self.picking.bc_scan("6901234567892", {})
        self.picking.bc_set_move_qty(state["moves"][0]["move_id"], 7, state["ctx"])
        events = self.env["stock.barcode.scan.event"].search([("picking_id", "=", self.picking.id)])
        self.assertEqual(events.mapped("kind"), ["scan", "manual"])
        self.assertEqual(sum(events.mapped("qty")), 7)
        res = self.picking.bc_validate(backorder=False)
        self.assertTrue(res["done"])
        self.assertEqual(self.picking.move_ids.quantity, 7)

    def test_live_update_and_presence(self):
        self.env["bus.bus"].search([]).unlink()
        self.picking.with_user(self.operator).bc_scan("6901234567892", {})
        self.env.cr.precommit.run()  # bus notifications are written at commit time
        channel = "stock_barcode_ce.stock.picking.%s" % self.picking.id
        notes = self.env["bus.bus"].sudo().search([("channel", "like", channel)])
        self.assertTrue(notes, "other scanners of the transfer are notified")
        self.assertNotIn("6901234567892", notes[0].message, "no business data in the notification")
        state = self.picking.bc_get_state({})
        self.assertEqual([p["user"] for p in state["presence"]], [self.operator.name])
        self.assertIn(channel, state["channels"])

    def test_package_and_transfer_kinds(self):
        bin_loc = self.env["stock.location"].create({"name": "B1", "location_id": self.wh.lot_stock_id.id, "barcode": "B1-CODE"})
        state = self.picking.bc_scan("6901234567892", {})
        state = self.picking.bc_scan("B1-CODE", state["ctx"])
        kinds = self.env["stock.barcode.scan.event"].search([("picking_id", "=", self.picking.id)]).mapped("kind")
        self.assertEqual(kinds.count("transfer"), 2, "the scanned unit moved to the bin line: -1 / +1")
        self.assertEqual(sum(self.picking.move_line_ids.mapped("bc_qty")), 1)
        self.assertTrue(bin_loc)
