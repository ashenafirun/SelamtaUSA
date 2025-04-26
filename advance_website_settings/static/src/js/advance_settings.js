/** @odoo-module **/
// odoo.define('advance_website_settings.advance_website_settings', function (require) {
  // "use strict";

import publicWidget from '@web/legacy/js/public/public_widget';
import { patch } from '@web/core/utils/patch';

import { rpc } from "@web/core/network/rpc";
import { WebsiteSale } from '@website_sale/js/website_sale';
import { _t } from "@web/core/l10n/translation";
import VariantMixin from "@website_sale/js/sale_variant_mixin";
import wSaleUtils from "@website_sale/js/website_sale_utils";
// import core from "@web/legacy/js/core";
import { EventBus, whenReady } from "@odoo/owl";
import {
  ProductConfiguratorDialog
} from '@sale/js/product_configurator_dialog/product_configurator_dialog';
import {
  QuantityButtons
} from '@sale/js/quantity_buttons/quantity_buttons';

  const html = document.documentElement;
  const gotoshop = html.dataset.shoppageRedirect;

  const originalOnChangeCombinationinherit = VariantMixin._onChangeCombination;
  VariantMixin._onChangeCombination = function (ev, $parent, combination) {
    originalOnChangeCombinationinherit.apply(this, [ev, $parent, combination]);
    var varient_id = $(".main_product > .product_id").attr("value")
    if (varient_id){
      rpc('/varient/limit/', { id: varient_id }).then(function (res) {
        $('.main_product > .product_id').attr('min_val', res['min_value'])
        $('.main_product > .product_id').attr('max_val', res['max_value'])
        $('.main_product > .product_id').attr('conf_max_val', res['conf_max_value'])
        $('.main_product > .product_id').attr('conf_min_val', res['conf_min_value'])
        $('.main_product > .product_id').attr('enable_limit', res["enable_limit"])
        $('.main_product > .product_id').attr('min_val_temp', res['min_value_temp'])
        $('.main_product > .product_id').attr('max_val_temp', res['max_value_temp'])
        $('.main_product > .product_id').attr('enable_limit_template', res["enable_limit_template"])
  
      })
    }
  }


  function _min_max_varidation(min_quant_varient, max_quant_varient, enable_limit_varient, enable_limit_template, min_quantity, max_quantity, current_quant_value, conf_product_min_quant, conf_product_max_quant) {
    var error
    var enable_limit_varient = Boolean(parseInt(enable_limit_varient))
    var enable_limit_template = Boolean(parseInt(enable_limit_template))

    if (((min_quant_varient != undefined) || (max_quant_varient != undefined)) && (enable_limit_varient)) {
      if (current_quant_value < parseInt(min_quant_varient) && (min_quant_varient != "-1")) {
        error = _t("Minimum of ")  + min_quant_varient +   _t(" product quantities are required.")
        $('.quantity').val(min_quant_varient)
        ProductConfiguratorDialog._setQuantity($('.product_id').attr('value'), min_quant_varient)
        $('.quantity').trigger('change')

      }
      else if (current_quant_value > parseInt(max_quant_varient) && (max_quant_varient != "-1")) {
        error = _t("Maximum ") +  max_quant_varient +  _t(" product quantities allowed")
        $('.quantity').val(max_quant_varient)
        $('.quantity').trigger('change')

      }
    }


    else if (((min_quantity != undefined) || (max_quantity != undefined)) && (enable_limit_template)) {
      if (current_quant_value < parseInt(min_quantity) && (min_quantity != "-1")) {
        error = _t("Minimum of ") +  min_quantity +  _t(" product quantities are required.")
        $('.quantity').val(min_quantity)
        $('.quantity').trigger('change')


      }
      else if (current_quant_value > parseInt(max_quantity) && (max_quantity != "-1")) {
        error = _t("Maximum ") + max_quantity + _t(" product quantities allowed")
        $('.quantity').val(max_quantity)
        $('.quantity').trigger('change')

      }
    }
    else if ((current_quant_value < conf_product_min_quant) && (conf_product_min_quant > 0)) {
      error = _t("Minimum of ") +  conf_product_min_quant +  _t(" product quantities are required.")
      $('.quantity').val(conf_product_min_quant)
      // ProductConfiguratorDialog.prototype._setQuantity(parseInt($('.product_template_id').attr('value')), conf_product_min_quant)
      $('.quantity').trigger('change')

    }
    else if ((current_quant_value > conf_product_max_quant) && (conf_product_max_quant > 0)) {
      error = _t("Maximum ") +  conf_product_max_quant + _t(" product quantities allowed")
      $('.quantity').val(conf_product_max_quant)
      $('.quantity').trigger('change')
    }
    if (error) {
      return error
    }
    return true



  };
  patch(ProductConfiguratorDialog.prototype, { 
    async onConfirm(options) {
      var min_quant_varient = $('.product_id').attr('min_val')
      var max_quant_varient = $('.product_id').attr('max_val')
      var enable_limit_varient = $('.product_id').attr('enable_limit')
      var enable_limit_template = $('.product_id').attr('enable_limit_template')
      var min_quantity = $('.main_product > .product_id').attr('min_val_temp')
      var max_quantity = $('.main_product > .product_id').attr('max_val_temp')
      var current_quant_value = parseInt($(".quantity").val())
      var conf_product_min_quant = parseInt($('.product_id').attr('conf_min_val'))
      var conf_product_max_quant = parseInt($('.product_id').attr('conf_max_val'))
      var validator = _min_max_varidation(min_quant_varient, max_quant_varient, enable_limit_varient, enable_limit_template, min_quantity, max_quantity, current_quant_value, conf_product_min_quant, conf_product_max_quant)
      if (validator == true) {
        return super.onConfirm(options);
      }
      else {
        $('.o_sale_product_configurator_edit').popover({
          title: _t("WARNING!!"),
          placement: "top",
          trigger: 'focus',
          content: validator,
        });
        $('.o_sale_product_configurator_edit').popover('show');
        setTimeout(function () { $('.o_sale_product_configurator_edit').popover("dispose"); }, 3000);
        return false
      }

    }
  }),


  


  publicWidget.registry.WebsiteSale.include({

     _onClickAdd: function(ev){
      ev.currentTarget
      if (product_id){
        var product_id = $(ev.currentTarget).parent().find('input').val()
       rpc('/varient/limit/', { id: product_id }).then(function (res){
        $(ev.currentTarget).parent().find('input').attr('min_val', res['min_value'])
        $(ev.currentTarget).parent().find('input').attr('max_val', res['max_value'])
        $(ev.currentTarget).parent().find('input').attr('conf_max_val', res['conf_max_value'])
        $(ev.currentTarget).parent().find('input').attr('conf_min_val', res['conf_min_value'])
        $(ev.currentTarget).parent().find('input').attr('enable_limit', res["enable_limit"])
        $(ev.currentTarget).parent().find('input').attr('min_value_temp', res["min_value_temp"])
        $(ev.currentTarget).parent().find('input').attr('max_value_temp', res["max_value_temp"])
        $(ev.currentTarget).parent().find('input').attr('enable_limit_template', res["enable_limit_template"])
      })

      }
      
      return this._super(...arguments)
    },

    _handleAdd: function () {
      var self = this;
      var arg = arguments;
      if (gotoshop === '3') {
        self.forceDialog = false;
      }
      return self._super.apply(self, arg);
    },

    _submitForm: function () {
      var self = this;
      var arg = arguments;
      if (self.isBuyNow) {
        return self._super.apply(self, arg);
      }
      else {
        if (gotoshop === '3') {

          const params = self.rootProduct;
          const $product = $('#product_detail');
          const productTrackingInfo = $product.data('product-tracking-info');
          if (productTrackingInfo) {
            productTrackingInfo.quantity = params.quantity;
            $product.trigger('add_to_cart_event', [productTrackingInfo]);
          }
          params.add_qty = params.quantity;
          params.product_custom_attribute_values = JSON.stringify(params.product_custom_attribute_values);
          params.no_variant_attribute_values = JSON.stringify(params.no_variant_attribute_values);
          delete params.quantity;
          self._addToCartInPage(params);
          // self._addToCartInPage(self.rootProduct)
          setInterval(function () {
            wUtils.sendRequest('/shop', {});
          }, 2000)
        }
        else {
          return self._super.apply(self, arg);
        }
      }
    },
    _changeCartQuantity: function ($input, value, $dom_optional, line_id, productIDs) {
      $.each($dom_optional, function (elem) {
        $(elem).find('.js_quantity').text(value);
        productIDs.push($(elem).find('span[data-product-id]').data('product-id'));
      });
      $input.data('update_change', true);

      rpc("/shop/cart/update_json",{
        line_id: line_id,
        product_id: parseInt($input.data('product-id'), 10),
        set_qty: value
       
      
  }).then(function (data) {
        const bus = new EventBus();
        $input.data('update_change', false);
        var check_value = parseInt($input.val() || 0, 10);
        if (isNaN(check_value)) {
          check_value = 1;
        }
        if (value !== check_value) {
          $input.trigger('change');
          return;
        }
        sessionStorage.setItem('website_sale_cart_quantity', data.cart_quantity);
        if (!data.cart_quantity) {
          return window.location = '/shop/cart';
        }
        $input.val(data.quantity);
        $('.js_quantity[data-line-id=' + line_id + ']').val(data.quantity).text(data.quantity);

        wSaleUtils.updateCartNavBar(data);
        wSaleUtils.showWarning(data.warning);

        $(".is_amount_valid").attr("is_amount_valid", data["is_amount_valid"])
        // Propagating the change to the express checkout forms
        bus.trigger('cart_amount_changed', data.amount, data.minor_amount);
      });
    },

    _submitForm: function (ev) {
      if ($('.product_id').attr('min_val')!=undefined){

        var min_quant_varient = $('.product_id').attr('min_val')
        var max_quant_varient = $('.product_id').attr('max_val')
        var enable_limit_varient = $('.product_id').attr('enable_limit')
        var enable_limit_template = $('.product_id').attr('enable_limit_template')
        var min_quantity = $('#max_min_values').attr('min_quantity')
        var max_quantity = $('#max_min_values').attr('max_quantity')
        var current_quant_value = parseInt($(".quantity").val())
        var conf_product_min_quant = parseInt($('.product_id').attr('conf_min_val'))
        var conf_product_max_quant = parseInt($('.product_id').attr('conf_max_val'))
        var validator = _min_max_varidation(min_quant_varient, max_quant_varient, enable_limit_varient, enable_limit_template, min_quantity, max_quantity, current_quant_value, conf_product_min_quant, conf_product_max_quant)
        if (validator == true) {
  
          return this._super.apply(this, arguments)
        }
        else {
          $('#add_to_cart').popover({
            title: _t("WARNING!!"),
            placement: "top",
            trigger: 'focus',
            content: validator,
          });
          $('#add_to_cart').popover('show');
          setTimeout(function () { $('#add_to_cart').popover("dispose"); }, 3000);
          return false
        }
      } 
      else{
        var min_quant_varient = this.$itemImgContainer.find('input[name=product_id]').attr('min_val')
        var max_quant_varient = this.$itemImgContainer.find('input[name=product_id]').attr('max_val')
        var enable_limit_varient = this.$itemImgContainer.find('input[name=product_id]').attr('enable_limit')
        var enable_limit_template = this.$itemImgContainer.find('input[name=product_id]').attr('enable_limit_template')
        var min_quantity = this.$itemImgContainer.find('input[name=product_id]').attr('min_value_temp')
        var max_quantity = this.$itemImgContainer.find('input[name=product_id]').attr('max_value_temp')
        var current_quant_value = 1
        var conf_product_min_quant = parseInt(this.$itemImgContainer.find('input[name=product_id]').attr('conf_min_val'))
        var conf_product_max_quant = parseInt(this.$itemImgContainer.find('input[name=product_id]').attr('conf_max_val'))
        var validator = _min_max_varidation(min_quant_varient, max_quant_varient, enable_limit_varient, enable_limit_template, min_quantity, max_quantity, current_quant_value, conf_product_min_quant, conf_product_max_quant)
        if (validator == true) {
  
          return this._super.apply(this, arguments)
        }
        else {
          var list = this.$itemImgContainer.find('.o_wsale_product_btn')
          this.$itemImgContainer.find('.o_wsale_product_btn').popover({
            title: _t("WARNING!!"),
            placement: "top",
            trigger: 'focus',
            content: validator,
          });
          this.$itemImgContainer.find('.o_wsale_product_btn').popover('show');
          setTimeout(function () { list.popover("dispose"); }, 3000);
          return false
        }
      }


    },
    _onChangeCombination: function (ev, $parent, combination) {
      this._super.apply(this, arguments)
      var varient_id = $('.product_id').attr('value')
      if (varient_id){
        rpc('/varient/limit/', { id: varient_id }).then(function (res) {
          $('.product_id').attr('min_val', res['min_value'])
          $('.product_id').attr('max_val', res['max_value'])
          $('.product_id').attr('conf_max_val', res['conf_max_value'])
          $('.product_id').attr('conf_min_val', res['conf_min_value'])
          $('.product_id').attr('enable_limit', res["enable_limit"])
          $('.product_id').attr('enable_limit_template', res["enable_limit_template"])
        })
      }

    }
  })


  $(document).ready(function () {
    function escapeRegExp(text) {
      return text.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, '\\$&');
    }
    var code = $('html').attr('lang');
    var constraints;
    $('.oe_website_sale').find('.wk_cart_values').hide()

    try {
      rpc('/website/wk_lang',  {
        'code': code
      })
        .then(function (res) {

          constraints = res;
        });

    } catch (e) {
      console.error(e);
    }
    $("div[name=o_express_checkout_container]").click(function(ev){
      if (!$(".is_amount_valid").attr('is_amount_valid')) {
        $(":first-child").removeAttr('data-bs-target');
        $(":first-child").removeAttr('data-bs-toggle');
        var conf_value = $('.oe_website_sale').find('.wk_cart_values span.oe_currency_value').slice(0, 1).text();
        var pricelist_symbol = $('.oe_website_sale').find('.wk_min_price_value').attr('currency_symbol');
        var pricelist_val = $('.oe_website_sale').find('.wk_min_price_value').attr('conf_value')
        var cart_value = $('#order_total').find('.oe_currency_value').text();
        var thousand_sep = new RegExp(escapeRegExp(constraints.thousands_sep), "g")
        var decimal_sep = new RegExp(escapeRegExp(constraints.decimal_point), "g")
        var cart = parseFloat(cart_value.replace(thousand_sep, '').replace(decimal_sep, '.'))
        var check = parseFloat(conf_value.replace(thousand_sep, '').replace(decimal_sep, '.'))
        var currency_symbol = $('.oe_website_sale').find('.wk_cart_values').attr('currency_symbol');
        var conf_wk_min_quant_values = $('.wk_min_quant_values').attr('conf_value')
        var conf_wk_max_quant_values = $('.wk_max_quant_values').attr('conf_value')
        var cart_quant_val = $('.oe_website_sale').find('.js_quantity')
        var error_content
        cart_quant_val.each(function () {
          var cart_product_quant = parseInt($(this).val())
          var product_min_value = $(this).parents('tr').find(".min_max_validate").attr('min_value')
          var product_max_value = $(this).parents('tr').find(".min_max_validate").attr('max_value')
          var enable_limit_template = $(this).parents('tr').find(".min_max_validate").attr('enable_limit_template')
          var curent_varient_count = $(this).parents('tr').find(".varient_limit").attr('current_varient_len')
          var max_varient_quant = $(this).parents('tr').find(".varient_limit").attr('max_varient')
          var min_varient_quant = $(this).parents('tr').find(".varient_limit").attr('min_varient')
          var enable_limit = $(this).parents('tr').find(".varient_limit").attr('enable_limit')
          var conf_product_min_quant = parseInt(conf_wk_min_quant_values)
          var conf_product_max_quant = parseInt(conf_wk_max_quant_values)
          var product_name = $(this).parents('tr').find("strong").text()
  
          if (((max_varient_quant != undefined) || (min_varient_quant != undefined)) && (enable_limit)) {
            if (cart_product_quant < parseInt(min_varient_quant) && (min_varient_quant != "-1")) {
              error_content = _t("Minimum of ") + min_varient_quant + _t(" product quantities are required :- ") + product_name
              $(this).val(min_varient_quant)
              $(this).trigger('change')
              return false
            }
            else if (cart_product_quant > parseInt(max_varient_quant) && (max_varient_quant != "-1")) {
              error_content = _t("Maximum ") +  max_varient_quant +  _t(" product quantities allowed :- ") +  product_name
              $(this).val(max_varient_quant)
              $(this).trigger('change')
              return false
            }
          }
  
          else if (((product_min_value != undefined) || (product_max_value != undefined)) && (enable_limit_template)) {
            if ((cart_product_quant < parseInt(product_min_value)) && (product_min_value != "-1")) {
              error_content = _t("Minimum of ") + product_min_value + (" product quantities are required :- ") + product_name
              $(this).val(product_min_value)
              $(this).trigger('change')
              return false
  
            }
            else if ((cart_product_quant > parseInt(product_max_value)) && (product_max_value != "-1")) {
              error_content = _t("Maximum ") +  product_max_value + _t(" product quantities allowed :- ") + product_name
              $(this).val(product_max_value)
              $(this).trigger('change')
              return false
            }
          }
          else if ((cart_product_quant < conf_product_min_quant) && (conf_product_min_quant != '-1')) {
            error_content = _t("Minimum of ") + conf_product_min_quant +  (" product quantities are required :- ") + product_name
            $(this).val(conf_product_min_quant)
            $(this).trigger('change')
  
          }
          else if ((cart_product_quant > conf_product_max_quant) && (conf_product_max_quant != '-1')) {
            error_content = _t("Maximum ") +  conf_product_max_quant +  _t(" product quantities allowed :- ") + product_name
            $(this).val(conf_product_max_quant)
            $(this).trigger('change')
          }
          if (!$(".is_amount_valid").attr('is_amount_valid')) {
            if (pricelist_val){
              error_content = _t("A minimum purchase total of ") + pricelist_symbol + " " + pricelist_val + _t(" is required to validate your order, current purchase total is ") + pricelist_symbol + " " + cart_value
          }
          else{
            error_content = _t("A minimum purchase total of ") + currency_symbol + " " + conf_value + _t(" is required to validate your order, current purchase total is ") + currency_symbol + " " + cart_value
          }
        }
        }
        )
        var $link = $(this);
        if (error_content) {
          ev.preventDefault();
          $(this).popover({
            title: _t("WARNING!!"),
            placement: "top",
            trigger: 'focus',
            content: error_content,
          });
          $(this).popover('show');
        }
        setTimeout(function () { $link.popover("dispose"); }, 3000);
        error_content = _t("A minimum purchase total of ") + currency_symbol + " " + conf_value + _t(" is required to validate your order, current purchase total is ") + currency_symbol + " " + cart_value
      }
    })

   

    $('.oe_website_sale').on('click', 'a[href$="/shop/checkout?express=1"]', function (ev) {

      var conf_value = $('.oe_website_sale').find('.wk_cart_values span.oe_currency_value').slice(0, 1).text();
      var pricelist_symbol = $('.oe_website_sale').find('.wk_min_price_value').attr('currency_symbol');
        var pricelist_val = $('.oe_website_sale').find('.wk_min_price_value').attr('conf_value')
      var cart_value = $('#order_total').find('.oe_currency_value').text();
      var thousand_sep = new RegExp(escapeRegExp(constraints.thousands_sep), "g")
      var decimal_sep = new RegExp(escapeRegExp(constraints.decimal_point), "g")
      var cart = parseFloat(cart_value.replace(thousand_sep, '').replace(decimal_sep, '.'))
      var check = parseFloat(conf_value.replace(thousand_sep, '').replace(decimal_sep, '.'))
      var currency_symbol = $('.oe_website_sale').find('.wk_cart_values').attr('currency_symbol');
      var conf_wk_min_quant_values = $('.wk_min_quant_values').attr('conf_value')
      var conf_wk_max_quant_values = $('.wk_max_quant_values').attr('conf_value')
      var cart_quant_val = $('.oe_website_sale').find('.js_quantity')

      var error_content
      cart_quant_val.each(function () {
        var cart_product_quant = parseInt($(this).val())
        var product_min_value = $(this).parents('tr').find(".min_max_validate").attr('min_value')
        var product_max_value = $(this).parents('tr').find(".min_max_validate").attr('max_value')
        var enable_limit_template = $(this).parents('tr').find(".min_max_validate").attr('enable_limit_template')
        var curent_varient_count = $(this).parents('tr').find(".varient_limit").attr('current_varient_len')
        var max_varient_quant = $(this).parents('tr').find(".varient_limit").attr('max_varient')
        var min_varient_quant = $(this).parents('tr').find(".varient_limit").attr('min_varient')
        var enable_limit = $(this).parents('tr').find(".varient_limit").attr('enable_limit')
        var conf_product_min_quant = parseInt(conf_wk_min_quant_values)
        var conf_product_max_quant = parseInt(conf_wk_max_quant_values)
        var product_name = $(this).parents('tr').find("strong").text()

        if (((max_varient_quant != undefined) || (min_varient_quant != undefined)) && (enable_limit)) {
          if (cart_product_quant < parseInt(min_varient_quant) && (min_varient_quant != "-1")) {
            error_content = _t("Minimum of ") + min_varient_quant + _t("product quantities are required :- ") + product_name
            $(this).val(min_varient_quant)
            $(this).trigger('change')
            return false
          }
          else if (cart_product_quant > parseInt(max_varient_quant) && (max_varient_quant != "-1")) {
            error_content = _t("Maximum") + max_varient_quant + _t("product quantities allowed :- ") + product_name
            $(this).val(max_varient_quant)
            $(this).trigger('change')
            return false
          }
        }

        else if (((product_min_value != undefined) || (product_max_value != undefined)) && (enable_limit_template)) {
          if ((cart_product_quant < parseInt(product_min_value)) && (product_min_value != "-1")) {
            error_content = _t("Minimum of ") + product_min_value +  _t("product quantities are required :- ") + product_name
            $(this).val(product_min_value)
            $(this).trigger('change')
            return false

          }
          else if ((cart_product_quant > parseInt(product_max_value)) && (product_max_value != "-1")) {
            error_content = _t("Maximum") +  product_max_value + _t("product quantities allowed :- ") + product_name
            $(this).val(product_max_value)
            $(this).trigger('change')
            return false
          }
        }
        else if ((cart_product_quant < conf_product_min_quant) && (conf_product_min_quant != '-1')) {
          error_content = _t("Minimum of ") + conf_product_min_quant + _t(" product quantities are required :- ") + product_name
          $(this).val(conf_product_min_quant)
          $(this).trigger('change')

        }
        else if ((cart_product_quant > conf_product_max_quant) && (conf_product_max_quant != '-1')) {
          error_content = _t("Maximum ") + conf_product_max_quant + _t(" product quantities allowed :- ") + product_name
          $(this).val(conf_product_max_quant)
          $(this).trigger('change')
        }
        if (!$(".is_amount_valid").attr('is_amount_valid')) {
          if (pricelist_val){
            error_content = _t("A minimum purchase total of ") + pricelist_symbol + " " + pricelist_val + _t(" is required to validate your order, current purchase total is ") + pricelist_symbol + " " + cart_value
        }
        else{
          error_content = _t("A minimum purchase total of ") + currency_symbol + " " + conf_value + _t(" is required to validate your order, current purchase total is ") + currency_symbol + " " + cart_value
        }
        }
      }
      )
      var $link = $(this);
      if (error_content) {
        ev.preventDefault();
        $(this).popover({
          title: _t("WARNING!!"),
          placement: "top",
          trigger: 'focus',
          content: error_content,
        });
        $(this).popover('show');
      }
      setTimeout(function () { $link.popover("dispose"); }, 3000);
    });

    var totalPriceElem = $('span#sub_total');
    var quantityField = $('.css_quantity input[type="text"].quantity');
    var defaultPrice = $(".css_editable_mode_hidden .oe_price");

    var price;

    function numberWithCommas(x, dec_point, thousands_sep, grouping) {
      //[3,3],,,[3,0],,,[] => three cases are there for now in odoo
      //Implemented for speciific these cases

      var parts = x.toString().split(dec_point);
      grouping = grouping.slice(1, grouping.length - 1); // grouping == string, sliced '[' & ']'

      if (grouping.length == 0) {
        parts[0] = parts[0].replace(/\B(?=(\d{0})+(?!\d))/g, thousands_sep);
      }
      else if (grouping.length == 3 && grouping[0] == '3' && grouping[2] == '0') {
        parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, thousands_sep);
      }
      else {
        let len = parts[0].length;
        if (len <= 3) { }
        else if (len <= 6 && len >= 4) {
          let part_last = parts[0].slice(-3);
          parts[0] = parts[0].slice(0, len - 3) + thousands_sep + part_last;
        }
        else if (len > 6) {
          let part_last_1 = parts[0].slice(-3);
          let part_last_2 = parts[0].slice(-6, -3);
          parts[0] = parts[0].slice(0, len - 6) + thousands_sep + part_last_2 + thousands_sep + part_last_1;
        }
        else { }
      }
      return parts.join(dec_point);
    }


    defaultPrice.on('DOMSubtreeModified', function () {
      try {
        rpc('/website/wk_lang', {
          'code': code
        })
          .then(function (res) {
            const dec_point = res.decimal_point;
            const thousands_sep = res.thousands_sep;
            const grouping = res.sep_format;

            if (dec_point == '.') {
              price = defaultPrice.text().split(thousands_sep).join('');
              totalPriceElem.text(res.symbol + " " + numberWithCommas((quantityField.val() * price.replace(res.symbol, "")).toFixed(2), dec_point, thousands_sep, grouping));
            }
            else if (dec_point == ',') {
              price = defaultPrice.text().split(thousands_sep).join('');
              price = price.replace(',', '.');
              price = (quantityField.val() * price).toFixed(2);
              price = price.replace('.', ',');
              totalPriceElem.text(numberWithCommas(price, dec_point, thousands_sep, grouping));
            }
          });

      } catch (e) {
        console.error(e);
      }
    });
    publicWidget.registry.WebsiteSale.include({
      onChangeVariant: async function (ev) {
    
        var res = await this._super.apply(this, arguments);
        var $parent = $(ev.target).closest(".js_product");
        return res;
      },
      _onChangeCombination: async function (ev, $parent, combination) {
        
        var res = this._super.apply(this, arguments);
        var variant_code=combination.variant_code
        $("#msg_div").text(variant_code)
       
        return res
      },
    })
  });
// });
