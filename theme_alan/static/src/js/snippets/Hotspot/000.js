/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { QuickView } from "theme_alan.QuickView";
import { HotspotPopover } from "theme_alan.Hotspot";
import { renderToElement } from "@web/core/utils/render";
import { serializeDateTime } from '@web/core/l10n/dates';
import publicWidget from "@web/legacy/js/public/public_widget";

const { DateTime } = luxon;

export const ImgHotSpot = publicWidget.Widget.extend({
    selector:'.hotspot',
    init: function () {
        this._super.apply(this, arguments);
    },

    start:function(ev){
        if(this.$target.find(".hs_icon").hasClass("dynamic_type")){
            if(this.$target.find(".hs_icon").attr("data-dy_type") == "popover"){
                let prod_tmpl_id = this.$target.find(".hs_icon").attr("data-product_tmpl_id");
                var pop_style = this.$target.find(".hs_icon").attr('data-po_style') == undefined ? '' :this.$target.find(".hs_icon").attr('data-po_style');
                if(prod_tmpl_id){
                    rpc('/get_hotspot_product',{'product_tmpl_id':prod_tmpl_id, 'style':pop_style}).then((res)=>{
                        this._showPopover(res['template']);
                    })
                }
            }
            else if(this.$target.find(".hs_icon").attr("data-dy_type") == "modal"){
                let prod_tmpl_id = this.$target.find(".hs_icon").attr("data-product_tmpl_id");
                this.$target.find(".hs_icon").on("click", function(){
                    this.call('dialog', 'add', QuickView, {
                        productTemplateId: parseInt(prod_tmpl_id),
                        ptavIds: [],
                        customPtavs:[],
                        quantity: 1,
                        soDate: serializeDateTime(DateTime.now()),
                        edit: false,
                        isFrontend: true,
                        options: false,
                        discard: () => {},
                    })
                }.bind(this));
            }
        }else if(this.$target.find(".hs_icon").hasClass("static_type")){
            var title = this.$target.find(".hs_icon").attr('data-po_title') == undefined ? '':this.$target.find(".hs_icon").attr('data-po_title');
            var description = this.$target.find(".hs_icon").attr('data-po_desc') == undefined ? '':this.$target.find(".hs_icon").attr('data-po_desc');
            var btn_txt = this.$target.find(".hs_icon").attr('data-po_btxt') == undefined ? '':this.$target.find(".hs_icon").attr('data-po_btxt');

            var language = document.getElementsByTagName("html")[0].getAttribute("lang");
            var activeLang = language.replace(/-/g, "_");

            var data_lang = 'data-lang-'
            var activeLanguage = data_lang.concat("",activeLang);
            if(this.$target.find(".hs_icon").attr(activeLanguage)){
                title = this.$target.find(".hs_icon").attr(activeLanguage) == undefined ? '':this.$target.find(".hs_icon").attr(activeLanguage);
            }

            var data_descr_lang = 'data-description-lang-'
            var activeLanguageDescription = data_descr_lang.concat("",activeLang);
            if(this.$target.find(".hs_icon").attr(activeLanguageDescription)){
                description = this.$target.find(".hs_icon").attr(activeLanguageDescription) == undefined ? '':this.$target.find(".hs_icon").attr(activeLanguageDescription);
            }

            var data_btn_lang = 'data-btn-lang-'
            var activeLanguageBtn = data_btn_lang.concat("",activeLang);
            if(this.$target.find(".hs_icon").attr(activeLanguageBtn)){
                btn_txt = this.$target.find(".hs_icon").attr(activeLanguageBtn) == undefined ? '':this.$target.find(".hs_icon").attr(activeLanguageBtn);
            }

            var btn_url = this.$target.find(".hs_icon").attr('data-po_bturl') == undefined ? '':this.$target.find(".hs_icon").attr('data-po_bturl');
            var img_url = this.$target.find(".hs_icon").attr('data-po_imgurl') == undefined ? '' :this.$target.find(".hs_icon").attr('data-po_imgurl');
            var pop_thm = this.$target.find(".hs_icon").attr('data-po_theme') == undefined ? '' :this.$target.find(".hs_icon").attr('data-po_theme');
            var pop_style = this.$target.find(".hs_icon").attr('data-po_style') == undefined ? '' :this.$target.find(".hs_icon").attr('data-po_style');
            var context = { 'title':title,'description':description,'btn_txt':btn_txt,
                'btn_url':btn_url,'img_url':img_url,'pop_thm':pop_thm, 'pop_style':pop_style }
            if(this.$target.find(".hs_icon").attr("data-st_type") == "popover"){
                let template = $(renderToElement("theme_alan.s_static_hotspot_popover", {data:context}))
                this._showPopover(template);
            }
            else if(this.$target.find(".hs_icon").attr("data-st_type") == "modal"){
                this.$target.find(".hs_icon").on("click",function(){
                    this.call("dialog", "add", HotspotPopover, {data:context})
                }.bind(this));
            }
        }
    },

    _showPopover(template){
        var target = this.$target;
        target.find(".hs_icon").popover({
            html: true,
            container: 'body',
            trigger : 'manual',
            content: $(template),
        }).on("mouseenter", function () {
            $(this).popover("show");
            $(".popover").on("mouseleave", function () {
                target.find(".hs_icon").popover('hide');
            }).addClass("as-popover");
        }).on("mouseleave", function () {
            setTimeout(function () {
                if (!$(".popover:hover").length) {
                    target.find(".hs_icon").popover('hide');
                }
            }, 100);
        });

    }
})
publicWidget.registry.ImgHotSpot = ImgHotSpot;

export default {
    ImgHotSpot: publicWidget.registry.ImgHotSpot,
};
