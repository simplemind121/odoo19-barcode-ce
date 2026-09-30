import * as ProductScreen from "@point_of_sale/../tests/pos/tours/utils/product_screen_util";
import * as Chrome from "@point_of_sale/../tests/pos/tours/utils/chrome_util";
import * as Dialog from "@point_of_sale/../tests/generic_helpers/dialog_util";
import { scan_barcode } from "@point_of_sale/../tests/generic_helpers/utils";
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("pos_barcode_ce_create_unknown", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            scan_barcode("6901234567809"),
            Dialog.confirm("Create product"),
            {
                content: "product form prefilled with the barcode",
                trigger: ".modal .o_field_widget[name=barcode] input:value(6901234567809)",
            },
            {
                trigger: ".modal .o_field_widget[name=name] textarea, .modal .o_field_widget[name=name] input",
                run: "edit POS Scanned Snack",
            },
            {
                trigger: ".modal .o_field_widget[name=list_price] input",
                run: "edit 4.2",
            },
            {
                trigger: ".modal .o_form_button_save, .modal .modal-footer .btn-primary",
                run: "click",
            },
            ProductScreen.selectedOrderlineHas("POS Scanned Snack", 1),
            scan_barcode("6901234567809"),
            ProductScreen.selectedOrderlineHas("POS Scanned Snack", 2),
            Chrome.endTour(),
        ].flat(),
});
