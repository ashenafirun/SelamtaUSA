/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { ProductQueries } from "theme_alan.ProductQueries";
import publicWidget from "@web/legacy/js/public/public_widget";
import { ProductAdvanceInfo } from "theme_alan.ProductAdvanceInfo";

// Product Info
export const ProductDetailInfo = publicWidget.Widget.extend({
    selector:".as-product-details-common",
    events:{
        'scroll':'_stickyCart',
        'click .as_sticky_action':'_sticky_btn',
		'mouseenter .as-pager-prod':'_show_pager_product_info',
        'mouseleave .as-pager-prod':'_hide_pager_product_info',
    },

    start: function () {
        $(window).on('scroll', function() {
            this._stickyCart();
        }.bind(this));

        new Swiper(".as-al-ass-swiper", {
            slidesPerView: 1.75,
            spaceBetween: 10,
            navigation: {
				nextEl: ".swiper-button-ass-next",
				prevEl: ".swiper-button-ass-prev",
            },
            breakpoints: {
				640: {
					slidesPerView: 2,
					spaceBetween: 24,
				},
				768: {
					slidesPerView: 3,
					spaceBetween: 24,
				},
				1024: {
					slidesPerView: 4,
					spaceBetween: 24,
				},

            },
        });

        new Swiper(".as-al-alt-swiper", {
            slidesPerView: 1.75,
            spaceBetween: 10,
            navigation: {
				nextEl: ".swiper-button-alt-next",
				prevEl: ".swiper-button-alt-prev",
            },
            breakpoints: {
				640: {
					slidesPerView: 2,
					spaceBetween: 24,
				},
				768: {
					slidesPerView: 3,
					spaceBetween: 24,
				},
				1024: {
					slidesPerView: 4,
					spaceBetween: 24,
				},
            },
        });
        return this._super.apply(this, arguments);
    },

    _stickyCart:function(){

        var addToCartBtns = this.$target.find('.js_main_product');
        if(this.$target.find('.as-sticky-cart-active').length != 0 && addToCartBtns.length != 0){
            const top = this.$target.find('.js_main_product').offset().top;
            const bottom = this.$target.find('.js_main_product').offset().top + this.$target.find('.js_main_product').outerHeight();
            const bottom_screen = $(window).scrollTop() + $(window).innerHeight();
            const top_screen = $(window).scrollTop();
            if ((bottom_screen > top) && (top_screen < bottom)){

                if(this.$target.find('.as-product-sticky-cart').hasClass("as-stikcy-show")){
                    this.$target.find('.as-product-sticky-cart').removeClass("as-stikcy-show");
                }
            } else {
                if(top){
                    if(!this.$target.find('.as-product-sticky-cart').hasClass("as-stikcy-show")){
                        this.$target.find('.as-product-sticky-cart').addClass("as-stikcy-show");
                    }
                }
            }
        }
        var offset = 450;
        var $back_to_top = $('.as-scroll-to-top');
        ($('#wrapwrap').scrollTop() > offset) ? $back_to_top.addClass('as-bt-visible'): $back_to_top.removeClass('as-bt-visible');
    },

    _sticky_btn:function(ev){
        this.$target.find($(ev.target).data('target_id')).trigger("click");
    },

	_show_pager_product_info(ev){
        if($(ev.currentTarget).attr('id') == "as-pre-prod-info"){
            this.$target.find(".as-pre-prod-info").removeClass("d-none");
        }else{
            this.$target.find(".as-next-prod-info").removeClass("d-none");
        }
    },

    _hide_pager_product_info(ev){
        this.$target.find(".as-pager-prod-info").addClass("d-none")
    },

})
publicWidget.registry.ProductDetailInfo = ProductDetailInfo;

// Product Any Queries
export const AlanProductQueries = publicWidget.Widget.extend({
	selector: '.product_queries',
	disabledInEditableMode: false,
	events : {
		'click #any_queries': '_onClickQueries',
	},

	_onClickQueries:function(){
		let inputproduct = $("#product").val();
		var context = rpc('/product_queries', {product_id: inputproduct})
		Promise.all([context]).then((response) => {
			if (response[0] == false){
				$('.query-msg')[0].classList.remove("d-none");
			}
			else{
				this.call("dialog", "add", ProductQueries, {
                    product_id: inputproduct, user_email:response[0]['user_email'],
                    user_id:response[0]['user_id'],user_name:response[0]['user_name'],
                    dialog_header: response[0]['dialog_header'],
                    dialog_header_desc: response[0]['dialog_header_desc'],
                    acknowledgement_message: response[0]['acknowledgement_message']})
			}
		});
  }
});
publicWidget.registry.AlanProductQueries = AlanProductQueries;

// Product Rating View
export const ParoductRatingView = publicWidget.Widget.extend({
    selector: '.o_website_rating_static',
    events : {
        'click ':'_openReviewsTab',
    },

    start: function () {
        const urlParams = new URLSearchParams(window.location.search);
        const openReviewsTab = urlParams.get('open') == 'reviews';
        if(openReviewsTab){
            this._openReviewsTab();
        }
    },

    _openReviewsTab: function(){
        const reviewsTabButton = document.querySelector('#nav-reviews-tab');
        if (reviewsTabButton) {
            reviewsTabButton.click();
            $('html, body').animate({
                scrollTop: $(".product-details-tabs").offset().top - 100
            }, 800);
        }
    }

})
publicWidget.registry.ParoductRatingView = ParoductRatingView;


// Product Advance Info
export const AlanProductAdvanceInfo = publicWidget.Widget.extend({
    "selector": ".show_advance_product",
    events : {
        "click": "_show_advance_info_dialog"
    },
    _show_advance_info_dialog: function(){
        const data_info_id = parseInt(this.$target.attr("data-info_id"))
        this.call("dialog", "add", ProductAdvanceInfo, { infoId: data_info_id})
    }
});
publicWidget.registry.AlanProductAdvanceInfo = AlanProductAdvanceInfo;

export default {
    ProductDetailInfo: publicWidget.registry.ProductDetailInfo,
    AlanProductQueries: publicWidget.registry.AlanProductQueries,
    ParoductRatingView: publicWidget.registry.ParoductRatingView,
    AlanProductAdvanceInfo: publicWidget.registry.AlanProductAdvanceInfo,
};
