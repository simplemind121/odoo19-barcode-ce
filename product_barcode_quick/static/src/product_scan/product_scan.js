import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useBus, useService } from "@web/core/utils/hooks";

export class ProductScan extends Component {
    static template = "product_barcode_quick.ProductScan";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.barcodeCamera = useService("barcode_camera");
        const barcode = useService("barcode");
        this.state = useState({
            manual: "",
            busy: false,
            result: null,
            history: [],
        });
        useBus(barcode.bus, "barcode_scanned", (ev) => this.onScan(ev.detail.barcode));
    }

    formatPrice(product) {
        return `${product.currency_symbol}${product.list_price.toFixed(2)}`;
    }

    async onScan(code) {
        code = (code || "").trim();
        if (!code || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const res = await this.orm.call("product.product", "bcq_lookup", [code]);
            this.state.result = res;
            this.state.history.unshift({ code, found: res.found, name: res.found ? res.product.display_name : "" });
            this.state.history.splice(8);
            if (res.found) {
                this.barcodeCamera.feedback.success();
            } else {
                this.barcodeCamera.feedback.warning();
                await this.createProduct(code);
            }
        } finally {
            this.state.busy = false;
        }
    }

    submitManual(ev) {
        ev.preventDefault();
        const code = this.state.manual;
        this.state.manual = "";
        this.onScan(code);
    }

    openCamera() {
        this.barcodeCamera.open({ title: _t("Scan products") });
    }

    async createProduct(code) {
        await this.action.doAction("product_barcode_quick.action_product_barcode_quick", {
            additionalContext: { default_barcode: code },
            onClose: async (infos) => {
                if (infos && infos.bcq_product_id) {
                    const res = await this.orm.call("product.product", "bcq_lookup", [code || ""]);
                    if (res.found) {
                        this.state.result = res;
                        this.notification.add(_t("Product created"), { type: "success" });
                    }
                }
            },
        });
    }

    openProduct() {
        const product = this.state.result.product;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.template",
            res_id: product.tmpl_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    printLabel() {
        const product = this.state.result.product;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "product.label.layout",
            views: [[false, "form"]],
            target: "new",
            name: _t("Print labels"),
            context: {
                default_product_ids: [product.id],
                default_print_format: "th40x30",
            },
        });
    }
}

registry.category("actions").add("product_barcode_quick.product_scan", ProductScan);
