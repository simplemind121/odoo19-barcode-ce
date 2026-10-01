# Scanner API reference

The scanner client talks to the server through ordinary Odoo RPC calls
(`orm.call`) on public model methods named `bc_*`. This page lists them.

The API is internal to the suite. It can change between versions; changes are
recorded in [../CHANGELOG.md](../CHANGELOG.md).

## Conventions

*   Every method starts with `bc_guard()`. The caller must be an inventory
    user or a barcode operator, otherwise the call raises `AccessError`.
*   Methods on a transfer or a batch return the full
    [state object](#state-object).
*   Business errors (`UserError`, `ValidationError`) are caught and returned
    as `feedback` with level `danger`. They do not raise.
*   The client sends its device id in the RPC context key `bc_device`. It is
    stored on scan events and in the scan log.

## Scan context

The client keeps a small context between calls and sends it back as `ctx`.
The server returns the updated context in `state.ctx`.

| Key | Type | Meaning |
| --- | --- | --- |
| `source_location_id` | id or `false` | Location the user is picking from |
| `dest_location_id` | id or `false` | Location the next scans go to |
| `result_package_id` | id or `false` | Package the next scans go into |
| `pending_line_ids` | list of ids | Scanned lines that have no confirmed destination yet |
| `last_line_id` | id or `false` | The line changed by the last scan |
| `pending_product_id` | id or `false` | Tracked product waiting for a lot or serial number |

Unknown keys are dropped. The context comes from the browser, so server code
must treat every id in it as untrusted input.

## Transfers: `stock.picking`

The same methods exist on `stock.picking.batch`; they run the engine on all
transfers of the batch.

| Method | Arguments | Description |
| --- | --- | --- |
| `bc_get_state` | `ctx=None` | Returns the state. Changes nothing. |
| `bc_scan` | `barcode, ctx=None, uuid=None` | Processes one scan. With a `uuid` that was already recorded, returns the state with `feedback.duplicate = true` and changes nothing. |
| `bc_set_qty` | `line_id, qty, ctx=None` | Sets the scanned quantity of one move line. Refused under the `bc_scan_only` rule unless the user is a supervisor. Quantity 0 on a scanner-created line deletes the line. |
| `bc_set_move_qty` | `move_id, qty, ctx=None` | Sets the scanned quantity of a whole move. Untracked products only. |
| `bc_add_product` | `product_id, qty=1.0, ctx=None` | Adds a product without scanning it. Subject to `bc_scan_only`. |
| `bc_put_in_pack` | `ctx=None` | Puts all scanned, unpacked lines into a new package. |
| `bc_validate` | `force=False, backorder=None, expired_ok=False` | Validates. Returns a [validation result](#validation-result), not a state. |
| `bc_print` | `what="operations"` | Returns a report action. `what` is `operations`, `delivery` or `labels`. |
| `bc_create_return` | — | `stock.picking` only. Creates the return of a done transfer. Returns `{id, name}`. |
| `bc_home_scan` | `barcode` | Model method. Resolves a code scanned on the home screen. Returns `{open, id \| location_id \| barcode \| message}`. |
| `bc_direct_print` | `kind="products"` | From `stock_barcode_print_ce`. Queues labels on the user's printer. |

### State object

```jsonc
{
  "model": "stock.picking",
  "ids": [42],
  "name": "WH/IN/00042",
  "state": "assigned",            // Odoo transfer state
  "code": "incoming",             // operation type code
  "picking_type": "My Company: Receipts",
  "partner": "Azure Interior",
  "origin": "P00012",
  "location": {"id": 4, "name": "Partners/Vendors"},
  "location_dest": {"id": 8, "name": "WH/Stock"},
  "moves": [ /* see below */ ],
  "total_demand": 12.0,
  "total_done": 5.0,
  "ctx": { /* scan context, plus *_name display values */ },
  "feedback": {"level": "success", "message": "...", "line_id": 77},
  "action": false,                // client action to run, or false
  "multi_location": true,         // user has storage locations enabled
  "use_packages": true,
  "show_lots": true,
  "is_supervisor": false,
  "can_create_product": false,
  "uid": 7,
  "presence": [{"user": "Marc Demo", "seconds": 14}],
  "channels": ["stock_barcode_ce.stock.picking.42"],
  "rules": {
    "manual_allowed": true,
    "require_source": false,
    "require_dest": false,
    "require_pack": false
  }
}
```

One entry of `moves`:

```jsonc
{
  "move_id": 101,
  "picking": "WH/IN/00042",
  "product_id": 23,
  "product": "[FURN_0001] Desk Organizer",
  "barcode": "2300001000008",
  "default_code": "FURN_0001",
  "pack_codes": [["06012345678901", 12.0]],   // packaging barcode, units
  "tracking": "none",             // "none" | "lot" | "serial"
  "uom": "Units",
  "demand": 10.0,
  "done": 5.0,
  "complete": false,
  "over": false,
  "lines": [{
    "id": 77,
    "reserved": 10.0,
    "bc_qty": 5.0,
    "lot": "",
    "location": "Partners/Vendors", "location_id": 4,
    "location_dest": "WH/Stock/A-01-1-01", "location_dest_id": 31,
    "package": "", "result_package": "",
    "dest_confirmed": true
  }]
}
```

### Feedback

| Key | Meaning |
| --- | --- |
| `level` | `success`, `info`, `warning` or `danger`. The client plays a sound per level. |
| `message` | Translated text shown to the user. |
| `line_id` | The move line changed by the scan, when there is one. |
| `need_lot` | The product is tracked; the next scan must be a lot or serial. |
| `unknown_barcode` | The code is unknown. The client offers product creation or a product request. |
| `open` | `{model, id}`: the scan was another transfer or batch; the client opens it. |
| `duplicate` | The scan's `uuid` was already recorded. |
| `package_id` | The package created by put in pack. |

### Validation result

`bc_validate` returns one of the following.

| Shape | Meaning | Next call |
| --- | --- | --- |
| `{level, message, done: true, backorders, next_actions}` | The transfer is done. | — |
| `{confirm: "nothing_scanned", allowed, message}` | Nothing was scanned. | `bc_validate(force=True)` when `allowed` |
| `{confirm: "backorder", pickings, force, message}` | Some quantities are missing. | `bc_validate(force=<force>, backorder=True \| False)` |
| `{confirm: "expired", allowed, lots, message}` | Expired lots. | `bc_validate(..., expired_ok=True)` when `allowed` |
| `{level: "danger", message}` | A rule or Odoo refused. | Fix and retry |
| `{level: "info", action}` | Odoo returned a wizard action. | The client runs the action |

`next_actions` is a list of `{label, action}` buttons contributed by
`sale_barcode_ce` (create invoice) and `purchase_barcode_ce` (create bill)
through the `_bc_next_actions()` hook.

## Home screen: `stock.picking.type`

| Method | Arguments | Description |
| --- | --- | --- |
| `bc_dashboard` | — | Model method. Operation types grouped by warehouse, with ready, waiting, late and backorder counts. |
| `bc_pickings` | `search=""` | Open transfers of one operation type. |
| `bc_new_picking` | — | Creates an empty transfer of this type. |
| `bc_batches` | `is_wave=False` | Open batches or waves. |

## Inventory counting: `stock.quant`

All are model methods. The counting context holds the location being counted.

| Method | Arguments | Description |
| --- | --- | --- |
| `bc_inv_state` | `ctx=None, feedback=None` | Returns the counting state. |
| `bc_inv_scan` | `barcode, ctx=None` | Scans a location, product, lot or package. Not idempotent: no `uuid`. |
| `bc_inv_set_qty` | `quant_id, qty, ctx=None` | Types a counted quantity. |
| `bc_inv_clear` | `quant_id, ctx=None` | Removes a count. |
| `bc_inv_zero_uncounted` | `ctx=None` | Sets uncounted quants of the location to zero. Supervisor only. |
| `bc_inv_apply` | `ctx=None` | Applies the counts. Supervisor only. |

## Scrap: `stock.scrap`

All are model methods.

| Method | Arguments | Description |
| --- | --- | --- |
| `bc_scrap_state` | `ctx=None, feedback=None` | Returns the scrap screen state, with available quantity and reasons. |
| `bc_scrap_scan` | `barcode, ctx=None` | Scans a location, product or lot. |
| `bc_scrap_confirm` | `ctx=None, qty=1.0, reason_ids=None` | Creates and validates the scrap. Supervisor only. |

## Products: `product.product` and `product.barcode.request`

| Method | Arguments | Description |
| --- | --- | --- |
| `product.product.bcq_lookup` | `barcode` | Model method. For the "Scan products" screen. Returns `{found: true, product, qty}` with name, codes, price, unit and quantity on hand, or `{found: false, barcode, gtin_like, gtin_valid}`. |
| `product.product.bcq_find_by_barcode` | `barcode` | Server-side helper. Returns `(product, qty, uom, parsed)`; handles packaging, GS1 and nomenclature rules. |
| `product.product.bcq_can_create` | — | Whether the user may create products. |
| `product.barcode.request.bcq_request` | `barcode, origin=None, note=None` | Files or increments a product creation request. |

## Command barcodes

A scanned code that starts with `O-CMD.` or `O-BTN.` is a command.

| Code | Effect |
| --- | --- |
| `O-BTN.VALIDATE`, `O-CMD.VALIDATE` | Validate |
| `O-BTN.PACK`, `O-CMD.PACK` | Put in pack |
| `O-BTN.DISCARD`, `O-CMD.DISCARD`, `O-CMD.RESET` | Clear the scan context |
| `O-BTN.PRINT-OP`, `O-CMD.PRINT` | Print the operations report |
| `O-BTN.PRINT-SLIP` | Print the delivery slip |
| `O-BTN.MAIN-MENU`, `O-CMD.MAIN-MENU` | Back to the home screen |

A printable sheet of these codes is available from an operation type record:
**Print → Barcode commands sheet**.

## Print agent endpoints

See [label-printing.md](label-printing.md#agent-protocol).
