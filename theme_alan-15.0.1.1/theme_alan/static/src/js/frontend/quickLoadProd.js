odoo.define('theme_alan.quick_product_load', function (require) {
"use strict";

var publicWidget = require("web.public.widget");
var url = window.location.href;
var call = false;

publicWidget.registry.ajaxProductLoadAuto = publicWidget.Widget.extend({
    selector:'div#wrapwrap',
    events:{
        'scroll':'_autoLoadShopProduct'
    },
    _autoLoadShopProduct:function(){
        if($('.as_load_product').offset() != undefined){
            var gettop = $('.as_load_product').offset().top;
            var getheight = $('.as_load_product').outerHeight();
            var getwindowheight = $(window).height();
            var nxtbtnpos = gettop+getheight-getwindowheight;
            if (nxtbtnpos < 30){
                if(call != true){
                    $('.as_load_product').click();
                    call = true;
                }
            }else{
                call = false;
            }
        }
    }
});

publicWidget.registry.alan_quick_product_load = publicWidget.Widget.extend({
    "selector": ".as_load_product",
    events : {
        "click": "_loadProduct"
    },
    _loadProduct:function(ev){
        var cr = this;
        var page = cr.$el.attr("page");
        $(ev.currentTarget).addClass("as-load-product");
        cr._rpc({
            route: "/json/shop/product/",
            params: {
                "page":cr.$el.attr("page"),
                "ppg":cr.$el.attr("ppg"),
                "attrval":cr.$el.attr("attrval"),
                "sel_tag_list":cr.$el.attr("sel_tag_list"),
                "sel_brand_list":cr.$el.attr("sel_brand_list"),
                "rating":cr.$el.attr("rating"),
                "min_price":cr.$el.attr("min_price"),
                "max_price":cr.$el.attr("max_price"),
                "order":cr.$el.attr("order"),
            }
        }).then(function (result) {
            $(ev.currentTarget).removeClass("as-load-product");
            $(".load_next_product").before(result["product"]);
            $(".pagination").replaceWith(result["pager_template"]);
        });
        var maxpage = cr.$el.attr("max_page");
        var page = Number(page) + 1;
        cr.$el.attr("page",page);
        if(page == maxpage){
            cr.$el.remove();
        };
        var maxpage = cr.$el.attr("max_page");
        cr.$el.attr("page",page);
        if(page == maxpage){cr.$el.remove();}
        var checkurl = url.split("/");
        var checkattrurl = url.split("=");
        var url_have_page = false;
        if(checkattrurl.length > 1){
            var spliturl = url.split("?");
            var checksuburl = spliturl[0].split("/");
            for (let index = 0; index < checksuburl.length; index++){
                if(checksuburl[index] == "page"){
                    url_have_page = true;
                }
            }
            if(url_have_page != true){
                var new_url =  checksuburl.join("/") + "/page/" + page + "?" +spliturl[1];
            }else{
                checksuburl.pop();
                checksuburl.push(page);
                var new_url = checksuburl.join("/") + "?" +spliturl[1];
            }
        }else{
            for (let index = 0; index < checkurl.length; index++) {
                if(checkurl[index] == "page"){
                    url_have_page = true;
                }
            }
            if(url_have_page != true){
                var new_url = url + "/page/" + page;
            }else{
                checkurl.pop();
                checkurl.push(page);
                var new_url = checkurl.join("/");
                }
            }
        $(".page-item").each(function () {
            var getclassid = $(this).attr("id");
            if(getclassid != undefined){
                var getpagenum = getclassid.slice(4);
                var activediv = $(this).hasClass("active");
                if(activediv == true){
                    $(this).removeClass("active");
                }
                if(getpagenum == page){
                    $(this).addClass("active");
                }
            }
        });
        window.history.pushState("data","Title",new_url);
    },
});
});