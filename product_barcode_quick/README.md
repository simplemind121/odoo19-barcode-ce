# Product Barcode Quick Entry (CE)

Scan a barcode to look up a product or to create it, generate in-store
EAN-13 codes, and print thermal price labels as PDF. This module also owns
the **Barcode** app root menu.

| | |
| --- | --- |
| Technical name | `product_barcode_quick` |
| Depends on | `product`, `base_setup`, `barcodes_gs1_nomenclature`, `barcode_camera_ce` |
| License | LGPL-3 |

## What it adds

*   **Barcode → Scan products.** A known code shows the product with price
    and quantity on hand. An unknown code opens a creation form with the
    barcode filled in.
*   **In-store barcodes.** Generates EAN-13 codes with a company prefix (20,
    or 24 to 29) from a sequence, and skips codes that are in use.
*   **Check-digit validation.** Refuses EAN/UPC product barcodes with a wrong
    check digit.
*   **Thermal label formats.** 40×30, 50×30 and 60×40 mm in the standard
    label wizard, one label per page.
*   **Product requests.** A user without product rights can file a request
    for an unknown code (**Barcode → Product requests**). The request closes
    when a product with that barcode is created.

## Configuration

**Settings → Product Barcodes**:

| Setting | Default | Note |
| --- | --- | --- |
| In-store barcode prefix | `20` | 21 to 23 are reserved by Odoo's default nomenclature. |
| Validate EAN/UPC check digit | On | This differs from stock Odoo, which accepts any barcode. Clear it to restore the stock behaviour. |

## Behaviour to know

The check-digit constraint applies when a product barcode is created or
changed, from any screen and from imports. Existing barcodes are not
re-checked. See [docs/compatibility.md](../docs/compatibility.md).

## Code map

| Path | Content |
| --- | --- |
| `models/barcode_tools.py` | GTIN check digit, EAN-13 generation |
| `models/product.py` | Lookup (`bcq_find_by_barcode`, `bcq_lookup`), constraint, generation |
| `models/product_barcode_request.py` | Product requests |
| `wizard/product_barcode_quick.py` | Quick creation wizard |
| `wizard/product_label_layout.py` | Thermal formats in the label wizard |
| `static/src/product_scan/` | Scan products screen |

See the [repository README](../README.md) for the whole suite.
