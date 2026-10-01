# POS Barcode (CE)

In the Point of Sale, lets a cashier with product rights create an unknown
scanned product on the spot and sell it.

| | |
| --- | --- |
| Technical name | `pos_barcode_ce` |
| Depends on | `point_of_sale`, `product_barcode_quick` |
| Auto-install | Yes, when both dependencies are installed |
| License | LGPL-3 |

## What it adds

Odoo's POS already scans with the camera and looks up products on the server.
This module changes one thing: when a scanned code matches no product and the
user may create products, a dialog asks whether to create it. After saving,
the new product is loaded into the session and added to the current order.

Users without product creation rights get the standard "unknown barcode"
behaviour.

## Requirements

The cashier needs the group **Product / Administrator**
(`product.group_product_manager`). A POS manager without it cannot create
products.

## Behaviour to know

The dialog is a difference from stock Odoo and there is no setting to turn it
off. Uninstall the module to restore the stock behaviour. See
[docs/compatibility.md](../docs/compatibility.md).

## Code map

| Path | Content |
| --- | --- |
| `static/src/product_screen_patch.js` | Patch of `ProductScreen._barcodeProductAction` |

See the [repository README](../README.md) for the whole suite.
