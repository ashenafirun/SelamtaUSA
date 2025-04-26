/** @odoo-module alias=theme_alan.MiniCart **/

import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";
import { useDebounced } from "@web/core/utils/timing";
import { renderToElement } from "@web/core/utils/render";
import { Component, onWillStart, useState } from "@odoo/owl";
import wSaleUtils from "@website_sale/js/website_sale_utils";

export class MiniCartLine extends Component {
    static template = "theme_alan.Minicartline";
    static props = {
        image_url:String,
        website_url:String,
        display_name: String,
        price_total: Number,
        product_uom_qty: Number,
        line_id: Number,
        product_id: Number,
        formated_amount: String,
    }
    setup() {
        this.state = useState({
            add_quantity: this.props.product_uom_qty,
            cart_quantity: this.props.cart_quantity
        })
        this.wishlistProductIDs = JSON.parse(sessionStorage.getItem('website_sale_wishlist_product_ids') || '[]');
        this.debouncedUpdateQuantity = useDebounced(this._updateQuantity, 500, {
            execBeforeUnmount: true,
        });
        super.setup();
    }
    async _updateQuantity(qty){
        await rpc("/shop/cart/update_json", {
            line_id: this.props.line_id,
            product_id: parseInt(this.props.product_id),
            set_qty: this.state.add_quantity,
            display: true,
        }).then((data) => {
            wSaleUtils.updateCartNavBar(data);
        });
        await this.props.main_obj._loadProductData()
    }

    increaseQuantity() {
        this.state.add_quantity = this.state.add_quantity + 1
        this.state.cart_quantity = this.state.cart_quantity + 1
        this.debouncedUpdateQuantity();
    }

    decreaseQuantity() {
        if (this.state.add_quantity == 1 && $('.as_mini_cart_products').find('li.as_mini_cart_product_line').length == 1){
            this.props.main_obj.clearCart()
        }
        else{
            this.state.add_quantity = this.state.add_quantity - 1
            this.debouncedUpdateQuantity();
        }
    }

    get disableRemove() {
        return this.state.add_quantity == 0;
    }

    async setQuantity(event) {
        this.state.add_quantity = event.target.value
        this.debouncedUpdateQuantity();
    }

    async removeProduct(){
        if($('.as_mini_cart_products').find('li.as_mini_cart_product_line').length == 1){
            await this.props.main_obj.clearCart()
        }
        else{
            this.state.add_quantity = 0
            this.debouncedUpdateQuantity();
        }
    }

    async saveForLater(){
        if(this.props.product_id){
            await this.removeProduct()
            if(!this.wishlistProductIDs.includes(parseInt(this.props.product_id))){
                await rpc('/shop/wishlist/add', {
                product_id: parseInt(this.props.product_id),
                }).then(function () {
                    const $navButton = $('header .o_wsale_my_wish').first();
                    const $wishButton = $('.o_wsale_my_wish');
                    const qty = $wishButton.find('.my_wish_quantity').html();
                    wSaleUtils.animateClone($navButton, $('.form'), 25, 40);
                    $wishButton.find('.my_wish_quantity').text(parseInt(qty)+1);
                })
            }
        }
    }
}

export class MiniCart extends Component {
    static template = "theme_alan.Minicart";
    static components = { Dialog , MiniCartLine};
    static props = {
        close: Function,
        card_qty: Number,
    };

    setup() {
        this.state = useState({
            product_lines: [],
            suggested_products: [],
            cart_summary: [],
        });
        onWillStart(async () => {
            await this._loadProductData();
        });
        super.setup();
    }

    async _loadProductData() {
        const { cart_quantity, website_order_lines, suggested_products, cart_summary } = await rpc('/get_mini_cart');

        this.props.card_qty = cart_quantity;
        this.state.product_lines = website_order_lines;
        this.state.suggested_products = suggested_products;
        this.state.cart_summary = cart_summary;
    }

    async addSuggestedProduct(product_id) {
        await rpc("/shop/cart/update_json", {
            product_id: parseInt(product_id),
            add_qty: 1,
            display: true,
        }).then((data) => {
            wSaleUtils.updateCartNavBar(data);
        });
        await this._loadProductData();
    }

    async clearCart() {
        await rpc('/as_clear_cart');
        const $emptyCartTemplate = renderToElement("theme_alan.as_empty_mini_cart");
        $(this.__owl__.bdom.el).find(".cart_body").replaceWith($emptyCartTemplate);
        $(this.__owl__.bdom.el).find(".as_cart_qty").remove();
        $(".my_cart_quantity").text("0");
    }
}


export default {
    MiniCartLine: MiniCartLine,
    MiniCart: MiniCart,

}