/** @odoo-module **/
import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.CreditPaymentToggle = publicWidget.Widget.extend({
  selector: ".oe_website_sale",

  events: {
    'change input[name="payment_option"]': "_onConfirmStyleChange",
    'change input[name="o_payment_use_credit_limit_checkbox"]': "_onCreditToggle",
  },

  start() {
    this._applyToggle();
    return this._super(...arguments);
  },

  _onConfirmStyleChange() {
    this._applyToggle();
  },

  _applyToggle() {
    const showPastDue = $("#adv_payment_method_hide").data("show-past-due");
    if (showPastDue) {
        this.$("#o_payment_form").hide();
        const submit_btn = document.querySelector("button[name='o_payment_submit_button']");
        if (submit_btn) {
            submit_btn.style.display = "none";
        }
    }

    const isCreditSelected = this.$("#credit_limit").is(":checked");
    const isPastDueSelected = this.$("#past_due_balance").is(":checked");

    if (isCreditSelected || isPastDueSelected) {
      this.$("#payment_method").hide();
      this.$('[name="website_sale_non_free_cart"]').hide();
      this.$('[name="o_website_sale_credit_free_cart"]').show();
    } else {
      this.$("#payment_method").show();
      this.$('[name="website_sale_non_free_cart"]').show();
      this.$('[name="o_website_sale_credit_free_cart"]').hide();
    }
  },

  _onCreditToggle(ev) {
    ev.stopPropagation();

    const checked = ev.currentTarget.checked;

    // Find the parent payment option container for this checkbox
    const $option = $(ev.currentTarget).closest('[name="o_payment_option"]');
    const $breakdown = $option.find(".js_credit_breakdown");

    if (checked) {
        $breakdown.show();
        this._updateChargeNote();

    } else {
        $breakdown.hide();
    }
    },

    _updateChargeNote() {
        const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        if (!checkedRadio) {
            this.$('.js_charge_note').hide();
            return;
        }

        const providerCode = checkedRadio.dataset.providerCode || '';
        const methodCode = checkedRadio.dataset.paymentMethodCode || '';
        const optionType = checkedRadio.dataset.paymentOptionType || '';
        // const isAdyenCard =
        //     (optionType === 'payment_method' && providerCode === 'adyen' && methodCode === 'card') ||
        //     (optionType === 'token' && providerCode === 'adyen');
        const isAdyenCard =
            (optionType === 'payment_method' &&
                providerCode === 'adyen' &&
                methodCode === 'card') ||

            (optionType === 'token' &&
                providerCode === 'adyen' &&
                !['ach_direct_debit'].includes(methodCode));

        this.$('.js_charge_note').toggle(isAdyenCard);
    },

});


/**
 * Override PaymentForm to inject credit limit logic into the transaction params.
 *
 * When the "Use Credit Limit" checkbox is checked inside the selected payment
 * option, we:
 *   1. Set the form's data-amount to the remaining amount (order total - credit).
 *   2. Add `use_credit_limit: true` to the transaction route params.
 */
publicWidget.registry.PaymentForm.include({

    events: Object.assign({}, publicWidget.registry.PaymentForm.prototype.events, {
        'click .o_payment_credit_limit_container': '_onCreditContainerClick',
    }),

    /**
     * Intercept click events on the credit limit container to prevent them
     * from bubbling up to the radio button label's stretched ::before overlay.
     * The CSS fix (z-index) is the primary solution; this is a safety net.
     */
    _onCreditContainerClick(ev) {
        ev.stopPropagation();
    },

    /**
     * Override: after expanding the inline form, preserve the credit limit
     * checkbox state if it's present in the selected option.
     */
    async _selectPaymentOption(ev) {
        // Guard: if the click originated from the credit checkbox or its
        // container, skip the base logic entirely.
        const target = ev.target || ev.originalEvent?.target;
        if (target) {
            if (target.name === 'o_payment_use_credit_limit_checkbox') {
                return;
            }
            if (target.closest && target.closest('.o_payment_credit_limit_container')) {
                return;
            }
        }

        await this._super(...arguments);
        // Reset all credit breakdowns
        this.$('.js_credit_breakdown').hide();
        // Uncheck credit checkboxes in non-selected options
        this.el.querySelectorAll('[name="o_payment_option"]').forEach(option => {
            const radio = option.querySelector('[name="o_payment_radio"]');
            if (radio && !radio.checked) {
                const cb = option.querySelector('[name="o_payment_use_credit_limit_checkbox"]');
                if (cb) {
                    cb.checked = false;
                }
            }
        });
        // Reset the amount to the order total when switching options
        this._resetAmountToOrderTotal();
    },

    /**
     * Override: inject `use_credit_limit` flag and the reduced amount into the
     * transaction route params when the credit checkbox is checked.
     */
    _prepareTransactionRouteParams() {
        const params = this._super(...arguments);

        const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        if (!checkedRadio) {
            return params;
        }

        const option = checkedRadio.closest('[name="o_payment_option"]');
        const creditCheckbox = option
            ? option.querySelector('[name="o_payment_use_credit_limit_checkbox"]')
            : null;

        if (creditCheckbox && creditCheckbox.checked) {
            const availableCredit = parseFloat(this.el.dataset.availableCredit) || 0;
            const orderTotal = parseFloat(this.el.dataset.orderTotal) || 0;

            if (availableCredit > 0 && orderTotal > 0) {
                const creditToUse = Math.min(availableCredit, orderTotal);
                const remainingAmount = Math.max(orderTotal - creditToUse, 0);

                params['amount'] = remainingAmount;
                params['use_credit_limit'] = true;
            }
        }

        return params;
    },

    /**
     * Reset the form amount back to the order total.
     */
    _resetAmountToOrderTotal() {
        const orderTotal = this.el.dataset.orderTotal;
        if (orderTotal) {
            this.el.dataset.amount = orderTotal;
        }
    },
});
