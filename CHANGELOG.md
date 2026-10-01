# Changelog

All notable changes to this project are recorded in this file. Versions are
suite versions; the matching module versions are given in parentheses.

## Unreleased

### Fixed
- `product_barcode_quick`: the thermal label PDF test hung on Odoo 19 because
  wkhtmltopdf's asset request waited on the test transaction. The test now
  renders inside `allow_pdf_render()`.
- `dev-env.sh`: the generated `scripts/test.sh` runs the suite in a one-off
  container instead of inside the running dev server container, which caused
  the same hang.

### Added
- GitHub Actions workflow that runs the full suite, browser tours included,
  on every push and pull request.
- Full text of the LGPL-3 licence.
- Documentation: deployment, label printing, compatibility with stock Odoo,
  architecture, scanner API reference, development guide, per-module READMEs,
  contribution guide, security policy, code of conduct, issue and pull request
  templates.

## 2.1 (stock_barcode_ce 19.0.2.1.0, stock_barcode_print_ce 19.0.1.0.0)
- Direct thermal label printing (TSPL/ZPL) through a local print agent: product, lot/serial,
  location and package labels; PDF fallback when no printer is configured.
- Scan to scrap (supervisors) and scan to return a done transfer.
- Operators without product rights can file a product creation request instead of failing.
- Expired lots are confirmed inside the scanner; operators are blocked, supervisors may validate.

## 2.0 (stock_barcode_ce 19.0.2.0.0)
- Scan events replace row updates: ten concurrent scanners on one transfer, zero lock conflicts.
- Idempotent scans (client-generated id): a re-sent scan is never counted twice.
- Offline queue for the open transfer, with pending preview and a list of refused scans.
- Live refresh over the bus and presence of the other scanners on the transfer.
- Migration of in-progress scanned quantities from 1.x.

## 1.1
- Scan log (append-only, versioned) for audit and future reconciliation datasets.
- Per operation type scan rules: source/destination location required, no typed quantities,
  packing required, refuse extra products, refuse over-quantity.
- Operator and supervisor roles; operators have no Inventory backend access.
- Barcode data check: wrong check digits, codes misread by the nomenclature, duplicates,
  products and locations without barcode.
- Backorder confirmation asked inside the scanner instead of the backend wizard.

## 1.0
- Camera scanning everywhere, warehouse scanner (receipts, deliveries, transfers, counting,
  lots/serials, packages, GS1, command barcodes, batch/wave), scan-to-create products, in-store
  EAN-13 codes, thermal PDF labels, bin generator, sale/purchase scanning and settlement, POS.
