# Barcode Direct Label Printing (CE)

Prints product, lot, location and package labels straight to TSPL or ZPL
thermal printers, through a small agent that runs in the warehouse network.

| | |
| --- | --- |
| Technical name | `stock_barcode_print_ce` |
| Depends on | `stock_barcode_ce` |
| Python dependency | Pillow |
| License | LGPL-3 |

## What it adds

*   **Barcode → Configuration → Label printing:** print agents, label
    printers, print jobs.
*   Label rendering in TSPL and ZPL. Text is drawn as a bitmap on the server,
    so the printer needs no CJK font.
*   Print actions in the scanner menu and on the location, package and lot
    lists.
*   Two HTTP endpoints for the agent, authenticated by a token.
*   `tools/label_print_agent.py`: the agent. Standard library only, plus
    `pywin32` for USB printers on Windows.

Without a configured printer, the print actions fall back to PDF.

## Quick start

```bash
python3 tools/label_print_agent.py --url https://odoo.example.com --token <token>
```

Create the agent and the printer in Odoo first. The complete guide,
including printer targets, the agent protocol and troubleshooting, is in
[docs/label-printing.md](../docs/label-printing.md).

## Security

The agent token gives access to the label data queued for that agent. Keep
it secret and use HTTPS. See [SECURITY.md](../SECURITY.md).

## Code map

| Path | Content |
| --- | --- |
| `models/label_render.py` | TSPL and ZPL rendering, text bitmaps |
| `models/label_printer.py` | Agent, printer and job models; job cleanup cron |
| `models/stock_integration.py` | Print actions on transfers, batches, products, locations, packages, lots |
| `controllers/main.py` | `/barcode_label/agent/poll` and `/ack` |
| `tools/label_print_agent.py` | The agent |
