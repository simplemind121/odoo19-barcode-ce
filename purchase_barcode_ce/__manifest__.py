{
    "name": "Purchase Barcode (CE)",
    "summary": "Scan products into RFQs; create the vendor bill right after a scanned receipt",
    "version": "19.0.1.1.0",
    "category": "Inventory/Purchase",
    "license": "LGPL-3",
    "author": "letaoge",
    "depends": ["purchase_stock", "stock_barcode_ce"],
    "data": ["views/purchase_order_views.xml"],
    "installable": True,
    "auto_install": True,
}
