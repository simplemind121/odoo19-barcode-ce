import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { bcCall } from "./device";

export class ScrapScreen extends Component {
    static template = "stock_barcode_ce.Scrap";
    static props = { registerScanHandler: Function, onBack: Function };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.barcodeCamera = useService("barcode_camera");
        this.state = useState({ data: null, qty: "1", reasons: [], busy: false });
        onWillStart(() => this.call("bc_scrap_state", [{}]));
        this.props.registerScanHandler((code) => this.call("bc_scrap_scan", [code, this.state.data.ctx]));
    }

    async call(method, args, kwargs = {}) {
        this.state.busy = true;
        try {
            const data = await bcCall(this.orm, "stock.scrap", method, args, kwargs);
            this.state.data = data;
            const fb = data.feedback;
            if (fb) {
                if (fb.level === "success") {
                    this.barcodeCamera.feedback.success();
                } else if (fb.level === "danger") {
                    this.barcodeCamera.feedback.error();
                } else {
                    this.barcodeCamera.feedback.warning();
                }
                if (fb.done) {
                    this.state.qty = "1";
                    this.state.reasons = [];
                }
            }
        } finally {
            this.state.busy = false;
        }
    }

    toggleReason(id) {
        const i = this.state.reasons.indexOf(id);
        if (i >= 0) {
            this.state.reasons.splice(i, 1);
        } else {
            this.state.reasons.push(id);
        }
    }

    confirm() {
        const qty = parseFloat(this.state.qty);
        if (!qty || qty <= 0) {
            return;
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("Scrap"),
            body: _t("Scrap %(qty)s x %(product)s? This removes it from stock.", {
                qty,
                product: this.state.data.product,
            }),
            confirmLabel: _t("Scrap"),
            confirm: () => this.call("bc_scrap_confirm", [this.state.data.ctx, qty, [...this.state.reasons]]),
            cancel: () => {},
        });
    }
}
