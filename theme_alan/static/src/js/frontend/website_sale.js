/** @odoo-module **/

import { markup } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { MiniCart } from "theme_alan.MiniCart";
import { _t } from '@web/core/l10n/translation';
import { QuickView } from "theme_alan.QuickView";
import { ColorVariant} from "theme_alan.ColorVariant";
import { serializeDateTime } from '@web/core/l10n/dates';
import publicWidget from "@web/legacy/js/public/public_widget";
import VariantMixin from "@website_sale/js/sale_variant_mixin";
import { deserializeDateTime } from "@web/core/l10n/dates";

const { DateTime } = luxon;

// Load More
export const AjaxProductLoad = publicWidget.Widget.extend({
    selector:".as_shop_page",
    disabledInEditableMode: false,
    events:{
        'click #loadMoreproducts':'_loadProduct'
    },

    init: function () {
        this._super.apply(this, arguments);
        this.rpc = rpc;
    },

    InitLoadProducts:function(){
        this.next_products = false;
        this.pager = false;
        this.rmn_ids = []
        var $next_page = $(".alan_pager").find("li.active").next();
        var prd_ids = $next_page.data('prd_ids')
        let next_url = $next_page.find("a").attr("href");

        if(next_url == undefined || next_url == "" || prd_ids == undefined || prd_ids == ""){
            this.$target.find("#loadMoreproducts").hide();
            this.$target.find(".all_loaded").removeClass('d-none').empty().append("All products are loaded.")
        }
        else{
            this.$target.find(".all_loaded").addClass('d-none').empty()
            var ppr = $next_page.data('ppr')
            var $lasttr = this.$target.find(".o_wsale_products_grid_table_wrapper").find("tbody tr:last").find('td')
            if ($lasttr.length < ppr){
                for (let i = 0; i < $lasttr.length; i++) {
                    this.rmn_ids.push(parseInt($($lasttr[i]).find('.product_ref_id').val()))
                }
            }
            var products = this.$target.find(".o_wsale_products_grid_table_wrapper").find('input.product_ref_id').map(function(){return parseInt($(this).val());}).get();
            var all_prds = $.merge(this.rmn_ids, prd_ids)
            this.rpc("/nextpage/products",{
                        'product_ids': all_prds,
                        'products': products,
                        'ppr': ppr,
                    }
            ).then( (result) => {
                if(result){
                    this.next_products = result;
                }
            });
        }
    },

    _loadProduct:function(){
        if(this.next_products != false){
            var $active_page = $(".alan_pager").find("li.active");
            var $next_page = $(".alan_pager").find("li.active").next();
            var ppr = $next_page.data('ppr')
            // var $lasttr = this.$target.find(".o_wsale_products_grid_table_wrapper").find("tbody tr:last").find('td')
            // if ($lasttr.length < ppr){
            //     this.$target.find(".o_wsale_products_grid_table_wrapper").find("tbody tr:last").remove()
            // }
            this.$target.find(".o_wsale_products_grid_table_wrapper").find("section").append(this.next_products);
            $active_page.removeClass('active');
            $next_page.addClass('active');
        }
        this.InitLoadProducts();
        this.trigger_up('widgets_start_request', {
            $target:$('.as_similar_product'),
        });
        this.trigger_up('widgets_start_request', {
            $target:$('.o_wsale_product_grid_wrapper'),
        });
        this.trigger_up('widgets_start_request', {
            $target:$('.as_offer_timer')
        });
    },
    start:function(){
        this.InitLoadProducts();

    }
});
publicWidget.registry.AjaxProductLoad = AjaxProductLoad;

//  Scroll Top
export const ScrolltoTop = publicWidget.Widget.extend({
    'selector': '#wrapwrap',
    'events':{
        'click .as_scroll_to_top, .as-scroll-top' : '_scroll2Top',
        'scroll': '_scroll2TopVisibility',
    },
    _scroll2TopVisibility:function(){
        if(this.$target.scrollTop() > 800){
            this.$target.find(".as_scroll_to_top").addClass("as_scroll_show");
        }else{
            this.$target.find(".as_scroll_to_top").removeClass("as_scroll_show");
        }
    },
    _scroll2Top:function(){
        $("html, body").animate({ scrollTop: 0 }, 500);
    }
});
publicWidget.registry.ScrolltoTop = ScrolltoTop;

//Similar Product
export const AlanSimilarProduct = publicWidget.Widget.extend({
    selector: '.as_similar_product',
    disabledInEditableMode: false,
    events : {
        'click':'_show_similar',
    },
    _show_similar:function(ev){
        var template = rpc('/get_similar_product', { product_id: parseInt($(ev.currentTarget).attr('data-product_tmpl_id')) });
        Promise.all([template]).then((response) => {
            $(".offcanvas_similar_product").append(markup(response[0]))
        });
    }
})
publicWidget.registry.AlanSimilarProduct = AlanSimilarProduct;

// Color Variant Icon
export const ShopVariantColor = publicWidget.Widget.extend({
    selector: '.as_color_variant',
    disabledInEditableMode: false,
    events : {
        'mouseenter .as_color_variant_img':'_show_color_image',
        'mouseleave .as_color_variant_img':'_show_default_image',
        'click .as_color_variant_img':'_show_color_variant',
    },
    _show_color_image:function(ev){
        let color_image = $(ev.currentTarget).find("[data-color-image]").attr("data-color-image");
        let $img = this.$target.find(".oe_product_image_img_wrapper > img");
        let default_url = $img.attr("src");
        this.$target.attr("data-default-src",default_url);
        $img.attr("src", color_image);
    },
    _show_default_image:function(ev){
        let default_url = this.$target.attr("data-default-src");
        this.$target.find(".oe_product_image_img_wrapper > img").attr("src", default_url);
    },
    _show_color_variant:function(ev){
        var template = rpc('/get_color_product', { product_id: parseInt($(ev.currentTarget).attr('data-product_tmpl_id')) });
        let content = []
        Promise.all([template]).then((response) => {
            content = response
            this.call("dialog", "add", ColorVariant, {
                body: markup(content[0]),
            })
        });
    }
})
publicWidget.registry.ShopVariantColor = ShopVariantColor;

// Offer Timer
export const AlanOfferTimer =  publicWidget.Widget.extend({
    selector: ".as_offer_timer",
    disabledInEditableMode: false,
    start: function() {
        if(!this.editableMode){
            if(this.$target.attr("data-offer")!= 'false'){

                var asOfferTimer = setInterval(function () { this.call("offer_timer", "create", {target: this.$target, offerDate: this.$target.attr("data-offer")})}.bind(this), 1000);
                let get_timer_info = sessionStorage.getItem("as_timer_ids");
                var get_timer_ids = [];
                if (get_timer_info) {
                    get_timer_ids = JSON.parse(get_timer_info) || [];
                }
                if (get_timer_ids.indexOf(asOfferTimer) == -1) {
                    get_timer_ids.push(asOfferTimer);
                    sessionStorage.setItem("as_timer_ids", JSON.stringify(get_timer_ids));
                }
            }
            else{
                let storedTimerInfo = sessionStorage.getItem("as_timer_ids");
                if (storedTimerInfo) {
                    let storedTimerIds = JSON.parse(storedTimerInfo);
                    storedTimerIds.forEach(intervalId => {
                        clearInterval(intervalId);
                    });
                }
                sessionStorage.removeItem("as_timer_ids");
            }
        }
        else{
            let timer_info = sessionStorage.getItem("as_timer_ids");
            if(timer_info !=  undefined){
                let timer_ids = JSON.parse(timer_info)
                for (const time_id of timer_ids) {
                    clearInterval(time_id);
                }
            }
            this.$target.empty();
        }
    },

});
publicWidget.registry.AlanOfferTimer = AlanOfferTimer;

// Quick View
export const AlanQuickView = publicWidget.Widget.extend({
    selector: '.as_quick_view',
    disabledInEditableMode: false,
    events : {
        'click':'_show_quick_view',
    },

    _show_quick_view: async function(ev){
        var productSelector = [
            'input[type="hidden"][name="product_id"]',
            'input[type="radio"][name="product_id"]:checked'
        ];
        const $form = $(ev.currentTarget).closest('form')
        const productTemplateId = parseInt($form.find('input[type="hidden"][name="product_template_id"]').first().val());
        const product_custom_attribute_values = VariantMixin.getCustomVariantValues($form.find('.js_product'))
        const variant_values = VariantMixin.getSelectedVariantValues($form.find('.js_product'))
        this.call('dialog', 'add', QuickView, {
            productTemplateId: productTemplateId,
            ptavIds: variant_values,
            customPtavs: product_custom_attribute_values.map(
                customPtav => ({
                    id: customPtav.custom_product_template_attribute_value_id,
                    value: customPtav.custom_value,
                })
            ),
            quantity: 1,
            soDate: serializeDateTime(DateTime.now()),
            edit: false,
            isFrontend: true,
            options: false,
            discard: () => {},
        });
    },

})
publicWidget.registry.AlanQuickView = AlanQuickView;

// Mini Cart
export const AlanMiniCart = publicWidget.Widget.extend({
    selector: ".as_mini_cart",
    events:{
        'click':'_show_mini_cart',
    },
    _show_mini_cart:function(ev){
        ev.preventDefault();
        this.call('dialog', 'add', MiniCart)
    },
});
publicWidget.registry.AlanMiniCart = AlanMiniCart;

// Attribute Search
export const AttributeSearch = publicWidget.Widget.extend({
    selector:'.as_filter_search',
    events:{
        'keyup':'_search_attribute'
    },
   _search_attribute(ev) {
    let curr_val = this.$target.val().toLowerCase();
    let $item = $(ev.target).parents(".accordion-item");

    let $attrs = $item.find("label.form-check-label");
    let $color = $item.find("label.css_attribute_color");
    let $brands = $item.find("label.as_brand_attr_image");

    if ($attrs.length > 0) {
        $attrs.each((index, iter) => {
            let attr = $(iter).text().toLowerCase();
            $(iter).parent('.form-check').toggleClass("d-none", !attr.includes(curr_val));
        });
    }

    if ($color.length > 0) {
        $color.each((index, iter) => {
            let attr = $(iter).find("input").attr("title").toLowerCase();
            $(iter).toggleClass("d-none", !attr.includes(curr_val));
        });
    }

    if ($brands.length > 0) {
        $brands.each((index, iter) => {
            let attr = $(iter).attr('data-name').toLowerCase();
            $(iter).toggleClass("d-none", !attr.includes(curr_val));
        });
    }
}

})
publicWidget.registry.AttributeSearch = AttributeSearch;

//  Clear Filter
export const AlanClearFilter = publicWidget.Widget.extend({
    selector:".o_wsale_products_page",
    events:{
        'click .as-clear-filter':'_clearFilter',
    },
    _clearFilter:function(ev){
        const fieldName = $(ev.currentTarget).data("name");
        const fieldValue = $(ev.currentTarget).data("value");
        const $filterForm = this.$target.find("form.js_attributes");
        const $input = $filterForm.find('input[name="'+fieldName+'"][value="' + fieldValue + '"]');
        if($input.length == 0){
            const $option = $filterForm.find('option[value=' + fieldValue + ']');
            $option.closest('select').val('').trigger("change");
        }
        $input.prop('checked', false);
        $input.trigger("change");
    },
    start: function () {
        new Swiper(".as_wsale_filmstip", {
            slidesPerView: "auto",
            spaceBetween: 10,
            loop: true,
            autoplay: {
                delay: 3000,
                disableOnInteraction: false,
            },
            navigation: {
              nextEl: ".swiper-button-next",
              prevEl: ".swiper-button-prev",
            },
        });
        return this._super.apply(this, arguments);
    },

});
publicWidget.registry.alanClearFilter = AlanClearFilter;

export default {
    AjaxProductLoad: publicWidget.registry.AjaxProductLoad,
    ScrolltoTop: publicWidget.registry.ScrolltoTop,
    AlanSimilarProduct: publicWidget.registry.AlanSimilarProduct,
    ShopVariantColor: publicWidget.registry.ShopVariantColor,
    AlanOfferTimer: publicWidget.registry.AlanOfferTimer,
    AlanQuickView: publicWidget.registry.AlanQuickView,
    AlanMiniCart: publicWidget.registry.AlanMiniCart,
    AttributeSearch: publicWidget.registry.AttributeSearch,
    AlanClearFilter:publicWidget.registry.alanClearFilter,
};
