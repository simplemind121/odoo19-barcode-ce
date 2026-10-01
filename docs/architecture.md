# Architecture

This document explains how the suite is put together and why. It describes the
`main` branch. For the history behind each decision, see
[PROJECT_HISTORY.md](PROJECT_HISTORY.md) (Chinese).

## Goals and non-goals

Goals:

*   Give Odoo 19 Community a warehouse scanner that works on phones, on laptop
    cameras and with scanner guns.
*   Leave stock accounting to Odoo. The scanner prepares quantities; Odoo
    validates the transfer.
*   Let several people scan the same transfer at the same time.
*   Survive a weak network on the warehouse floor.

Non-goals:

*   Reimplementing or copying the Enterprise `stock_barcode` module.
*   Manufacturing, quality checks, IoT box integration, consignment stock, kits.
*   A full offline mode. Only the open transfer is queued offline.

## Module map

```
barcode_camera_ce          camera service, scan dialog, navbar button
        ▲
product_barcode_quick      "Barcode" app root, product lookup and creation,
        ▲                  in-store codes, thermal label formats (PDF)
        │
stock_barcode_ce           scan engine, scanner UI, counting, scrap, returns,
        ▲                  rules, roles, scan log, scan events
        │
        ├── stock_barcode_print_ce   TSPL/ZPL rendering, print queue, agent
        ├── sale_barcode_ce          scan into quotations, invoice shortcut
        └── purchase_barcode_ce      scan into RFQs, vendor bill shortcut

pos_barcode_ce             depends on product_barcode_quick only
```

`sale_barcode_ce`, `purchase_barcode_ce` and `pos_barcode_ce` are thin and
auto-install when their Odoo app is present.

## Request flow of one scan

```
phone / scanner gun
   │  barcode string + client uuid + scan context
   ▼
stock.picking.bc_scan()                     models/stock_picking.py
   │ 1. bc_guard(): access check, then sudo for operators
   │ 2. duplicate uuid? -> return current state
   ▼
stock.barcode.resolver.resolve()            models/barcode_resolver.py
   │ string -> command | GS1 | transfer | batch | operation type |
   │           location | product (+qty) | lot | package | unknown
   ▼
_bc_dispatch() inside a savepoint
   │ location  -> source or destination of the scan context
   │ product   -> find or create a move line, insert a scan event
   │ package   -> take a whole package, or set the destination package
   │ command   -> validate, pack, print, clear, main menu
   ▼
stock.barcode.scan.log (one row)   +   bus notification to other scanners
   ▼
_bc_state() -> one JSON object -> the OWL client re-renders
```

The client holds no business logic. Every call returns the complete state of
the transfer, so the UI cannot drift from the server.

## Barcode resolution order

`stock.barcode.resolver.resolve()` tries, in this order, and stops at the
first match:

1.  Command barcodes (`O-CMD.*`, `O-BTN.*`).
2.  GS1-128 aggregate codes, when the company uses a GS1 nomenclature.
3.  Transfer reference, then batch reference.
4.  Operation type barcode.
5.  Location barcode.
6.  Product barcode, including packaging barcodes and nomenclature rules
    (weight, price). A packaging barcode returns the contained quantity.
7.  Lot or serial number name.
8.  Package name.
9.  A code that the nomenclature classifies as a package: a new package name.
10. Unknown. The caller may treat it as a new lot name when a tracked product
    is waiting for one.

The nomenclature alone is not enough to classify a code, because the default
rules reserve prefixes 21–23 and 10. That is why records are looked up
explicitly.

## Data model

Only the tables added by this suite are listed.

| Model | Module | Purpose |
| --- | --- | --- |
| `stock.barcode.scan.event` | `stock_barcode_ce` | One row per quantity change on a move line. The scanned quantity is the sum. |
| `stock.barcode.scan.log` | `stock_barcode_ce` | One row per scanner action, for audit and for idempotency (`client_uuid`, unique). Versioned with `schema_version`. |
| `stock.barcode.resolver` | `stock_barcode_ce` | Abstract model; turns a string into typed records. |
| `stock.barcode.health` | `stock_barcode_ce` | Barcode data check: wrong check digits, misread prefixes, duplicates, missing codes. |
| `stock.bin.generator` | `stock_barcode_ce` | Wizard that creates zone-rack-level-bin locations with barcodes. |
| `product.barcode.request` | `product_barcode_quick` | A request, filed by an operator, to create a product for an unknown code. |
| `product.barcode.quick` | `product_barcode_quick` | Wizard that creates a product from a scanned code. |
| `barcode.label.agent` | `stock_barcode_print_ce` | A print agent and its token. |
| `barcode.label.printer` | `stock_barcode_print_ce` | A thermal printer: target, language, dpi, label size. |
| `barcode.label.job` | `stock_barcode_print_ce` | One queued print job. |

Fields added to standard models:

| Model | Field | Purpose |
| --- | --- | --- |
| `stock.move.line` | `bc_qty` | Computed: sum of scan events. Writing it records the difference as a new event. |
| `stock.move.line` | `bc_dest_confirmed` | The destination location was scanned. |
| `stock.move.line` | `bc_created` | The line was created by the scanner, not by a reservation. |
| `stock.picking.type` | `bc_require_source`, `bc_require_dest`, `bc_scan_only`, `bc_require_pack`, `bc_block_extra`, `bc_block_over` | Scan rules. All default to off. |
| `res.company` | `bcq_instore_prefix`, `bcq_strict_gtin` | In-store EAN-13 prefix; check-digit validation (default on). |
| `res.users` | `bc_label_printer_id` | The user's default label printer. |

## Concurrency: scan events

Version 1 updated `stock.move.line` on every scan. With six people on one
transfer, about 5% of scans were refused because of row lock conflicts.

Since version 2 a scan only inserts a row in `stock.barcode.scan.event`.
Inserts do not conflict. `stock.move.line.bc_qty` is a non-stored computed
field that sums the events with one SQL query.

Rule for contributors: **do not write a stored field of a shared row on the
scan hot path.** Even an unrelated field updates `write_date` and brings the
conflicts back. Use `line._bc_add(delta)`.

The quantities reach Odoo's own fields only at validation; see
[Validation](#validation).

## Idempotency

The client generates a UUID for each scan. The server stores it in
`stock.barcode.scan.log.client_uuid`, which has a partial unique index. When a
scan arrives with a UUID that is already logged, the server returns the
current state with an "Already recorded" message and changes nothing.

This applies to transfer and batch scans. Inventory counting scans carry no
UUID and must be made online.

## Offline queue

The client (`static/src/app/operation.js`) keeps a queue of scans in
`localStorage`, keyed by the open transfer.

*   A scan is queued first, then sent. Scans are sent strictly in order.
*   When a request fails because of the network, the queue retries with an
    increasing delay. The page shows the number of pending scans and previews
    the pending quantity on each product.
*   Validate, put in pack and add product are disabled while scans are
    pending.
*   A queued scan that the server refuses after reconnection (unknown code,
    rule violation) is listed on the page. It is never dropped silently.
*   The queue survives a page reload.

## Live refresh and presence

After a change the server sends a `stock_barcode_ce/update` notification on
the channel `stock_barcode_ce.<model>.<id>` of each transfer and of its batch.
The payload holds the record id, the user id, the user name and the device id.
It holds no business data. Other clients respond by reloading the state.

"Presence" is the list of other users who have a scan log row for the transfer
in the last two minutes.

Live refresh needs `workers > 0` and a proxy that forwards websockets.

## Validation

`_bc_validate_inner()` does the following inside one savepoint:

1.  Check the scan rules of the operation type.
2.  If nothing was scanned, return a question to the client: validate all
    reserved quantities? Under the `bc_scan_only` rule only a supervisor may
    say yes.
3.  Otherwise, for moves with at least one scanned line: delete the lines that
    were not scanned, then write `quantity = bc_qty` and `picked = True` on the
    scanned lines.
4.  Ask about expired lots, when `product_expiry` is installed. The scanner
    asks the question itself because operators cannot open backend wizards.
5.  Ask about a backorder, using Odoo's own `_check_backorder()`.
6.  Call the standard `button_validate()` with `skip_backorder` and, when the
    user declined the backorder, `picking_ids_not_to_backorder`.

Backorders, valuation layers and accounting entries are produced by Odoo.

## Roles and access

| Group | Implied by | Can do |
| --- | --- | --- |
| `group_barcode_operator` | — | Use the scanner. No Inventory backend. Read access to the stock models. |
| `group_barcode_supervisor` | `stock.group_stock_user` | Operator rights, plus: override `bc_scan_only`, validate unscanned transfers, apply counts, scrap, confirm expired lots, read the scan log. |

Every public scanner method starts with `bc_guard(records)`:

*   Inventory users and superuser: the records are returned unchanged.
*   Operators: `check_access("read")` on the records, then `records.sudo()`.
    `sudo()` keeps the real uid, so `create_uid`, chatter and the scan log
    still name the operator.
*   Anyone else: `AccessError`.

See [../SECURITY.md](../SECURITY.md) for the trust model that follows from
this design.

## Label printing

Two paths exist and both are kept:

*   **PDF.** `product_barcode_quick` adds three thermal formats to the standard
    label wizard. The browser prints the PDF. This is the fallback when no
    printer is configured.
*   **Direct.** `stock_barcode_print_ce` renders TSPL or ZPL on the server.
    Text is drawn as a bitmap with Pillow, so the printer needs no CJK font;
    barcodes use the printer's native commands. Jobs are queued in
    `barcode.label.job`. A local agent polls Odoo over HTTPS and forwards the
    bytes to the printer. Only outgoing connections are used.

A job that stays in state `sent` without an acknowledgement is put back in the
queue by a cron job that runs every five minutes. The worst case is one
duplicate label, never a lost one.

Details: [label-printing.md](label-printing.md).

## Client

The scanner is one OWL client action, `stock_barcode_ce.main`, in
`stock_barcode_ce/static/src/app/`:

| File | Screen |
| --- | --- |
| `main.js` | Home: operation types by warehouse, transfer lists, global scan |
| `operation.js` | A transfer or a batch: scanning, offline queue, validation dialogs |
| `inventory.js` | Inventory counting |
| `scrap.js` | Scan to scrap |
| `device.js` | Stable device id, stored in `localStorage` |

Camera access goes through the `barcode_camera_ce` service, which wraps the
`BarcodeVideoScanner` component that ships in Odoo's `web` module.

## Known limitations

*   The offline queue covers the open transfer only.
*   Scan rules are set per operation type; there is no global policy screen.
*   Scan events are deleted together with their move line
    (`ondelete="cascade"`), and inventory managers have delete access to the
    scan log. The tables are append-only by convention, not by constraint.
*   Multi-step routes are covered by tests but have not been run in a real
    multi-step warehouse.
*   See [compatibility.md](compatibility.md) for behaviour that differs from
    stock Odoo.
