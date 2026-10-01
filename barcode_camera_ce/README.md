# Barcode Camera (CE)

Camera scanning anywhere in the Odoo backend. This is the base module of the
suite; the other modules use its scan service.

| | |
| --- | --- |
| Technical name | `barcode_camera_ce` |
| Depends on | `web`, `barcodes` |
| License | LGPL-3 |

## What it adds

*   A scan button in the navbar that opens the camera.
*   A scan dialog with continuous scanning, a camera switch, and manual input
    for when a label is unreadable.
*   Sound and vibration feedback per result level.
*   Field widgets that add a camera button to a char field
    (`camera_char_field`) and to a barcode handler field
    (`camera_handler_field`).
*   One input path for camera and scanner gun. When both read the same label
    at the same moment the code is counted once; repeated scans on one device
    are all counted.

It wraps the `BarcodeVideoScanner` component that ships in Odoo's `web`
module. No third-party scanning library is added.

## Requirements

Browsers only grant camera access on HTTPS or `localhost`.

## Code map

| Path | Content |
| --- | --- |
| `static/src/core/barcode_camera_service.js` | The scan service |
| `static/src/core/feedback.js` | Sound and vibration |
| `static/src/dialog/` | Scan dialog |
| `static/src/fields/` | Field widgets |
| `static/src/systray/` | Navbar button |

See the [repository README](../README.md) for the whole suite.
