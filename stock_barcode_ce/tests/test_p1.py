import datetime

from odoo import Command, fields
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestBarcodeP1(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.wh = env["stock.warehouse"].search([("company_id", "=", env.company.id)], limit=1)
        cls.stock = cls.wh.lot_stock_id
        cls.cola = env["product.product"].create({"name": "Cola", "is_storable": True, "barcode": "6901234567892"})
        cls.operator = new_test_user(env, "bc_p1_op", groups="stock_barcode_ce.group_barcode_operator")
        cls.supervisor = new_test_user(env, "bc_p1_sup", groups="stock_barcode_ce.group_barcode_supervisor")

    def _picking(self, ptype, product, qty):
        picking = self.env["stock.picking"].create({
            "picking_type_id": ptype.id, "location_id": ptype.default_location_src_id.id,
            "location_dest_id": ptype.default_location_dest_id.id,
            "move_ids": [Command.create({"product_id": product.id, "product_uom_qty": qty,
                                         "location_id": ptype.default_location_src_id.id,
                                         "location_dest_id": ptype.default_location_dest_id.id})]})
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _scan(self, rec, codes, ctx=None):
        state = None
        for code in codes:
            state = rec.bc_scan(code, ctx)
            ctx = state["ctx"]
        return state

    # returns --------------------------------------------------------
    def test_return_created_and_scanned_by_operator(self):
        self.env["stock.quant"]._update_available_quantity(self.cola, self.stock, 5)
        out = self._picking(self.wh.out_type_id, self.cola, 3)
        self._scan(out, ["6901234567892"] * 3)
        self.assertTrue(out.bc_validate()["done"])
        res = out.with_user(self.operator).bc_create_return()
        ret = self.env["stock.picking"].browse(res["id"])
        self.assertEqual(ret.move_ids.product_uom_qty, 3)
        self.assertEqual(ret.return_id, out)
        self._scan(ret.with_user(self.operator), ["6901234567892"])
        state = ret.with_user(self.operator).bc_validate()
        self.assertEqual(state.get("confirm"), "backorder")
        self.assertTrue(ret.with_user(self.operator).bc_validate(backorder=False)["done"])
        self.assertEqual(self.cola.qty_available, 3, "5 - 3 shipped + 1 returned")

    # scrap ----------------------------------------------------------
    def test_scrap_supervisor_only(self):
        self.env["stock.quant"]._update_available_quantity(self.cola, self.stock, 5)
        Scrap = self.env["stock.scrap"]
        state = Scrap.with_user(self.operator).bc_scrap_scan("6901234567892", {})
        state = Scrap.with_user(self.operator).bc_scrap_confirm(state["ctx"], 2)
        self.assertEqual(state["feedback"]["level"], "danger")
        self.assertEqual(self.cola.qty_available, 5)
        reason = self.env["stock.scrap.reason.tag"].create({"name": "Damaged"})
        sup = Scrap.with_user(self.supervisor)
        state = sup.bc_scrap_scan(self.stock.barcode, {})
        state = sup.bc_scrap_scan("6901234567892", state["ctx"])
        self.assertEqual(state["available"], 5)
        state = sup.bc_scrap_confirm(state["ctx"], 9, [reason.id])
        self.assertEqual(state["feedback"]["level"], "danger", "cannot scrap more than available")
        state = sup.bc_scrap_confirm(state["ctx"], 2, [reason.id])
        self.assertTrue(state["feedback"].get("done"), state["feedback"])
        self.assertEqual(self.cola.qty_available, 3)
        scrap = self.env["stock.scrap"].search([("product_id", "=", self.cola.id)])
        self.assertEqual(scrap.scrap_reason_tag_ids, reason)
        self.assertEqual(scrap.create_uid, self.supervisor)

    def test_scrap_tracked_needs_lot(self):
        milk = self.env["product.product"].create({"name": "Milk", "is_storable": True, "tracking": "lot",
                                                   "barcode": "6901234567816"})
        lot = self.env["stock.lot"].create({"name": "M-1", "product_id": milk.id})
        self.env["stock.quant"]._update_available_quantity(milk, self.stock, 4, lot_id=lot)
        sup = self.env["stock.scrap"].with_user(self.supervisor)
        state = sup.bc_scrap_scan("6901234567816", {})
        self.assertEqual(state["feedback"]["level"], "warning")
        state2 = sup.bc_scrap_confirm(state["ctx"], 1)
        self.assertEqual(state2["feedback"]["level"], "danger")
        state = sup.bc_scrap_scan("M-1", state["ctx"])
        state = sup.bc_scrap_confirm(state["ctx"], 1)
        self.assertTrue(state["feedback"].get("done"), state["feedback"])
        self.assertEqual(self.env["stock.quant"]._get_available_quantity(milk, self.stock, lot_id=lot), 3)

    # expired lots -----------------------------------------------------
    def test_expired_lot_needs_supervisor(self):
        if "product_expiry_alert" not in self.env["stock.lot"]._fields:
            self.skipTest("product_expiry not installed")
        milk = self.env["product.product"].create({"name": "Milk", "is_storable": True, "tracking": "lot",
                                                   "barcode": "6901234567816", "use_expiration_date": True})
        lot = self.env["stock.lot"].create({
            "name": "OLD-1", "product_id": milk.id,
            "expiration_date": fields.Datetime.now() - datetime.timedelta(days=3)})
        self.env["stock.quant"]._update_available_quantity(milk, self.stock, 2, lot_id=lot)
        out = self._picking(self.wh.out_type_id, milk, 2)
        self._scan(out.with_user(self.operator), ["OLD-1", "OLD-1"])
        res = out.with_user(self.operator).bc_validate()
        self.assertEqual(res.get("confirm"), "expired", res)
        self.assertFalse(res["allowed"])
        res = out.with_user(self.operator).bc_validate(expired_ok=True)
        self.assertEqual(res.get("level"), "danger")
        self.assertNotEqual(out.state, "done")
        res = out.with_user(self.supervisor).bc_validate()
        self.assertTrue(res["allowed"])
        res = out.with_user(self.supervisor).bc_validate(expired_ok=True)
        self.assertTrue(res.get("done"), res)

    # unknown product requests -----------------------------------------
    def test_operator_requests_unknown_product(self):
        picking = self._picking(self.wh.in_type_id, self.cola, 1)
        state = picking.with_user(self.operator).bc_scan("6901234567809", {})
        self.assertFalse(state["can_create_product"])
        self.assertEqual(state["feedback"]["unknown_barcode"], "6901234567809")
        Req = self.env["product.barcode.request"].with_user(self.operator)
        self.assertEqual(Req.bcq_request("6901234567809", picking.name)["level"], "success")
        Req.bcq_request("6901234567809", picking.name)
        req = self.env["product.barcode.request"].search([("barcode", "=", "6901234567809")])
        self.assertEqual((len(req), req.count, req.state, req.user_id), (1, 2, "open", self.operator))
        self.assertTrue(picking.bc_get_state({})["can_create_product"], "admin can create products")
        product = self.env["product.product"].create({"name": "Chips", "barcode": "6901234567809"})
        self.assertEqual((req.state, req.product_id), ("done", product))
        self.assertEqual(Req.bcq_request("6901234567809")["level"], "info")
