{
    "name": "Sales Barcode (CE)",
    "summary": "Scan products into quotations; invoice right after a scanned delivery",
    "version": "19.0.1.0.0",
    "category": "Sales/Sales",
    "license": "LGPL-3",
    "author": "letaoge",
    "depends": ["sale_stock", "stock_barcode_ce"],
    "data": ["views/sale_order_views.xml"],
    "assets": {
        "web.assets_tests": ["sale_barcode_ce/static/tests/tours/**/*"],
    },
    "installable": True,
    "auto_install": True,
}
