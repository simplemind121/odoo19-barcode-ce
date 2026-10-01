# Deployment guide

This guide covers installing, configuring, upgrading and rolling back the
suite on an Odoo 19 Community server. A Chinese guide with the acceptance
checklist for the warehouse team is in
[README_安装与验收.md](README_安装与验收.md).

## Before you begin

Check each item. The deployment script checks the ones marked *(checked)*.

*   Odoo **19.0 Community**.
*   **HTTPS** in front of Odoo. Browsers only give camera access on HTTPS.
    Scanner guns do not need it.
*   **`wkhtmltopdf 0.12.6.1 (with patched qt)`** in the Odoo container
    *(checked)*. Other builds print PDF labels at the wrong size. The official
    `odoo:19` image has the right one.
*   **Pillow** in the Odoo Python environment *(checked)*.
*   **`workers > 0`** *(checked)* and a reverse proxy that forwards
    **websockets**. Needed for live refresh between scanners; without it the
    scanner polls.
*   A **database backup**. The script backs up the module folders only.

    ```bash
    docker exec <postgres-container> pg_dump -U odoo -Fc <db> > before.dump
    ```

*   Read [compatibility.md](compatibility.md). Three changes to standard
    screens are on by default.

## Install with the script

`deploy-barcode-ce.sh` targets a dockerised Odoo whose addons folder is
mounted from the host. Run it on the server, from the repository root.

```bash
./deploy-barcode-ce.sh --check   # checks only; changes nothing
./deploy-barcode-ce.sh           # deploy to the staging defaults
./deploy-barcode-ce.sh --prod    # deploy to the production defaults
```

The defaults are at the top of the script. Edit them, or override them:

| Option | Meaning | Default |
| --- | --- | --- |
| `--container NAME` | Odoo container | `staging-odoo` |
| `--db NAME` | Database | `staging` |
| `--addons DIR` | Host folder mounted as extra addons | `/opt/prod-apps/odoo/addons` |
| `--prod` | Use the production container and database set in the script | — |
| `--no-backup` | Skip the backup of the existing module folders | Backup on |
| `--check` | Run the environment checks and exit | — |

What the script does: checks the environment, backs up the existing module
folders, copies the seven modules, installs or upgrades them, restarts the
container, inspects the startup log, and prints the rollback command.

It takes the modules from `odoo19_barcode_ce_*.zip` next to it or under
`dist/` when such a file exists, otherwise from the module folders of this
repository.

Deploy to staging first and run the acceptance checklist before you deploy to
production.

## Install by hand

1.  Copy the seven module folders into a directory on the Odoo
    `addons_path`.
2.  Restart Odoo, then **Apps → Update Apps List**.
3.  Install **Stock Barcode (CE)**. Install **Barcode Direct Label Printing
    (CE)** as well if you print labels directly.

Or from the command line:

```bash
odoo -d <db> -i stock_barcode_ce,stock_barcode_print_ce --stop-after-init
```

`sale_barcode_ce`, `purchase_barcode_ce` and `pos_barcode_ce` install
automatically when Sales, Purchase or Point of Sale is installed.

## Configure

### Inventory settings

**Inventory → Configuration → Settings**. Enable what you use: **Storage
Locations**, **Lots & Serial Numbers**, **Packages**. To scan GS1-128 codes,
set **Barcode Nomenclature** to **Default GS1 Nomenclature**.

### Roles

**Settings → Users**, section **Barcode scanner**.

| Role | Give it to |
| --- | --- |
| Operator | Warehouse staff who only scan. They get no Inventory backend and land on the scanner after login. |
| Supervisor | Staff who may type quantities under strict rules, validate unscanned transfers, apply counts, scrap, confirm expired lots, and read the scan log. |

Inventory users and managers are supervisors automatically. Read the trust
model in [../SECURITY.md](../SECURITY.md) before you create operators.

### Scan rules

**Inventory → Configuration → Operation Types → (a type) → Barcode rules**.
All rules are off after installation.

| Rule | Effect |
| --- | --- |
| Source location required | A product can be scanned only after its source location (deliveries, internal transfers). |
| Destination location required | Every scanned line needs a scanned destination before validation. |
| No typed quantities | Operators cannot type quantities, add products by hand or validate unscanned transfers. |
| Packing required | Every scanned line must be in a package before validation. |
| Refuse products not in the transfer | An unexpected product is refused. |
| Refuse quantities above demand | Over-scanning is refused. |

### Product barcodes

**Settings → Product Barcodes**.

*   **In-store barcode prefix:** first two digits of generated EAN-13 codes.
    Allowed: 20 and 24 to 29. Prefixes 21 to 23 are used by Odoo's default
    nomenclature for weight, discount and price codes.
*   **Check-digit validation:** on by default. Clear it to accept any
    barcode, as stock Odoo does.

### Check your barcode data

Before you enable strict rules, run **Barcode → Configuration → Barcode data
check** on a copy of the production database. It lists wrong check digits,
codes that the nomenclature would misread, duplicates, and products and
locations without a barcode.

### Label printing

See [label-printing.md](label-printing.md).

## Upgrade

Use the deployment script, or by hand:

```bash
odoo -d <db> \
     -u barcode_camera_ce,product_barcode_quick,stock_barcode_ce,stock_barcode_print_ce,sale_barcode_ce,purchase_barcode_ce,pos_barcode_ce \
     --stop-after-init
```

*   Ask operators to finish or pause their transfers first. The scanner is
    unavailable during the upgrade.
*   **From 1.x to 2.x:** scanned quantities of open transfers are converted
    to scan events of kind "migrated". Add `-i stock_barcode_print_ce` if you
    want direct printing; it is a new module in 2.1.

## Roll back

The script prints the exact command after a deployment. In general:

1.  Restore the module folders from the backup that the script made under the
    backup directory.
2.  Restart the Odoo container.
3.  If the newer version changed the data model, restore the database dump
    that you took before deploying. Downgrading modules on a migrated
    database is not supported.

## Uninstall

Uninstall the modules from **Apps**. Uninstalling `stock_barcode_ce` deletes
the scan events and the scan log. Export them first if you need the audit
trail. Stock moves that were validated through the scanner are ordinary Odoo
records and are not affected.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| The camera button does nothing, or the browser reports no camera | The page is not on HTTPS, or camera permission was denied | Serve Odoo over HTTPS; allow the camera for the site |
| PDF labels are too large or too small | Wrong wkhtmltopdf build | Install `0.12.6.1 (with patched qt)` |
| Chinese text on PDF labels is garbled | No CJK font in the container | Install `fonts-noto-cjk` |
| Other phones do not refresh | `workers = 0`, or the proxy does not forward websockets | Set workers; proxy `/websocket` |
| "You are not allowed to use the barcode scanner" | The user has neither the operator role nor Inventory rights | Grant a role |
| Saving a product fails with a check-digit error | Check-digit validation is on | Correct the code, or clear the setting |
| The print agent gets HTTP 403 | Wrong or regenerated token, or the wrong database | Copy the token again; pass `--db` |
