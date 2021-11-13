odoo.define('theme_alan.similar_product', function (require) {
'use strict';

var publicWidget = require('web.public.widget');
var VariantMixin = require('website_sale.VariantMixin');
var Dialog = require('web.Dialog');
const webUtils = require('web.utils');

var similarProduct =  Dialog.extend(VariantMixin, {
    template: 'theme_alan.core_front_dialog',
    xmlDependencies: Dialog.prototype.xmlDependencies.concat([
        '/theme_alan/static/src/xml/core_front_dialog.xml', ]),
    events: _.extend({}, Dialog.prototype.events, { 'click .as_close':'close' }),
    willStart:function(){
        return this._super.apply(this, arguments).then(() => {
            this.$modal.addClass("as-similar-product-modal as-side-modal as-modal").removeClass("o_technical_modal");
        })
    },
    init: function (src, opts) {
        let initData = { subTemplate: opts.subTemplate || "", renderHeader: 0, renderFooter: 0, backdrop: true }
        this._super(src, _.extend(initData));
        this.options = opts;
    },
});

publicWidget.registry.similar_Product = publicWidget.Widget.extend(VariantMixin,{
    'selector':'#wrapwrap',
    'events':{ 'click a.o_alter_view':'_getAlternativeProduct' },
    _getAlternativeProduct:function(ev){
        var cr = this;
        var prod_temp_id = $(ev.currentTarget).attr('data-product_template_id');
        $(ev.currentTarget).addClass("as-btn-loading");
        cr._rpc({
            route: '/json/alternative_product/',
            params: { 'prod_tmp_id':prod_temp_id }
        }).then(function (response) {
            var similarDialog = new similarProduct(cr,{
                subTemplate:webUtils.Markup(response['quickAlterTemp'])});
                similarDialog.open();
                $(ev.currentTarget).removeClass("as-btn-loading");
        });
    }
});
});