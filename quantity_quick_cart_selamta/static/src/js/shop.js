
import publicWidget from "@web/legacy/js/public/public_widget";
import WebsiteSale from '@website_sale/js/website_sale';
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import wSaleUtils from '@website_sale/js/website_sale_utils';
import { Component } from "@odoo/owl";

publicWidget.registry.WebsiteSale.include({

//    	events: _.extend({}, publicWidget.registry.WebsiteSale.prototype.events || {}, {
//            "click .sh_add_cart, .sh_add_cart_dyn, .sh_add_cart_list": "_onClickAddDirectCart",
//            'change input[name="add_qty"]': '_onChangeAddQuantity',
//        }),

        _onClickAddDirectCart: function (ev) {
            ev.preventDefault();
            if($(ev.currentTarget).hasClass('out_of_stock')) { return; }
            this._addNewProducts($(ev.currentTarget));
        },

        /**
         * @private
         */

        _addNewProducts: function ($el) {
            var self = this;
            var productID = $el.data("product-product-id");
            if ($el.hasClass("sh_add_cart_dyn")) {
                productID = $el.parent().find(".product_id").val();
                if (!productID) {
                    // case List View Variants
                    productID = $el.parent().find("input:checked").first().val();
                }
                productID = parseInt(productID, 10);
            }

            var $form = $el.closest("form");
            var templateId = $form.find(".product_template_id").val();
            // when adding from /shop instead of the product page, need another selector
            if (!templateId) {
                templateId = $el.data("product-template-id");
            }
            var productReady = this.selectOrCreateProduct($el.closest("form"), productID, templateId, false);
            var line_id = parseInt($el.data("line-id"), 10);

            productReady.then(function (productId) {
                productId = parseInt(productId, 10);
                if (productId) {
                    return self
                        ._rpc({
                            route: "/shop/cart/update_json",
                            params: {
                                product_id: productId,
                                line_id: line_id,
                                add_qty: $el.closest("form").find(".quantity").val() || 1.0,
                            },
                        })
                        .then(function (data) {
                            var $q = $(".my_cart_quantity");
                            if (data.cart_quantity) {
                                $q.parents("li:first").removeClass("d-none");
                                $(".o_wsale_my_cart").show();
                                $(".my_cart_quantity").text(data.cart_quantity);
                            }
                            wSaleUtils.animateClone($(".o_wsale_my_cart"), $el.closest("form"), 20, 10);
                        });
                }
            });
        },

        //--------------------------------------------------------------------------
        // Handlers
        //--------------------------------------------------------------------------

        _onChangeAddQuantity: function (ev) {
            ev.preventDefault();
            var $link = $(ev.currentTarget);
         	var data = $link.closest('input[name="add_qty"]').val();
         	var default_value = $link.closest('input[name="add_qty"]').data('setqty');
        	if(parseInt(data) < parseInt(default_value)){
        		var set_data = default_value;
//        		document.getElementById("qty_id").value = set_data;
        		$link.closest('input[name="add_qty"]').val(set_data);

        	}
            this._super.apply(this, arguments);
            return false;
        },

        //--------------------------------------------------------------------------
        // Private
        //--------------------------------------------------------------------------

        /**
         * @private override
         */
        _changeCartQuantity: function ($input, value, $dom_optional, line_id, productIDs) {
            this._super.apply(this, arguments);
            var data = value;
            var default_value = $input.data("setqty");
            if (value != 0) {
                if (parseInt(data) < parseInt(default_value)) {
                    var set_data = default_value;
                    //document.getElementById("qty_id").value = set_data;
                    $input.val(set_data);
                }
            }
        },
    });
