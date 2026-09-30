import { browser } from "@web/core/browser/browser";

let audioCtx = null;

function tone(frequency, duration, type = "sine", volume = 0.25) {
    try {
        const Ctx = browser.AudioContext || browser.webkitAudioContext;
        if (!Ctx) {
            return;
        }
        audioCtx = audioCtx || new Ctx();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = type;
        osc.frequency.value = frequency;
        gain.gain.value = volume;
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        const now = audioCtx.currentTime;
        osc.start(now);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);
        osc.stop(now + duration);
    } catch {
        // Audio is best effort only.
    }
}

function vibrate(pattern) {
    if (browser.navigator && "vibrate" in browser.navigator) {
        try {
            browser.navigator.vibrate(pattern);
        } catch {
            // ignore
        }
    }
}

export const scanFeedback = {
    success() {
        tone(1320, 0.09, "square", 0.15);
        vibrate(60);
    },
    warning() {
        tone(660, 0.15, "triangle", 0.2);
        vibrate([60, 60, 60]);
    },
    error() {
        tone(220, 0.35, "sawtooth", 0.2);
        vibrate([200, 80, 200]);
    },
};
