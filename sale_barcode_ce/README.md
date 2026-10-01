# Sales Barcode (CE)

Scan products into quotations, and invoice right after a scanned delivery.

| | |
| --- | --- |
| Technical name | `sale_barcode_ce` |
| Depends on | `sale_stock`, `stock_barcode_ce` |
| Auto-install | Yes, when both dependencies are installed |
| License | LGPL-3 |

## What it adds

*   **Quotation form.** In states *Quotation* and *Quotation Sent*, a scan
    adds the product as an order line, or adds to the quantity of an existing
    line. Packaging and weight barcodes set the quantity. Unknown codes and
    products that cannot be sold show a warning.
*   **After a scanned delivery.** When the sales order is ready to invoice,
    the scanner offers a **Create invoice** button that opens Odoo's standard
    invoicing wizard.

## Behaviour to know

Stock Odoo does not react to scans on the quotation form; this module does,
and there is no setting to turn it off. Uninstall the module to restore the
stock behaviour. See [docs/compatibility.md](../docs/compatibility.md).

Confirmed orders are not changed by scanning.

See the [repository README](../README.md) for the whole suite.
