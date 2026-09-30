import { registry } from "@web/core/registry";

function scan(code) {
    return {
        content: `scan ${code}`,
        trigger: ".o_bcq_scan",
        run() {
            odoo.__WOWL_DEBUG__.root.env.services.barcode.bus.trigger("barcode_scanned", {
                barcode: code,
                target: document.body,
            });
        },
    };
}

registry.category("web_tour.tours").add("product_barcode_quick_tour", {
    steps: () => [
        scan("6901234567892"),
        { trigger: ".o_bcq_card .o_bcq_name:contains(Tour Cola)" },
        { trigger: ".o_bcq_price:contains(3.50)" },
        scan("6901234567809"),
        {
            content: "unknown code opens the quick create form prefilled",
            trigger: ".modal .o_field_widget[name=barcode] input:value(6901234567809)",
        },
        { trigger: ".modal .o_field_widget[name=name] input", run: "edit Tour Tea" },
        { trigger: ".modal .o_field_widget[name=list_price] input", run: "edit 5" },
        { trigger: ".modal button[name=action_create]", run: "click" },
        { trigger: ".o_bcq_card .o_bcq_name:contains(Tour Tea)" },
        { trigger: ".o_bcq_history li:contains(6901234567809)" },
        {
            content: "print label wizard opens with thermal format",
            trigger: ".o_bcq_print",
            run: "click",
        },
        { trigger: ".modal .o_field_widget[name=print_format] input:checked[data-value=th40x30], .modal .o_field_widget[name=print_format] select, .modal .o_field_widget[name=print_format]" },
        { trigger: ".modal .btn-close, .modal button.btn-secondary:contains(Discard)", run: "click" },
        { trigger: "body:not(:has(.modal))" },
    ],
});
