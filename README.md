# odoo19-barcode-ce

Camera and hardware barcode scanning for **Odoo 19 Community Edition**: a warehouse scanner app
(receipts, deliveries, internal transfers, inventory counts, lots/serials, packages, GS1, batch and
wave picking), scan-to-create products, thermal label printing, and scanning inside sales, purchase
and POS. No Odoo Enterprise code is used; everything here is written from scratch and released under
the LGPL-3.

> 中文说明见 [`docs/README_安装与验收.md`](docs/README_安装与验收.md)（安装、使用、验收清单）
> 和 [`docs/PROJECT_HISTORY.md`](docs/PROJECT_HISTORY.md)（设计决策、踩过的坑、验证结论）。

## Why

Odoo 19 Community has the building blocks (barcode nomenclatures, a camera scanner component in
`web`, POS camera scanning) but no warehouse Barcode app — that one is Enterprise only. This suite
fills that gap with a mobile-first scanner UI and keeps all stock movements on Odoo's standard
business logic (backorders, putaway, reservations, valuation, accounting).

## Modules

| Module | What it does | Depends on |
| --- | --- | --- |
| `barcode_camera_ce` | Camera scanning anywhere in the backend: navbar scan button, continuous scan dialog, sound/vibration, camera and scanner gun share one input path with cross-source de-duplication | `web`, `barcodes` |
| `product_barcode_quick` | "Barcode" app: scan to look up a product, create unknown ones on the spot, in-store EAN-13 generation (prefix 20/24-29), EAN/UPC check-digit validation, 40×30 / 50×30 / 60×40 mm thermal label formats, product creation requests | `product`, `barcodes_gs1_nomenclature`, `barcode_camera_ce` |
| `stock_barcode_ce` | The warehouse scanner: receipts, deliveries, transfers, putaway, counting, lots/serials, packages, GS1, command barcodes, batch/wave picking, scrap, returns, bin generator, scan log, per-operation-type scan rules, operator/supervisor roles | `stock`, `stock_picking_batch`, `bus`, `product_barcode_quick` |
| `stock_barcode_print_ce` | Direct label printing to TSPL/ZPL thermal printers through a small local agent (`tools/label_print_agent.py`) | `stock_barcode_ce` |
| `sale_barcode_ce` | Scan products into quotations; invoice right after a scanned delivery | `sale_stock`, `stock_barcode_ce` |
| `purchase_barcode_ce` | Scan products into RFQs; vendor bill follows the scanned received quantity | `purchase_stock`, `stock_barcode_ce` |
| `pos_barcode_ce` | POS: an unknown scanned code creates the product and adds it to the order | `point_of_sale`, `product_barcode_quick` |

Install `stock_barcode_ce` (plus `stock_barcode_print_ce` if you print labels); the rest install
automatically when the matching Odoo app is present.

## Design notes worth knowing

* **Scan events, not row updates.** A scan inserts a row in `stock.barcode.scan.event`; the scanned
  quantity of a move line is the sum of its events. Ten people can scan the same transfer at once
  without lock conflicts. Quantities are written to Odoo's own fields at validation time.
* **Idempotent scans.** Every scan carries a client-generated id, so a scan re-sent after a network
  failure is recognized and never counted twice. This is what makes the offline queue safe.
* **Offline queue.** Scans are stored on the device and replayed in order when the network returns;
  the UI shows what is pending and what the server refused.
* **Live updates.** Other scanners of the same transfer refresh over the Odoo bus (websocket); the
  notification carries no business data, only ids.
* **Server-side scan engine.** Barcode resolution (location / product / packaging / lot / package /
  GS1 / command) and all the rules live in Python, so the UI stays thin and the behaviour is covered
  by tests.
* **Scanner-only roles.** A "Barcode / Operator" user has no access to the Inventory backend; the
  engine checks read access and then runs in sudo, keeping `create_uid` and the scan log on the real
  user. Supervisors may override scan rules, apply counts and validate expired lots.

## Requirements

* Odoo 19 Community
* Pillow (in the Odoo image already) for label text rendering
* HTTPS for camera access (browsers refuse `getUserMedia` otherwise)
* `workers > 0` and websockets proxied for live refresh (it falls back to polling)
* `wkhtmltopdf 0.12.6.1 (patched qt)` for correct PDF label sizes (the official Odoo image has it)

## Install

```bash
./deploy-barcode-ce.sh --check      # environment check only
./deploy-barcode-ce.sh              # staging
./deploy-barcode-ce.sh --prod       # production
```

The script installs from `dist/odoo19_barcode_ce_*.zip` when present, otherwise straight from the
module folders in this repository. Or copy the folders into your addons path and install
`stock_barcode_ce` the usual way.

## Development and tests

`./dev-env.sh` sets up an isolated dev stack and `scripts/test.sh` runs the suite.
See [`CLAUDE.md`](CLAUDE.md) — it describes the layout, the sandbox setup (Odoo source + PostgreSQL +
headless Chromium) and how to run the test suite, including the browser tours.

```bash
odoo -d test_db --addons-path=addons,/path/to/this/repo \
     -i stock_barcode_ce --test-tags=/stock_barcode_ce --stop-after-init
```

The suite is 83 tests, 11 of which drive a real browser (camera dialog, product creation, receipt,
delivery with backorder, counting, restricted operator, offline queue and replay, scrap and return,
product request, sales order scanning, POS unknown code).

## Status

Running in production on a single-warehouse setup since v1.0. Current version: see each module's
`__manifest__.py` (`stock_barcode_ce` 19.0.2.1.0).

Not implemented: manufacturing (MRP) and quality scanning, IoT box printing, consignment/owner
stock, kits.

## License

LGPL-3.0-or-later, like Odoo Community. See [`LICENSE`](LICENSE).
