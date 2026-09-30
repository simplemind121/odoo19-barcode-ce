import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useBus, useService } from "@web/core/utils/hooks";

/**
 * Drop-in replacement of the `barcode_handler` widget that also renders a
 * camera button. Hardware scans and camera scans both update the field, which
 * triggers the model's `on_barcode_scanned` onchange.
 */
export class CameraHandlerField extends Component {
    static template = "barcode_camera_ce.CameraHandlerField";
    static props = { ...standardFieldProps, label: { type: String, optional: true } };

    setup() {
        const barcode = useService("barcode");
        this.barcodeCamera = useService("barcode_camera");
        useBus(barcode.bus, "barcode_scanned", (ev) => this.onBarcode(ev.detail.barcode));
    }

    async onBarcode(code) {
        if (this.props.readonly) {
            return;
        }
        await this.props.record.update({ [this.props.name]: code });
    }

    openCamera() {
        // Camera results go through the bus, so dedupe and feedback are shared.
        this.barcodeCamera.open();
    }
}

registry.category("fields").add("barcode_camera_handler", {
    component: CameraHandlerField,
    extractProps: ({ attrs }) => ({ label: attrs.string }),
});
