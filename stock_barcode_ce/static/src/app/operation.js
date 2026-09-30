import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { ConnectionLostError } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { bcCall, getDeviceId } from "./device";

function newUuid() {
    if (browser.crypto && browser.crypto.randomUUID) {
        return browser.crypto.randomUUID();
    }
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useDebounced } from "@web/core/utils/timing";

export class Operation extends Component {
    static template = "stock_barcode_ce.Operation";
    static props = {
        model: String,
        id: Number,
        registerScanHandler: Function,
        onBack: Function,
        onHome: Function,
        openRecord: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.barcodeCamera = useService("barcode_camera");
        this.state = useState({
            data: null,
            ctx: {},
            busy: false,
            editing: null, // {kind: 'move'|'line', id, value}
            menu: false,
            adding: false,
            addTerm: "",
            addResults: [],
            done: null,
            pending: [], // scans waiting for the server (offline or in flight)
            offline: false,
            rejected: [], // scans refused by the server after an offline period
        });
        this.queue = Promise.resolve();
        this.busService = useService("bus_service");
        this.queueKey = `stock_barcode_ce.queue.${this.props.model}.${this.props.id}`;
        this.deviceId = getDeviceId();
        this.processing = false;
        this.retryDelay = 2000;
        this.retryTimer = null;
        this.refreshTimer = null;
        this.channels = [];
        this.onBusUpdate = (payload) => {
            if (payload.device === this.deviceId) {
                return;
            }
            browser.clearTimeout(this.refreshTimer);
            this.refreshTimer = browser.setTimeout(() => this.refreshFromOthers(), 400);
        };
        this.onOnline = () => this.processQueue(true);
        this.loadQueue();
        this.searchProducts = useDebounced(this._searchProducts.bind(this), 250);
        onWillStart(async () => {
            try {
                await this.call("bc_get_state", []);
            } catch (e) {
                if (!(e instanceof ConnectionLostError)) {
                    throw e;
                }
                this.state.offline = true;
            }
        });
        onMounted(() => {
            this.subscribe();
            browser.addEventListener("online", this.onOnline);
            if (this.state.pending.length) {
                this.processQueue();
            }
        });
        onWillUnmount(() => {
            browser.removeEventListener("online", this.onOnline);
            browser.clearTimeout(this.retryTimer);
            browser.clearTimeout(this.refreshTimer);
            this.busService.unsubscribe("stock_barcode_ce/update", this.onBusUpdate);
            for (const channel of this.channels) {
                this.busService.deleteChannel(channel);
            }
        });
        this.props.registerScanHandler((code) => this.scan(code));
    }

    get record() {
        return [this.props.id];
    }

    /** Serialize RPCs: a fast scanner can send several codes per second. */
    enqueue(fn) {
        this.queue = this.queue.then(fn, fn);
        return this.queue;
    }

    async call(method, args, kwargs = {}) {
        this.state.busy = true;
        try {
            const data = await bcCall(this.orm,this.props.model, method, [this.record, ...args], kwargs);
            this.apply(data);
            return data;
        } finally {
            this.state.busy = false;
        }
    }

    apply(data) {
        this.state.data = data;
        this.state.ctx = data.ctx || {};
        const fb = data.feedback;
        if (fb && fb.level) {
            if (fb.level === "success") {
                this.barcodeCamera.feedback.success();
            } else if (fb.level === "warning" || fb.level === "info") {
                this.barcodeCamera.feedback.warning();
            } else {
                this.barcodeCamera.feedback.error();
            }
            if (fb.open) {
                this.props.openRecord(fb.open.model, fb.open.id);
            }
        }
        if (data.action) {
            this.handleServerAction(data.action);
        }
    }

    // ------------------------------------------------------------------
    // scan queue: every scan gets a unique id, is stored on the device and
    // sent in order. A re-sent scan is recognized by the server (no double count).
    // ------------------------------------------------------------------
    loadQueue() {
        try {
            const raw = browser.localStorage.getItem(this.queueKey);
            this.state.pending = raw ? JSON.parse(raw) : [];
        } catch {
            this.state.pending = [];
        }
    }

    saveQueue() {
        try {
            if (this.state.pending.length) {
                browser.localStorage.setItem(this.queueKey, JSON.stringify(this.state.pending));
            } else {
                browser.localStorage.removeItem(this.queueKey);
            }
        } catch {
            // storage full or disabled: the in-memory queue still works
        }
    }

    scan(code) {
        if (this.state.done) {
            return;
        }
        this.state.pending.push({ uuid: newUuid(), code, offline: this.state.offline, ts: Date.now() });
        this.saveQueue();
        if (this.state.offline) {
            this.barcodeCamera.feedback.warning();
        }
        return this.processQueue();
    }

    get busy() {
        return this.state.busy || this.state.offline || this.state.pending.length > 0;
    }

    async processQueue(fromOnline = false) {
        if (this.processing) {
            return;
        }
        this.processing = true;
        browser.clearTimeout(this.retryTimer);
        try {
            while (this.state.pending.length) {
                const item = this.state.pending[0];
                let data;
                try {
                    data = await bcCall(this.orm, this.props.model, "bc_scan", [this.record, item.code, this.state.ctx], {
                        uuid: item.uuid,
                    });
                } catch (e) {
                    if (e instanceof ConnectionLostError) {
                        this.state.offline = true;
                        this.retryTimer = browser.setTimeout(() => this.processQueue(), this.retryDelay);
                        this.retryDelay = Math.min(this.retryDelay * 2, 15000);
                        return;
                    }
                    this.state.pending.shift();
                    this.saveQueue();
                    this.state.rejected.push({ code: item.code, message: e.message || String(e) });
                    continue;
                }
                const wasOffline = item.offline || this.state.offline;
                this.state.pending.shift();
                this.saveQueue();
                this.state.offline = false;
                this.retryDelay = 2000;
                const fb = data.feedback;
                if (wasOffline && fb && fb.level === "danger") {
                    this.state.rejected.push({ code: item.code, message: fb.message, unknown: fb.unknown_barcode });
                }
                this.apply(data);
            }
        } finally {
            this.processing = false;
        }
    }

    /** Offline preview: units scanned on this device but not yet sent, per move. */
    get offlineAdds() {
        const adds = {};
        let unknown = 0;
        for (const item of this.state.pending) {
            let matched = false;
            for (const move of this.moves) {
                if (move.barcode && move.barcode === item.code) {
                    adds[move.move_id] = (adds[move.move_id] || 0) + 1;
                    matched = true;
                    break;
                }
                const pack = (move.pack_codes || []).find((p) => p[0] === item.code);
                if (pack) {
                    adds[move.move_id] = (adds[move.move_id] || 0) + pack[1];
                    matched = true;
                    break;
                }
            }
            if (!matched) {
                unknown++;
            }
        }
        return { adds, unknown };
    }

    dismissRejected() {
        this.state.rejected = [];
    }

    // ------------------------------------------------------------------
    // live updates from the other scanners of this transfer
    // ------------------------------------------------------------------
    subscribe() {
        const channels = (this.state.data && this.state.data.channels) || [];
        this.channels = channels;
        for (const channel of channels) {
            this.busService.addChannel(channel);
        }
        this.busService.subscribe("stock_barcode_ce/update", this.onBusUpdate);
    }

    async refreshFromOthers() {
        if (this.state.pending.length || this.state.editing || this.state.done || this.processing) {
            return;
        }
        const keepFeedback = this.state.data && this.state.data.feedback;
        try {
            const data = await bcCall(this.orm, this.props.model, "bc_get_state", [this.record, this.state.ctx]);
            data.feedback = keepFeedback;
            this.state.data = data;
        } catch {
            // next update or scan will refresh
        }
    }

    handleServerAction(action) {
        if (action.client === "main_menu") {
            this.props.onHome();
        } else if (action.client === "do_action") {
            this.action.doAction(action.action);
        } else if (action.level !== undefined) {
            // validation result coming from a command barcode
            this.handleValidateResult(action);
        }
    }

    // ------------------------------------------------------------------
    get moves() {
        return this.state.data ? this.state.data.moves : [];
    }

    get feedback() {
        return this.state.data && this.state.data.feedback;
    }

    get progress() {
        const d = this.state.data;
        if (!d || !d.total_demand) {
            return 0;
        }
        return Math.min(100, Math.round((d.total_done / d.total_demand) * 100));
    }

    isActive(move) {
        const last = this.state.ctx.last_line_id;
        return last && move.lines.some((l) => l.id === last);
    }

    moveClass(move) {
        const cls = [];
        if (move.over) {
            cls.push("o_bcce_over");
        } else if (move.complete) {
            cls.push("o_bcce_complete");
        } else if (move.done > 0) {
            cls.push("o_bcce_partial");
        }
        if (this.isActive(move)) {
            cls.push("o_bcce_active");
        }
        return cls.join(" ");
    }

    fmt(qty) {
        return Number.isInteger(qty) ? String(qty) : qty.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
    }

    detailLines(move) {
        return move.lines.filter(
            (l) => l.bc_qty > 0 || l.lot || l.package || this.state.data.multi_location
        );
    }

    // ------------------------------------------------------------------
    // quantity editing
    // ------------------------------------------------------------------
    startEditMove(move) {
        if (move.tracking !== "none") {
            return;
        }
        this.state.editing = { kind: "move", id: move.move_id, value: String(move.done) };
    }

    startEditLine(line) {
        this.state.editing = { kind: "line", id: line.id, value: String(line.bc_qty) };
    }

    async saveEdit(ev) {
        if (ev) {
            ev.preventDefault();
        }
        const edit = this.state.editing;
        if (!edit) {
            return;
        }
        const qty = parseFloat(edit.value);
        this.state.editing = null;
        if (Number.isNaN(qty)) {
            return;
        }
        if (edit.kind === "move") {
            await this.call("bc_set_move_qty", [edit.id, qty, this.state.ctx]);
        } else {
            await this.call("bc_set_qty", [edit.id, qty, this.state.ctx]);
        }
    }

    cancelEdit() {
        this.state.editing = null;
    }

    async increment(move) {
        await this.enqueue(() => this.call("bc_add_product", [move.product_id, 1, this.state.ctx]));
    }

    // ------------------------------------------------------------------
    // add product manually
    // ------------------------------------------------------------------
    toggleAdd() {
        this.state.adding = !this.state.adding;
        this.state.addTerm = "";
        this.state.addResults = [];
    }

    onAddInput(ev) {
        this.state.addTerm = ev.target.value;
        this.searchProducts();
    }

    async _searchProducts() {
        const term = this.state.addTerm.trim();
        if (!term) {
            this.state.addResults = [];
            return;
        }
        this.state.addResults = await this.orm.call("product.product", "name_search", [], {
            name: term,
            domain: [["type", "=", "consu"]],
            limit: 8,
        });
    }

    async addProduct(productId) {
        this.toggleAdd();
        await this.enqueue(() => this.call("bc_add_product", [productId, 1, this.state.ctx]));
    }

    // ------------------------------------------------------------------
    // actions
    // ------------------------------------------------------------------
    async putInPack() {
        this.state.menu = false;
        await this.call("bc_put_in_pack", [this.state.ctx]);
    }

    async clearContext() {
        this.state.menu = false;
        await this.call("bc_scan", ["O-BTN.discard", this.state.ctx]);
    }

    async print(what) {
        this.state.menu = false;
        const action = await bcCall(this.orm,this.props.model, "bc_print", [this.record, what]);
        await this.action.doAction(action);
    }

    openInBackend() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: this.props.model,
            res_id: this.props.id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async requestProduct(code) {
        const res = await this.orm.call("product.barcode.request", "bcq_request", [code, this.state.data.name]);
        this.state.data.feedback = { level: res.level, message: res.message };
    }

    async createReturn() {
        const res = await bcCall(this.orm, this.props.model, "bc_create_return", [this.record]);
        this.props.openRecord("stock.picking", res.id);
    }

    createProduct(code) {
        this.action.doAction("product_barcode_quick.action_product_barcode_quick", {
            additionalContext: { default_barcode: code },
            onClose: (infos) => {
                if (infos && infos.bcq_product_id) {
                    this.enqueue(() => this.scan(code));
                }
            },
        });
    }

    async validate(force = false, backorder = null, expiredOk = false) {
        if (this.state.pending.length || this.state.offline) {
            return;
        }
        this.state.busy = true;
        let res;
        try {
            const kwargs = { force };
            if (backorder !== null) {
                kwargs.backorder = backorder;
            }
            if (expiredOk) {
                kwargs.expired_ok = true;
            }
            this.lastExpiredOk = expiredOk;
            res = await bcCall(this.orm, this.props.model, "bc_validate", [this.record], kwargs);
        } finally {
            this.state.busy = false;
        }
        await this.handleValidateResult(res);
    }

    async handleValidateResult(res) {
        if (res.confirm === "nothing_scanned" && res.allowed === false) {
            this.barcodeCamera.feedback.error();
            this.state.data.feedback = { level: "danger", message: _t("Nothing has been scanned yet.") };
            return;
        }
        if (res.confirm === "expired") {
            if (!res.allowed) {
                this.barcodeCamera.feedback.error();
                this.state.data.feedback = {
                    level: "danger",
                    message: res.message + " " + _t("A supervisor must confirm this transfer."),
                };
                return;
            }
            this.dialog.add(ConfirmationDialog, {
                title: _t("Expired lots"),
                body: res.message,
                confirmLabel: _t("Validate anyway"),
                confirm: () => this.validate(false, null, true),
                cancel: () => {},
            });
            return;
        }
        if (res.confirm === "backorder") {
            const expired = this.lastExpiredOk || false;
            this.dialog.add(ConfirmationDialog, {
                title: _t("Create a backorder?"),
                body: res.message,
                confirmLabel: _t("Create backorder"),
                cancelLabel: _t("No backorder"),
                confirm: () => this.validate(res.force || false, true, expired),
                cancel: () => this.validate(res.force || false, false, expired),
                dismiss: () => {},
            });
            return;
        }
        if (res.confirm === "nothing_scanned") {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Nothing scanned"),
                body: res.message,
                confirmLabel: _t("Validate all"),
                confirm: () => this.validate(true),
                cancel: () => {},
            });
            return;
        }
        if (res.action) {
            await this.action.doAction(res.action, {
                onClose: async () => {
                    await this.call("bc_get_state", [this.state.ctx]);
                    if (this.state.data.state === "done") {
                        this.barcodeCamera.feedback.success();
                        this.state.done = { level: "success", message: _t("Validated"), backorders: [], next_actions: [] };
                    }
                },
            });
            return;
        }
        if (res.done) {
            this.barcodeCamera.feedback.success();
            this.state.done = res;
            await this.call("bc_get_state", [{}]);
            return;
        }
        this.barcodeCamera.feedback.error();
        this.state.data.feedback = { level: res.level || "danger", message: res.message };
    }

    async runNextAction(nextAction) {
        let action = nextAction.action;
        if (action.type === "ir.actions.server_call") {
            // Server method returning an action (e.g. purchase.order.action_create_invoice)
            action = await this.orm.call(action.model, action.method, [[action.res_id]]);
        }
        if (action) {
            await this.action.doAction(action);
        }
    }
}
