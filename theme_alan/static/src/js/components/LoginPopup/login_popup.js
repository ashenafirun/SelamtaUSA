/** @odoo-module alias=theme_alan.LoginPopup **/

import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { imageUrl } from "@web/core/utils/urls";
import { Component, onWillStart, useRef, useState} from "@odoo/owl";
import { getLastConnectedUsers, setLastConnectedUsers } from "@web/core/user";
import { addLoadingEffect } from '@web/core/utils/ui';

export class LoginPopup extends Component {
    static template = "theme_alan.LoginPopup";
    static props = {
        close: Function,
        csrf_token: String,
        reset_password_enabled :Boolean,
        signup_enabled:Boolean,
        website_logo: String,
        providers: { type: Array, optional: true },
    };

    setup() {
        const users = getLastConnectedUsers();
        this.root = useRef("root");
        this.state = useState({
            users,
            displayUserChoice: users.length,
        });
        this.props.csrf_token = odoo.csrf_token
        onWillStart(this.onWillStart);
        super.setup();
    }

    async onWillStart() {
        await rpc('/get_login_popup').then((result) => {
            this.props.reset_password_enabled = result['reset_password_enabled']
            this.props.signup_enabled = result['signup_enabled']
            this.props.website_logo = result['website_logo']
            this.props.providers = result['providers']

        } );
    }

    checkAuthentication(ev) {
        // ev.preventDefault();
        let $modal = $(this.__owl__.bdom.parentEl);
        const login = $modal.find("#login").val();
        const password = $modal.find("#password").val();
        if (login.trim() != "" && password.trim() != "") {
            ev.preventDefault();
            return rpc("/alan/login/authenticate", { "login": login, "password": password }).then(function (result) {
                if (result["login_success"] == true) {
                    addLoadingEffect($modal.find(".loginbtn")[0])
                    window.location.href = '/odoo';
                } else if ("error" in result) {
                    $modal.find("#errormsg").css("display","block").empty().append(result["error"]);
                }
            })
        }
    }

    userSignup(ev){
        let $modal = $(this.__owl__.bdom.parentEl);
        const logins = $modal.find("#logins").val();
        const passwords = $modal.find("#passwords").val();
        const names = $modal.find("#names").val();
        const confirm_passwords = $modal.find("#confirm_passwords").val();
        const token = $modal.find("#token").val()
        if(logins.trim() != "" && passwords.trim() != ""
        && confirm_passwords.trim() != "" && names.trim() != ""){
            ev.preventDefault();
            return rpc("/alan/signup/authenticate",{
                "login":logins,
                "name":names,
                "password":passwords,
                "confirm_password":confirm_passwords,
                "token":token
                }
            ).then(function (result) {
                if("error" in result){
                    $modal.find("#errors").css("display","block").empty().append(result["error"])
                }
                else if(result["signup_success"] == true){
                    addLoadingEffect($modal.find(".signupbtn")[0])
                    window.location.href = '/odoo';
                }
            });
        }
    }

    backToLogin(){
        let $modal = $(this.__owl__.bdom.parentEl);
        $modal.find("#as-login").click();
    }

    getAvatarUrl({ partnerId, partnerWriteDate: unique }) {
        return imageUrl("res.partner", partnerId, "avatar_128", { unique });
    }

    toggleFormDisplay() {
        let $modal = $(this.__owl__.bdom.parentEl);
        $modal.find(".as_choose_login").removeClass('d-none')
        $modal.find(".as_login_popup_form").addClass('d-none')
    }

    remove(deletedUser) {
        this.state.users = this.state.users.filter((user) => user !== deletedUser);
        setLastConnectedUsers(this.state.users);
        if (!this.state.users.length) {
            this.fillForm();
        }
    }

    fillForm(login = "") {
        let $modal = $(this.__owl__.bdom.parentEl);
        $modal.find(".as_choose_login").addClass('d-none')
        $modal.find(".as_login_popup_form").removeClass('d-none')
        $modal.find("#login").val(login)
    }
}

export default {
    LoginPopup: LoginPopup
}
