import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { bcCall } from "./device";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

export class InventoryCount extends Component {
    static template = "stock_barcode_ce.InventoryCount";
    static props = {
        locationId: { type: [Number, Boolean], optional: true },
        registerScanHandler: Function,
        onBack: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.barcodeCamera = useService("barcode_camera");
        this.state = useState({ data: null, ctx: {}, editing: null, busy: false });
        this.queue = Promise.resolve();
        onWillStart(async () => {
            if (this.props.locationId) {
                await this.call("bc_inv_scan_location", []);
            } else {
                await this.call("bc_inv_state", [{}]);
            }
        });
        this.props.registerScanHandler((code) => {
            this.queue = this.queue.then(() => this.call("bc_inv_scan", [code, this.state.ctx]));
            return this.queue;
        });
    }

    async call(method, args) {
        this.state.busy = true;
        try {
            let data;
            if (method === "bc_inv_scan_location") {
                data = await bcCall(this.orm,"stock.quant", "bc_inv_state", [{ location_id: this.props.locationId }]);
            } else {
                data = await bcCall(this.orm,"stock.quant", method, args);
            }
            this.state.data = data;
            this.state.ctx = data.ctx;
            const fb = data.feedback;
            if (fb) {
                if (fb.level === "success") {
                    this.barcodeCamera.feedback.success();
                } else if (fb.level === "danger") {
                    this.barcodeCamera.feedback.error();
                } else {
                    this.barcodeCamera.feedback.warning();
                }
            }
            return data;
        } finally {
            this.state.busy = false;
        }
    }

    fmt(qty) {
        return Number.isInteger(qty) ? String(qty) : qty.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
    }

    startEdit(row) {
        this.state.editing = { id: row.id, value: String(row.counted) };
    }

    async saveEdit(ev) {
        ev.preventDefault();
        const edit = this.state.editing;
        this.state.editing = null;
        const qty = parseFloat(edit.value);
        if (!Number.isNaN(qty)) {
            await this.call("bc_inv_set_qty", [edit.id, qty, this.state.ctx]);
        }
    }

    async countExpected(row) {
        await this.call("bc_inv_set_qty", [row.id, row.quantity, this.state.ctx]);
    }

    async remove(row) {
        await this.call("bc_inv_clear", [row.id, this.state.ctx]);
    }

    toggleAllUsers() {
        this.call("bc_inv_state", [{ ...this.state.ctx, all_users: !this.state.ctx.all_users }]);
    }

    zeroUncounted() {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Set uncounted to zero"),
            body: _t("Every product of this location that you did not count will be set to 0 when you apply."),
            confirmLabel: _t("Set to zero"),
            confirm: () => this.call("bc_inv_zero_uncounted", [this.state.ctx]),
            cancel: () => {},
        });
    }

    apply() {
        const n = this.state.data.counted.length;
        this.dialog.add(ConfirmationDialog, {
            title: _t("Apply counts"),
            body: _t("Update the stock of %s counted line(s)?", n),
            confirmLabel: _t("Apply"),
            confirm: () => this.call("bc_inv_apply", [this.state.ctx]),
            cancel: () => {},
        });
    }

    async requestProduct(code) {
        const res = await this.orm.call("product.barcode.request", "bcq_request", [code, "Inventory count"]);
        this.state.data.feedback = { level: res.level, message: res.message };
    }

    createProduct(code) {
        this.action.doAction("product_barcode_quick.action_product_barcode_quick", {
            additionalContext: { default_barcode: code },
            onClose: (infos) => {
                if (infos && infos.bcq_product_id) {
                    this.call("bc_inv_scan", [code, this.state.ctx]);
                }
            },
        });
    }
}
