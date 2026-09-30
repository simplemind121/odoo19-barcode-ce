import base64
import json
import os
import re
import socket
import threading

from odoo import Command
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

AGENT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools", "label_print_agent.py")


class Common:
    @classmethod
    def _setup_common(cls):
        env = cls.env
        cls.agent = env["barcode.label.agent"].create({"name": "Warehouse PC"})
        cls.printer = env["barcode.label.printer"].create({
            "name": "Receiving TSPL", "agent_id": cls.agent.id, "target": "tcp://127.0.0.1:1", "language": "tspl",
            "width_mm": 40, "height_mm": 30})
        cls.cola = env["product.product"].create({
            "name": "可口可乐 Coca-Cola 330ml 罐装", "is_storable": True, "barcode": "6901234567892",
            "list_price": 3.5, "default_code": "COLA330"})


@tagged("post_install", "-at_install")
class TestLabelRender(Common, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_common()

    def _tspl_bitmap(self, data):
        m = re.search(rb"BITMAP (\d+),(\d+),(\d+),(\d+),0,", data)
        x, y, wbytes, h = map(int, m.groups())
        start = m.end()
        return x, y, wbytes, h, data[start:start + wbytes * h]

    def test_tspl_product_label(self):
        Render = self.env["barcode.label.render"]
        data = Render.render(self.printer, [(Render._content_product(self.cola), 3)])
        self.assertTrue(data.startswith(b"SIZE 40.0 mm,30.0 mm\r\nGAP 2.0 mm,0 mm"))
        self.assertIn(b'"EAN13"', data)
        self.assertIn(b'"690123456789"\r\n', data, "TSPL EAN13 takes 12 digits, the printer adds the check digit")
        self.assertTrue(data.endswith(b"PRINT 1,3\r\n"))
        x, y, wbytes, h, bits = self._tspl_bitmap(data)
        self.assertEqual(len(bits), wbytes * h)
        self.assertLessEqual(x + wbytes * 8, 40 * 8, "text fits the label width")
        # black pixels exist (bit 0 = black in TSPL)
        zero_bits = sum(8 - bin(b).count("1") for b in bits)
        self.assertGreater(zero_bits, 200, "the product name was drawn")
        bar_y = int(re.search(rb"BARCODE \d+,(\d+),", data).group(1))
        self.assertLessEqual(y + h, bar_y, "text does not overlap the barcode")

    def test_zpl_and_code128(self):
        self.printer.write({"language": "zpl", "width_mm": 60, "height_mm": 40})
        Render = self.env["barcode.label.render"]
        loc = self.env["stock.location"].create({"name": "A-01-1-01", "barcode": "WH1-A-01-1-01",
                                                 "location_id": self.env.ref("stock.stock_location_stock").id})
        data = Render.render(self.printer, [(Render._content_location(loc), 2)]).decode()
        self.assertTrue(data.startswith("^XA"))
        self.assertIn("^PW480", data)
        self.assertIn("^LL320", data)
        self.assertIn("^GFA,", data)
        self.assertIn("^BCN,", data)
        self.assertIn("^FDWH1-A-01-1-01^FS", data)
        self.assertIn("^PQ2", data)
        self.assertTrue(data.strip().endswith("^XZ"))
        ean = Render.render(self.printer, [(Render._content_product(self.cola), 1)]).decode()
        self.assertIn("^BEN,", ean)
        self.assertIn("^FD690123456789^FS", ean)

    def test_lot_label_and_300dpi(self):
        self.printer.dpi = "300"
        lot = self.env["stock.lot"].create({"name": "LOT2609A", "product_id": self.cola.id})
        Render = self.env["barcode.label.render"]
        data = Render.render(self.printer, [(Render._content_lot(lot), 1)])
        self.assertIn(b'"128"', data)
        self.assertIn(b'"LOT2609A"', data)
        x, y, wbytes, h, _bits = self._tspl_bitmap(data)
        self.assertLessEqual(x + wbytes * 8, 40 * 12)

    def test_picking_direct_print_and_fallback(self):
        wh = self.env["stock.warehouse"].search([("company_id", "=", self.env.company.id)], limit=1)
        t = wh.in_type_id
        picking = self.env["stock.picking"].create({
            "picking_type_id": t.id, "location_id": t.default_location_src_id.id,
            "location_dest_id": t.default_location_dest_id.id,
            "move_ids": [Command.create({"product_id": self.cola.id, "product_uom_qty": 10,
                                         "location_id": t.default_location_src_id.id,
                                         "location_dest_id": t.default_location_dest_id.id})]})
        picking.action_confirm()
        ctx = {}
        for _i in range(4):
            ctx = picking.bc_scan("6901234567892", ctx)["ctx"]
        operator = new_test_user(self.env, "bc_print_op", groups="stock_barcode_ce.group_barcode_operator")
        res = picking.with_user(operator).bc_direct_print("products")
        self.assertEqual(res["level"], "success", res)
        job = self.env["barcode.label.job"].search([], limit=1)
        self.assertEqual(job.label_count, 4, "one label per scanned unit")
        self.assertEqual(job.user_id, operator)
        self.printer.active = False
        res = picking.bc_direct_print("products")
        self.assertTrue(res.get("fallback"))


@tagged("post_install", "-at_install")
class TestLabelAgent(Common, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_common()

    def _post(self, route, payload):
        return self.url_open(route, data=json.dumps(payload), headers={"Content-Type": "application/json"})

    def test_agent_protocol(self):
        self.assertEqual(self._post("/barcode_label/agent/poll", {"token": "wrong-token-xxxxxxxxxxxx"}).status_code, 403)
        job = self.printer._print([(self.env["barcode.label.render"]._content_product(self.cola), 1)], "t")
        res = self._post("/barcode_label/agent/poll", {"token": self.agent.token}).json()
        self.assertEqual([j["id"] for j in res["jobs"]], [job.id])
        self.assertEqual(job.state, "sent")
        self.assertFalse(self._post("/barcode_label/agent/poll", {"token": self.agent.token}).json()["jobs"],
                         "a job is handed out once")
        self._post("/barcode_label/agent/ack", {"token": self.agent.token, "id": job.id, "ok": False, "error": "paper out"})
        self.assertEqual(job.state, "error")
        self.assertEqual(job.error, "paper out")
        other = self.env["barcode.label.agent"].create({"name": "Other"})
        self.assertEqual(self._post("/barcode_label/agent/ack", {"token": other.token, "id": job.id, "ok": True}).status_code, 404)

    def test_agent_script_with_network_printer(self):
        """The real agent script, against a stand-in HTTP endpoint that replays what the
        Odoo controller returned, and a fake TCP label printer."""
        import http.server
        import importlib.util

        job = self.printer._print([(self.env["barcode.label.render"]._content_product(self.cola), 2)], "e2e")
        expected = base64.b64decode(job.data)
        received, acks = [], []

        printer = socket.socket()
        printer.bind(("127.0.0.1", 0))
        printer.listen(1)
        self.printer.target = "tcp://127.0.0.1:%s" % printer.getsockname()[1]
        poll_payload = self._post("/barcode_label/agent/poll", {"token": self.agent.token}).json()

        def printer_loop():
            conn, _addr = printer.accept()
            chunks = []
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            received.append(b"".join(chunks))
            conn.close()

        test = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                test.assertEqual(body["token"], test.agent.token)
                if self.path.startswith("/barcode_label/agent/poll"):
                    out = poll_payload
                else:
                    acks.append(body)
                    out = {"ok": True}
                data = json.dumps(out).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        threading.Thread(target=printer_loop, daemon=True).start()
        spec = importlib.util.spec_from_file_location("label_print_agent", AGENT)
        agent_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(agent_mod)
        # jobs in poll_payload still point to the old target: rewrite as Odoo would now
        for j in poll_payload["jobs"]:
            j["target"] = self.printer.target
        handled = agent_mod.run_once("http://127.0.0.1:%s" % httpd.server_address[1], self.agent.token)
        httpd.shutdown()
        printer.close()
        self.assertEqual(handled, 1)
        self.assertEqual(received, [expected], "the printer received exactly the job bytes")
        self.assertEqual(acks, [{"token": self.agent.token, "id": job.id, "ok": True}])
        # replay the ack on the real controller
        self._post("/barcode_label/agent/ack", acks[0])
        self.assertEqual(job.state, "done")
        self.assertTrue(self.agent.last_seen)

    def test_agent_reports_printer_errors(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("label_print_agent", AGENT)
        agent_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(agent_mod)
        with self.assertRaises(OSError):
            agent_mod.send_to_printer("tcp://127.0.0.1:1", b"x")
        with self.assertRaises(ValueError):
            agent_mod.send_to_printer("lpt1", b"x")
