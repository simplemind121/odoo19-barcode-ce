from odoo import Command
from odoo.tests import TransactionCase, tagged

from odoo.addons.product_barcode_quick.models.barcode_tools import make_ean13


@tagged("post_install", "-at_install")
class TestStockBarcodeCE(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        env.user.group_ids |= env.ref("stock.group_stock_multi_locations") | env.ref("stock.group_production_lot") \
            | env.ref("stock.group_tracking_lot")
        cls.wh = env["stock.warehouse"].search([("company_id", "=", env.company.id)], limit=1)
        cls.stock = cls.wh.lot_stock_id
        gen = env["stock.bin.generator"].create({
            "warehouse_id": cls.wh.id, "parent_location_id": cls.stock.id,
            "zones": "A", "racks": 1, "levels": 1, "bins": 2})
        gen.action_generate()
        Loc = env["stock.location"]
        cls.bin1 = Loc.search([("barcode", "=", "%s-A-01-1-01" % cls.wh.code)])
        cls.bin2 = Loc.search([("barcode", "=", "%s-A-01-1-02" % cls.wh.code)])
        Product = env["product.product"]
        cls.cola = Product.create({"name": "Cola", "is_storable": True, "barcode": "6901234567892"})
        cls.chips = Product.create({"name": "Chips", "is_storable": True, "barcode": "6901234567809"})
        cls.milk = Product.create({"name": "Milk", "is_storable": True, "barcode": make_ean13("690123456781"),
                                   "tracking": "lot"})
        cls.phone = Product.create({"name": "Phone", "is_storable": True, "barcode": make_ean13("690123456782"),
                                    "tracking": "serial"})
        cls.type_in = cls.wh.in_type_id
        cls.type_out = cls.wh.out_type_id
        cls.type_int = cls.wh.int_type_id
        (cls.type_in | cls.type_out | cls.type_int).write({"create_backorder": "ask"})

    # helpers ---------------------------------------------------------
    def _picking(self, ptype, lines):
        picking = self.env["stock.picking"].create({
            "picking_type_id": ptype.id,
            "location_id": ptype.default_location_src_id.id,
            "location_dest_id": ptype.default_location_dest_id.id,
            "move_ids": [Command.create({
                "product_id": p.id, "product_uom_qty": q, "product_uom": p.uom_id.id,
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

    def _move(self, state, product):
        return next(m for m in state["moves"] if m["product_id"] == product.id)

    def _set_stock(self, product, location, qty, lot=None, package=None):
        self.env["stock.quant"]._update_available_quantity(product, location, qty, lot_id=lot, package_id=package)

    def _process_backorder_action(self, action, backorder=True):
        wiz = self.env[action["res_model"]].with_context(action["context"]).create({})
        return wiz.process() if backorder else wiz.process_cancel_backorder()

    # tests -----------------------------------------------------------
    def test_bins_generated_with_barcodes(self):
        self.assertTrue(self.bin1 and self.bin2)
        self.assertEqual(self.bin1.usage, "internal")
        self.assertEqual(self.bin1.location_id.usage, "view")
        self.assertIn("A-01-1-01", self.bin1.complete_name)
        res = self.env["stock.barcode.resolver"].resolve(self.bin1.barcode)
        self.assertEqual(res["location"], self.bin1)

    def test_receipt_partial_with_bin_and_backorder(self):
        picking = self._picking(self.type_in, [(self.cola, 5)])
        state = self._scan(picking, ["6901234567892"] * 3)
        move = self._move(state, self.cola)
        self.assertEqual(move["done"], 3)
        self.assertEqual(state["feedback"]["level"], "success")
        state = self._scan(picking, [self.bin1.barcode], state["ctx"])
        self.assertEqual(state["feedback"]["level"], "success")
        scanned = [l for l in self._move(state, self.cola)["lines"] if l["bc_qty"]]
        self.assertEqual(scanned[0]["location_dest_id"], self.bin1.id)
        res = picking.bc_validate()
        self.assertEqual(res.get("confirm"), "backorder", res)
        res = picking.bc_validate(backorder=True)
        self.assertTrue(res["done"], res)
        self.assertEqual(picking.state, "done")
        self.assertEqual(self.cola.with_context(location=self.bin1.id).qty_available, 3)
        backorder = self.env["stock.picking"].search([("backorder_id", "=", picking.id)])
        self.assertEqual(backorder.move_ids.product_uom_qty, 2)

    def test_receipt_full_scan_validates_directly(self):
        picking = self._picking(self.type_in, [(self.cola, 2), (self.chips, 1)])
        self._scan(picking, [self.bin2.barcode, "6901234567892", "6901234567892", "6901234567809"])
        res = picking.bc_validate()
        self.assertTrue(res["done"], res)
        self.assertEqual(self.cola.with_context(location=self.bin2.id).qty_available, 2)
        self.assertEqual(self.chips.with_context(location=self.bin2.id).qty_available, 1)

    def test_delivery_pick_from_bin(self):
        self._set_stock(self.cola, self.bin1, 10)
        picking = self._picking(self.type_out, [(self.cola, 4)])
        state = self._scan(picking, [self.bin1.barcode] + ["6901234567892"] * 4)
        self.assertEqual(self._move(state, self.cola)["done"], 4)
        self.assertTrue(self._move(state, self.cola)["complete"])
        res = picking.bc_validate()
        self.assertTrue(res["done"], res)
        self.assertEqual(self.cola.with_context(location=self.bin1.id).qty_available, 6)

    def test_wrong_location_is_rejected(self):
        picking = self._picking(self.type_out, [(self.cola, 1)])
        other_wh = self.env["stock.warehouse"].create({"name": "WH2", "code": "WH2"})
        state = picking.bc_scan(other_wh.lot_stock_id.barcode)
        self.assertEqual(state["feedback"]["level"], "danger")

    def test_unexpected_product_is_added(self):
        picking = self._picking(self.type_in, [(self.cola, 1)])
        state = self._scan(picking, ["6901234567892", "6901234567809"])
        self.assertEqual(state["feedback"]["level"], "warning")
        self.assertEqual(self._move(state, self.chips)["done"], 1)
        res = picking.bc_validate()
        self.assertTrue(res["done"], res)
        self.assertEqual(self.chips.qty_available, 1)

    def test_unknown_barcode(self):
        picking = self._picking(self.type_in, [(self.cola, 1)])
        state = picking.bc_scan("1234")
        self.assertEqual(state["feedback"]["level"], "danger")
        self.assertEqual(state["feedback"]["unknown_barcode"], "1234")

    def test_lot_receipt(self):
        picking = self._picking(self.type_in, [(self.milk, 5)])
        state = picking.bc_scan(self.milk.barcode)
        self.assertTrue(state["feedback"].get("need_lot"))
        state = self._scan(picking, ["LOT-A", self.milk.barcode, "LOT-A", self.milk.barcode, "LOT-B"], state["ctx"])
        move = self._move(state, self.milk)
        self.assertEqual(move["done"], 3)
        lots = {l["lot"]: l["bc_qty"] for l in move["lines"] if l["bc_qty"]}
        self.assertEqual(lots, {"LOT-A": 2, "LOT-B": 1})
        res = picking.bc_validate()
        self.assertEqual(res.get("confirm"), "backorder")
        picking.bc_validate(backorder=False)
        self.assertFalse(self.env["stock.picking"].search([("backorder_id", "=", picking.id)]))
        lot_a = self.env["stock.lot"].search([("name", "=", "LOT-A"), ("product_id", "=", self.milk.id)])
        self.assertEqual(lot_a.product_qty, 2)

    def test_serial_duplicate(self):
        picking = self._picking(self.type_in, [(self.phone, 2)])
        state = self._scan(picking, [self.phone.barcode, "SN-001", self.phone.barcode, "SN-001"])
        self.assertEqual(state["feedback"]["level"], "danger")
        state = self._scan(picking, [self.phone.barcode, "SN-002"], state["ctx"])
        self.assertEqual(self._move(state, self.phone)["done"], 2)
        res = picking.bc_validate()
        self.assertTrue(res["done"], res)
        self.assertEqual(self.env["stock.lot"].search_count([("product_id", "=", self.phone.id)]), 2)

    def test_lot_delivery_other_lot(self):
        lot1 = self.env["stock.lot"].create({"name": "L1", "product_id": self.milk.id})
        lot2 = self.env["stock.lot"].create({"name": "L2", "product_id": self.milk.id})
        self._set_stock(self.milk, self.bin1, 5, lot=lot1)
        self._set_stock(self.milk, self.bin2, 5, lot=lot2)
        picking = self._picking(self.type_out, [(self.milk, 3)])
        # reserved lot may be L1; the picker takes L2 instead (scanning the lot directly)
        state = self._scan(picking, ["L2", "L2", "L2"])
        move = self._move(state, self.milk)
        self.assertEqual(move["done"], 3)
        res = picking.bc_validate()
        self.assertTrue(res["done"], res)
        self.assertEqual(self.env["stock.quant"]._get_available_quantity(self.milk, self.bin2, lot_id=lot2), 2)
        self.assertEqual(self.env["stock.quant"]._get_available_quantity(self.milk, self.bin1, lot_id=lot1), 5)

    def test_gs1_single_scan(self):
        self.env.company.nomenclature_id = self.env.ref("barcodes_gs1_nomenclature.default_gs1_nomenclature")
        picking = self._picking(self.type_in, [(self.milk, 6)])
        code = "01" + self.milk.barcode.rjust(14, "0") + "10GS1LOT\x1d" + "376"
        state = picking.bc_scan(code)
        self.assertEqual(state["feedback"]["level"], "success", state["feedback"])
        move = self._move(state, self.milk)
        self.assertEqual(move["done"], 6)
        self.assertEqual(move["lines"][-1]["lot"], "GS1LOT")
        # GS1 location
        self.bin1.barcode = "4145412345000003"  # not a real GLN, just a stored code
        res = picking.bc_validate()
        self.assertTrue(res["done"], res)

    def test_packaging_barcode_counts_carton(self):
        dozen = self.env.ref("uom.product_uom_dozen")
        self.env["product.uom"].create({"product_id": self.cola.id, "uom_id": dozen.id, "barcode": "16901234567899"})
        picking = self._picking(self.type_in, [(self.cola, 24)])
        state = self._scan(picking, ["16901234567899", "16901234567899"])
        self.assertEqual(self._move(state, self.cola)["done"], 24)

    def test_put_in_pack_and_whole_package(self):
        picking = self._picking(self.type_in, [(self.cola, 2)])
        state = self._scan(picking, ["6901234567892", "6901234567892"])
        state = picking.bc_put_in_pack(state["ctx"])
        self.assertEqual(state["feedback"]["level"], "success")
        package = self.env["stock.package"].browse(state["feedback"]["package_id"])
        picking.bc_validate()
        self.assertEqual(picking.state, "done")
        self.assertEqual(package.quant_ids.quantity, 2)
        self.assertEqual(package.location_id, self.stock)
        # now ship the whole package by scanning it
        out = self._picking(self.type_out, [(self.cola, 2)])
        state = out.bc_scan(package.name)
        self.assertEqual(state["feedback"]["level"], "success", state["feedback"])
        self.assertEqual(self._move(state, self.cola)["done"], 2)
        res = out.bc_validate()
        self.assertTrue(res["done"], res)

    def test_scan_package_as_destination(self):
        picking = self._picking(self.type_in, [(self.cola, 1)])
        state = self._scan(picking, ["PACK0000777", "6901234567892"])
        line = [l for l in self._move(state, self.cola)["lines"] if l["bc_qty"]][0]
        self.assertEqual(line["result_package"], "PACK0000777")

    def test_nothing_scanned_needs_confirmation(self):
        self._set_stock(self.cola, self.stock, 5)
        picking = self._picking(self.type_out, [(self.cola, 2)])
        res = picking.bc_validate()
        self.assertEqual(res.get("confirm"), "nothing_scanned")
        self.assertNotEqual(picking.state, "done")
        res = picking.bc_validate(force=True)
        self.assertTrue(res["done"], res)

    def test_command_validate_and_set_qty(self):
        picking = self._picking(self.type_in, [(self.cola, 10)])
        state = picking.bc_scan("6901234567892")
        move = self._move(state, self.cola)
        state = picking.bc_set_move_qty(move["move_id"], 10, state["ctx"])
        self.assertEqual(self._move(state, self.cola)["done"], 10)
        state = picking.bc_scan("O-BTN.validate", state["ctx"])
        self.assertEqual(picking.state, "done")
        self.assertTrue(state["action"]["done"])

    def test_new_receipt_from_scratch(self):
        picking_id = self.type_in.bc_new_picking()
        picking = self.env["stock.picking"].browse(picking_id)
        state = self._scan(picking, ["6901234567892", "6901234567892", "6901234567809"])
        self.assertEqual(self._move(state, self.cola)["done"], 2)
        res = picking.bc_validate()
        self.assertTrue(res["done"], res)
        self.assertEqual(self.cola.qty_available, 2)

    def test_internal_transfer_bin_to_bin(self):
        self._set_stock(self.cola, self.bin1, 5)
        picking_id = self.type_int.bc_new_picking()
        picking = self.env["stock.picking"].browse(picking_id)
        state = self._scan(picking, [self.bin1.barcode, "6901234567892", "6901234567892", self.bin2.barcode])
        self.assertIn("put in", state["feedback"]["message"])
        res = picking.bc_validate()
        self.assertTrue(res["done"], res)
        self.assertEqual(self.cola.with_context(location=self.bin2.id).qty_available, 2)
        self.assertEqual(self.cola.with_context(location=self.bin1.id).qty_available, 3)

    def test_batch_transfer(self):
        self._set_stock(self.cola, self.stock, 10)
        self._set_stock(self.chips, self.stock, 10)
        p1 = self._picking(self.type_out, [(self.cola, 2)])
        p2 = self._picking(self.type_out, [(self.chips, 1), (self.cola, 1)])
        batch = self.env["stock.picking.batch"].create({"picking_ids": [(6, 0, (p1 | p2).ids)]})
        batch.action_confirm()
        state = self._scan(batch, ["6901234567892"] * 3 + ["6901234567809"])
        self.assertTrue(state["is_batch"])
        self.assertEqual(sum(m["done"] for m in state["moves"]), 4)
        res = batch.bc_validate()
        self.assertTrue(res["done"], res)
        self.assertEqual((p1 | p2).mapped("state"), ["done", "done"])

    def test_inventory_count(self):
        Quant = self.env["stock.quant"]
        self._set_stock(self.cola, self.bin1, 5)
        self._set_stock(self.chips, self.bin1, 3)
        state = Quant.bc_inv_scan(self.bin1.barcode)
        self.assertEqual(len(state["expected"]), 2)
        ctx = state["ctx"]
        for code in ["6901234567892"] * 4:
            state = Quant.bc_inv_scan(code, ctx)
            ctx = state["ctx"]
        counted = state["counted"]
        self.assertEqual(counted[0]["counted"], 4)
        self.assertEqual(counted[0]["diff"], -1)
        state = Quant.bc_inv_zero_uncounted(ctx)
        self.assertEqual(len(state["counted"]), 2)
        state = Quant.bc_inv_apply(ctx)
        self.assertTrue(state["feedback"].get("applied"))
        self.assertEqual(self.cola.with_context(location=self.bin1.id).qty_available, 4)
        self.assertEqual(self.chips.with_context(location=self.bin1.id).qty_available, 0)

    def test_inventory_lot_count(self):
        Quant = self.env["stock.quant"]
        state = Quant.bc_inv_scan(self.bin2.barcode)
        state = Quant.bc_inv_scan(self.milk.barcode, state["ctx"])
        self.assertTrue(state["feedback"].get("need_lot"))
        state = Quant.bc_inv_scan("NEWLOT", state["ctx"])
        state = Quant.bc_inv_scan(self.milk.barcode, state["ctx"])
        state = Quant.bc_inv_scan("NEWLOT", state["ctx"])
        self.assertEqual(state["counted"][0]["counted"], 2)
        Quant.bc_inv_apply(state["ctx"])
        lot = self.env["stock.lot"].search([("name", "=", "NEWLOT")])
        self.assertEqual(lot.product_qty, 2)

    def test_home_scan(self):
        picking = self._picking(self.type_in, [(self.cola, 1)])
        Picking = self.env["stock.picking"]
        self.assertEqual(Picking.bc_home_scan(picking.name), {"open": "picking", "id": picking.id})
        self.assertEqual(Picking.bc_home_scan(self.bin1.barcode)["open"], "inventory")
        self.assertEqual(Picking.bc_home_scan("6901234567892")["open"], "product")
        self.assertFalse(Picking.bc_home_scan("nothing-here")["open"])

    def test_dashboard(self):
        self._picking(self.type_in, [(self.cola, 1)])
        data = self.env["stock.picking.type"].bc_dashboard()
        wh = next(w for w in data["warehouses"] if w["id"] == self.wh.id)
        receipts = next(t for t in wh["types"] if t["id"] == self.type_in.id)
        self.assertGreaterEqual(receipts["ready"], 1)
        listing = self.type_in.bc_pickings()
        self.assertTrue(listing["pickings"])

    def test_location_labels_render(self):
        report = self.env.ref("stock_barcode_ce.action_report_location_label_th40x30")
        html = report._render_qweb_html(report.report_name, (self.bin1 | self.bin2).ids)[0].decode()
        self.assertEqual(html.count('class="o_th_label"'), 2)
        self.assertIn(self.bin1.barcode, html)
        report = self.env.ref("stock_barcode_ce.action_report_barcode_commands")
        html = report._render_qweb_html(report.report_name, self.type_in.ids)[0].decode()
        self.assertIn("O-BTN.validate", html)

    def test_quick_create_storable(self):
        wiz = self.env["product.barcode.quick"].create({"barcode": make_ean13("690123456783"), "name": "New", "tracking": "lot"})
        wiz.action_create()
        product = self.env["product.product"].search([("barcode", "=", wiz.barcode)])
        self.assertTrue(product.is_storable)
        self.assertEqual(product.tracking, "lot")
