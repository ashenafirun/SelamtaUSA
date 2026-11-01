/** @odoo-module **/
/**
 * Time picked from a list instead of typed: a dropdown of times every 30 minutes
 * (06:00 ... 20:00) for a Float hours field (9.5 = 09:30).
 *
 *   <field name="pickup_ready_time" widget="selamta_time_select"/>
 *   <field name="x" widget="selamta_time_select" options="{'step': 15, 'start': 5, 'end': 22}"/>
 *
 * step is in minutes; start and end are hours. A value that is not on the list (set by
 * a carrier connection, say 17:15) is still shown and kept.
 */
import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { formatFloatTime } from "@web/views/fields/formatters";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const MINUTE = 1 / 60;

export class TimeSelectField extends Component {
    static template = "selamta_ltl.TimeSelectField";
    static props = {
        ...standardFieldProps,
        step: { type: Number, optional: true },
        start: { type: Number, optional: true },
        end: { type: Number, optional: true },
    };
    static defaultProps = {
        step: 30,
        start: 6,
        end: 20,
    };

    get value() {
        return this.props.record.data[this.props.name] || 0;
    }

    get formattedValue() {
        return formatFloatTime(this.value);
    }

    /** Minutes since midnight, so the list has no floating point drift. */
    get currentMinutes() {
        return Math.round(this.value * 60);
    }

    get options() {
        const step = Math.max(1, Math.round(this.props.step));
        const first = Math.round(this.props.start * 60);
        const last = Math.round(this.props.end * 60);
        const minutes = [];
        for (let m = first; m <= last; m += step) {
            minutes.push(m);
        }
        if (!minutes.includes(this.currentMinutes)) {
            minutes.push(this.currentMinutes);
            minutes.sort((a, b) => a - b);
        }
        return minutes.map((m) => ({
            minutes: m,
            label: formatFloatTime(m / 60),
        }));
    }

    onChange(ev) {
        const minutes = parseInt(ev.target.value, 10);
        if (Number.isNaN(minutes)) {
            return;
        }
        const hours = minutes / 60;
        if (Math.abs(hours - this.value) < MINUTE / 2) {
            return;
        }
        this.props.record.update({ [this.props.name]: hours });
    }
}

export const timeSelectField = {
    component: TimeSelectField,
    displayName: _t("Time (pick from a list)"),
    supportedOptions: [
        { label: _t("Minutes between times"), name: "step", type: "number", default: 30 },
        { label: _t("First time (hour)"), name: "start", type: "number", default: 6 },
        { label: _t("Last time (hour)"), name: "end", type: "number", default: 20 },
    ],
    supportedTypes: ["float"],
    isEmpty: () => false,
    extractProps: ({ options }) => {
        const props = {};
        for (const key of ["step", "start", "end"]) {
            if (typeof options[key] === "number") {
                props[key] = options[key];
            }
        }
        return props;
    },
};

registry.category("fields").add("selamta_time_select", timeSelectField);
