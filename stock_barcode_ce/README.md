# Stock Barcode (CE)

The warehouse scanner: a mobile-first client action for receipts, deliveries,
internal transfers, batch and wave picking, inventory counts, scrap and
returns.

| | |
| --- | --- |
| Technical name | `stock_barcode_ce` |
| Depends on | `stock`, `bus`, `stock_picking_batch`, `barcodes_gs1_nomenclature`, `barcode_camera_ce`, `product_barcode_quick` |
| License | LGPL-3 |

## What it adds

*   **Barcode → Scanner.** Operation types by warehouse, transfer lists, and
    a global scan that opens a transfer, a batch, an operation type, a
    location count or a product.
*   **Scanning a transfer or a batch.** Locations, products, packaging
    codes, lots and serial numbers, packages, GS1-128, command barcodes.
*   **Several people on one transfer**, with live refresh and a presence
    indicator.
*   **Offline queue** for the open transfer.
*   **Inventory counting**, **scan to scrap**, and **returns** of done
    transfers.
*   **Scan rules** per operation type, all off by default.
*   **Roles:** Operator (scanner only) and Supervisor.
*   **Scan log** (**Barcode → Scan log**) and scan events, for audit.
*   **Barcode data check** and **bin generator** under **Barcode →
    Configuration**.
*   Thermal PDF labels for locations and packages, and a printable sheet of
    command barcodes.

## How scanning works

| Flow | Sequence |
| --- | --- |
| Receipt | Scan products, then the destination location. Or the location first. |
| Delivery | Scan the source location, then products. A different lot than reserved is accepted. |
| Internal transfer | Source location, products, destination location. |
| Tracked product | Product, then its lot or serial. A GS1 code carries product, lot and quantity at once. |
| Packaging code | One scan counts the contained quantity. |
| Package | An empty or new package code: following products go into it. A package with stock: the whole package is moved. |
| Validate | Only scanned quantities are processed; the rest follows the backorder choice. |
| Count | Scan the location, then products. A supervisor applies the counts. |

## Behaviour to know

Validation always ends with Odoo's `button_validate()`. Several steps differ
from the backend flow, for example the operator role, returns created for
the full quantity, and putaway evaluated per unit for scanner-created lines.
The full list is in [docs/compatibility.md](../docs/compatibility.md).

Read the trust model in [SECURITY.md](../SECURITY.md) before you create
operator users.

## Code map

| Path | Content |
| --- | --- |
| `models/stock_picking.py` | Scan engine: state, dispatch, rules, validation, returns |
| `models/barcode_resolver.py` | Barcode string to typed records |
| `models/stock_barcode_scan_event.py` | Quantity events |
| `models/stock_barcode_scan_log.py` | Audit log and idempotency |
| `models/stock_move_line.py` | `bc_qty` as the sum of events |
| `models/stock_quant.py` | Inventory counting |
| `models/stock_scrap.py` | Scan to scrap |
| `models/stock_picking_batch.py` | Batch and wave entry points |
| `models/stock_picking_type.py` | Scan rules, home screen data |
| `models/barcode_security.py` | `bc_guard` and role helpers |
| `models/stock_barcode_health.py` | Barcode data check |
| `wizard/stock_bin_generator.py` | Bin generator |
| `static/src/app/` | OWL client |
| `migrations/19.0.2.0.0/` | 1.x to 2.0 data migration |
| `tests/` | Python tests and browser tours |

Further reading: [architecture](../docs/architecture.md),
[scanner API](../docs/scanner-api.md).
