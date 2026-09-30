# CLAUDE.md

Guide for working on this repository with Claude Code.

## What this is

Seven Odoo 19 **Community** addons that add camera/scanner barcode workflows (warehouse scanner,
product entry, label printing, sale/purchase/POS scanning). Enterprise's `stock_barcode` is **not**
used and must never be copied — everything here is an independent implementation under LGPL-3.

Read `README.md` first for the module map, then `docs/PROJECT_HISTORY.md` — it records why the
architecture looks like this, the bugs that shaped it and what has actually been verified (中文). `docs/README_安装与验收.md` is the Chinese
install/acceptance document handed to the warehouse team; keep it in sync when behaviour changes.

## Layout

```
barcode_camera_ce/        camera scanning service, scan dialog, field widgets, navbar button
product_barcode_quick/    Barcode app root menu, product scan screen, quick create, in-store codes,
                          thermal label formats (PDF), product creation requests
stock_barcode_ce/         the scanner itself
  models/barcode_resolver.py     raw string -> typed records (location/product/lot/package/GS1/command)
  models/stock_picking.py        scan engine: state, dispatch, rules, validation, returns
  models/stock_barcode_scan_event.py   append-only quantity events (concurrency)
  models/stock_barcode_scan_log.py     audit log + idempotency (client_uuid)
  models/stock_quant.py          inventory counting
  models/stock_scrap.py          scan-to-scrap
  models/barcode_security.py     bc_guard / operator / supervisor helpers
  static/src/app/                OWL client action (main/operation/inventory/scrap)
  migrations/                    1.x -> 2.0 data migration
stock_barcode_print_ce/   TSPL/ZPL rendering, printer/agent/job models, agent endpoints,
                          tools/label_print_agent.py (standalone, stdlib only)
sale_barcode_ce/ purchase_barcode_ce/ pos_barcode_ce/    thin integrations
scripts/deploy-barcode-ce.sh     deployment to a dockerised Odoo
```

## Conventions

* Server-side first: barcode resolution, rules and state building live in Python and return one JSON
  state per call; the OWL client renders it. New behaviour needs a Python test, not just a tour.
* Public scanner API methods are `bc_*` on the model; internal helpers are `_bc_*`.
* Every scanner entry point starts with `bc_guard(self)` (access control) and mutating ones log to
  `stock.barcode.scan.log` and notify the bus.
* **Never write a shared row on the scan hot path.** Quantities are events; writing a stored field on
  `stock.move.line` updates `write_date` and brings back lock conflicts. Use `line._bc_add(delta)`.
* Source strings are English; Chinese lives in `i18n/zh_CN.po` (regenerate the `.pot`, then merge).
* Style: no Enterprise-looking wording, keep labels short enough for a phone screen.

## Dev environment and tests

`./dev-env.sh` builds an isolated dev stack (Odoo container with headless Chromium, CJK fonts and the
test dependencies + its own PostgreSQL, ports 8169/5442 by default) and writes `scripts/test.sh`.
It never touches production. Then:

```bash
./scripts/test.sh                    # all 7 modules, including the browser tours
./scripts/test.sh stock_barcode_ce   # one module
./scripts/test.sh stock_barcode_ce TestBarcodeV2
./scripts/test.sh --core             # Odoo's own stock suite, as a regression baseline
```

Doing it by hand instead: Odoo 19 source + PostgreSQL + `wkhtmltopdf 0.12.6.1 (patched qt)` +
`fonts-noto-cjk` + `pip install rlPyCairo websocket-client polib`, a headless Chromium on PATH for
the tours, then `odoo -d t1 --addons-path=<odoo>/addons,. -i <modules> --test-tags=<tags>
--stop-after-init --log-level=test`.

CI: `.github/workflows/tests.yml` runs the same suite (all 7 modules, tours included) on every push
inside the official `odoo:19` image; the full log is uploaded as the `odoo-test-log` artifact.

Useful checks that caught real bugs before:

* run Odoo's own `--test-tags=/stock` suite with and without these modules and compare — they must
  match (5 pre-existing failures come from `purchase` being installed, not from us);
* concurrency: N threads scanning one picking through `registry.cursor()`, expect zero
  serialization failures and recorded qty == successful scans;
* upgrade with live data: install the previous version, scan half a transfer, then `-u`.

## Testing gotchas

* `bus.bus` notifications are written at commit: call `env.cr.precommit.run()` in tests.
* PDF rendering in tests needs `with_context(force_report_rendering=True)`.
* External processes hitting the test server need `self.http_request_allow_all = True`, and a
  blocking subprocess while holding the test cursor deadlocks — drive the agent in-process instead.
* POS product creation requires `product.group_product_manager`.

## Current state

83 tests pass (11 browser tours). In production on one warehouse. Versions live in each
`__manifest__.py`; `stock_barcode_ce` is 19.0.2.1.0.

## Roadmap

Short term, in the modules:

* MRP and quality scanning, IoT-box printing, consignment/owner stock, kits — all unimplemented.
* Offline queue currently covers the open transfer only; counting is online-only.
* Scan rules are per operation type; there is no global policy screen yet.

Bigger, separate project (not in this repo): a standalone service for AI carton-spec intake
(photograph a carton, a cloud model fills unit→carton data), packing-list matching, unique carton
labels and period reconciliation (quantity, amount, partner accounts), with a thin Odoo adapter.
The `stock.barcode.scan.event` and `stock.barcode.scan.log` tables are the intended data source for
it — keep them append-only and versioned (`schema_version`).

## Safety rails

* Don't change stock semantics behind Odoo's back: the engine must always end with standard
  `button_validate()` / `action_done()` so backorders, valuation and accounting stay correct.
* Keep operator (no backend rights) paths working: any new wizard opened from the scanner must be
  reachable by a user with only `stock_barcode_ce.group_barcode_operator`, or the scanner must ask
  the question itself (see how backorder and expired-lot confirmations are handled).
* The scan log is append-only; never add code that edits or deletes rows.
