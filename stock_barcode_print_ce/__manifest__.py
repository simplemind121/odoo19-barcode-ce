{
    "name": "Barcode Direct Label Printing (CE)",
    "summary": "Print product, lot, location and package labels straight to TSPL/ZPL thermal printers through a small local agent",
    "version": "19.0.1.0.0",
    "category": "Inventory/Barcode",
    "license": "LGPL-3",
    "author": "letaoge",
    "depends": ["stock_barcode_ce"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/label_printer_views.xml",
    ],
    "assets": {
        "web.assets_backend": ["stock_barcode_print_ce/static/src/**/*"],
    },
    "external_dependencies": {"python": ["PIL"]},
}
