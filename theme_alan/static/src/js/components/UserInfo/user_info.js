/** @odoo-module alias=theme_alan.UserInformDialog **/

import { Dialog } from "@web/core/dialog/dialog";
const { Component } = owl;

class UserInformDialog extends Component {
    static template = "theme_alan.userInfo";
    static components = { Dialog };
    setup() {
        this.title = "Test";
        this.footer = false;
        this.header = false;
    }
    _confirm(){
        this.props.onConfirm();
        this.props.close();
    }
    _cancel(){
        this.props.close();
    }
}



export default {
    UserInformDialog: UserInformDialog,
}
