{
    "name": "Product Barcode Quick Entry (CE)",
    "summary": "Scan to look up or create products, in-store EAN-13 codes, thermal price labels",
    "version": "19.0.1.1.0",
    "category": "Inventory/Barcode",
    "license": "LGPL-3",
    "author": "letaoge",
    "depends": ["product", "base_setup", "barcodes_gs1_nomenclature", "barcode_camera_ce"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "report/product_label_reports.xml",
        "report/product_label_templates.xml",
        "wizard/product_barcode_quick_views.xml",
        "views/product_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "product_barcode_quick/static/src/**/*",
        ],
        "web.assets_tests": [
            "product_barcode_quick/static/tests/tours/**/*",
        ],
    },
    "installable": True,
}
