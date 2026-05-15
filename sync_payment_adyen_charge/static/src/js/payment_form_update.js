/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.AdyenFeeSwitcher = publicWidget.Widget.extend({
  selector: "#pay_with",
  events: {
    "click #o_payment_installments_tab": "_onClickInstallment",
    "click #o_payment_full_tab": "_onClickFull",
  },

  start() {
    const res = this._super(...arguments);

    this.wrapper = Array.from(
      document.querySelectorAll("#fee_wrapper, #fee_wrapper_token"),
    );

    if (!this.wrapper.length) return res;

    this.wrapperData = [];

    this.wrapper.forEach((wrapper) => {
      const data = {
        wrapper,
        feeBadge: wrapper.querySelector(
          ".badge.rounded-pill.text-bg-secondary.ms-1",
        ),
        partialBase: parseFloat(wrapper.dataset.amount_custom || "0"),
        fullBase: parseFloat(wrapper.dataset.full_amount || "0"),
        partialFee: parseFloat(wrapper.dataset.fees_amount || "0"),
        fullFee: parseFloat(wrapper.dataset.full_fee || "0"),
        remaining: parseFloat(wrapper.dataset.full_amount || "0"),
      };
      this.wrapperData.push(data);
    });

    return res;
  },

  _onClickInstallment() {
    this._updateFee(true);
  },

  _onClickFull() {
    this._updateFee(false);
  },

  _updateFee(isInstallment) {
    if (!Array.isArray(this.wrapperData) || !this.wrapperData.length) {
      return;
    }
    this.wrapperData.forEach((data) => {
      const { wrapper, feeBadge } = data;
      if (!feeBadge) return;

      let baseAmount, fee;
      if (isInstallment) {
        baseAmount = data.partialBase;
        fee = data.partialFee;
        data.remaining = Math.max(data.remaining - baseAmount, 0);
      } else {
        baseAmount = data.remaining > 0 ? data.remaining : data.fullBase;
        const fullFeeRate = data.fullFee / data.fullBase;
        fee = baseAmount * fullFeeRate;
        data.remaining = 0;
      }
      feeBadge.textContent = `+ $${fee.toFixed(2)} Fees`;
      wrapper.dataset.fees_amount = fee.toFixed(2);
      wrapper.dataset.amount_custom = baseAmount.toFixed(2);
      wrapper.dataset.is_installment = isInstallment ? "1" : "0";
    });
  },
});
