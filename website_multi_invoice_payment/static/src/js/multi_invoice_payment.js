/** @odoo-module */

import publicWidget from "@web/legacy/js/public/public_widget";

import { _t } from "@web/core/l10n/translation";

publicWidget.registry.MultiInvoicePayment = publicWidget.Widget.extend({
  selector: ".o_portal_wrap",
  events: {
    "click #go_payment": "_onClickMultiPay",
    "change .payall": "_onPayallChange",
    "change input.pay": "_onPayChange",
  },

  _onPayChange(ev) {
    var checked_length = $("input.pay:checked").length;
    $(".payall").prop(
      "checked",
      checked_length == $("input.pay").length ? true : false,
    );
  },

  _onPayallChange(ev) {
    $("input.pay").prop("checked", $(ev.currentTarget).prop("checked"));
  },

  _onClickMultiPay(ev) {
    var form = document.createElement("form");
    $("body").append(form);
    form.action = "/payment/pay";
    // form.method = 'POST';
    var invoice_ids = [];
    var currency_ids = [];
    $.each($(".pay:checked"), function () {
      var invoice_id = Number($(this).data("id"));
      var amount = Number($(this).data("amount"));
      var currency_id = Number($(this).data("currency_id"));
      currency_ids.push(currency_id);
      if (!isNaN(invoice_id)) {
        invoice_ids.push(invoice_id);
        var input = document.createElement("input");
        input.type = "hidden";
        input.name = invoice_id;
        input.value = amount;
        form.appendChild(input);
      }
    });
    if (invoice_ids.length == 0) {
      alert("Please select at least 1 Invoice.");
    } else {
      if (new Set(currency_ids).size == 1) {
        form.submit();
      } else {
        alert("Please select invoices that have the same currency.");
      }
    }
  },
});
export default publicWidget.registry.MultiInvoicePayment;
