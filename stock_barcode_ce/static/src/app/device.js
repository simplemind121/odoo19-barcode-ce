import { browser } from "@web/core/browser/browser";

const KEY = "stock_barcode_ce.device";

/** Stable per-browser identifier written into the scan log. */
export function getDeviceId() {
    let id = null;
    try {
        id = browser.localStorage.getItem(KEY);
        if (!id) {
            id = Math.random().toString(36).slice(2, 10);
            browser.localStorage.setItem(KEY, id);
        }
    } catch {
        id = "nostorage";
    }
    const ua = browser.navigator.userAgent || "";
    const platform = /iPhone|iPad/.test(ua)
        ? "iOS"
        : /Android/.test(ua)
          ? "Android"
          : /Windows/.test(ua)
            ? "Windows"
            : /Mac/.test(ua)
              ? "Mac"
              : "Other";
    return `${platform}-${id}`;
}

/** orm.call with the device id in the context. */
export function bcCall(orm, model, method, args, kwargs = {}) {
    return orm.call(model, method, args, {
        ...kwargs,
        context: { ...(kwargs.context || {}), bc_device: getDeviceId() },
    });
}
