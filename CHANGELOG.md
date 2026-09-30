# Changelog

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
