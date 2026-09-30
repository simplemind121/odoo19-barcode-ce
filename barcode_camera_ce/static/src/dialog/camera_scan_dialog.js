import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { BarcodeVideoScanner } from "@web/core/barcode/barcode_video_scanner";
import { scanFeedback } from "../core/feedback";

export class CameraScanDialog extends Component {
    static template = "barcode_camera_ce.CameraScanDialog";
    static components = { Dialog, BarcodeVideoScanner };
    static props = {
        close: Function,
        onScan: Function,
        single: { type: Boolean, optional: true },
        title: { type: String, optional: true },
    };

    setup() {
        this.state = useState({
            error: null,
            last: null,
            count: 0,
            facingMode: "environment",
            manual: "",
        });
        this.title = this.props.title || _t("Scan with camera");
    }

    onResult(code) {
        if (!code) {
            return;
        }
        scanFeedback.success();
        this.state.last = code;
        this.state.count++;
        if (this.props.single) {
            this.props.close();
        }
        this.props.onScan(code);
    }

    onError(error) {
        this.state.error = (error && error.message) || _t("Camera unavailable");
    }

    switchCamera() {
        this.state.error = null;
        this.state.facingMode = this.state.facingMode === "environment" ? "user" : "environment";
    }

    submitManual(ev) {
        ev.preventDefault();
        const code = this.state.manual.trim();
        if (code) {
            this.state.manual = "";
            this.onResult(code);
        }
    }
}
