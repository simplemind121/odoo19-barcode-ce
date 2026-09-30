from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.product_barcode_quick.models.barcode_tools import make_ean13


@tagged("post_install", "-at_install")
class TestBarcodeControls(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        env.ref("base.group_user").implied_ids |= env.ref("stock.group_stock_multi_locations")
        cls.wh = env["stock.warehouse"].search([("company_id", "=", env.company.id)], limit=1)
        cls.stock = cls.wh.lot_stock_id
        env["stock.bin.generator"].create({
            "warehouse_id": cls.wh.id, "parent_location_id": cls.stock.id,
            "zones": "Z", "racks": 1, "levels": 1, "bins": 2}).action_generate()
        Loc = env["stock.location"]
        cls.bin1 = Loc.search([("barcode", "=", "%s-Z-01-1-01" % cls.wh.code)])
        cls.bin2 = Loc.search([("barcode", "=", "%s-Z-01-1-02" % cls.wh.code)])
        cls.cola = env["product.product"].create({"name": "Cola", "is_storable": True, "barcode": "6901234567892"})
        cls.chips = env["product.product"].create({"name": "Chips", "is_storable": True, "barcode": "6901234567809"})
        cls.operator = new_test_user(env, "bc_operator", groups="stock_barcode_ce.group_barcode_operator")
        cls.supervisor = new_test_user(env, "bc_supervisor", groups="stock_barcode_ce.group_barcode_supervisor")
        cls.type_in = cls.wh.in_type_id
        cls.type_out = cls.wh.out_type_id
        cls.type_int = cls.wh.int_type_id

    def _picking(self, ptype, lines):
        picking = self.env["stock.picking"].create({
            "picking_type_id": ptype.id,
            "location_id": ptype.default_location_src_id.id,
            "location_dest_id": ptype.default_location_dest_id.id,
            "move_ids": [Command.create({
                "product_id": p.id, "product_uom_qty": q,
                "location_id": ptype.default_location_src_id.id,
                "location_dest_id": ptype.default_location_dest_id.id,
            }) for p, q in lines],
        })
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _scan(self, rec, codes, ctx=None):
        state = None
        for code in codes:
            state = rec.bc_scan(code, ctx)
            ctx = state["ctx"]
        return state

    # ------------------------------------------------------------------ roles
    def test_operator_scanner_only(self):
        picking = self._picking(self.type_in, [(self.cola, 2)])
        op_picking = picking.with_user(self.operator)
        # no backend write access
        with self.assertRaises(AccessError):
            op_picking.write({"origin": "hack"})
        with self.assertRaises(AccessError):
            self.env["stock.picking"].with_user(self.operator).create({"picking_type_id": self.type_in.id})
        # but the scanner works end to end
        state = self._scan(op_picking.with_context(bc_device="Android-test"), ["6901234567892", "6901234567892", self.bin1.barcode])
        self.assertEqual(state["moves"][0]["done"], 2)
        res = op_picking.bc_validate()
        self.assertTrue(res["done"], res)
        self.assertEqual(picking.state, "done")
        logs = self.env["stock.barcode.scan.log"].search([("picking_id", "=", picking.id)])
        self.assertEqual(set(logs.mapped("user_id")), {self.operator})
        self.assertIn("Android-test", logs.mapped("device"))
        self.assertIn("validate", logs.mapped("operation"))
        # dashboard is reachable, the inventory app menu is not
        self.assertTrue(self.env["stock.picking.type"].with_user(self.operator).bc_dashboard()["warehouses"])
        self.assertEqual(self.operator.action_id.id, self.env.ref("stock_barcode_ce.action_stock_barcode_ce_main").id)
        self.assertFalse(self.operator.has_group("stock.group_stock_user"))

    def test_user_without_role_refused(self):
        nobody = new_test_user(self.env, "bc_nobody", groups="base.group_user")
        picking = self._picking(self.type_in, [(self.cola, 1)])
        with self.assertRaises(AccessError):
            picking.with_user(nobody).bc_scan("6901234567892")

    def test_operator_multicompany_isolation(self):
        other = self.env["res.company"].create({"name": "Other Co"})
        other_wh = self.env["stock.warehouse"].search([("company_id", "=", other.id)], limit=1)
        picking = self.env["stock.picking"].with_company(other).create({
            "picking_type_id": other_wh.in_type_id.id,
            "location_id": other_wh.in_type_id.default_location_src_id.id,
            "location_dest_id": other_wh.lot_stock_id.id})
        with self.assertRaises(AccessError):
            picking.with_user(self.operator).bc_get_state()

    # ------------------------------------------------------------------ rules
    def test_rule_scan_only(self):
        self.type_in.bc_scan_only = True
        picking = self._picking(self.type_in, [(self.cola, 5)])
        state = picking.with_user(self.operator).bc_scan("6901234567892")
        move_id = state["moves"][0]["move_id"]
        self.assertFalse(state["rules"]["manual_allowed"])
        state = picking.with_user(self.operator).bc_set_move_qty(move_id, 5, state["ctx"])
        self.assertEqual(state["feedback"]["level"], "danger")
        self.assertEqual(state["moves"][0]["done"], 1)
        state = picking.with_user(self.operator).bc_add_product(self.cola.id, 1, state["ctx"])
        self.assertEqual(state["feedback"]["level"], "danger")
        # supervisor may type
        state = picking.with_user(self.supervisor).bc_set_move_qty(move_id, 5, state["ctx"])
        self.assertEqual(state["moves"][0]["done"], 5)
        logs = self.env["stock.barcode.scan.log"].search([("picking_id", "=", picking.id), ("operation", "=", "set_qty")])
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs.filtered(lambda l: l.user_id == self.supervisor).old_quantity, 1)
        # forcing an unscanned validation is refused for operators
        other = self._picking(self.type_in, [(self.chips, 1)])
        res = other.with_user(self.operator).bc_validate(force=True)
        self.assertEqual(res["level"], "danger")
        self.assertNotEqual(other.state, "done")
        res = other.with_user(self.operator).bc_validate()
        self.assertFalse(res["allowed"])

    def test_rule_require_source(self):
        self.type_out.bc_require_source = True
        self.env["stock.quant"]._update_available_quantity(self.cola, self.bin1, 5)
        picking = self._picking(self.type_out, [(self.cola, 1)])
        state = picking.bc_scan("6901234567892")
        self.assertEqual(state["feedback"]["level"], "danger")
        state = self._scan(picking, [self.bin1.barcode, "6901234567892"], state["ctx"])
        self.assertEqual(state["feedback"]["level"], "success")

    def test_rule_require_dest(self):
        self.type_in.bc_require_dest = True
        picking = self._picking(self.type_in, [(self.cola, 1)])
        self._scan(picking, ["6901234567892"])
        res = picking.bc_validate()
        self.assertEqual(res["level"], "danger")
        self.assertNotEqual(picking.state, "done")
        picking.bc_scan(self.bin2.barcode, {"pending_line_ids": picking.move_line_ids.filtered("bc_qty").ids})
        res = picking.bc_validate()
        self.assertTrue(res["done"], res)

    def test_rule_require_pack(self):
        self.type_in.bc_require_pack = True
        picking = self._picking(self.type_in, [(self.cola, 1)])
        state = self._scan(picking, ["6901234567892"])
        self.assertEqual(picking.bc_validate()["level"], "danger")
        picking.bc_put_in_pack(state["ctx"])
        self.assertTrue(picking.bc_validate()["done"])

    def test_rule_block_extra_and_over(self):
        self.type_in.write({"bc_block_extra": True, "bc_block_over": True})
        picking = self._picking(self.type_in, [(self.cola, 1)])
        state = self._scan(picking, ["6901234567809"])
        self.assertEqual(state["feedback"]["level"], "danger")
        self.assertEqual(len(state["moves"]), 1)
        state = self._scan(picking, ["6901234567892", "6901234567892"])
        self.assertEqual(state["feedback"]["level"], "danger")
        self.assertEqual(state["moves"][0]["done"], 1)

    # ------------------------------------------------------------------ inventory roles
    def test_inventory_operator_counts_supervisor_applies(self):
        Quant = self.env["stock.quant"]
        Quant._update_available_quantity(self.cola, self.bin1, 5)
        op = Quant.with_user(self.operator)
        state = op.bc_inv_scan(self.bin1.barcode)
        state = op.bc_inv_scan("6901234567892", state["ctx"])
        state = op.bc_inv_scan("6901234567892", state["ctx"])
        self.assertFalse(state["is_supervisor"])
        state = op.bc_inv_apply(state["ctx"])
        self.assertEqual(state["feedback"]["level"], "danger")
        state = op.bc_inv_zero_uncounted(state["ctx"])
        self.assertEqual(state["feedback"]["level"], "danger")
        self.assertEqual(self.cola.with_context(location=self.bin1.id).qty_available, 5)
        sup = Quant.with_user(self.supervisor)
        state = sup.bc_inv_state({"all_users": True})
        self.assertEqual(state["counted"][0]["user"], self.operator.name)
        state = sup.bc_inv_apply({"all_users": True})
        self.assertTrue(state["feedback"].get("applied"), state["feedback"])
        self.assertEqual(self.cola.with_context(location=self.bin1.id).qty_available, 2)
        ops = self.env["stock.barcode.scan.log"].search([("operation", "like", "inv_")]).mapped("operation")
        self.assertIn("inv_scan", ops)
        self.assertIn("inv_apply", ops)

    # ------------------------------------------------------------------ log
    def test_scan_log_append_only(self):
        picking = self._picking(self.type_in, [(self.cola, 1)])
        picking.with_context(bc_device="iOS-abc").bc_scan("unknown-code")
        log = self.env["stock.barcode.scan.log"].search([("picking_id", "=", picking.id)], limit=1)
        self.assertEqual(log.level, "danger")
        self.assertEqual(log.barcode, "unknown-code")
        self.assertEqual(log.resolved_type, "unknown")
        self.assertEqual(log.schema_version, 1)
        with self.assertRaises(AccessError):
            log.with_user(self.supervisor).write({"barcode": "x"})
        self.assertTrue(log.with_user(self.supervisor).read(["barcode"]))

    # ------------------------------------------------------------------ data check
    def test_health_check(self):
        Product = self.env["product.product"]
        self.env.company.bcq_strict_gtin = False
        bad = Product.create({"name": "Bad digit", "barcode": "6901234567891"})
        weight_like = Product.create({"name": "Looks like weight", "barcode": make_ean13("210000100000")})
        lot_like = Product.create({"name": "Looks like lot", "barcode": "10123"})
        nobarcode = Product.create({"name": "No barcode"})
        self.bin2.barcode = self.chips.barcode  # a location label printed with a product code
        health = self.env["stock.barcode.health"].create({})
        health.action_run()
        by_cat = {}
        for line in health.line_ids:
            by_cat.setdefault(line.category, self.env["product.product"])
            by_cat[line.category] |= line.product_id
        self.assertIn(bad, by_cat["invalid_digit"])
        self.assertIn(weight_like, by_cat["nomenclature"])
        self.assertIn(lot_like, by_cat["nomenclature"])
        self.assertIn(nobarcode, by_cat["missing"])
        self.assertTrue(by_cat.get("duplicate"))
        self.assertNotIn(self.cola, by_cat.get("invalid_digit", Product))
        self.assertTrue(health.summary)
        health.action_generate_missing()
        self.assertTrue(nobarcode.barcode.startswith("20"))
