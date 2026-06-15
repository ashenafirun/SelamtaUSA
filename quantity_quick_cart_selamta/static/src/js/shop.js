/** @odoo-module **/

    import publicWidget from "@web/legacy/js/public/public_widget";
    import website_sale_utils from "@website_sale/js/website_sale_utils";
    import { rpc } from "@web/core/network/rpc";

    publicWidget.registry.WebsiteSale.include({

        events: Object.assign({}, publicWidget.registry.WebsiteSale.prototype.events || {}, {
            "click .sh_add_cart, .sh_add_cart_dyn, .sh_add_cart_list": "_onClickAddDirectCart",
            'change input[name="add_qty"]': '_onChangeAddQuantity',
        }),

        start: function(){
            this._super.apply(this, arguments);
            this.$('.quick_add_pop_view_list[data-bs-toggle="popover"]').popover({
                delay: {
                  "show": 200,
                  "hide": 2000
                }
            });
        },

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
                    return rpc("/shop/cart/update_json", {
                                product_id: productId,
                                line_id: line_id,
                                add_qty: $el.closest("form").find(".quantity").val() || 1.0,
                        })
                        .then(function (data) {
                            var $q = $(".my_cart_quantity");
                            if (data.cart_quantity) {
                                $q.parents("li:first").removeClass("d-none");
                                $(".o_wsale_my_cart").show();
                                $(".my_cart_quantity").text(data.cart_quantity);
                            }
                            website_sale_utils.animateClone($(".o_wsale_my_cart"), $el.closest("form"), 20, 10);
                            website_sale_utils.updateCartNavBar(data);
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
            var $input = $link.closest('input[name="add_qty"]');
            var data = $input.val();
            var default_value = $input.data('setqty');
            if(parseInt(data) < parseInt(default_value)){
                $input.val(default_value);
                $('.sh-min-qty-toast').remove();
                var $toast = $('<div class="sh-min-qty-toast alert alert-warning alert-dismissible fade show" role="alert" style="position:fixed;bottom:20px;right:20px;z-index:9999;min-width:320px;box-shadow:0 4px 12px rgba(0,0,0,0.15);"><i class="fa fa-exclamation-triangle me-2"></i> Minimum order quantity for this product is <strong>' + default_value + ' units</strong>. Your quantity has been updated.<button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>');
                $('body').append($toast);
                setTimeout(function(){ $toast.fadeOut(500, function(){ $(this).remove(); }); }, 4000);
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
                    $input.val(set_data);
                }
            }
        },
    });
