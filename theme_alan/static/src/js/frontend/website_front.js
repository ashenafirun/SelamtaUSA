/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";
import { _t } from '@web/core/l10n/translation';
import { LoginPopup } from "theme_alan.LoginPopup";
import publicWidget from "@web/legacy/js/public/public_widget";

// Login Popup
export const AlanLoginPopup = publicWidget.Widget.extend({
    selector: ".as_login_popup",
    events:{
        'click':'_show_login_popup',
    },

    _show_login_popup:function(ev){
        ev.preventDefault();
        $(".btn-close").trigger("click");
        this.call("dialog", "add", LoginPopup, {})
    }
})

let AlanSliders = publicWidget.Widget.extend({
    init: function () {
        this._super.apply(this, arguments);
        this.rpc = rpc
    },
    _get_loader:function(){
        var loader = '<div class="card">\
            <svg class="bd-placeholder-img card-img-top" width="100%" height="180" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Placeholder" preserveAspectRatio="xMidYMid slice" focusable="false">\
                <title>Placeholder</title>\
                <rect width="100%" height="100%" fill="#868e96"></rect>\
            </svg>\
            <div class="card-body">\
                <h5 class="card-title placeholder-glow">\
                    <span class="placeholder col-6"></span>\
                </h5>\
                <p class="card-text placeholder-glow">\
                    <span class="placeholder col-7"></span>\
                    <span class="placeholder col-4"></span>\
                    <span class="placeholder col-4"></span>\
                    <span class="placeholder col-6"></span>\
                    <span class="placeholder col-8"></span>\
                </p>\
                <a href="#" tabindex="-1" class="btn btn-primary disabled placeholder col-6"></a>\
            </div>\
        </div>';
        this.$target.empty().append(loader)
    },
    _getProductSlider:function(){
        for (const product_slider of this.$target) {
            let snippet_editor = JSON.parse($(product_slider).attr("data-design-edit"))
            let context = {
                'snippet':$(product_slider).attr("data-snippet-name"),
                'record_ids':JSON.parse($(product_slider).attr("data-records-ids")),
                'modal':$(product_slider).attr("data-modal"),
                'design_editor':snippet_editor,
            }

            if(!this.editableMode){
                rpc('/get_snippet_template', context).then((res)=>{
                    if(this.selector == "[data-snippet-name='CategoryProduct'], [data-snippet-name='categories_products']" || this.selector == "[data-snippet-name='BrandProduct'], [data-snippet-name='brand_products']"){
                        $(product_slider).empty().append(res['template']);
                        var $template = $(product_slider).find('.as_page_swiper')
                        for (let s_templ of $template) {

                            $(s_templ).attr("id",'as_swiper_slider_as');
                            if(Object.keys(res.slider_config).length != 0){
                                new Swiper("#as_swiper_slider_as", res.slider_config);
                            }
                            $(s_templ).removeAttr("id","as_swiper_slider_as")
                        }

                    }
                    else{
                        if('record_ids' in res){
                            $(product_slider).attr("data-records-ids", JSON.stringify(res.record_ids))
                        }
                        var $template =  $(res['template']).attr("id","as_swiper_slider_as");
                        $(product_slider).empty().append($template);
                        if(Object.keys(res.slider_config).length != 0){
                            new Swiper("#as_swiper_slider_as", res.slider_config);
                        }
                        $template.removeAttr("id");
                    }
                    this.trigger_up('widgets_start_request', {$target: $template});
                    this.trigger_up('widgets_start_request', {$target: $(".as_quick_view")});
                    this.trigger_up('widgets_start_request', {$target: $(".as_color_variant")});
                    this.trigger_up('widgets_start_request', {$target: $(".oe_website_sale")});

                });
            }
            else{
                $(product_slider).parents(".s_dynamic_snippets").attr("contenteditable",true)
                $(product_slider).empty().append("<div class='text-center'> <h3>"+snippet_editor.name+"</h3> </div>");
            }
        }
    },
    _tab_change:function(ev){
        this.$target.find(".as-tab-name").removeClass("active");
        let tab_id = $(ev.currentTarget).data('id');
        $(ev.currentTarget).addClass('active');
        if(this.selector == "[data-snippet-name='CategoryProduct'], [data-snippet-name='categories_products']"){
            var slider_tab = "[data-tab-id='category_"+tab_id+"']";
            this.$target.find(".as_category_products").removeClass("active");

        }else{
            var slider_tab = "[data-tab-id='brand_"+tab_id+"']";
            this.$target.find(".as_brand_products").removeClass("active");
        }
        this.$target.find(".as-tab-pane").removeClass("active")
        this.$target.find(slider_tab).addClass("active");
    },

})


publicWidget.registry.alanProductSlider = AlanSliders.extend({
    selector:"[data-snippet-name='ProductSlider'], [data-snippet-name='products'], [data-snippet-name='BestSellingProduct'], [data-snippet-name='LatestProduct']",
    disabledInEditableMode: false,
    start:function(){
        this._get_loader()
        this._getProductSlider();
    }
});

publicWidget.registry.alanCategoryProduct = AlanSliders.extend({
    selector:"[data-snippet-name='CategoryProduct'], [data-snippet-name='categories_products']",
    disabledInEditableMode: false,
    events:{
        'click .as-tab-name':'_tab_change'
    },
    start:function(){
        this._get_loader()
        this._getProductSlider();
    }
});

publicWidget.registry.alanBrandProduct = AlanSliders.extend({
    selector:"[data-snippet-name='BrandProduct'], [data-snippet-name='brand_products']",
    disabledInEditableMode: false,
    events:{
        'click .as-tab-name':'_tab_change'
    },
    start:function(){
        this._get_loader()
        this._getProductSlider();
    }
});


publicWidget.registry.alanProductBanner = AlanSliders.extend({
    selector:"[data-snippet-name='ProductBanner'], [data-snippet-name='product_banner']",
    disabledInEditableMode: false,
    start:function(){
        this._get_loader()
        this._getProductSlider();
    }
});

publicWidget.registry.alanCategorySlider = AlanSliders.extend({
    selector:"[data-snippet-name='CategorySlider'], [data-snippet-name='categories']",
    disabledInEditableMode: false,
    start:function(){
        this._get_loader()
        this._getProductSlider();
    }
});

publicWidget.registry.alanBrandSlider = AlanSliders.extend({
    selector:"[data-snippet-name='BrandSlider'], [data-snippet-name='brands']",
    disabledInEditableMode: false,
    start:function(){
        this._get_loader()
        this._getProductSlider();
    }
});

publicWidget.registry.alanBlogSlider = AlanSliders.extend({
    selector:"[data-snippet-name='BlogSlider'], [data-snippet-name='blogs']",
    disabledInEditableMode: false,
    start:function(){
        this._get_loader()
        this._getProductSlider();
    }
});


publicWidget.registry.MegaMenuTabsSnippets = publicWidget.Widget.extend({
    selector: '.as-mm-tabs-level-1',
    disabledInEditableMode:false,
    events:{
        'mouseenter':'_showMegaMenuTabs',
        'click .as-mob-tab-menu':'_showMegaMenuTabsMob',
    },
    _showMegaMenuTabs:function(ev){
        if($(ev.currentTarget).hasClass("active") == false){
            this.$target.parents(".as-mm-tabs-levels").find(".as-mm-tabs-level-1.active").removeClass("active");
            $(ev.currentTarget).addClass("active");
        }
    },
    _showMegaMenuTabsMob:function(ev){
        ev.preventDefault();
        ev.stopPropagation();
        if($(ev.currentTarget).parents(".as-mm-tabs-level-1").hasClass("as-mob-menu")){
            $(ev.currentTarget).parents(".as-mm-tabs-level-1").removeClass("active").removeClass("as-mob-menu");
        }else{
            $(ev.currentTarget).parents(".as-mm-tabs-level-1").addClass("active").addClass("as-mob-menu");
        }
    }
});


publicWidget.registry.AdvanceMegaMenu = publicWidget.Widget.extend({
    selector: '.as-advance-header',
    start:function(){
        this.$target.find('.as-ah-mobile_menu').click(function (ev) {
            ev.stopPropagation();
            // $(ev.currentTarget).addClass("as-ah-h1-close")
            $(ev.currentTarget).parents(".as-l1-items").addClass("as-ah-h1-open").trigger('click');
        });
        this.$target.find('.as-ah-mobile_menu-l2').click(function (ev) {
            ev.stopPropagation();
            $(ev.currentTarget).parents(".as-l2-items").addClass("as-ah-h2-open").trigger('click');
        });
        this.$target.find('.as-ah-mobile_menu-l3').click(function (ev) {
            ev.stopPropagation();
            $(ev.currentTarget).parents(".as-l3-items").addClass("as-ah-h3-open").trigger('click');
        });
    },
});

publicWidget.registry.AdvanceMegaMenuMobile = publicWidget.Widget.extend({
    selector: '.as-mob-2nd-menu',
    start:function(){
        this.$target.find('.as_mob_2nd_btn').click(function(ev){
            $($(ev.currentTarget)[0].nextElementSibling).addClass("as-advance-header-open")
        })
        this.$target.find('.as-bbl-1').click(function(ev){
            $(ev.currentTarget).parents(".as-advance-header").removeClass("as-advance-header-open")
        })
        this.$target.find('.as-bbl-2').click(function(ev){
            $(ev.currentTarget).parents(".as-l1-items").removeClass("as-ah-h1-open")
        })
        this.$target.find('.as-bbl-3').click(function(ev){
            $(ev.currentTarget).parents(".as-l2-items").removeClass("as-ah-h2-open")
        })
        this.$target.find('.as-bbl-4').click(function(ev){
            $(ev.currentTarget).parents(".as-l3-items").removeClass("as-ah-h3-open")
        })
    }
});

publicWidget.registry.MegaMenuSnippets = publicWidget.Widget.extend({
    selector: '.nav-item',
    disabledInEditableMode:false,
    is_clicked :false,
    events:{
        'click .as-advance-nav-mob':'_advanceNavMob',
        'click .as-advance-header-close':'_advanceNavMobClose',
        'click .swiper-button-next, .swiper-button-prev':'_stopCloseMenu',
    },
    init: function () {
        this._super.apply(this, arguments);
    },
    _stopCloseMenu:function(ev){
        ev.preventDefault();
        ev.stopPropagation()
    },
    start:function(){
        this.$target.find('.as-ah-mobile_menu-l1').click(function (ev) {
            $(ev.currentTarget).click(function (ev) {
                if($(ev.currentTarget).parents(".as-ah-h1-open").length){
                    $(ev.currentTarget).parents(".as-l1-items").removeClass("as-ah-h1-open");
                    $($(ev.currentTarget)[0].nextElementSibling).find(".as-l2-items").removeClass("as-ah-h2-open")
                    $($(ev.currentTarget)[0].nextElementSibling).find(".as-l3-items").removeClass("as-ah-h3-open")
                }
                else{
                    $(ev.currentTarget).parents(".as-l1-items").addClass("as-ah-h1-open").trigger('click');
                }
            });

        });
        this.$target.find('.as-ah-mobile_menu-l2').click(function (ev) {
            $(ev.currentTarget).click(function (ev) {
                if($(ev.currentTarget).parents(".as-ah-h2-open").length){
                    $(ev.currentTarget).parents(".as-l2-items").removeClass("as-ah-h2-open");
                    $($(ev.currentTarget).parents(".as-l2-link")[0].nextElementSibling).find(".as-l3-items").removeClass("as-ah-h3-open")
                }
                else{
                    $(ev.currentTarget).parents(".as-l2-items").addClass("as-ah-h2-open").trigger('click');
                }
            });

        });
        this.$target.find('.as-ah-mobile_menu-l3').click(function (ev) {
            $(ev.currentTarget).click(function (ev) {
                if($(ev.currentTarget).parents(".as-ah-h3-open").length){
                    $(ev.currentTarget).parents(".as-l3-items").removeClass("as-ah-h3-open");
                }
                else{
                    $(ev.currentTarget).parents(".as-l3-items").addClass("as-ah-h3-open").trigger('click');
                }
            });
        });
    },
    _advanceNavMob: function(ev){
        $($(ev.currentTarget)).addClass("as-advance-header-close")
        $($(ev.currentTarget)[0].nextElementSibling).addClass("as-advance-header-open")

    },
    _advanceNavMobClose:function(ev){
        $($(ev.currentTarget)).removeClass("as-advance-header-close")
        $($(ev.currentTarget)[0].nextElementSibling).removeClass("as-advance-header-open")
        $($(ev.currentTarget)[0].nextElementSibling).find(".as-l1-items").removeClass("as-ah-h1-open")
        $($(ev.currentTarget)[0].nextElementSibling).find(".as-l2-items").removeClass("as-ah-h2-open")
        $($(ev.currentTarget)[0].nextElementSibling).find(".as-l3-items").removeClass("as-ah-h3-open")
    },
})



let MegaMenuSnippets = publicWidget.Widget.extend({
    init: function () {
        this._super.apply(this, arguments);
        this.rpc = rpc
    },
    _showMegaMenu: async function(ev){

        for (const product_slider of this.$target) {
            let snippet_editor = JSON.parse($(product_slider).attr("data-design-edit"))
            let context = {
                'snippet':$(product_slider).attr("data-snippet-name"),
                'record_ids':JSON.parse($(product_slider).attr("data-records-ids")),
                'modal':$(product_slider).attr("data-modal"),
                'design_editor':JSON.parse($(product_slider).attr("data-design-edit")),
            }
            if(!this.editableMode){
                rpc('/get_megamenu_snippet_template', context).then((res)=>{
                    if('record_ids' in res){
                        $(product_slider).attr("data-records-ids", JSON.stringify(res.record_ids))
                    }
                    var $template =  $(res['template']).attr("id","as_swiper_slider_as");
                    $(product_slider).empty().append($template);
                    if(Object.keys(res.slider_config).length != 0){
                        new Swiper("#as_swiper_slider_as", res.slider_config);
                    }
                    $template.removeAttr("id");
                })
            }
            else{

                $(product_slider).parents(".as_mega_menu").attr("contenteditable",true)
                $(product_slider).empty().append("<div class='text-center'> <h3>"+snippet_editor.name+"</h3> </div>");
            }
        }

    }
})


publicWidget.registry.alanMegamenuProductSlider = MegaMenuSnippets.extend({
    selector:"[data-snippet-name='megamenu_products'],[data-snippet-name='MegaMenuProduct']",
    disabledInEditableMode: false,
    start:function(){

        this._showMegaMenu();
    }
});


publicWidget.registry.alanMegamenuCategorySlider = MegaMenuSnippets.extend({
    selector:"[data-snippet-name='megamenu_category'],[data-snippet-name='MegaMenuCategory']",
    disabledInEditableMode: false,
    start:function(){
        this._showMegaMenu();
    }
});


publicWidget.registry.alanMegamenuBrandSlider = MegaMenuSnippets.extend({
    selector:"[data-snippet-name='megamenu_brand'],[data-snippet-name='MegaMenuBrand']",
    disabledInEditableMode: false,
    start:function(){
        this._showMegaMenu();
    }
});
export const HeroSlider = publicWidget.Widget.extend({
    selector:".hero_slider",
    disabledInEditableMode: false,
    start:function(){
        var data = new Swiper(".as-slide-swiper", {
            slidesPerView: 1,
            centeredSlides: true,
            slidesPerGroup: 1,
            spaceBetween: 15,
            slideToClickedSlide: true,
            loop: true,
            pagination: {
                el: ".swiper-pagination",
                clickable: true,
            },
            navigation: {
                nextEl: ".swiper-button-next",
                prevEl: ".swiper-button-prev",
            },
              breakpoints: {
                1024: {
                  slidesPerView: 1.60,
                },
              },
        });
    }
});
publicWidget.registry.HeroSlider = HeroSlider;

publicWidget.registry.MegaMenuDropdown.include({

    _updateActiveMenuLinks() {
        // Prevent having several active links in the menu.
        if (this.el.querySelector(".navbar #top_menu a.nav-link.active")) {
            return;
        }
        const currentHrefWithoutHash = `${window.location.origin}${window.location.pathname}`;
        // Check and update the active state of menu items based on the current
        // page
        const megaMenuEls = this.el.querySelectorAll(".o_mega_menu");
        let matchingLink = null;
        megaMenuEls.forEach((megaMenuEl, position) => {
            const linkEls = Array.from(megaMenuEl.querySelectorAll(`a:not([href="#"])`));
            matchingLink = linkEls.find((linkEl) => {
                const url = new URL(linkEl.href);
                return `${url.origin}${url.pathname}` === currentHrefWithoutHash;
            });
            if (matchingLink) {
                const megaMenuToggleEl = megaMenuEl
                    .closest(".nav-item")
                    .querySelector(".o_mega_menu_toggle");
                // Target the corresponding link in the mobile navigation. Since the
                // mega-menu for mobile is dynamically rendered, it is not
                // accessible at this moment.
                const mobileMegaMenuToggleEl = this.el.querySelectorAll(
                    "#top_menu_collapse_mobile .top_menu .o_mega_menu_toggle"
                )[position];

                if (megaMenuToggleEl && mobileMegaMenuToggleEl){
                    megaMenuToggleEl.classList.add("active");
                    mobileMegaMenuToggleEl.classList.add("active");
                }

            }
        });
    },
})

export default {
    HeroSlider: publicWidget.registry.HeroSlider
};


publicWidget.registry.AlanLoginPopup = AlanLoginPopup;
