
/** @odoo-module alias=theme_alan.ProductQueries **/

import { Component } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

export class ProductQueries extends Component {
    static template = "theme_alan.ProductQueries";
    static props = {
        close: Function,
        product_id: Number,
        user_email: String,
        user_id: Number,
        user_email:String,
        dialog_header: String,
        dialog_header_desc: String,
        acknowledgement_message: String,
    }

    send_queries(ev){
        let $modal = $(this.__owl__.bdom.parentEl);
        var email = $modal.find("#email").val();
        var message = $modal.find("#message").val();
        var user_id = $modal.find("#customer_id").val();
        let radios = $modal.find('.ContactPreference');
        let selectedValue = '';
        for (let i = 0; i < radios.length; i++) {
            if (radios[i].checked) {
                selectedValue = radios[i].id;
                break;
            }
        }
        if (message == '') {
            $modal.find(".msg").addClass("border").addClass("border-danger")
        }
        var context = { message: message,user_id:user_id,email:email,product_id:this.props.product_id,contact_preference:selectedValue}
        if (message){
            return rpc('/send_queries_mail', context).then((response) => {
                $modal.find(".queries-container").hide();
                $modal.find("#thank-you").removeClass("o_hidden");
                setTimeout(() => {
                    this.props.close();
                }, 2000);
            })
        }
    }

    _onChangeInput(){
        $(this.__owl__.bdom.parentEl).find(".msg").removeClass("border").removeClass("border-danger")
    }
}


export default {
    ProductQueries: ProductQueries
}