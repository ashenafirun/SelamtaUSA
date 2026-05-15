/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

// Select Adyen Payment Method
publicWidget.registry.PaymentForm.include({
  events: Object.assign({}, publicWidget.Widget.prototype.events, {
    'click [name="o_payment_radio"]': "_selectPaymentOption",
    'change [name="o_payment_use_credit_limit_checkbox"]': "_onCreditLimitCheckboxChange",
  }),

  async _selectPaymentOption(ev) {
    await this._super(...arguments);

    // Past Due option exists -> hide payment methods + fees
    const pastDueView = document.getElementById("adv_payment_method_hide");

    if (pastDueView) {
        this._toggleAdyenFeeRows(false);
        this._toggleCreditRow(false, 0);

        const paymentDiv = document.getElementById("payment_method");
        if (paymentDiv) {
            paymentDiv.style.display = "none";
        }

        return;
    }

    const isCreditSelected = this._isCreditLimitSelected();

    if (isCreditSelected) {
      this._toggleAdyenFeeRows(false);
      this._toggleCreditRow(false, 0);
      return;
    }

    const checkedRadio = ev.target;
    this._applyCreditAndAdyenState(checkedRadio);
  },

  async start() {
    await this._super(...arguments);

    const pastDueView = document.getElementById("adv_payment_method_hide");

        if (pastDueView) {
            this._toggleAdyenFeeRows(false);
            this._toggleCreditRow(false, 0);

            const paymentDiv = document.getElementById("payment_method");
            if (paymentDiv) {
                paymentDiv.style.display = "none";
            }

            return;
        }


    if (this._isCreditLimitSelected()) {
      this._toggleAdyenFeeRows(false);
      this._toggleCreditRow(false, 0);
      return;
    }


    const checkedRadio = this.el.querySelector(
      'input[name="o_payment_radio"]:checked',
    );
    if (checkedRadio) {
      this._applyCreditAndAdyenState(checkedRadio);
    }
  },

  _applyCreditAndAdyenState(checkedRadio) {
    const isAdyen = this._isAdyenOption(checkedRadio);
    const optionContainer = checkedRadio.closest('[name="o_payment_option"]');
    const creditCheckbox = optionContainer ? optionContainer.querySelector('[name="o_payment_use_credit_limit_checkbox"]') : null;
    const isChecked = creditCheckbox && creditCheckbox.checked;

    const orderTotal = parseFloat(this.el.dataset.orderTotal) || 0;
    const availableCredit = parseFloat(this.el.dataset.availableCredit) || 0;

    let newAmountToCharge = orderTotal;
    let creditToUse = 0;

    if (isChecked) {
        creditToUse = Math.min(availableCredit, orderTotal);
        newAmountToCharge = Math.max(orderTotal - creditToUse, 0);
    }

    this._toggleCreditRow(isChecked, creditToUse);

    if (isAdyen) {
        this._updateAdyenDisplay(newAmountToCharge);
        this._toggleAdyenFeeRows(true);
    } else {
        this._toggleAdyenFeeRows(false);
    }
  },

  _isCreditLimitSelected() {
    const creditRadio = document.querySelector(
      'input[name="payment_option"]:checked',
    );
    // return creditRadio && creditRadio.value === '3';
    // return creditRadio && (creditRadio.value === '2' || creditRadio.value === '3');
    return creditRadio && creditRadio.value === "2";
  },

  async _onCreditLimitCheckboxChange(ev) {
    const checkedRadio = this.el.querySelector(
        'input[name="o_payment_radio"]:checked'
    );
    this._applyCreditAndAdyenState(checkedRadio);
  },

  _updateAdyenDisplay(amountToPay) {
      const feeRow = document.getElementById("order_total_adyen_fee_label");
      const grandTotalSpan = document.getElementById("adyen_grand_total_amount");
      if (!feeRow || !grandTotalSpan) return;

      // 1. Get Fee Rules
      const fixedFee = parseFloat(feeRow.getAttribute('data-fee-fixed')) || 0;
      const variableRate = parseFloat(feeRow.getAttribute('data-fee-var')) || 0;

      // 2. Calculate Fee on the amount actually being paid via Adyen
      let newFee = 0;
      if (amountToPay > 0) {
          newFee = (amountToPay * variableRate) + fixedFee;
      }

      // 3. Grand Total is ONLY what the customer pays NOW (Balance + Fee)
      const orderTotal = parseFloat(this.el.dataset.orderTotal) || 0;

      // const newGrandTotal = amountToPay + newFee;
      const newGrandTotal = orderTotal + newFee;

      // 4. Update UI
      const feeAmountEl = feeRow.querySelector('.monetary_field');
      if (feeAmountEl) {
          feeAmountEl.innerText = this._formatCurrency(newFee);
      }
      grandTotalSpan.innerText = this._formatCurrency(newGrandTotal);

      // this._toggleAdyenFeeRows(amountToPay > 0);
      this._toggleAdyenFeeRows(true);
  },

  _formatCurrency(amount) {
      // Simple helper to format to 2 decimal places
      // For production, use Odoo's web.field_utils to get proper currency symbols
      const formattedNum = amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      const row = document.getElementById("order_credit_to_use");
      if (!row) {
          return formattedNum;
      }
      const symbol = row.dataset.currencySymbol || '';
      const position = row.dataset.currencyPosition || 'before';
      if (position === 'after') {
          return `${formattedNum} ${symbol}`;
      } else {
          return `${symbol} ${formattedNum}`;
      }
  },

  _isAdyenOption(radio) {
    const providerCode = this._getProviderCode(radio);
    const paymentOptionType = this._getPaymentOptionType(radio);
    const pmCode = this._getPaymentMethodCode(radio);

    const isAdyenToken =
      providerCode === "adyen" && paymentOptionType === "token" && !['ach_direct_debit'].includes(pmCode);
    const isAdyenCardMethod = providerCode === "adyen" && pmCode === "card";

    return isAdyenToken || isAdyenCardMethod;
  },
  /**
   * Show or hide the "Credit to be used" row in the order summary.
   * @param {Boolean} show  – whether to display the row
   * @param {Number}  amount – credit amount to display
   */
  _toggleCreditRow(show, amount) {
      const row = document.getElementById('order_credit_to_use');
      const amountEl = document.getElementById('credit_to_use_amount');
      if (!row) return;

      row.style.display = show ? '' : 'none';
      if (amountEl) {
          amountEl.innerText = show ? this._formatCurrency(amount) : '';
      }
  },

  _toggleAdyenFeeRows(show) {
    const feeRow = document.getElementById("order_total_adyen_fee_label");
    const totalRow = document.getElementById("order_total_grand_total");
    if (!feeRow || !totalRow) return;

    feeRow.style.display = show ? "" : "none";
    totalRow.style.display = show ? "" : "none";
  },
});
