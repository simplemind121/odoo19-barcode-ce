# odoo19-barcode-ce

[![tests](https://github.com/simplemind121/odoo19-barcode-ce/actions/workflows/tests.yml/badge.svg)](https://github.com/simplemind121/odoo19-barcode-ce/actions/workflows/tests.yml)
[![License: LGPL-3.0-or-later](https://img.shields.io/badge/license-LGPL--3.0--or--later-blue.svg)](LICENSE)
![Odoo 19.0 Community](https://img.shields.io/badge/Odoo-19.0%20Community-714B67.svg)

Camera and hardware barcode scanning for **Odoo 19 Community Edition**: a
warehouse scanner app (receipts, deliveries, internal transfers, inventory
counts, lots and serial numbers, packages, GS1, batch and wave picking),
scan-to-create products, thermal label printing, and scanning inside sales,
purchase and POS.

No Odoo Enterprise code is used. Everything here is an independent
implementation released under the LGPL-3.

> 中文说明：[README.zh-CN.md](README.zh-CN.md)

## Contents

*   [Why this exists](#why-this-exists)
*   [Modules](#modules)
*   [Requirements](#requirements)
*   [Quick start](#quick-start)
*   [Documentation](#documentation)
*   [Design in brief](#design-in-brief)
*   [Tests](#tests)
*   [Project status](#project-status)
*   [Contributing](#contributing)
*   [Security](#security)
*   [License and disclaimer](#license-and-disclaimer)

## Why this exists

Odoo 19 Community ships the building blocks (barcode nomenclatures, a camera
scanner component in `web`, POS camera scanning) but no warehouse Barcode app;
that app is Enterprise only. This suite fills the gap with a mobile-first
scanner UI. Stock movements still go through Odoo's standard business logic
(backorders, reservations, valuation, accounting): the scanner always finishes
with the standard `button_validate()`.

## Modules

| Module | What it does | Depends on |
| --- | --- | --- |
| [`barcode_camera_ce`](barcode_camera_ce/README.md) | Camera scanning anywhere in the backend: navbar scan button, continuous scan dialog, sound and vibration. Camera and scanner gun share one input path. | `web`, `barcodes` |
| [`product_barcode_quick`](product_barcode_quick/README.md) | "Barcode" app root: scan to look up a product, create unknown ones, generate in-store EAN-13 codes, validate EAN/UPC check digits, print 40×30 / 50×30 / 60×40 mm thermal labels (PDF). | `product`, `base_setup`, `barcodes_gs1_nomenclature`, `barcode_camera_ce` |
| [`stock_barcode_ce`](stock_barcode_ce/README.md) | The warehouse scanner: receipts, deliveries, transfers, putaway, counting, lots and serials, packages, GS1, command barcodes, batch and wave picking, scrap, returns, bin generator, scan log, scan rules, operator and supervisor roles. | `stock`, `stock_picking_batch`, `bus`, `barcodes_gs1_nomenclature`, `barcode_camera_ce`, `product_barcode_quick` |
| [`stock_barcode_print_ce`](stock_barcode_print_ce/README.md) | Direct label printing to TSPL/ZPL thermal printers through a small local agent. | `stock_barcode_ce` |
| [`sale_barcode_ce`](sale_barcode_ce/README.md) | Scan products into quotations; invoice right after a scanned delivery. | `sale_stock`, `stock_barcode_ce` |
| [`purchase_barcode_ce`](purchase_barcode_ce/README.md) | Scan products into RFQs; create the vendor bill after a scanned receipt. | `purchase_stock`, `stock_barcode_ce` |
| [`pos_barcode_ce`](pos_barcode_ce/README.md) | POS: an unknown scanned code can create the product and add it to the order. | `point_of_sale`, `product_barcode_quick` |

Install `stock_barcode_ce`, plus `stock_barcode_print_ce` if you print labels
directly. The sales, purchase and POS modules install automatically when the
matching Odoo app is present.

## Requirements

*   Odoo 19.0 Community.
*   HTTPS, for camera access. Browsers refuse `getUserMedia` on plain HTTP.
    Scanner guns work without it.
*   `wkhtmltopdf 0.12.6.1 (with patched qt)` for correct PDF label sizes. The
    official `odoo:19` image has it.
*   Pillow, for label text rendering. The official image has it.
*   `workers > 0` and websockets proxied, for live refresh between scanners.
    Without them the scanner falls back to polling.

## Quick start

Copy the seven module folders into your addons path, update the apps list, and
install **Stock Barcode (CE)**. For a dockerised Odoo there is a deployment
script that checks the environment, backs up the module folders and prints the
rollback command:

```bash
./deploy-barcode-ce.sh --check   # environment check only, changes nothing
./deploy-barcode-ce.sh           # deploy to staging
./deploy-barcode-ce.sh --prod    # deploy to production
```

The script does not back up the database. Take a `pg_dump` first. See
[docs/deployment.md](docs/deployment.md).

To try it locally with demo data:

```bash
./dev-env.sh          # isolated Odoo + PostgreSQL on ports 8169 / 5442
./scripts/test.sh     # run the full suite
```

See [docs/development.md](docs/development.md).

## Documentation

| Document | Audience | Content |
| --- | --- | --- |
| [docs/deployment.md](docs/deployment.md) | Administrators | Prerequisites, install, upgrade, rollback, configuration |
| [docs/label-printing.md](docs/label-printing.md) | Administrators | Print agent setup, printer targets, agent protocol |
| [docs/compatibility.md](docs/compatibility.md) | Administrators, reviewers | Where behaviour differs from stock Odoo 19 Community |
| [docs/architecture.md](docs/architecture.md) | Developers | Data model, scan engine, concurrency, offline queue, roles |
| [docs/scanner-api.md](docs/scanner-api.md) | Developers | The `bc_*` RPC methods and the state object |
| [docs/development.md](docs/development.md) | Developers | Dev environment, tests, conventions |
| [docs/README_安装与验收.md](docs/README_安装与验收.md) | 仓库团队 | 安装、使用、验收清单（中文） |
| [docs/PROJECT_HISTORY.md](docs/PROJECT_HISTORY.md) | 接手开发者 | 设计决策、踩过的坑、验证结论（中文） |
| [CHANGELOG.md](CHANGELOG.md) | Everyone | Release notes |

## Design in brief

*   **Scan events, not row updates.** A scan inserts a row in
    `stock.barcode.scan.event`. The scanned quantity of a move line is the sum
    of its events, so several people can scan one transfer without lock
    conflicts. Quantities reach Odoo's own fields at validation time.
*   **Idempotent scans.** Every scan carries a client-generated id. A scan
    re-sent after a network failure is recognized and not counted twice.
*   **Offline queue.** Scans are stored on the device and replayed in order
    when the network returns. It covers the open transfer; counting is online
    only.
*   **Server-side scan engine.** Barcode resolution and all rules live in
    Python and return one JSON state per call. The OWL client only renders it.
*   **Scanner-only roles.** A "Barcode / Operator" user has no Inventory
    backend access. See [SECURITY.md](SECURITY.md) for the trust model.

Details are in [docs/architecture.md](docs/architecture.md).

## Tests

The suite has 83 tests, 11 of which drive a real headless browser. CI runs it
on every push inside the official `odoo:19` image; see
[`.github/workflows/tests.yml`](.github/workflows/tests.yml).

```bash
./scripts/test.sh                    # all seven modules
./scripts/test.sh stock_barcode_ce   # one module
```

## Project status

Version 2.1 (`stock_barcode_ce` 19.0.2.1.0). In production on one
single-warehouse installation since 1.0.

Not verified on real hardware by the automated tests: camera framing, scanner
gun models, and the paper output of thermal printers. Use the acceptance
checklist in [docs/README_安装与验收.md](docs/README_安装与验收.md).

Not implemented: manufacturing (MRP) and quality scanning, IoT box printing,
consignment (owner) stock, kits, offline counting.

Known behaviour differences from stock Odoo are listed in
[docs/compatibility.md](docs/compatibility.md).

## Contributing

Bug reports and pull requests are welcome. Read
[CONTRIBUTING.md](CONTRIBUTING.md) first. This project follows a
[code of conduct](CODE_OF_CONDUCT.md).

## Security

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
Do not open a public issue for them.

## License and disclaimer

LGPL-3.0-or-later, like Odoo Community. See [LICENSE](LICENSE) and
[AUTHORS](AUTHORS).

This is not an official Odoo product and is not affiliated with or endorsed by
Odoo S.A. "Odoo" is a trademark of Odoo S.A.
