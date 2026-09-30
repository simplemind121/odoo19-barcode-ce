import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { useBus, useService } from "@web/core/utils/hooks";
import { bcCall } from "./device";
import { BarcodeVideoScanner } from "@web/core/barcode/barcode_video_scanner";
import { Operation } from "./operation";
import { InventoryCount } from "./inventory";
import { ScrapScreen } from "./scrap";

const CODE_ICONS = { incoming: "fa-download", outgoing: "fa-upload", internal: "fa-exchange" };

export class StockBarcodeMain extends Component {
    static template = "stock_barcode_ce.Main";
    static components = { Operation, InventoryCount, ScrapScreen, BarcodeVideoScanner };
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.barcodeCamera = useService("barcode_camera");
        const barcode = useService("barcode");
        this.codeIcons = CODE_ICONS;
        this.state = useState({
            view: "home",
            params: {},
            dashboard: null,
            pickingList: null,
            batches: null,
            search: "",
            camera: false,
            homeMessage: "",
            manual: "",
            stack: [],
        });
        // Child screens register their scan handler here.
        this.scanHandler = null;
        useBus(barcode.bus, "barcode_scanned", (ev) => this.onScan(ev.detail.barcode));
        onWillStart(async () => {
            const params = (this.props.action && this.props.action.params) || {};
            if (params.open === "picking" || params.open === "batch") {
                this.state.view = "operation";
                this.state.params = { model: params.open === "batch" ? "stock.picking.batch" : "stock.picking", id: params.id };
            } else {
                await this.loadDashboard();
            }
        });
    }

    // ------------------------------------------------------------------
    // navigation
    // ------------------------------------------------------------------
    async go(view, params = {}, push = true) {
        if (push) {
            this.state.stack.push({ view: this.state.view, params: this.state.params });
        }
        this.scanHandler = null;
        this.state.view = view;
        this.state.params = params;
        this.state.homeMessage = "";
        if (view === "home") {
            await this.loadDashboard();
        } else if (view === "pickings") {
            await this.loadPickings();
        } else if (view === "batches") {
            this.state.batches = await bcCall(this.orm,"stock.picking.type", "bc_batches", [params.isWave || false]);
        } else if (view === "types") {
            await this.loadDashboard();
        }
    }

    async back() {
        const prev = this.state.stack.pop();
        if (prev) {
            await this.go(prev.view, prev.params, false);
        } else {
            await this.go("home", {}, false);
        }
    }

    async home() {
        this.state.stack = [];
        await this.go("home", {}, false);
    }

    async loadDashboard() {
        this.state.dashboard = await bcCall(this.orm,"stock.picking.type", "bc_dashboard", []);
    }

    async loadPickings() {
        this.state.pickingList = await bcCall(this.orm,"stock.picking.type", "bc_pickings", [[this.state.params.typeId]], {
            search: this.state.search || "",
        });
    }

    openType(type) {
        this.state.search = "";
        this.go("pickings", { typeId: type.id });
    }

    openPicking(id) {
        this.go("operation", { model: "stock.picking", id });
    }

    openBatch(id) {
        this.go("operation", { model: "stock.picking.batch", id });
    }

    async newPicking() {
        const id = await bcCall(this.orm,"stock.picking.type", "bc_new_picking", [[this.state.params.typeId]]);
        this.go("operation", { model: "stock.picking", id });
    }

    openProductLookup() {
        this.action.doAction("product_barcode_quick.action_product_scan");
    }

    // ------------------------------------------------------------------
    // scanning
    // ------------------------------------------------------------------
    toggleCamera() {
        this.state.camera = !this.state.camera;
    }

    onCameraResult(code) {
        this.barcodeCamera.dispatch(code);
    }

    onCameraError(error) {
        this.state.camera = false;
        this.notification.add(error.message || _t("Camera unavailable"), { type: "warning" });
    }

    submitManual(ev) {
        ev.preventDefault();
        const code = this.state.manual.trim();
        this.state.manual = "";
        if (code) {
            this.barcodeCamera.dispatch(code, "manual");
        }
    }

    async onScan(code) {
        if (!code) {
            return;
        }
        if (this.scanHandler) {
            return this.scanHandler(code);
        }
        if (["home", "types", "pickings", "batches"].includes(this.state.view)) {
            const res = await bcCall(this.orm,"stock.picking", "bc_home_scan", [code]);
            this.handleOpen(res);
        }
    }

    handleOpen(res) {
        if (!res || !res.open) {
            this.barcodeCamera.feedback.error();
            this.state.homeMessage = (res && res.message) || "";
            return;
        }
        this.barcodeCamera.feedback.success();
        if (res.open === "picking") {
            this.openPicking(res.id);
        } else if (res.open === "batch") {
            this.openBatch(res.id);
        } else if (res.open === "picking_type") {
            this.go("pickings", { typeId: res.id });
        } else if (res.open === "inventory") {
            this.go("inventory", { locationId: res.location_id });
        } else if (res.open === "product") {
            this.action.doAction("product_barcode_quick.action_product_scan");
        } else if (res.open === "home") {
            this.home();
        }
    }

    registerScanHandler(handler) {
        this.scanHandler = handler;
    }

    // record opened from a scan inside an operation (another transfer)
    openRecord(model, id) {
        if (model === "stock.picking.batch") {
            this.openBatch(id);
        } else {
            this.openPicking(id);
        }
    }

    typeLabel(code) {
        return { incoming: _t("Receipt"), outgoing: _t("Delivery"), internal: _t("Internal") }[code] || code;
    }
}

registry.category("actions").add("stock_barcode_ce.main", StockBarcodeMain);
