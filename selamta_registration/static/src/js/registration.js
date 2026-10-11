/** @odoo-module **/
/*
 * Selamta wholesale registration form helpers:
 *  - ZIP code -> city and state (built-in U.S. ZIP list on the server)
 *  - street address suggestions while typing (Google Places, when a key is set)
 *  - EIN shown as 12-3456789, U.S. phones as (404) 555-1234
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
        if (this.suggestEl) {
            this.suggestEl.remove();
        }
        if (this.zipHintEl) {
            this.zipHintEl.remove();
        }
        this._super(...arguments);
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
