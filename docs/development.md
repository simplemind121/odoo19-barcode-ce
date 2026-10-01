# Development guide

This guide gets you from a fresh clone to a passing test run, and lists the
conventions and pitfalls you need to know before you change code.

## Prerequisites

*   Docker with the `docker compose` plugin.
*   About 6 GB of free disk space (Odoo source, images, two volumes).
*   Git.

You do not need a local Python or PostgreSQL installation.

## Set up the environment

```bash
git clone https://github.com/simplemind121/odoo19-barcode-ce.git
cd odoo19-barcode-ce
./dev-env.sh
```

`dev-env.sh` builds an isolated stack under `.devenv/` (ignored by Git):

*   an Odoo 19 container with headless Chromium, CJK fonts and the test
    dependencies, on <http://127.0.0.1:8169>;
*   its own PostgreSQL 16, on port 5442;
*   a checkout of the Odoo 19 Community source, needed by the test framework;
*   the generated script `scripts/test.sh`.

The first run takes 5 to 10 minutes. Later runs reuse everything.

| Command | Effect |
| --- | --- |
| `./dev-env.sh` | Start, or create, the stack |
| `./dev-env.sh --port 8170 --pg-port 5443` | Use other ports |
| `./dev-env.sh --down` | Stop the stack; data is kept |
| `./dev-env.sh --destroy` | Stop the stack and delete its volumes |
| `./dev-env.sh --seed-from <db>` | Copy a database from a local production PostgreSQL container into `devdb` |

The stack never connects to a production database on its own. Do not point it
at one: the tests validate transfers, scrap products and apply inventory
counts.

## Run the tests

```bash
./scripts/test.sh                                # all seven modules
./scripts/test.sh stock_barcode_ce               # one module
./scripts/test.sh stock_barcode_ce TestBarcodeV2 # one test class
./scripts/test.sh --core                         # Odoo's own stock suites
```

Each run creates a new database `test_<HHMMSS>` and runs in a one-off
container. The summary line looks like this:

```
0 failed, 0 error(s) of 83 tests when loading database 'test_223102'
```

The full log is written to `/tmp/test_<HHMMSS>.log` on the host.

The suite has 83 tests. Eleven are browser tours that drive headless
Chromium: camera dialog, product creation, receipt, delivery with backorder,
counting, restricted operator, offline queue and replay, scrap and return,
product request, sales order scanning, POS unknown code.

### Continuous integration

[`.github/workflows/tests.yml`](../.github/workflows/tests.yml) runs the same
suite on every push and pull request, inside the official `odoo:19` image
against PostgreSQL 16. The job fails when the log contains an `ERROR` or
`CRITICAL` line. The full log is uploaded as the `odoo-test-log` artifact.

### Running without Docker

You need the Odoo 19 source, PostgreSQL, `wkhtmltopdf 0.12.6.1 (with patched
qt)`, `fonts-noto-cjk`, a headless Chromium on `PATH`, and:

```bash
pip install rlPyCairo websocket-client polib
```

Then:

```bash
odoo -d t1 --addons-path=<odoo>/addons,. \
     -i stock_barcode_ce,stock_account,product_expiry \
     --test-tags=/stock_barcode_ce --stop-after-init --log-level=test
```

## Try it by hand

Create a database with demo data and open it in a browser:

```bash
cd .devenv
docker compose run --rm -T odoo odoo -d trial \
    --db_host=db --db_user=odoo --db_password=odoo \
    --addons-path=/mnt/odoo-src/addons,/mnt/project \
    --with-demo -i stock_barcode_ce,stock_barcode_print_ce \
    --stop-after-init
```

Open <http://127.0.0.1:8169/web/login?db=trial>. A database created from the
command line has the default administrator account of Odoo; change its
password if the port is reachable by anyone else.

The camera needs HTTPS or `localhost`. On a phone, use a tunnel or a reverse
proxy with a certificate.

## Repository layout

```
barcode_camera_ce/        camera service, scan dialog, field widgets, navbar button
product_barcode_quick/    Barcode app root menu, product scan screen, quick create,
                          in-store codes, thermal label formats, product requests
stock_barcode_ce/         the scanner
  models/barcode_resolver.py          string -> typed records
  models/stock_picking.py             scan engine, rules, validation, returns
  models/stock_barcode_scan_event.py  quantity events
  models/stock_barcode_scan_log.py    audit log, idempotency
  models/stock_quant.py               inventory counting
  models/stock_scrap.py               scan to scrap
  models/barcode_security.py          bc_guard and role helpers
  static/src/app/                     OWL client action
  static/tests/tours/                 browser tours
  migrations/                         1.x -> 2.0 data migration
stock_barcode_print_ce/   TSPL/ZPL rendering, printer, agent and job models,
                          agent endpoints, tools/label_print_agent.py
sale_barcode_ce/  purchase_barcode_ce/  pos_barcode_ce/   thin integrations
scripts/                  deployment and publishing scripts; test.sh is generated
docs/                     documentation
```

## Conventions

*   **Server first.** Barcode resolution, rules and state building live in
    Python and return one JSON state per call. New behaviour needs a Python
    test.
*   **Naming.** Public scanner RPC methods are `bc_*`; internal helpers are
    `_bc_*`. In `product_barcode_quick` the prefix is `bcq_`.
*   **Entry points.** Every public scanner method starts with
    `bc_guard(self)`. Methods that change data write to
    `stock.barcode.scan.log` and call `_bc_notify()`.
*   **Hot path.** Do not write a stored field of `stock.move.line` during a
    scan. Use `line._bc_add(delta)`.
*   **Translations.** Source strings are English. After changing strings,
    regenerate `i18n/<module>.pot` and merge into `i18n/zh_CN.po`.
*   **Versions.** `19.0.<major>.<minor>.<patch>` in `__manifest__.py`. Bump
    when the data model changes. Put data migrations under
    `migrations/<version>/`.

The rules that reviewers enforce are in
[../CONTRIBUTING.md](../CONTRIBUTING.md#rules-that-reviewers-enforce).

## Testing pitfalls

*   **PDF rendering hangs.** Render reports inside
    `with self.allow_pdf_render():` and with
    `with_context(force_report_rendering=True)`. Otherwise wkhtmltopdf's
    request for the assets waits on the test transaction forever.
*   **Do not run tests next to a live server.** `docker exec` into the running
    dev container produces the same hang. `scripts/test.sh` uses
    `docker compose run`, which starts a separate container.
*   **Bus notifications are sent at commit.** In a test, call
    `self.env.cr.precommit.run()` before you assert on them.
*   **External processes.** A process that calls the test server needs
    `self.http_request_allow_all = True`. A blocking subprocess that waits on
    the server while the test holds the cursor deadlocks; drive the print
    agent in-process with `run_once()`.
*   **POS product creation** needs the group `product.group_product_manager`.
*   **Namespace packages.** In Odoo 19 both `odoo` and `odoo.addons` are
    namespace packages without `__file__`. Do not derive paths from them.

## Checks beyond the unit tests

These have caught real bugs. Run them before a release that touches the scan
engine.

*   **Core regression.** Run Odoo's own stock suites with and without the
    suite installed and compare the results; they must match.
    `./scripts/test.sh --core` runs them with the suite installed.
*   **Concurrency.** N threads scanning one transfer through
    `registry.cursor()`. Expect zero serialization failures, and a recorded
    quantity equal to the number of successful scans.
*   **Upgrade with live data.** Install the previous version, scan half a
    transfer, then upgrade with `-u` and finish the transfer.

## Release checklist

1.  All tests pass locally and in CI.
2.  `version` bumped in the manifests that changed.
3.  `CHANGELOG.md`: move **Unreleased** to a new version heading with the
    date.
4.  `docs/README_安装与验收.md` and `docs/compatibility.md` match the new
    behaviour.
5.  Tag the commit `v<major>.<minor>.<patch>` and push the tag.
