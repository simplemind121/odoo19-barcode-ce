import { registry } from "@web/core/registry";

function scan(code, trigger) {
    return {
        content: `scan ${code}`,
        trigger,
        run() {
            odoo.__WOWL_DEBUG__.root.env.services.barcode.bus.trigger("barcode_scanned", {
                barcode: code,
                target: document.body,
            });
        },
    };
}

registry.category("web_tour.tours").add("sale_barcode_ce_tour", {
    steps: () => [
        { trigger: ".o_field_widget[name=partner_id] input", run: "edit Tour Customer" },
        { trigger: ".ui-autocomplete a:contains(Tour Customer)", run: "click" },
        { trigger: ".o_bcce_handler_btn" },
        scan("6901234567892", ".o_field_widget[name=partner_id] input:value(Tour Customer)"),
        { trigger: ".o_field_widget[name=order_line] .o_data_row:contains(Tour Cola)" },
        scan("6901234567892", ".o_field_widget[name=order_line] .o_data_row:contains(Tour Cola)"),
        { trigger: ".o_field_widget[name=order_line] .o_data_row:contains(Tour Cola) td[name=product_uom_qty]:contains(2)" },
        { trigger: ".o_form_button_save", run: "click" },
        { trigger: ".o_form_saved" },
    ],
});
