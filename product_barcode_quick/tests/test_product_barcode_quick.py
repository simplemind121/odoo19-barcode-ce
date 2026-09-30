import json

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.product_barcode_quick.models.barcode_tools import gtin_is_valid, make_ean13


@tagged("post_install", "-at_install")
class TestProductBarcodeQuick(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Product = cls.env["product.product"]
        cls.cola = cls.Product.create({"name": "Cola 330ml", "barcode": "6901234567892", "list_price": 3.5})

    def test_gtin_tools(self):
        self.assertTrue(gtin_is_valid("6901234567892"))
        self.assertFalse(gtin_is_valid("6901234567891"))
        self.assertTrue(gtin_is_valid("036000291452"))  # UPC-A
        self.assertEqual(make_ean13("200000000001"), "2000000000015")

    def test_instore_generation(self):
        codes = set()
        for _i in range(5):
            code = self.Product._bcq_next_instore_barcode()
            self.assertEqual(len(code), 13)
            self.assertTrue(code.startswith("20"))
            self.assertTrue(gtin_is_valid(code))
            codes.add(code)
        self.assertEqual(len(codes), 5)
        p = self.Product.create({"name": "No code"})
        p.action_bcq_generate_barcode()
        self.assertTrue(p.barcode.startswith("20"))
        self.env.company.bcq_instore_prefix = "27"
        self.assertTrue(self.Product._bcq_next_instore_barcode().startswith("27"))

    def test_generation_skips_used_codes(self):
        seq = self.env["ir.sequence"].search([("code", "=", "product_barcode_quick.instore")])
        nxt = seq.number_next_actual
        taken = make_ean13("20" + str(nxt).rjust(10, "0"))
        self.Product.create({"name": "Taken", "barcode": taken})
        self.assertNotEqual(self.Product._bcq_next_instore_barcode(), taken)

    def test_prefix_constraint(self):
        with self.assertRaises(ValidationError):
            self.env.company.bcq_instore_prefix = "23"

    def test_check_digit_constraint(self):
        with self.assertRaises(ValidationError):
            self.Product.create({"name": "Bad", "barcode": "6901234567891"})
        self.env.company.bcq_strict_gtin = False
        self.Product.create({"name": "Bad allowed", "barcode": "6901234567891"})
        # Non numeric / other lengths are never checked
        self.env.company.bcq_strict_gtin = True
        self.Product.create({"name": "Code128", "barcode": "ABC-123"})

    def test_lookup_variants(self):
        res = self.Product.bcq_lookup("6901234567892")
        self.assertTrue(res["found"])
        self.assertEqual(res["product"]["id"], self.cola.id)
        # UPC-A stored, EAN-13 scanned (leading zero)
        upc = self.Product.create({"name": "US item", "barcode": "036000291452"})
        self.assertEqual(self.Product.bcq_lookup("0036000291452")["product"]["id"], upc.id)
        # GTIN-14 scanned
        self.assertEqual(self.Product.bcq_lookup("06901234567892")["product"]["id"], self.cola.id)
        # unknown
        res = self.Product.bcq_lookup("6901234567809")
        self.assertFalse(res["found"])
        self.assertTrue(res["gtin_like"])

    def test_lookup_packaging(self):
        dozen = self.env.ref("uom.product_uom_dozen")
        self.env["product.uom"].create({"product_id": self.cola.id, "uom_id": dozen.id, "barcode": "16901234567899"})
        product, qty, _u, _p = self.Product.bcq_find_by_barcode("16901234567899")
        self.assertEqual(product, self.cola)
        self.assertEqual(qty, 12)

    def test_lookup_weight_barcode(self):
        kg = self.env.ref("uom.product_uom_kgm")
        apples = self.Product.create({"name": "Apples", "barcode": make_ean13("210000100000"), "uom_id": kg.id})
        # 21 00001 01250 + check -> 1.250 kg
        code = make_ean13("210000101250")
        product, qty, _u, parsed = self.Product.bcq_find_by_barcode(code)
        self.assertEqual(product, apples)
        self.assertAlmostEqual(qty, 1.25)

    def test_lookup_gs1(self):
        self.env.company.nomenclature_id = self.env.ref("barcodes_gs1_nomenclature.default_gs1_nomenclature")
        product, qty, _u, data = self.Product.bcq_find_by_barcode("0106901234567892" + "3712")
        self.assertEqual(product, self.cola)
        self.assertEqual(qty, 12)

    def test_quick_create_wizard(self):
        wiz = self.env["product.barcode.quick"].create({"barcode": "6901234567809", "name": "Tea", "list_price": 5})
        wiz.action_create()
        tea = self.Product.search([("barcode", "=", "6901234567809")])
        self.assertEqual(tea.name, "Tea")
        self.assertEqual(tea.lst_price, 5)
        wiz2 = self.env["product.barcode.quick"].create({"barcode": "6901234567809", "name": "Dup"})
        self.assertTrue(wiz2.barcode_warning)
        with self.assertRaises(UserError):
            wiz2.action_create()
        wiz3 = self.env["product.barcode.quick"].create({"name": "In-store"})
        wiz3.action_generate_barcode()
        self.assertTrue(wiz3.barcode.startswith("20"))

    def test_thermal_label_render(self):
        for fmt in ("th40x30", "th50x30", "th60x40"):
            wiz = self.env["product.label.layout"].create({
                "product_ids": [(6, 0, self.cola.ids)], "print_format": fmt, "custom_quantity": 3})
            xml_id, data = wiz._prepare_report_data()
            data = json.loads(json.dumps(data))  # like the web client
            report = self.env.ref(xml_id)
            html = report._render_qweb_html(report.report_name, [], data=data)[0].decode()
            self.assertEqual(html.count('class="o_th_label"'), 3)
            self.assertIn("6901234567892", html)
            self.assertIn("Cola 330ml", html)
        # the real PDF renders one page per label
        wiz = self.env["product.label.layout"].create({
            "product_ids": [(6, 0, self.cola.ids)], "print_format": "th40x30", "custom_quantity": 2})
        xml_id, data = wiz._prepare_report_data()
        data = json.loads(json.dumps(data))
        # wkhtmltopdf fetches the assets over HTTP: let that request reuse the test cursor
        with self.allow_pdf_render():
            pdf = self.env["ir.actions.report"].with_context(force_report_rendering=True)._render_qweb_pdf(
                xml_id, [], data=data)[0]
        self.assertTrue(pdf.startswith(b"%PDF"))
        from odoo.tools.pdf import PdfFileReader
        import io
        reader = PdfFileReader(io.BytesIO(pdf))
        self.assertEqual(len(reader.pages), 2, "one page per label")
        box = reader.pages[0].mediabox
        # 40 x 30 mm in points (1 mm = 2.8346 pt)
        self.assertAlmostEqual(float(box.width), 40 * 2.8346, delta=3)
        self.assertAlmostEqual(float(box.height), 30 * 2.8346, delta=3)
