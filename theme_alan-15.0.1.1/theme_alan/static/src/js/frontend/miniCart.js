odoo.define('theme_alan.mini_cart', function (require) {
"use strict";

const publicWidget = require('web.public.widget');
const { AjaxAddToCart }  = require('theme_alan.core_mixins');
const alanMiniCart  = require('theme_alan.as_mini_cart_base');
const webUtils = require('web.utils');

publicWidget.registry.as_mini_cart = publicWidget.Widget.extend(AjaxAddToCart, {
    selector:".as-mini-cart",
    events:{
        'click':'_openMiniCart'
    },
    _openMiniCart:function(ev){
        $(ev.currentTarget).addClass("as-btn-loading")
        this._alanMiniCart().then((response) => {
            var miniCart = new alanMiniCart(this,{
                subTemplate:webUtils.Markup(response['template']),
                size:'large',
            });
            miniCart.open();
            $(ev.currentTarget).removeClass("as-btn-loading")
        })
    }
});
});