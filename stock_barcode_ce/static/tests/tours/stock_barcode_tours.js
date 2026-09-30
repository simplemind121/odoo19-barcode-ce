import { registry } from "@web/core/registry";

function scan(code, trigger = ".o_bcce_app") {
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

registry.category("web_tour.tours").add("stock_barcode_ce_receipt_tour", {
    steps: () => [
        { trigger: ".o_bcce_tile_ops" },
        scan("BCTOUR/IN/001"),
        { trigger: ".o_bcce_op_name:contains(BCTOUR/IN/001)" },
        scan("6901234567892", ".o_bcce_operation"),
        { trigger: ".o_bcce_feedback.o_bcce_fb_success" },
        scan("6901234567892", ".o_bcce_move:contains(Tour Cola) .o_bcce_done_qty:contains(1)"),
        { trigger: ".o_bcce_move.o_bcce_complete:contains(Tour Cola) .o_bcce_done_qty:contains(2)" },
        scan("WHT-A-01-1-01", ".o_bcce_operation"),
        { trigger: ".o_bcce_feedback:contains(will be put in)" },
        {
            content: "unknown code offers product creation",
            ...scan("6901234567809", ".o_bcce_operation"),
        },
        { trigger: ".o_bcce_create_product", run: "click" },
        { trigger: ".modal .o_field_widget[name=name] input", run: "edit Tour Crackers" },
        { trigger: ".modal button[name=action_create]", run: "click" },
        { trigger: ".o_bcce_move:contains(Tour Crackers) .o_bcce_done_qty:contains(1)" },
        { trigger: ".o_bcce_validate", run: "click" },
        { trigger: ".o_bcce_done:contains(Validated)" },
        { trigger: ".o_bcce_done_back", run: "click" },
        { trigger: ".o_bcce_tile_ops" },
    ],
});

registry.category("web_tour.tours").add("stock_barcode_ce_inventory_tour", {
    steps: () => [
        { trigger: ".o_bcce_tile_inv", run: "click" },
        { trigger: ".o_bcce_inventory" },
        scan("WHT-A-01-1-01", ".o_bcce_inventory"),
        { trigger: ".o_bcce_expected:contains(Tour Cola)" },
        scan("6901234567892", ".o_bcce_inventory"),
        scan("6901234567892", ".o_bcce_counted:contains(Tour Cola) .o_bcce_done_qty:contains(1)"),
        { trigger: ".o_bcce_counted:contains(Tour Cola) .o_bcce_done_qty:contains(2)" },
        { trigger: ".o_bcce_counted:contains(Tour Cola) .o_bcce_inv_qty", run: "click" },
        { trigger: ".o_bcce_counted .o_bcce_qty_input", run: "edit 7" },
        { trigger: ".o_bcce_counted form button[type=submit]", run: "click" },
        { trigger: ".o_bcce_counted:contains(Tour Cola) .o_bcce_done_qty:contains(7)" },
        { trigger: ".o_bcce_apply", run: "click" },
        { trigger: ".modal .btn-primary:contains(Apply)", run: "click" },
        { trigger: ".o_bcce_feedback:contains(applied)" },
    ],
});

registry.category("web_tour.tours").add("stock_barcode_ce_delivery_list_tour", {
    steps: () => [
        { trigger: ".o_bcce_tile_ops", run: "click" },
        { trigger: ".o_bcce_type:contains(Delivery)", run: "click" },
        { trigger: ".o_bcce_picking_row:contains(BCTOUR/OUT/001)", run: "click" },
        { trigger: ".o_bcce_move:contains(Tour Cola)" },
        { trigger: ".o_bcce_move:contains(Tour Cola) .o_bcce_plus", run: "click" },
        { trigger: ".o_bcce_move:contains(Tour Cola) .o_bcce_done_qty:contains(1)" },
        { trigger: ".o_bcce_validate", run: "click" },
        { content: "partial: backorder question", trigger: ".modal .btn-primary:contains(Create backorder)", run: "click" },
        { trigger: ".o_bcce_done:contains(Validated)" },
    ],
});

registry.category("web_tour.tours").add("stock_barcode_ce_operator_tour", {
    steps: () => [
        { content: "operator lands in the scanner", trigger: ".o_bcce_tile_ops" },
        scan("BCTOUR/IN/OP1"),
        { trigger: ".o_bcce_op_name:contains(BCTOUR/IN/OP1)" },
        {
            content: "scan-only rule: no +1 / add product buttons",
            trigger: ".o_bcce_operation:not(:has(.o_bcce_plus)):not(:has(.o_bcce_add_btn))",
        },
        scan("6901234567892", ".o_bcce_operation"),
        { trigger: ".o_bcce_move .o_bcce_done_qty:contains(1)" },
        { trigger: ".o_bcce_validate", run: "click" },
        { trigger: ".modal .btn-primary:contains(Create backorder)", run: "click" },
        { trigger: ".o_bcce_done:contains(Validated)" },
        { trigger: ".o_bcce_done_back", run: "click" },
        { trigger: ".o_bcce_home", run: "click" },
        { trigger: ".o_bcce_tile_inv", run: "click" },
        { trigger: ".o_bcce_wait_supervisor" },
    ],
});

function setOffline(offline) {
    const XHR = window.XMLHttpRequest.prototype;
    if (!XHR.__bcceOrigSend) {
        XHR.__bcceOrigSend = XHR.send;
        XHR.__bcceOrigOpen = XHR.open;
        XHR.open = function (method, url, ...rest) {
            this.__bcceUrl = url;
            return XHR.__bcceOrigOpen.call(this, method, url, ...rest);
        };
        XHR.send = function (body) {
            if (window.__bcceOffline && String(this.__bcceUrl).includes("/web/dataset/call_kw") &&
                    String(body).includes("bc_scan")) {
                setTimeout(() => this.dispatchEvent(new Event("error")), 10);
                return;
            }
            return XHR.__bcceOrigSend.call(this, body);
        };
    }
    window.__bcceOffline = offline;
}

registry.category("web_tour.tours").add("stock_barcode_ce_offline_tour", {
    steps: () => [
        { trigger: ".o_bcce_tile_ops" },
        scan("BCTOUR/IN/OFF1"),
        { trigger: ".o_bcce_op_name:contains(BCTOUR/IN/OFF1)" },
        { content: "network drops", trigger: ".o_bcce_operation", run: () => setOffline(true) },
        scan("6901234567892", ".o_bcce_operation"),
        { trigger: ".o_bcce_sync_offline .o_bcce_pending_count:contains(1)" },
        scan("6901234567892", ".o_bcce_sync_offline"),
        { trigger: ".o_bcce_sync_offline .o_bcce_pending_count:contains(2)" },
        { content: "offline preview on the line", trigger: ".o_bcce_move .o_bcce_offline_add:contains(+2)" },
        { content: "validate is blocked while scans are pending", trigger: ".o_bcce_validate:disabled" },
        {
            content: "network is back",
            trigger: ".o_bcce_sync_offline",
            run: () => {
                setOffline(false);
                window.dispatchEvent(new Event("online"));
            },
        },
        { trigger: ".o_bcce_operation:not(:has(.o_bcce_sync))" },
        { trigger: ".o_bcce_move .o_bcce_done_qty:contains(2)" },
        { trigger: ".o_bcce_validate:enabled", run: "click" },
        { trigger: ".o_bcce_done:contains(Validated)" },
    ],
});

registry.category("web_tour.tours").add("stock_barcode_ce_p1_tour", {
    steps: () => [
        { content: "supervisor sees the scrap tile", trigger: ".o_bcce_tile_scrap", run: "click" },
        scan("6901234567892", ".o_bcce_scrap"),
        { trigger: ".o_bcce_scrap_product:contains(Tour Cola)" },
        { trigger: ".o_bcce_scrap_qty", run: "edit 2" },
        { trigger: ".o_bcce_scrap_reason:contains(Damaged)", run: "click" },
        { trigger: ".o_bcce_scrap_confirm", run: "click" },
        { trigger: ".modal .btn-primary:contains(Scrap)", run: "click" },
        { trigger: ".o_bcce_feedback:contains(scrapped)" },
        { trigger: ".o_bcce_home", run: "click" },
        { trigger: ".o_bcce_tile_ops" },
        scan("BCTOUR/OUT/DONE"),
        { trigger: ".o_bcce_op_name:contains(BCTOUR/OUT/DONE)" },
        { content: "done transfer offers a return", trigger: ".o_bcce_return", run: "click" },
        { content: "the return transfer opens (a receipt back into stock)", trigger: ".o_bcce_operation .o_bcce_op_name:not(:contains(BCTOUR/OUT/DONE))" },
        scan("6901234567892", ".o_bcce_operation"),
        { trigger: ".o_bcce_move .o_bcce_done_qty:contains(1)" },
    ],
});

registry.category("web_tour.tours").add("stock_barcode_ce_request_tour", {
    steps: () => [
        { trigger: ".o_bcce_tile_ops" },
        scan("BCTOUR/IN/REQ"),
        { trigger: ".o_bcce_op_name:contains(BCTOUR/IN/REQ)" },
        scan("6901234567809", ".o_bcce_operation"),
        { content: "operator cannot create products: can ask for one", trigger: ".o_bcce_request_product", run: "click" },
        { trigger: ".o_bcce_feedback:contains(Request sent)" },
    ],
});
