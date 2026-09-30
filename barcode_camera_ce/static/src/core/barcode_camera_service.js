import { registry } from "@web/core/registry";
import { isBarcodeScannerSupported } from "@web/core/barcode/barcode_video_scanner";
import { CameraScanDialog } from "../dialog/camera_scan_dialog";
import { scanFeedback } from "./feedback";

/**
 * Unifies camera scanning with the standard `barcode` service:
 *  - camera results are injected into `barcode.bus`, so every consumer that
 *    already listens to hardware scanners also receives camera scans;
 *  - an identical code coming from the *other* source within DEDUPE_MS (the
 *    camera and a hardware scanner reading the same label) is dropped. Repeated
 *    scans from the same source are kept: scanning an item twice is legitimate.
 */
export const DEDUPE_MS = 600;

export const barcodeCameraService = {
    dependencies: ["barcode", "dialog"],
    start(env, { barcode, dialog }) {
        let last = { code: null, time: 0, source: null };
        const originalTrigger = barcode.bus.trigger.bind(barcode.bus);
        barcode.bus.trigger = (name, payload) => {
            if (name === "barcode_scanned" && payload && payload.barcode) {
                const now = Date.now();
                const source = payload.source || "scanner";
                if (
                    payload.barcode === last.code &&
                    source !== last.source &&
                    now - last.time < DEDUPE_MS
                ) {
                    return;
                }
                last = { code: payload.barcode, time: now, source };
            }
            return originalTrigger(name, payload);
        };

        function dispatch(code, source = "camera") {
            barcode.bus.trigger("barcode_scanned", {
                barcode: code,
                target: document.body,
                source,
            });
        }

        return {
            isSupported: isBarcodeScannerSupported,
            feedback: scanFeedback,
            dispatch,
            /**
             * Opens a camera dialog that keeps scanning until closed.
             * @param {Object} options
             * @param {Function} [options.onScan] receives each code; defaults to
             *   dispatching into the barcode bus.
             * @param {boolean} [options.single] close after the first result
             * @param {string} [options.title]
             * @returns {Function} close function
             */
            open(options = {}) {
                return dialog.add(CameraScanDialog, {
                    title: options.title,
                    single: Boolean(options.single),
                    onScan: options.onScan || dispatch,
                });
            },
            /** Promise-based single scan. Resolves with the code, or null if cancelled. */
            scanOnce(title) {
                return new Promise((resolve) => {
                    let done = false;
                    dialog.add(
                        CameraScanDialog,
                        {
                            title,
                            single: true,
                            onScan: (code) => {
                                done = true;
                                resolve(code);
                            },
                        },
                        {
                            onClose: () => {
                                if (!done) {
                                    resolve(null);
                                }
                            },
                        }
                    );
                });
            },
        };
    },
};

registry.category("services").add("barcode_camera", barcodeCameraService);
