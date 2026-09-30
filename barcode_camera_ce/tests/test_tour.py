from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestBarcodeCameraTour(HttpCase):
    def test_camera_dialog_manual_entry_reaches_bus(self):
        self.start_tour("/odoo", "barcode_camera_ce_dialog_tour", login="admin")
