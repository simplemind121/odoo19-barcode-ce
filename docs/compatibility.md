# Behaviour differences from stock Odoo 19 Community

This page lists every place where installing the suite changes what a user
sees or what the system does, compared with an Odoo 19 Community database
without it. Use it to decide whether the suite fits a "no deviation from the
standard flows" requirement, and to know what to switch off.

Status of this list: compiled by reading the code of version 2.1 on
2026-10-01. The items are not each covered by a dedicated test. If you find a
difference that is missing here, please open an issue.

## Summary

*   Standard stock operations done in the backend (validate, backorder,
    return, scrap, inventory adjustment) are not overridden. No standard
    method of `stock.picking`, `stock.move`, `stock.move.line` or
    `stock.quant` is replaced.
*   Three changes are active by default on standard screens. They are listed
    in [Changes to standard screens](#changes-to-standard-screens).
*   The scanner itself reaches the same end state as the backend for
    validation and backorders, but takes a different path in several places.
    They are listed in [Differences inside the scanner](#differences-inside-the-scanner).

## Changes to standard screens

These apply even when nobody uses the scanner.

| # | Area | Stock Odoo | With the suite | Default | How to restore stock behaviour |
| --- | --- | --- | --- | --- | --- |
| 1 | Product barcode field | Any string is accepted. | A numeric code of 8, 12, 13 or 14 digits with a wrong check digit is refused when a product barcode is created or changed. Existing data is not re-checked. | On | **Settings → Product Barcodes**: clear the check-digit option (`res.company.bcq_strict_gtin`). |
| 2 | POS, unknown barcode | An "unknown barcode" notification. | A user with product creation rights is asked whether to create the product; the new product is added to the order. Other users get the stock behaviour. | On | Uninstall `pos_barcode_ce`. There is no setting. |
| 3 | Quotation and RFQ forms | A scan does nothing. | In states draft and sent, a scan adds the product as a line, or increments an existing line. | On | Uninstall `sale_barcode_ce` and `purchase_barcode_ce`. There is no setting. |
| 4 | Product label wizard | Standard formats. | Three extra formats: thermal 40×30, 50×30, 60×40 mm. Standard formats are unchanged. | Additive | — |
| 5 | Transfer and batch forms | — | A **Barcode** button opens the scanner. | Additive | — |
| 6 | Operation type form | — | A **Barcode rules** tab. All six rules are off. | Additive, off | — |
| 7 | Groups | — | `Inventory / User` implies `Barcode / Supervisor`. New group `Barcode / Operator`. | Additive | — |
| 8 | User home action | — | A user who is an operator and not an inventory user gets the scanner as home action, when no home action is set. | Operators only | Set another home action on the user. |

## Differences inside the scanner

These apply to work done through the scanner UI.

| # | Step | Backend flow | Scanner flow | Effect on the result |
| --- | --- | --- | --- | --- |
| 1 | Rights | The user needs Inventory rights to change a transfer. | An operator with read access only can scan and validate; the engine runs with `sudo()` after a read check. | A new role that does not exist in stock Odoo. See [../SECURITY.md](../SECURITY.md). |
| 2 | Done quantity | The user edits `quantity` on move lines. | Scans are stored as events. `quantity` and `picked` are written at validation. | Same end state. Until validation, the backend form does not show scanned quantities. |
| 3 | Unscanned lines | Reserved lines keep their quantity unless the user changes them. | At validation, for a move with at least one scanned line, the reserved lines that were not scanned are deleted. | Equivalent to picking only part of the move: the rest goes to a backorder or is cancelled. |
| 4 | Nothing scanned | **Validate** processes all reserved quantities. | The scanner asks for confirmation first, then does the same. | Same end state, one more confirmation. |
| 5 | Backorder | The backorder wizard. | The scanner asks the same question itself and passes the answer to `button_validate()` through the standard context keys. | Same end state. |
| 6 | Expired lots | The `product_expiry` confirmation wizard; any inventory user may confirm. | The scanner asks itself. Supervisors (which includes all inventory users) may confirm. Operator-only users are blocked. | Same for inventory users. |
| 7 | Putaway | The putaway rule is evaluated with the quantity of the line. | For a line created by the scanner, the rule is evaluated with quantity 1. | With putaway rules that depend on storage capacity, the suggested location can differ. |
| 8 | Product not in the transfer | The user adds a move and types the demand. | A move with demand 0 is created and confirmed, and the scanned quantity is recorded on it. Refused when the `bc_block_extra` rule is on. | The move's demand is 0 instead of the typed quantity. |
| 9 | Return | The return wizard; the user types the quantity to return per line. | The return is created for the full remaining quantity of every line. The user then scans what actually came back and validates; the rest is handled by the backorder question. | The return transfer's demand is the full quantity, not the returned quantity. |
| 10 | Scrap | An inventory user scraps from the backend. | Scan to scrap is for supervisors (which includes all inventory users). The backend scrap flow is unchanged. | Same for inventory users. |
| 11 | Inventory count | The user edits counted quantities and applies. | Counts are scanned. Applying, and setting uncounted quants to zero, need a supervisor. | Same for inventory users. |
| 12 | Scan rules | — | Optional per operation type: require source or destination scan, forbid typed quantities, require packing, refuse extra products, refuse over-quantity. | Off by default. |

## What stays standard

*   `button_validate()` is always the last step. Backorder creation, stock
    valuation, accounting entries and chained moves are Odoo's.
*   Invoices and vendor bills offered after validation call the standard
    actions (`sale.action_view_sale_advance_payment_inv`,
    `purchase.order.action_create_invoice`).
*   Barcode nomenclatures, including GS1, are Odoo's. The suite reads them and
    does not change the rules.

## Regression evidence

*   The suite's own 83 tests pass on every push; see
    [development.md](development.md).
*   The project history records a run of Odoo's own stock test suite (639
    tests) with identical results with and without the suite installed. That
    comparison is not yet part of CI. To repeat it, run
    `./scripts/test.sh --core` and compare with a run on a database without
    these modules.
