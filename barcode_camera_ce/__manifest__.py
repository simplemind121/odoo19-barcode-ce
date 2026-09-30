{
    "name": "Barcode Camera (CE)",
    "summary": "Scan barcodes with the device camera or a hardware scanner anywhere in Odoo",
    "version": "19.0.1.1.0",
    "category": "Inventory/Barcode",
    "license": "LGPL-3",
    "author": "letaoge",
    "depends": ["web", "barcodes"],
    "data": [],
    "assets": {
        "web.assets_backend": [
            "barcode_camera_ce/static/src/**/*",
        ],
        "web.assets_tests": [
            "barcode_camera_ce/static/tests/tours/**/*",
        ],
    },
    "installable": True,
}
