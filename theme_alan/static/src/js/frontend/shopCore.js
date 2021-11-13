odoo.define('theme_alan.shop_core', function (require) {
"use strict";

const publicWidget = require('web.public.widget')

publicWidget.registry.as_clear_filter = publicWidget.Widget.extend({
    selector: '.oe_website_sale',
    events:{ 'click .as-clear-filter':'_clearFilter' },
    start:function(){
        $('.as-shop-tags').tooltip({
            template: '<div class="tooltip as-tooltip-white"><div class="arrow"></div><div class="tooltip-inner"></div></div>'
          })
        return this._super.apply(this, arguments).then(() => {
            var catgeory_tag  = new Swiper('.as-shop-top-cat-slider',{
                navigation: {
                    nextEl: ".swiper-button-next",
                    prevEl: ".swiper-button-prev",
                },
                slidesPerView: "auto",
                spaceBetween: 10,
          })
        })
    },
    _clearFilter:function(ev){
        const fieldName = $(ev.currentTarget).data("name");
        const fieldValue = $(ev.currentTarget).data("value");
        const $filterForm = this.$target.find("form.js_attributes");
        const $input = $filterForm.find('input[name="'+fieldName+'"][value="' + fieldValue + '"]');
        if($input == undefined){
            const $option = $filterForm.find('option[value=' + fieldValue + ']');
            $option.closest('select').val('');
        }
        $input.prop('checked', false);
        $filterForm.submit();
    }
});
});