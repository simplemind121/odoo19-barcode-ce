# Label printing

The suite prints labels in two ways.

| Way | Module | When to use it |
| --- | --- | --- |
| PDF, printed by the browser | `product_barcode_quick`, `stock_barcode_ce` | No setup. Works with any printer the device can print to. |
| Direct, through a print agent | `stock_barcode_print_ce` | Thermal label printers (TSPL or ZPL). One tap from a phone, no print dialog. |

When no label printer is configured, the direct-print buttons fall back to
PDF.

## PDF labels

*   Products: the standard **Print Labels** wizard has three extra formats,
    thermal 40×30, 50×30 and 60×40 mm.
*   Locations and packages: select records in the list, then **Print**.
*   Command barcodes: on an operation type, **Print → Barcode commands
    sheet**.

PDF label sizes are only correct with `wkhtmltopdf 0.12.6.1 (with patched
qt)`.

## Direct printing

### How it works

```
Odoo (cloud or server)                       warehouse network
┌──────────────────────────┐                ┌───────────────────────────┐
│ barcode.label.job queue  │ ◄── HTTPS ───  │ label_print_agent.py      │
│ /barcode_label/agent/*   │    (outgoing)  │   │ raw TSPL / ZPL bytes  │
└──────────────────────────┘                │   ▼                       │
                                            │ label printer             │
                                            └───────────────────────────┘
```

The agent runs on any computer in the warehouse network. It polls Odoo and
forwards jobs to the printer. All connections are outgoing, so nothing needs
to be opened on the warehouse router, and a phone on mobile data can trigger
a print.

Text is drawn as a bitmap on the server, so the printer needs no Chinese
font. Barcodes use the printer's native barcode commands.

### Step 1: create an agent

1.  Open **Barcode → Configuration → Label printing → Print agents**.
2.  Create an agent and save it. Odoo generates a token.
3.  Copy the token. Treat it like a password.

### Step 2: run the agent

Copy `stock_barcode_print_ce/tools/label_print_agent.py` to the warehouse
computer. It needs Python 3 and nothing else, except `pywin32` for USB
printers on Windows.

```bash
python3 label_print_agent.py --url https://odoo.example.com --token <token>
```

| Option | Meaning |
| --- | --- |
| `--url` | Odoo base URL. Required. |
| `--token` | Agent token. Required. |
| `--db` | Database name. Needed only when the server hosts several databases. |
| `--interval` | Seconds between polls when idle. Default 2. |
| `--once` | Poll once and exit. |

Run it as a service so that it starts at boot. Example for systemd:

```ini
# /etc/systemd/system/label-print-agent.service
[Unit]
Description=Odoo label print agent
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 /opt/label_print_agent.py --url https://odoo.example.com --token <token>
Restart=always
RestartSec=5
User=labelagent

[Install]
WantedBy=multi-user.target
```

Make the unit file readable by root only, because it contains the token.

### Step 3: add a printer

Open **Barcode → Configuration → Label printing → Label printers** and create
a printer.

| Field | Value |
| --- | --- |
| Agent | The agent that can reach this printer |
| Target | See the table below |
| Language | TSPL (TSC, Gprinter, Xprinter, HPRT and compatible) or ZPL (Zebra) |
| Resolution | 203 or 300 dpi |
| Label width, height, gap | In millimetres |
| Darkness | 0 to 30 |
| Invert text bitmap (TSPL) | Tick it if text prints as white on a black block |

Targets:

| Target | Printer |
| --- | --- |
| `tcp://192.168.1.50:9100` | Network printer. The most common case. |
| `cups:QUEUE_NAME` | USB printer on Linux or macOS, through a raw CUPS queue |
| `win:PRINTER NAME` | USB printer on Windows. Needs `pip install pywin32`. |
| `file:/path/to/file` | Appends the bytes to a file. For tests. |

Click **Print test label**. Check that the label is black on white and that a
scanner reads the barcode.

Set each user's printer in **Settings → Users → (a user) → Default label
printer**. A user without one gets the first printer in the list.

### What can be printed

| Label | Where |
| --- | --- |
| Product labels, one per scanned unit | Scanner menu of a transfer or a batch |
| Lot and serial number labels | Scanner menu; lot list, **Action → Print labels on label printer** |
| Package labels | Scanner menu; package list, same action |
| Location labels | Location list, same action |

### Job states

| State | Meaning |
| --- | --- |
| Queued | Waiting for the agent |
| Sent to agent | The agent fetched it and has not answered yet |
| Printed | The agent sent it to the printer |
| Error | The agent could not print; the message is on the job |

A job that stays in **Sent to agent** for more than five minutes goes back to
**Queued**. If the agent crashed after printing and before answering, this
prints the label a second time. Finished jobs are deleted after 30 days.

## Agent protocol

Both endpoints accept `POST` with a JSON body and answer with JSON. They are
public routes authenticated by the token. Append `?db=<name>` on a
multi-database server.

### `POST /barcode_label/agent/poll`

Request:

```json
{"token": "<agent token>", "limit": 10}
```

Response:

```json
{"jobs": [
  {"id": 31, "name": "WH/IN/00042 (products)",
   "target": "tcp://192.168.1.50:9100",
   "data": "<base64 of the raw printer bytes>"}
]}
```

The returned jobs move to state **Sent to agent**. An invalid token answers
`403` with `{"error": "invalid token"}`.

### `POST /barcode_label/agent/ack`

Request:

```json
{"token": "<agent token>", "id": 31, "ok": true}
```

or, on failure:

```json
{"token": "<agent token>", "id": 31, "ok": false, "error": "connection refused"}
```

Response: `{"ok": true}`. A job that does not belong to the agent answers
`404`.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Text prints as a black block with white letters | Tick **Invert text bitmap (TSPL)** on the printer |
| Labels drift down the roll | Correct the label height and gap; run the printer's gap calibration |
| The agent logs HTTP 403 | The token is wrong or was regenerated; on a multi-database server pass `--db` |
| Jobs stay **Queued** | The agent is not running, or the printer belongs to another agent |
| Jobs go to **Error** with a connection message | The agent cannot reach the target; check the IP address, port 9100 and the cable |
| "No label printer" message, a PDF opens | No printer is configured, or the user has no default printer |

## Limitations

*   Real printers were not part of the automated tests. The end-to-end test
    uses a simulated network printer.
*   IoT box printing is not supported.
*   One agent serves the printers assigned to it; there is no failover
    between agents.
