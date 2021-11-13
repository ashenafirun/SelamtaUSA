odoo.define('theme_alan.quick_add_to_cart', function (require) {
'use strict';

var publicWidget = require('web.public.widget');
var quickProdView = require('theme_alan.as_quick_product_view');
const webUtils = require('web.utils');

publicWidget.registry.quick_add_to_cart = publicWidget.Widget.extend({
    'selector':'#wrapwrap',
    events : {
        "click a.as-quick-submit": "_quickAddToCart",
    },
    _quickAddToCart:function(ev){
        $(ev.currentTarget).addClass("as-btn-loading");
        var hasVariant = $(ev.currentTarget).attr('data-has-variant');
        var productId = $(ev.currentTarget).attr('data-product-id');
        if(hasVariant != "False"){
            this._quickVariantView(ev, hasVariant, productId);
        }else{
            var qac = new quickProdView(this,{});
            qac.quickAddCartDialog({'product_id':productId, 'show_direct':true,"currentTarget": ev.currentTarget});
        }
    },
    _quickVariantView:function(ev, hasVariant, productId){
        return this._rpc({
            route: '/get/quick_product_view',
            params: { 'hasVariant':hasVariant, 'productId':productId ,'viewType':'as-quick-add-to-cart'}
        }).then(function (response) {
            var qac = new quickProdView(this,{
                    subTemplate: webUtils.Markup(response['template']),
                    size:'large',
                    viewType:'quick-add-cart'
                });
            qac.open();
            $(ev.currentTarget).removeClass("as-btn-loading");
        });
    }
});
});