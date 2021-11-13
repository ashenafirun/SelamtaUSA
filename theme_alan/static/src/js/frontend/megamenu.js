odoo.define('theme_alan.megamenu', function (require) {
"use strict";

const publicWidget = require('web.public.widget');
const webUtils = require('web.utils');
const { AlanTemplateGetter,
        FetchProductsData,
        FetchCategoryData,
        BaseAlanQweb } = require("theme_alan.core_mixins");

publicWidget.registry.mega_menu = publicWidget.Widget.extend(AlanTemplateGetter, FetchProductsData, FetchCategoryData, BaseAlanQweb, {
    selector:'.as-dynamic-megamenu',

    start: function(editable_mode){
        var cr = this;
        cr.getMegaContent();
    },

    getMegaContent: function() {
        var cr = this;
        var contentType = cr.$target.attr("data-mega-popup");
        var mega_ui = cr.$target.attr("data-mega-ui");
        var col_ui = cr.$target.attr("data-col-ui");
        if (contentType == "theme_alan.product_mega_modal") {
            var prod_ids = cr.$target.attr("data-record-ids");
            var mega_view = cr.$target.attr("data-prod-mega-view");
            cr._fetchProductRawData(prod_ids,"product.template").then((rec) =>{
                if(rec != undefined){
                    let clean_res = []
                    rec.forEach(ele => {
                        ele['price'] = webUtils.Markup(ele['price'])
                        clean_res.push(ele);
                    })
                    let data = { "mega_ui":mega_ui, "prod_ids":prod_ids, "col_ui":col_ui,
                        "mega_data":clean_res, 'is_dynamic':true }
                    if(mega_view == "list"){
                        cr._getAlanTemplate("atharva_theme_base","as_mm_product_list",data).then((res) =>{
                            cr.$el.parent().empty().append(res['template']);
                        });
                    }else if(mega_view == "grid"){
                        cr._getAlanTemplate("atharva_theme_base","as_mm_product_grid",data).then((res) =>{
                            cr.$el.parent().empty().append(res['template']);
                        });
                    }else{
                        alert("Something went wrong!")
                    }
                }
            });
        }
        else if(contentType == "theme_alan.category_mega_modal"){
            var view = cr.$target.attr("data-cat-mega-view");
            var cat_data = cr.$target.attr("data-record-ids");
            var cat_ids = cr.$target.attr("data-cat-seq");
            var catData = cat_data.replace(/'/g, '"');
            cr._fetchMegaCategoryTemplate(view,catData,mega_ui,col_ui,cat_ids).then((rec) => {
                cr.$el.parent().empty().append(rec['template']);
            });
        }
    },
});
});