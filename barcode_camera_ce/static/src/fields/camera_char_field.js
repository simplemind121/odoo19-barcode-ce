import { CharField, charField } from "@web/views/fields/char/char_field";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/** Char field with a camera button that fills the value (e.g. product barcode). */
export class CameraCharField extends CharField {
    static template = "barcode_camera_ce.CameraCharField";

    setup() {
        super.setup();
        this.barcodeCamera = useService("barcode_camera");
    }

    async scan() {
        const code = await this.barcodeCamera.scanOnce();
        if (code) {
            await this.props.record.update({ [this.props.name]: code });
        }
    }
}

registry.category("fields").add("barcode_camera_char", {
    ...charField,
    component: CameraCharField,
});
