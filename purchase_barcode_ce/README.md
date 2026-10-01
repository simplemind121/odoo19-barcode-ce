# Purchase Barcode (CE)

Scan products into requests for quotation, and create the vendor bill right
after a scanned receipt.

| | |
| --- | --- |
| Technical name | `purchase_barcode_ce` |
| Depends on | `purchase_stock`, `stock_barcode_ce` |
| Auto-install | Yes, when both dependencies are installed |
| License | LGPL-3 |

## What it adds

*   **RFQ form.** In states *RFQ* and *RFQ Sent*, a scan adds the product as
    an order line, or adds to the quantity of an existing line. Unknown codes
    and products that cannot be purchased show a warning.
*   **After a scanned receipt.** When the purchase order is ready to bill,
    the scanner offers a **Create bill** button that calls Odoo's standard
    `action_create_invoice()`. The bill follows the received quantity
    according to the product's bill control policy.

## Behaviour to know

Stock Odoo does not react to scans on the RFQ form; this module does, and
there is no setting to turn it off. Uninstall the module to restore the stock
behaviour. See [docs/compatibility.md](../docs/compatibility.md).

Confirmed purchase orders are not changed by scanning.

See the [repository README](../README.md) for the whole suite.
