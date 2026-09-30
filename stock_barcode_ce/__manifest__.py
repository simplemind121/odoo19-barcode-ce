{
    "name": "Stock Barcode (CE)",
    "summary": "Barcode app for receipts, deliveries, transfers, counts, batches, lots, packages and GS1",
    "version": "19.0.2.1.0",
    "category": "Inventory/Barcode",
    "license": "LGPL-3",
    "author": "letaoge",
    "depends": [
        "stock",
        "bus",
        "stock_picking_batch",
        "barcodes_gs1_nomenclature",
        "barcode_camera_ce",
        "product_barcode_quick",
    ],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "report/stock_barcode_reports.xml",
        "report/stock_barcode_templates.xml",
        "wizard/stock_bin_generator_views.xml",
        "wizard/product_barcode_quick_views.xml",
        "views/stock_barcode_actions.xml",
        "views/stock_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "stock_barcode_ce/static/src/**/*",
        ],
        "web.assets_tests": [
            "stock_barcode_ce/static/tests/tours/**/*",
        ],
    },
    "installable": True,
}
