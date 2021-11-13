odoo.define('theme_alan.product_core', function (require) {
"use strict";

const publicWidget = require('web.public.widget')
const wSaleUtils = require('website_sale.utils');
const NavCartUpdate = wSaleUtils.updateCartNavBar;
const { AjaxAddToCart }  = require('theme_alan.core_mixins');

publicWidget.registry.as_product_details = publicWidget.Widget.extend(AjaxAddToCart, {
    selector:"#wrapwrap",
    'events':{
        'click a.img-gallery-tag':'_productImageClick',
        'click a.video-gallery-tag':'_productVideoClick',
        'click a#add_to_cart_cp_btn':'_stickyAddToCart',
        'click #as-scroll-top':'_asScrollTop',
        'click a#buy_now_cp_btn':'_stickyBuyNow',
        'click .o_website_rating_static':'_productRating',
        'scroll':'_stickyCart'
    },
    start: function () {
        return this._super.apply(this, arguments).then(() => {
            var alterna_and_access = new Swiper(".as-al-ass-swiper", {
                slidesPerView: 2,
                spaceBetween: 10,
                navigation: {
                  nextEl: ".swiper-button-next",
                  prevEl: ".swiper-button-prev",
                },
                breakpoints: {
                  640: {
                    slidesPerView: 2,
                  },
                  768: {
                    slidesPerView: 4,
                  },
                  1024: {
                    slidesPerView: 3,
                  },
                },
            });
        });
    },
    _productImageClick:function(e){
        e.preventDefault();
        $(e.currentTarget).parent().parent().magnificPopup({
            delegate: 'a',
            type: 'image',
            gallery: {
                enabled: true,
            }
        })
    },
    _productVideoClick:function(e){
        e.preventDefault();
        $(e.currentTarget).parent().magnificPopup({
            delegate: 'a',
            disableOn: 700,
            type: 'iframe',
            mainClass: 'mfp-fade',
            removalDelay: 160,
            preloader: false,
            fixedContentPos: false
        });
    },
    _stickyAddToCart:function(ev){
        const product_id = $(ev.currentTarget).closest("form").find("input[name='product_id']").val();
        this._alanAddToCart({"product_id" : product_id,"add_qty":1}).then(data =>{
            NavCartUpdate(data);
            location.href = "/shop/cart";
        })
    },
    _stickyBuyNow:function(){
        this.$target.find(".o_we_buy_now").trigger("click");
    },
    _asScrollTop:function (ev) {
        $("html, body").animate({ scrollTop: 0 }, "slow");
    },
    _productRating:function(ev){
        this.$target.find("#nav_tabs_link_3").trigger("click");
    },
    _stickyCart:function(ev){
        var cr = this;
        if(cr.$target.find('.as-sticky-cart-active').length != 0 ){
            const top = cr.$target.find('#add_to_cart').offset().top;
            const bottom = cr.$target.find('#add_to_cart').offset().top + cr.$target.find('#add_to_cart').outerHeight();
            const bottom_screen = $(window).scrollTop() + $(window).innerHeight();
            const top_screen = $(window).scrollTop();
            if ((bottom_screen > top) && (top_screen < bottom)){
                if(cr.$target.find('.as-product-sticky-cart').hasClass("as-stikcy-show")){
                    cr.$target.find('.as-product-sticky-cart').removeClass("as-stikcy-show");
                }
            } else {
                if(top < 0){
                    if(!cr.$target.find('.as-product-sticky-cart').hasClass("as-stikcy-show")){
                        cr.$target.find('.as-product-sticky-cart').addClass("as-stikcy-show");
                    }
                }
            }
        }
    }
});
});