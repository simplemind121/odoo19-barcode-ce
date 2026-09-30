import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

patch(ProductScreen.prototype, {
    async _barcodeProductAction(code) {
        const product = await this._getProductByBarcode(code);
        if (!product && this.pos.hasProductCreationAccess) {
            this.sound.play("scan-error");
            this.dialog.add(ConfirmationDialog, {
                title: _t("Unknown barcode"),
                body: _t("No product has the barcode %s. Create it now and add it to the order?", code.code),
                confirmLabel: _t("Create product"),
                confirm: () => this._bcceCreateProduct(code),
                cancel: () => {},
            });
            return;
        }
        return super._barcodeProductAction(code);
    },

    async _bcceCreateProduct(code) {
        const pos = this.pos;
        await pos.action.doAction("point_of_sale.product_template_action_add_pos", {
            additionalContext: { default_barcode: code.code },
            props: {
                onSave: async (record) => {
                    const tmplId = record.evalContext.id;
                    await pos.data.read("product.template", [tmplId]);
                    await pos.data.searchRead("product.product", [["product_tmpl_id", "=", tmplId]]);
                    await pos.action.doAction({ type: "ir.actions.act_window_close" });
                    const product = pos.models["product.product"].getBy("barcode", code.base_code || code.code);
                    if (product) {
                        await pos.addLineToCurrentOrder(
                            { product_id: product, product_tmpl_id: product.product_tmpl_id },
                            { code }
                        );
                    }
                },
            },
        });
    },
});
