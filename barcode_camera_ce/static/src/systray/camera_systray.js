import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/** Navbar camera button: every camera scan is broadcast like a hardware scan. */
export class CameraSystray extends Component {
    static template = "barcode_camera_ce.CameraSystray";
    static props = {};

    setup() {
        this.barcodeCamera = useService("barcode_camera");
    }

    onClick() {
        this.barcodeCamera.open();
    }
}

registry.category("systray").add(
    "barcode_camera_ce.CameraSystray",
    {
        Component: CameraSystray,
        isDisplayed: (env) => Boolean(env.services.barcode_camera?.isSupported()),
    },
    { sequence: 45 }
);
