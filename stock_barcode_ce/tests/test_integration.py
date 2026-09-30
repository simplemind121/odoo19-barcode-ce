from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBarcodeIntegration(TransactionCase):
    """Scanned transfers must behave exactly like transfers validated from the backend:
    multi-step routes, returns and stock valuation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        env.user.group_ids |= env.ref("stock.group_stock_multi_locations") | env.ref("stock.group_adv_location")
        cls.wh = env["stock.warehouse"].search([("company_id", "=", env.company.id)], limit=1)
        cls.cola = env["product.product"].create({
            "name": "Cola", "is_storable": True, "barcode": "6901234567892",
            "standard_price": 2.0, "categ_id": env.ref("product.product_category_goods").id})
        cls.cola.categ_id.property_cost_method = "fifo"
        cls.cola.categ_id.property_valuation = "real_time"
        cls.partner = env["res.partner"].create({"name": "Scan Partner"})

    def _scan(self, picking, codes, ctx=None):
        state = None
        for code in codes:
            state = picking.bc_scan(code, ctx)
            ctx = state["ctx"]
        return state

    def test_three_step_receipt(self):
        self.wh.reception_steps = "three_steps"
        picking = self.env["stock.picking"].create({
            "picking_type_id": self.wh.in_type_id.id,
            "location_id": self.wh.in_type_id.default_location_src_id.id,
            "location_dest_id": self.wh.wh_input_stock_loc_id.id,
            "move_ids": [Command.create({
                "product_id": self.cola.id, "product_uom_qty": 10,
                "location_id": self.wh.in_type_id.default_location_src_id.id,
                "location_dest_id": self.wh.wh_input_stock_loc_id.id})]})
        picking.action_confirm()
        self._scan(picking, ["6901234567892"] * 10)
        self.assertTrue(picking.bc_validate()["done"])
        # step 2: quality control, step 3: storage - both scanned as well
        for _step in range(2):
            nxt = self.env["stock.picking"].search([("origin", "=", picking.name)]) or \
                self.env["stock.picking"].search([("backorder_id", "=", False), ("state", "=", "assigned"),
                                                  ("picking_type_id", "!=", self.wh.in_type_id.id)], order="id desc", limit=1)
            nxt = nxt.filtered(lambda p: p.state == "assigned")[:1]
            self.assertTrue(nxt, "next step of the route should be ready")
            nxt.action_assign()
            self._scan(nxt, ["6901234567892"] * 10)
            self.assertTrue(nxt.bc_validate()["done"], nxt.picking_type_id.name)
        self.assertEqual(self.cola.with_context(location=self.wh.lot_stock_id.id).qty_available, 10)

    def test_two_step_delivery_and_return(self):
        self.wh.write({"delivery_steps": "pick_ship"})
        self.env.flush_all()
        self.env["stock.quant"]._update_available_quantity(self.cola, self.wh.lot_stock_id, 10)
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "order_line": [Command.create({"product_id": self.cola.id, "product_uom_qty": 4})]})
        order.action_confirm()
        pick = order.picking_ids.filtered(lambda p: p.picking_type_id == self.wh.pick_type_id)
        self.assertTrue(pick, "a pick step is expected")
        self._scan(pick, ["6901234567892"] * 4)
        self.assertTrue(pick.bc_validate()["done"])
        ship = (order.picking_ids - pick).filtered(lambda p: p.state not in ("done", "cancel"))
        self.assertTrue(ship, "the delivery step should follow the pick")
        ship.action_assign()
        self._scan(ship, ["6901234567892"] * 4)
        self.assertTrue(ship.bc_validate()["done"])
        self.assertEqual(self.cola.qty_available, 6)
        # customer returns 1 unit: the return picking is scanned too
        wizard = self.env["stock.return.picking"].with_context(active_id=ship.id, active_model="stock.picking").create({})
        wizard.product_return_moves.quantity = 1
        return_picking = self.env["stock.picking"].browse(wizard.action_create_returns()["res_id"])
        return_picking.action_assign()
        self._scan(return_picking, ["6901234567892"])
        self.assertTrue(return_picking.bc_validate()["done"])
        self.assertEqual(self.cola.qty_available, 7)

    def test_valuation_matches_scanned_quantity(self):
        if "stock.valuation.layer" not in self.env:
            self.skipTest("stock_account not installed")
        layers_before = self.env["stock.valuation.layer"].search([("product_id", "=", self.cola.id)])
        po = self.env["purchase.order"].create({
            "partner_id": self.partner.id,
            "order_line": [Command.create({"product_id": self.cola.id, "product_qty": 10, "price_unit": 3.0})]})
        po.button_confirm()
        picking = po.picking_ids
        self._scan(picking, ["6901234567892"] * 6)
        res = picking.bc_validate()
        self.assertEqual(res.get("confirm"), "backorder")
        picking.bc_validate(backorder=True)
        layers = self.env["stock.valuation.layer"].search([("product_id", "=", self.cola.id)]) - layers_before
        self.assertEqual(sum(layers.mapped("quantity")), 6)
        self.assertEqual(sum(layers.mapped("value")), 18.0, "6 units at 3.0 must be valued 18")
        self.assertTrue(layers.account_move_id, "a stock journal entry is expected in real time valuation")
        self.assertEqual(self.cola.qty_available, 6)
        self.assertEqual(self.cola.value_svl, 18.0)
