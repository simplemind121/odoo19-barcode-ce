import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("barcode_camera_ce_dialog_tour", {
    steps: () => [
        {
            content: "Spy on the barcode bus",
            trigger: ".o_main_navbar",
            run() {
                const bus = odoo.__WOWL_DEBUG__.root.env.services.barcode.bus;
                window.__bcceScans = [];
                bus.addEventListener("barcode_scanned", (ev) => window.__bcceScans.push(ev.detail.barcode));
            },
        },
        {
            content: "Open the camera dialog from the navbar",
            trigger: ".o_bcce_systray button",
            run: "click",
        },
        {
            content: "Camera dialog is open (headless: no real camera)",
            trigger: ".o_bcce_dialog .o_bcce_manual",
        },
        {
            content: "Type a code manually",
            trigger: ".o_bcce_manual",
            run: "edit 6901234567892",
        },
        {
            trigger: ".o_bcce_manual_add",
            run: "click",
        },
        {
            content: "Last scan displayed",
            trigger: ".o_bcce_last strong:contains(6901234567892)",
        },
        {
            content: "Hardware scanner reads the same label right after the camera: dropped",
            trigger: ".o_bcce_last strong:contains(6901234567892)",
            run() {
                odoo.__WOWL_DEBUG__.root.env.services.barcode.bus.trigger("barcode_scanned", {
                    barcode: "6901234567892",
                    target: document.body,
                });
                if (window.__bcceScans.length !== 1) {
                    throw new Error("cross-source duplicate not dropped: " + window.__bcceScans.length);
                }
            },
        },
        {
            content: "Scanning the same item again with the camera is kept",
            trigger: ".o_bcce_manual",
            run: "edit 6901234567892",
        },
        {
            trigger: ".o_bcce_manual_add",
            run: "click",
        },
        {
            trigger: ".o_bcce_last:contains(2 scanned)",
            run() {
                if (window.__bcceScans.length !== 2) {
                    throw new Error("expected 2 bus events, got " + window.__bcceScans.length);
                }
            },
        },
        {
            trigger: ".o_bcce_done",
            run: "click",
        },
        {
            trigger: "body:not(:has(.o_bcce_dialog))",
        },
    ],
});
