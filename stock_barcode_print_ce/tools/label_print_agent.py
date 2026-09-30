#!/usr/bin/env python3
"""Label print agent for stock_barcode_print_ce.

Runs on any computer of the warehouse network (Linux, macOS, Windows, Raspberry Pi).
It polls Odoo over HTTPS for label jobs and sends the raw TSPL/ZPL bytes to the printer.
Only outgoing connections are used: nothing to open on the warehouse router.

    python3 label_print_agent.py --url https://odoo.example.com --token XXXXXXXX

Printer targets (configured in Odoo on each printer):
    tcp://192.168.1.50:9100   network label printer (most common)
    cups:QUEUE_NAME           USB printer on Linux/macOS, raw queue (lp -o raw)
    win:PRINTER NAME          USB printer on Windows (needs: pip install pywin32)
    file:/path/to/file        append to a file (tests)

Standard library only (plus pywin32 for win: targets).
"""
import argparse
import base64
import json
import logging
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

_logger = logging.getLogger("label_print_agent")


def post(url, payload, timeout=30):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URL given by the operator
        return json.loads(resp.read().decode() or "{}")


def send_to_printer(target, data):
    if target.startswith("tcp://"):
        host, _sep, port = target[6:].rpartition(":")
        with socket.create_connection((host, int(port or 9100)), timeout=15) as sock:
            sock.sendall(data)
        return
    if target.startswith("cups:"):
        subprocess.run(["lp", "-d", target[5:], "-o", "raw"], input=data, check=True, timeout=30)  # noqa: S603,S607
        return
    if target.startswith("win:"):
        import win32print  # pylint: disable=import-error

        handle = win32print.OpenPrinter(target[4:])
        try:
            win32print.StartDocPrinter(handle, 1, ("Odoo label", None, "RAW"))
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, data)
            win32print.EndPagePrinter(handle)
            win32print.EndDocPrinter(handle)
        finally:
            win32print.ClosePrinter(handle)
        return
    if target.startswith("file:"):
        with open(target[5:], "ab") as fh:
            fh.write(data)
        return
    raise ValueError("unsupported printer target %r" % target)


def run_once(base, token, db=None):
    """Fetch and print pending jobs. Returns the number of jobs handled."""
    suffix = "?db=%s" % urllib.parse.quote(db) if db else ""
    res = post(base + "/barcode_label/agent/poll" + suffix, {"token": token})
    jobs = res.get("jobs") or []
    for job in jobs:
        try:
            send_to_printer(job["target"], base64.b64decode(job["data"]))
            post(base + "/barcode_label/agent/ack" + suffix, {"token": token, "id": job["id"], "ok": True})
            _logger.info("printed job %s (%s)", job["id"], job.get("name"))
        except Exception as e:  # noqa: BLE001 - report every failure to Odoo
            _logger.warning("job %s failed: %s", job["id"], e)
            post(base + "/barcode_label/agent/ack" + suffix, {"token": token, "id": job["id"], "ok": False, "error": str(e)})
    return len(jobs)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="Odoo base URL, e.g. https://odoo.example.com")
    parser.add_argument("--token", required=True, help="Agent token (Barcode > Configuration > Print agents)")
    parser.add_argument("--db", help="Database name, only needed when the server hosts several databases")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between polls when idle")
    parser.add_argument("--once", action="store_true", help="Poll once and exit (tests / cron)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    base = args.url.rstrip("/")
    if args.once:
        return 0 if run_once(base, args.token, args.db) >= 0 else 1
    delay = args.interval
    while True:
        try:
            handled = run_once(base, args.token, args.db)
            delay = 0.2 if handled else args.interval
        except urllib.error.HTTPError as e:
            if e.code == 403:
                _logger.error("token refused by Odoo; check the agent token")
            else:
                _logger.warning("Odoo returned %s", e.code)
            delay = min(max(delay * 2, args.interval), 60)
        except (urllib.error.URLError, OSError) as e:
            _logger.warning("cannot reach Odoo: %s", e)
            delay = min(max(delay * 2, args.interval), 60)
        time.sleep(delay)


if __name__ == "__main__":
    sys.exit(main())
