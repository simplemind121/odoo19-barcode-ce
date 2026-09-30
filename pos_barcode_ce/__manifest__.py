{
    "name": "POS Barcode (CE)",
    "summary": "Point of Sale: create an unknown scanned product on the spot and sell it",
    "version": "19.0.1.0.0",
    "category": "Sales/Point of Sale",
    "license": "LGPL-3",
    "author": "letaoge",
    "depends": ["point_of_sale", "product_barcode_quick"],
    "data": [],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_barcode_ce/static/src/**/*",
        ],
        "web.assets_tests": [
            "pos_barcode_ce/static/tests/tours/**/*",
        ],
        "point_of_sale.assets_debug": [
            "pos_barcode_ce/static/tests/tours/**/*",
        ],
    },
    "installable": True,
    "auto_install": True,
}
