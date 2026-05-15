/** @odoo-module **/
import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.CreditToggle = publicWidget.Widget.extend({
  selector: ".oe_website_sale",
  events: {
    "change .js_confirm_style": "_onConfirmStyleChange",
  },

  _onConfirmStyleChange: function (ev) {
    var paymentOption = $(ev.currentTarget).val();

    // if (paymentOption === "3") {
    //         window.location.href = "/my/invoices?filterby=overdue_invoices";
    //         return;
    //     }

    window.location.href = "/shop/payment?payment_option=" + paymentOption;
    // window.location.href = "/shop/payment";
  },
});
