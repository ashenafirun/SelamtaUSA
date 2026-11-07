/** @odoo-module **/
/*
 * Selamta wholesale registration form helpers:
 *  - ZIP code -> city and state (built-in U.S. ZIP list on the server)
 *  - street address suggestions while typing (Google Places, when a key is set)
 *  - EIN shown as 12-3456789, U.S. phones as (404) 555-1234
 *  - delivery days and hours picked with day buttons and time lists
 *    (they fill the plain "selamta_receiving_hours" text field)
 *
 * Runs only on the public page (never inside the website editor).
 */
import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";
import { debounce } from "@web/core/utils/timing";

function isUserEvent(ev) {
    // jQuery-wrapped events keep the browser event in originalEvent
    const native = ev.originalEvent || ev;
    return !!native.isTrusted;
}

// Selamta delivers Monday to Friday only, so no weekend buttons.
const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri"];
// Selamta's delivery window: 8:00 AM to 6:00 PM
const FIRST_TIME = 8 * 60; // 8:00 AM
const LAST_TIME = 18 * 60; // 6:00 PM
const TIME_STEP = 30;

function formatTime(minutes) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    const suffix = h < 12 ? "AM" : "PM";
    const h12 = h % 12 === 0 ? 12 : h % 12;
    return `${h12}:${String(m).padStart(2, "0")} ${suffix}`;
}

function formatDays(days) {
    // days: sorted indexes 0 (Mon) .. 4 (Fri) -> "Mon–Fri", "Tue, Thu", "Mon, Wed–Fri"
    const parts = [];
    let i = 0;
    while (i < days.length) {
        let j = i;
        while (j + 1 < days.length && days[j + 1] === days[j] + 1) {
            j++;
        }
        if (j - i >= 2) {
            parts.push(`${DAY_NAMES[days[i]]}\u2013${DAY_NAMES[days[j]]}`);
        } else {
            for (let k = i; k <= j; k++) {
                parts.push(DAY_NAMES[days[k]]);
            }
        }
        i = j + 1;
    }
    return parts.join(", ");
}

function newSessionToken() {
    if (window.crypto && window.crypto.randomUUID) {
        return window.crypto.randomUUID();
    }
    return "s" + Date.now().toString(36) + Math.random().toString(36).slice(2);
}

publicWidget.registry.SelamtaRegistrationForm = publicWidget.Widget.extend({
    selector: ".sel-reg-form form",
    events: {
        "input input[name='zip']": "_onZipInput",
        "input input[name='street']": "_onStreetInput",
        "keydown input[name='street']": "_onStreetKeydown",
        "blur input[name='street']": "_onStreetBlur",
        "input input[name='vat']": "_onEinInput",
        "blur input[type='tel']": "_onPhoneBlur",
        "input input[name='city']": "_onCityInput",
    },

    start() {
        this.zipEl = this.el.querySelector("input[name='zip']");
        this.cityEl = this.el.querySelector("input[name='city']");
        this.stateEl = this.el.querySelector("select[name='state_id']");
        this.streetEl = this.el.querySelector("input[name='street']");
        this.street2El = this.el.querySelector("input[name='street2']");
        this.lastZip = null;
        this.autoCity = null; // city value we filled in ourselves
        this.suggestions = [];
        this.activeIndex = -1;
        this.addressEnabled = false;
        this.sessionToken = null;
        this.requestSeq = 0;
        this._fetchSuggestionsDebounced = debounce(this._fetchSuggestions.bind(this), 250);

        if (this.streetEl) {
            const wrap = document.createElement("div");
            wrap.className = "sel-reg-street-wrap";
            this.streetEl.parentNode.insertBefore(wrap, this.streetEl);
            wrap.appendChild(this.streetEl);
            this.suggestEl = document.createElement("div");
            this.suggestEl.className = "sel-reg-suggest d-none";
            this.suggestEl.setAttribute("role", "listbox");
            this.suggestEl.id = "sel_reg_street_suggestions";
            wrap.appendChild(this.suggestEl);
            this.suggestEl.addEventListener("mousedown", (ev) => {
                // keep focus in the street field while clicking a suggestion
                ev.preventDefault();
                const item = ev.target.closest("[data-index]");
                if (item) {
                    this._selectSuggestion(parseInt(item.dataset.index, 10));
                }
            });
            this.streetEl.setAttribute("aria-autocomplete", "list");
            this.streetEl.setAttribute("aria-controls", this.suggestEl.id);
        }
        if (this.zipEl) {
            this.zipHintEl = document.createElement("div");
            this.zipHintEl.className = "small form-text sel-reg-zip-hint";
            this.zipHintEl.setAttribute("aria-live", "polite");
            this.zipEl.insertAdjacentElement("afterend", this.zipHintEl);
        }
        this._setupHoursPicker();

        rpc("/selamta/registration/config", {})
            .then((config) => {
                this.addressEnabled = !!(config && config.address_enabled);
                if (this.addressEnabled && this.streetEl) {
                    // Our suggestions replace the browser's own address dropdown here.
                    this.streetEl.setAttribute("autocomplete", "off");
                }
            })
            .catch(() => {});
        return this._super(...arguments);
    },

    destroy() {
        // Put the page back exactly as stored, so the website editor never saves
        // anything this script added.
        if (this.suggestEl) {
            this.suggestEl.remove();
        }
        if (this.streetEl) {
            const wrap = this.streetEl.closest(".sel-reg-street-wrap");
            if (wrap) {
                wrap.parentNode.insertBefore(this.streetEl, wrap);
                wrap.remove();
            }
            this.streetEl.setAttribute("autocomplete", "address-line1");
            this.streetEl.removeAttribute("aria-autocomplete");
            this.streetEl.removeAttribute("aria-controls");
            this.streetEl.removeAttribute("aria-expanded");
        }
        if (this.zipHintEl) {
            this.zipHintEl.remove();
        }
        if (this.hoursForm && this._onHoursFormReset) {
            this.hoursForm.removeEventListener("reset", this._onHoursFormReset);
        }
        if (this.hoursPickerEl) {
            this.hoursPickerEl.remove();
            this.hoursInput.classList.remove("d-none");
            if (this.hoursLabelEl && this.hoursLabelFor) {
                this.hoursLabelEl.setAttribute("for", this.hoursLabelFor);
            }
        }
        this._super(...arguments);
    },

    //--------------------------------------------------------------------------
    // Delivery days and hours
    //--------------------------------------------------------------------------

    _setupHoursPicker() {
        const input = this.el.querySelector("input[name='selamta_receiving_hours']");
        if (!input) {
            return;
        }
        this.hoursInput = input;
        const picker = document.createElement("div");
        picker.className = "sel-reg-hours-picker";

        // Days: "Any weekday" (already chosen) or "Only some weekdays", which opens
        // tick boxes with every weekday ticked. These controls belong to no form
        // (form attribute), so the website form never sends them; they only fill the
        // hidden text field.
        const NO_FORM = "sel_reg_no_form";
        const sectionLabel = (text) => {
            const el = document.createElement("div");
            el.className = "sel-reg-hours-q";
            el.textContent = text;
            return el;
        };
        picker.appendChild(sectionLabel("Which days?"));
        const modesEl = document.createElement("div");
        modesEl.className = "sel-reg-day-modes";
        modesEl.setAttribute("role", "radiogroup");
        modesEl.setAttribute("aria-label", "Which days?");
        const makeMode = (id, title, sub, checked) => {
            const label = document.createElement("label");
            label.className = "sel-reg-choice";
            label.htmlFor = id;
            const radio = document.createElement("input");
            radio.type = "radio";
            radio.className = "form-check-input";
            radio.name = "sel_reg_day_mode";
            radio.id = id;
            radio.checked = checked;
            radio.setAttribute("form", NO_FORM);
            radio.addEventListener("change", () => this._onDayModeChange());
            const text = document.createElement("span");
            text.className = "sel-reg-choice-text";
            const strong = document.createElement("strong");
            strong.textContent = title;
            text.appendChild(strong);
            if (sub) {
                const small = document.createElement("span");
                small.className = "sel-reg-choice-sub";
                small.textContent = sub;
                text.appendChild(small);
            }
            label.append(radio, text);
            modesEl.appendChild(label);
            return radio;
        };
        this.anyDayRadio = makeMode("sel_reg_days_any", "Any weekday", "Monday to Friday", true);
        this.someDaysRadio = makeMode("sel_reg_days_some", "Only some weekdays", "", false);
        picker.appendChild(modesEl);

        const someEl = document.createElement("div");
        someEl.className = "sel-reg-some-days d-none";
        const someHint = document.createElement("div");
        someHint.className = "small sel-reg-some-hint";
        someHint.textContent = "Untick the days you are closed.";
        const boxesEl = document.createElement("div");
        boxesEl.className = "sel-reg-days";
        boxesEl.setAttribute("role", "group");
        boxesEl.setAttribute("aria-label", "Delivery days");
        this.dayBoxes = DAY_NAMES.map((name, index) => {
            const label = document.createElement("label");
            label.className = "sel-reg-daybox";
            const box = document.createElement("input");
            box.type = "checkbox";
            box.className = "form-check-input";
            box.checked = true;
            box.dataset.day = index;
            box.setAttribute("form", NO_FORM);
            box.addEventListener("change", () => this._composeHours());
            const text = document.createElement("span");
            text.textContent = name;
            label.append(box, text);
            boxesEl.appendChild(label);
            return box;
        });
        this.daysWarningEl = document.createElement("div");
        this.daysWarningEl.className = "small sel-reg-hours-warning d-none";
        this.daysWarningEl.setAttribute("aria-live", "polite");
        this.daysWarningEl.textContent = "Tick at least one day.";
        someEl.append(someHint, boxesEl, this.daysWarningEl);
        picker.appendChild(someEl);
        this.someDaysEl = someEl;

        picker.appendChild(sectionLabel("What time?"));
        const timesEl = document.createElement("div");
        timesEl.className = "sel-reg-times";
        const makeSelect = (id, labelText, emptyText) => {
            const wrap = document.createElement("div");
            wrap.className = "sel-reg-time";
            const label = document.createElement("label");
            label.className = "small";
            label.htmlFor = id;
            label.textContent = labelText;
            const select = document.createElement("select");
            select.className = "form-select";
            select.id = id;
            const empty = document.createElement("option");
            empty.value = "";
            empty.textContent = emptyText;
            select.appendChild(empty);
            for (let t = FIRST_TIME; t <= LAST_TIME; t += TIME_STEP) {
                const option = document.createElement("option");
                option.value = String(t);
                option.textContent = formatTime(t);
                select.appendChild(option);
            }
            select.addEventListener("change", () => this._composeHours());
            wrap.append(label, select);
            timesEl.appendChild(wrap);
            return select;
        };
        this.fromEl = makeSelect("sel_reg_hours_from", "From", "Select time");
        this.toEl = makeSelect("sel_reg_hours_to", "Until", "Select time");
        picker.appendChild(timesEl);

        this.hoursWarningEl = document.createElement("div");
        this.hoursWarningEl.className = "small sel-reg-hours-warning d-none";
        this.hoursWarningEl.setAttribute("aria-live", "polite");
        this.hoursWarningEl.textContent = "The end time is earlier than the start time.";
        picker.appendChild(this.hoursWarningEl);

        input.classList.add("d-none");
        // after the "We deliver Monday to Friday..." hint, so the instructions come first
        const hint = input.parentElement.querySelector(".s_website_form_field_description");
        (hint || input).insertAdjacentElement("afterend", picker);
        this.hoursPickerEl = picker;
        // The field label pointed at the (now hidden) text box.
        this.hoursLabelEl = this.el.querySelector(`label[for='${input.id}']`);
        if (this.hoursLabelEl) {
            this.hoursLabelFor = input.id;
            this.hoursLabelEl.removeAttribute("for");
        }
        // "Any weekday" starts chosen, so the field already says "Mon–Fri". Odoo's
        // form clears its fields when it starts (and after sending), so fill it
        // again after every reset.
        this._composeHours();
        this.hoursForm = input.form;
        if (this.hoursForm) {
            this._onHoursFormReset = () => setTimeout(() => {
                if (this.hoursPickerEl && this.hoursPickerEl.isConnected) {
                    this._composeHours();
                }
            }, 0);
            this.hoursForm.addEventListener("reset", this._onHoursFormReset);
        }
    },

    _onDayModeChange() {
        const some = this.someDaysRadio.checked;
        this.someDaysEl.classList.toggle("d-none", !some);
        if (some && !this.dayBoxes.some((b) => b.checked)) {
            this.dayBoxes.forEach((b) => (b.checked = true));
        }
        this._composeHours();
    },

    _composeHours() {
        const days = this.anyDayRadio.checked
            ? DAY_NAMES.map((name, index) => index)
            : this.dayBoxes.filter((b) => b.checked).map((b) => parseInt(b.dataset.day, 10));
        this.daysWarningEl.classList.toggle("d-none", days.length > 0);
        const from = this.fromEl.value ? parseInt(this.fromEl.value, 10) : null;
        const to = this.toEl.value ? parseInt(this.toEl.value, 10) : null;
        let timeText = "";
        if (from !== null && to !== null) {
            timeText = `${formatTime(from)} \u2013 ${formatTime(to)}`;
        } else if (from !== null) {
            timeText = `from ${formatTime(from)}`;
        } else if (to !== null) {
            timeText = `until ${formatTime(to)}`;
        }
        const value = [formatDays(days), timeText].filter(Boolean).join(", ");
        this.hoursInput.value = value;
        this.hoursInput.dispatchEvent(new Event("input", { bubbles: true }));
        this.hoursWarningEl.classList.toggle("d-none", !(from !== null && to !== null && to <= from));
    },

    //--------------------------------------------------------------------------
    // Helpers
    //--------------------------------------------------------------------------

    _setValue(el, value) {
        if (!el || value === undefined || value === null) {
            return;
        }
        el.value = value;
        // let Odoo's form widget refresh its validation / visibility state
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
    },

    _setState(stateId) {
        if (!this.stateEl || !stateId) {
            return;
        }
        const option = this.stateEl.querySelector(`option[value='${parseInt(stateId, 10)}']`);
        if (option) {
            this._setValue(this.stateEl, String(parseInt(stateId, 10)));
        }
    },

    _fillCity(city) {
        if (!this.cityEl || !city) {
            return;
        }
        const current = this.cityEl.value.trim();
        if (!current || current === this.autoCity) {
            this._setValue(this.cityEl, city);
            this.autoCity = city;
        }
    },

    //--------------------------------------------------------------------------
    // ZIP -> city / state
    //--------------------------------------------------------------------------

    async _onZipInput() {
        const digits = this.zipEl.value.replace(/\D/g, "");
        if (digits.length < 5) {
            this.zipHintEl.textContent = "";
            this.lastZip = null;
            return;
        }
        const zip5 = digits.slice(0, 5);
        if (zip5 === this.lastZip) {
            return;
        }
        this.lastZip = zip5;
        let result;
        try {
            result = await rpc("/selamta/registration/zip", { zip_code: zip5 });
        } catch {
            return;
        }
        if (this.lastZip !== zip5) {
            return; // the user kept typing
        }
        if (!result || !result.city) {
            this.zipHintEl.textContent = "";
            return;
        }
        this._fillCity(result.city);
        this._setState(result.state_id);
        this.zipHintEl.textContent = `✓ ${result.city}, ${result.state_code}`;
    },

    _onCityInput(ev) {
        if (!isUserEvent(ev)) {
            return;
        }
        // The user typed their own city: never overwrite it again.
        this.autoCity = null;
    },

    //--------------------------------------------------------------------------
    // Street suggestions
    //--------------------------------------------------------------------------

    _onStreetInput(ev) {
        if (!isUserEvent(ev) || !this.addressEnabled) {
            return;
        }
        const query = this.streetEl.value.trim();
        if (query.length < 4) {
            this._hideSuggestions();
            return;
        }
        if (!this.sessionToken) {
            this.sessionToken = newSessionToken();
        }
        this._fetchSuggestionsDebounced(query);
    },

    async _fetchSuggestions(query) {
        const seq = ++this.requestSeq;
        let result;
        try {
            result = await rpc("/selamta/registration/address", {
                query,
                session_token: this.sessionToken,
            });
        } catch {
            return;
        }
        if (seq !== this.requestSeq || this.streetEl.value.trim() !== query) {
            return;
        }
        if (result && result.enabled === false) {
            this.addressEnabled = false;
        }
        this.suggestions = (result && result.suggestions) || [];
        this._renderSuggestions();
    },

    _renderSuggestions() {
        const el = this.suggestEl;
        el.textContent = "";
        this.activeIndex = -1;
        if (!this.suggestions.length || document.activeElement !== this.streetEl) {
            this._hideSuggestions();
            return;
        }
        this.suggestions.forEach((s, index) => {
            const item = document.createElement("button");
            item.type = "button";
            item.tabIndex = -1;
            item.className = "sel-reg-suggest-item";
            item.setAttribute("role", "option");
            item.dataset.index = index;
            const main = document.createElement("strong");
            main.textContent = s.main;
            item.appendChild(main);
            if (s.secondary) {
                const secondary = document.createElement("small");
                secondary.textContent = s.secondary;
                item.appendChild(secondary);
            }
            el.appendChild(item);
        });
        const footer = document.createElement("div");
        footer.className = "sel-reg-suggest-footer";
        footer.textContent = "powered by Google";
        el.appendChild(footer);
        el.classList.remove("d-none");
        this.streetEl.setAttribute("aria-expanded", "true");
    },

    _hideSuggestions() {
        if (!this.suggestEl) {
            return;
        }
        this.suggestEl.classList.add("d-none");
        this.suggestEl.textContent = "";
        this.suggestions = [];
        this.activeIndex = -1;
        this.streetEl.setAttribute("aria-expanded", "false");
    },

    _highlight(index) {
        const items = this.suggestEl.querySelectorAll(".sel-reg-suggest-item");
        items.forEach((item, i) => item.classList.toggle("active", i === index));
        this.activeIndex = index;
    },

    _onStreetKeydown(ev) {
        if (!this.suggestions.length || this.suggestEl.classList.contains("d-none")) {
            return;
        }
        if (ev.key === "ArrowDown") {
            ev.preventDefault();
            this._highlight((this.activeIndex + 1) % this.suggestions.length);
        } else if (ev.key === "ArrowUp") {
            ev.preventDefault();
            this._highlight(
                (this.activeIndex - 1 + this.suggestions.length) % this.suggestions.length
            );
        } else if (ev.key === "Enter") {
            // never submit the form from here
            ev.preventDefault();
            ev.stopPropagation();
            this._selectSuggestion(this.activeIndex >= 0 ? this.activeIndex : 0);
        } else if (ev.key === "Escape") {
            this._hideSuggestions();
        }
    },

    _onStreetBlur() {
        // small delay so a click on a suggestion still counts
        setTimeout(() => this._hideSuggestions(), 150);
    },

    async _selectSuggestion(index) {
        const suggestion = this.suggestions[index];
        if (!suggestion) {
            return;
        }
        const query = this.streetEl.value;
        this._hideSuggestions();
        // show the choice right away; the details call fills in the rest
        this.streetEl.value = suggestion.main;
        let address;
        try {
            address = await rpc("/selamta/registration/address/details", {
                place_id: suggestion.place_id,
                session_token: this.sessionToken,
                query,
            });
        } catch {
            address = null;
        }
        this.sessionToken = null; // a session ends with the details call
        if (!address || !address.street) {
            return;
        }
        this._setValue(this.streetEl, address.street);
        if (address.street2 && this.street2El && !this.street2El.value.trim()) {
            this._setValue(this.street2El, address.street2);
        }
        if (address.zip && this.zipEl) {
            this.lastZip = address.zip.slice(0, 5); // no extra ZIP lookup
            this._setValue(this.zipEl, address.zip);
            this.zipHintEl.textContent = "";
        }
        if (address.city && this.cityEl) {
            this._setValue(this.cityEl, address.city);
            this.autoCity = address.city;
        }
        this._setState(address.state_id);
        if (this.street2El) {
            this.street2El.focus();
        }
    },

    //--------------------------------------------------------------------------
    // Formatting
    //--------------------------------------------------------------------------

    _onEinInput(ev) {
        const el = ev.currentTarget;
        const digits = el.value.replace(/\D/g, "").slice(0, 9);
        const formatted = digits.length > 2 ? `${digits.slice(0, 2)}-${digits.slice(2)}` : digits;
        if (formatted !== el.value) {
            el.value = formatted;
        }
    },

    _onPhoneBlur(ev) {
        const el = ev.currentTarget;
        let digits = el.value.replace(/\D/g, "");
        if (digits === "1") {
            el.value = ""; // only the country code: treat as empty
            return;
        }
        if (digits.length === 11 && digits.startsWith("1")) {
            digits = digits.slice(1);
        }
        if (digits.length === 10) {
            el.value = `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
        }
    },
});

export default publicWidget.registry.SelamtaRegistrationForm;
