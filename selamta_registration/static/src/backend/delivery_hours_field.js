/** @odoo-module **/
// "Delivery days and hours" on the contact form: day buttons and From / Until lists
// instead of typing. Writes the same text the website form writes
// ("Mon–Fri, 8:00 AM – 4:30 PM"), so the green delivery bar, the website and older
// typed values all keep working. Text that doesn't fit the buttons (for example
// hours copied from an old tag) is shown as text until someone picks new hours.

import { Component, onWillUpdateProps, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const FIRST_TIME = 4 * 60; // 4:00 AM
const LAST_TIME = 23 * 60 + 30; // 11:30 PM
const TIME_STEP = 30;
const DASH = "–";
const TIME_RE = "(\\d{1,2}:\\d{2}\\s*[AP]\\.?M\\.?)";

export function formatTime(minutes) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    const suffix = h < 12 ? "AM" : "PM";
    const h12 = h % 12 === 0 ? 12 : h % 12;
    return `${h12}:${String(m).padStart(2, "0")} ${suffix}`;
}

export function formatDays(days) {
    // sorted indexes 0 (Mon) .. 6 (Sun) -> "Mon–Fri", "Tue, Thu", "Mon, Wed–Sat"
    const parts = [];
    let i = 0;
    while (i < days.length) {
        let j = i;
        while (j + 1 < days.length && days[j + 1] === days[j] + 1) {
            j++;
        }
        if (j - i >= 2) {
            parts.push(`${DAY_NAMES[days[i]]}${DASH}${DAY_NAMES[days[j]]}`);
        } else {
            for (let k = i; k <= j; k++) {
                parts.push(DAY_NAMES[days[k]]);
            }
        }
        i = j + 1;
    }
    return parts.join(", ");
}

export function composeHours(days, from, to) {
    let timeText = "";
    if (from !== null && to !== null) {
        timeText = `${formatTime(from)} ${DASH} ${formatTime(to)}`;
    } else if (from !== null) {
        timeText = `from ${formatTime(from)}`;
    } else if (to !== null) {
        timeText = `until ${formatTime(to)}`;
    }
    return [formatDays(days), timeText].filter(Boolean).join(", ");
}

function parseTime(text) {
    const m = /^(\d{1,2}):(\d{2})\s*([AP])\.?M\.?$/i.exec(text.trim());
    if (!m) {
        return null;
    }
    const hour = parseInt(m[1], 10);
    const minute = parseInt(m[2], 10);
    if (hour < 1 || hour > 12 || minute > 59) {
        return null;
    }
    return (hour % 12) * 60 + (m[3].toUpperCase() === "P" ? 12 * 60 : 0) + minute;
}

function isSelectable(t) {
    return t === null || (t >= FIRST_TIME && t <= LAST_TIME && (t - FIRST_TIME) % TIME_STEP === 0);
}

/**
 * "Mon, Wed–Fri, 9:00 AM – 3:00 PM" -> {days: [0, 2, 3, 4], from: 540, to: 900}.
 * Empty text -> nothing picked. Text the buttons can't show -> null.
 */
export function parseHours(value) {
    let rest = (value || "").trim();
    if (!rest) {
        return { days: [], from: null, to: null };
    }
    let from = null;
    let to = null;
    let m = new RegExp(`(?:^|,\\s*)${TIME_RE}\\s*[-${DASH}]\\s*${TIME_RE}$`, "i").exec(rest);
    if (m) {
        from = parseTime(m[1]);
        to = parseTime(m[2]);
        if (from === null || to === null) {
            return null;
        }
        rest = rest.slice(0, m.index);
    } else if ((m = new RegExp(`(?:^|,\\s*)from\\s+${TIME_RE}$`, "i").exec(rest))) {
        from = parseTime(m[1]);
        if (from === null) {
            return null;
        }
        rest = rest.slice(0, m.index);
    } else if ((m = new RegExp(`(?:^|,\\s*)until\\s+${TIME_RE}$`, "i").exec(rest))) {
        to = parseTime(m[1]);
        if (to === null) {
            return null;
        }
        rest = rest.slice(0, m.index);
    }
    const days = [];
    if (rest.trim()) {
        const lower = DAY_NAMES.map((d) => d.toLowerCase());
        for (const part of rest.split(",")) {
            const r = new RegExp(`^([a-z]{3})(?:\\s*[-${DASH}]\\s*([a-z]{3}))?$`, "i").exec(part.trim());
            if (!r) {
                return null;
            }
            const a = lower.indexOf(r[1].toLowerCase());
            const b = r[2] ? lower.indexOf(r[2].toLowerCase()) : a;
            if (a < 0 || b < a) {
                return null;
            }
            for (let d = a; d <= b; d++) {
                if (!days.includes(d)) {
                    days.push(d);
                }
            }
        }
    }
    if (!isSelectable(from) || !isSelectable(to)) {
        return null;
    }
    days.sort((x, y) => x - y);
    return { days, from, to };
}

export class DeliveryHoursField extends Component {
    static template = "selamta_registration.DeliveryHoursField";
    static props = { ...standardFieldProps };

    setup() {
        this.dayNames = DAY_NAMES;
        this.times = [];
        for (let t = FIRST_TIME; t <= LAST_TIME; t += TIME_STEP) {
            this.times.push({ value: t, label: formatTime(t) });
        }
        this.state = useState({ days: [], from: null, to: null, textMode: false, oldText: "" });
        this.lastValue = null;
        this.load(this.value);
        onWillUpdateProps((nextProps) => {
            const next = nextProps.record.data[nextProps.name] || "";
            if (next !== this.lastValue) {
                this.load(next);
            }
        });
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }

    get endBeforeStart() {
        const { from, to } = this.state;
        return from !== null && to !== null && to <= from;
    }

    load(value) {
        this.lastValue = value;
        const parsed = parseHours(value);
        if (parsed) {
            Object.assign(this.state, parsed, { textMode: false, oldText: "" });
        } else {
            Object.assign(this.state, { days: [], from: null, to: null, textMode: true, oldText: value });
        }
    }

    save(value) {
        this.lastValue = value;
        this.props.record.update({ [this.props.name]: value || false });
    }

    writePicked() {
        const { days, from, to } = this.state;
        const value = composeHours(days, from, to);
        if (!value && this.state.oldText) {
            return; // nothing picked yet: keep the old text
        }
        this.state.oldText = "";
        this.save(value);
    }

    toggleDay(index) {
        const days = this.state.days.filter((d) => d !== index);
        if (days.length === this.state.days.length) {
            days.push(index);
            days.sort((x, y) => x - y);
        }
        this.state.days = days;
        this.writePicked();
    }

    onTimeChange(which, ev) {
        this.state[which] = ev.target.value === "" ? null : parseInt(ev.target.value, 10);
        this.writePicked();
    }

    onTextChange(ev) {
        const value = ev.target.value.trim();
        this.state.oldText = value;
        this.save(value);
    }

    pickInstead() {
        Object.assign(this.state, { textMode: false, days: [], from: null, to: null, oldText: this.value });
    }

    typeInstead() {
        Object.assign(this.state, { textMode: true, oldText: this.value });
    }
}

export const deliveryHoursField = {
    component: DeliveryHoursField,
    displayName: _t("Delivery days and hours"),
    supportedTypes: ["char"],
};

registry.category("fields").add("selamta_delivery_hours", deliveryHoursField);
