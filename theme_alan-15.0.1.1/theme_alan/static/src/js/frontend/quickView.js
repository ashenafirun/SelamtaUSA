odoo.define('theme_alan.quick_view', function (require) {
'use strict';

var publicWidget = require('web.public.widget');
var quickProdView = require('theme_alan.as_quick_product_view');
const webUtils = require('web.utils');

publicWidget.registry.quick_view = publicWidget.Widget.extend({
    'selector':'#wrapwrap',
    events : {
        "click a.as-quick-view": "_quickView",
    },
    _quickView:function(ev){
        var productId = $(ev.currentTarget).attr('data-product-id');
        $(ev.currentTarget).addClass("as-btn-loading");
        return this._rpc({
            route: '/get/quick_product_view',
            params: {'productId':productId ,'viewType':'as-quick-view'}
        }).then(function (response) {
            var quickView = new quickProdView(this,{
                    subTemplate:webUtils.Markup(response['template']),
                    size:'large',
                    viewType:'quick-view'
                });
            quickView.open();
            $(ev.currentTarget).removeClass("as-btn-loading");
        });
    },
});
});