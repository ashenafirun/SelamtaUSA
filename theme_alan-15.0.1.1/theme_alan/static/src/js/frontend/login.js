odoo.define('theme_alan.login_popup', function (require) {
"use strict";

const publicWidget = require('web.public.widget')
var Dialog = require('web.Dialog');
const webUtils = require('web.utils');

var AlanLogin =  Dialog.extend({
    template: 'theme_alan.core_front_dialog',
    xmlDependencies: Dialog.prototype.xmlDependencies.concat([
        '/theme_alan/static/src/xml/core_front_dialog.xml', ]),
    events: _.extend({}, Dialog.prototype.events, {
        'click .as_close':'close',
        'click .loginbtn':'_checkAuthentication',
        'click .haveAccount':'_backToLogin',
        'click .signupbtn':'_userSignup',
    }),
    willStart:function(){
        return this._super.apply(this, arguments).then(() => {
            this.$modal.addClass("as-login-modal as-side-modal as-modal").removeClass("o_technical_modal");
        })
    },
    init: function (src, opts) {
        let initData = { subTemplate: opts.subTemplate || "", renderHeader: 0, renderFooter: 0, backdrop: true }
        this._super(src, _.extend(initData));
        this.options = opts;
    },
    _checkAuthentication:function(ev){
        var cr = this;
        const login = cr.$el.find("#login").val();
        const password = cr.$el.find("#password").val();

        if(login.trim() != "" && password.trim() != ""){
            ev.preventDefault();
            return cr._rpc({
                route: "/alan/login/authenticate",
                params: { "login":login, "password":password }
            }).then(function (result) {
                if(result["login_success"] == true){
                    window.location.reload();
                }
                else if("error" in result){
                    cr.$el.find("#errormsg").css("display","block").empty().append(result["error"]);
                }
            });
        }
    },
    _userSignup:function(ev){
        var cr = this;
        const logins = cr.$el.find("#logins").val();
        const passwords = cr.$el.find("#passwords").val();
        const names = cr.$el.find("#names").val();
        const confirm_passwords = cr.$el.find("#confirm_passwords").val();
        const token = cr.$el.find("#token").val()
        if(logins.trim() != "" && passwords.trim() != ""
            && confirm_passwords.trim() != "" && names.trim() != ""){
            ev.preventDefault();
            return cr._rpc({
                route: "/alan/signup/authenticate",
                params: {
                        "login":logins,
                        "name":names,
                        "password":passwords,
                        "confirm_password":confirm_passwords,
                        "token":token
                    }
            }).then(function (result) {
                if("error" in result){
                    cr.$el.find("#errors").css("display","block").empty().append(result["error"])
                }
                else if(result["signup_success"] == true){
                    window.location.reload();
                }
            });
        }
    },
    _backToLogin:function(){
        this.$el.find("#as-login").click();
    },
});

publicWidget.registry.alan_login = publicWidget.Widget.extend({
    selector:'.as-login',
    events:{
        'click':'_loginPopup'
    },
    start:function(){
        this._super.apply(this, arguments);
    },
    _loginPopup:function(ev){
        var cr = this;
        $(ev.currentTarget).addClass("as-btn-loading");
        cr._rpc({
            route: '/alan/login/',
            params: { }
        }).then(function (response) {
            var alanLogin = new AlanLogin(cr,{
                subTemplate:webUtils.Markup(response['template'])});
                $(ev.currentTarget).removeClass("as-btn-loading");
                alanLogin.open();
        });
    }
});
});