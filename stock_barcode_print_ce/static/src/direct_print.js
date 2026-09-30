import { patch } from "@web/core/utils/patch";
import { Operation } from "@stock_barcode_ce/app/operation";
import { ProductScan } from "@product_barcode_quick/product_scan/product_scan";
import { bcCall } from "@stock_barcode_ce/app/device";

patch(Operation.prototype, {
    async directPrint(kind) {
        this.state.menu = false;
        const res = await bcCall(this.orm, this.props.model, "bc_direct_print", [this.record, kind]);
        if (res.fallback) {
            this.state.data.feedback = { level: "warning", message: res.message };
            return this.print(kind === "products" ? "labels" : "operations");
        }
        this.state.data.feedback = { level: res.level, message: res.message };
    },
});

patch(ProductScan.prototype, {
    async printLabel() {
        const product = this.state.result.product;
        const res = await this.orm.call("product.product", "bc_direct_print", [[product.id], 1]);
        if (res.fallback) {
            return super.printLabel();
        }
        this.notification.add(res.message, { type: res.level === "success" ? "success" : "warning" });
    },
});
