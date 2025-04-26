/** @odoo-module alias=theme_alan.QuickView **/

import { markup } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";
import { cookie } from "@web/core/browser/cookie";
import { Product } from '@sale/js/product/product';
import { LoginPopup } from "theme_alan.LoginPopup";
import { useService } from "@web/core/utils/hooks";
import wSaleUtils from "@website_sale/js/website_sale_utils";
import { ProductAdvanceInfo } from "theme_alan.ProductAdvanceInfo";
import { onWillStart, onWillUpdateProps, useState, useRef} from "@odoo/owl";
import { ProductConfiguratorDialog } from "@sale/js/product_configurator_dialog/product_configurator_dialog";
import { ProductTemplateAttributeLine } from '@sale/js/product_template_attribute_line/product_template_attribute_line';
import { patch } from "@web/core/utils/patch";

export class AlanProductAttributeLine extends ProductTemplateAttributeLine {
    static template = "theme_alan.AlanProductAttributeLine";
    static components = { ...ProductTemplateAttributeLine.components};

    setup() {
        this.dialogService = useService("dialog");
        super.setup();
    }
    showAdvanceInfo(info_id){
        this.dialogService.add(ProductAdvanceInfo, { infoId: info_id});
    }
}

export class AlanProductBlock extends Product {
    static template = "theme_alan.AlanProductBlock";
    static components = { Dialog, ...Product.components, AlanProductAttributeLine};
    static props = { ...Product.props, modalRef: { type: Function, optional: true }, quickViewImageUrl: { type: String, optional: true },};

    setup() {
        this.state = useState({
            rating_template: "",
            show_compare: false,
            show_wishlist: false,
            show_buy_now: false,
            sale_count: "",
            bulk_save_view: "",
            tag_template: "",
            category_template: "",
            sku_template: "",
            brand_template: "",
            offer_timing: "",
            active_offer_timer: false,
            advance_info: {}

        });

        this.orm = useService("orm")
        this.dialogService = useService("dialog");
        this.OfferTimerServices = useService("offer_timer");
        this.offerTimerRef = useRef("offerTimerRef");
        this.notification = useService("notification");

        // Compare list
        this.comparelist_product_ids = JSON.parse(cookie.get("comparelist_product_ids") || "[]");
        this.product_compare_limit = 4;
        this.product_data = {};
        // Wishlist
        this.wishlistProductIDs = JSON.parse(sessionStorage.getItem("website_sale_wishlist_product_ids") || "[]");
        // Load initial data
        onWillStart(() => this._load_data(this.props.product_tmpl_id, this.props.id));
        // Update data on prop change
        onWillUpdateProps((nextProps) => this._load_data(this.props.product_tmpl_id, nextProps.id));
        super.setup();
    }

    get quickViewImageUrl(){
        const modelPath = this.props.id
            ? `product.product/${ this.props.id }`
            : `product.template/${ this.props.product_tmpl_id }`;
        return `/web/image/${ modelPath }/image_1920`;
    }

    showAdvanceInfo(info_id){
        this.dialogService.add(ProductAdvanceInfo, { infoId: info_id});
    }

    onPointerTimer(){
        this.OfferTimerServices.create({target:$(this.offerTimerRef.el), offerDate:this.state.offer_timing});
    }

    async _load_data(product_tmpl_id, product_id) {
        const templates = await rpc("/as_get_quick_view_templates", {
            product_tmpl_id,
            product_id,
        });

        const {
            rating_template,
            show_compare,
            show_wishlist,
            show_buy_now,
            sale_count,
            bulk_save_view,
            tag_template,
            brand_template,
            category_template,
            sku_template,
            active_b2b_mode,
            active_login_popup,
            offer_timing,
            active_offer_timer,
            advance_info,
        } = templates;

        Object.assign(this.state, {
            rating_template: markup(rating_template),
            show_compare,
            show_wishlist,
            show_buy_now,
            sale_count,
            active_b2b_mode,
            active_login_popup,
            bulk_save_view: markup(bulk_save_view),
            tag_template: markup(tag_template),
            brand_template: markup(brand_template),
            category_template: markup(category_template),
            sku_template: markup(sku_template),
            offer_timing,
            active_offer_timer,
            advance_info,
        });
        this.onPointerTimer()
    }

    loginPopup(){
        if (this.state.active_login_popup){
            this.dialogService.add(LoginPopup, {});
        }
        else{
            window.location.href = '/web/login';
        }
    }

    async addToCart() {
        this.props.configuratordialog.quantity = this.props.quantity
        const data = await rpc("/shop/cart/update_json", {
            product_id: parseInt(this.props.id),
            add_qty: this.props.quantity,
            display: true,
        });
        wSaleUtils.updateCartNavBar(data);
        this.notification.add(_t("Item(s) added to your cart"), { type: "success" });

    }

    async buyNow() {
        const data = await rpc("/shop/cart/update_json", {
            product_id: parseInt(this.props.id),
            add_qty: 1,
            display: true,
        });
        wSaleUtils.updateCartNavBar(data);
    }

    async addToCompareList() {
        if (this.comparelist_product_ids.length < this.product_compare_limit && !this.comparelist_product_ids.includes(parseInt(this.props.id))) {
            const cookies = JSON.parse(cookie.get("comparelist_product_ids") || "[]");
            const data = await rpc("/shop/get_product_data", {
                product_ids: [this.props.id],
                cookies: cookies,
            });
            this.comparelist_product_ids = JSON.parse(data.cookies);
            this.product_data[this.props.id] = data.product;
            cookie.set("comparelist_product_ids", JSON.stringify(this.comparelist_product_ids), 365 * 24 * 60 * 60, "required");
            const templates = this.comparelist_product_ids.map((id) => this.product_data[id]?.render).join("");
            $(".o_comparelist_products").html(templates);
            $(".o_product_circle").text(this.comparelist_product_ids.length);
            $(".o_comparelist_button").removeClass("d-md-block");
            this.notification.add(_t("Item(s) added to your Comaparelist"), { type: "success" });
        }
    }

    async addWishlist() {
        if (!this.wishlistProductIDs.includes(parseInt(this.props.id))) {
            await rpc("/shop/wishlist/add", { product_id: parseInt(this.props.id) });
            const $navButton = $("header .o_wsale_my_wish").first();
            const $wishButton = $(".o_wsale_my_wish");
            const qty = $wishButton.find(".my_wish_quantity").html();
            this.notification.add(_t("Item(s) added to your Wishlist"), { type: "success" });
            wSaleUtils.animateClone($navButton, $(".form"), 25, 40);
            $wishButton.find(".my_wish_quantity").text(parseInt(qty) + 1);
        }
    }
}

patch(ProductConfiguratorDialog.prototype, {
    _checkExclusions(product) {
        const combination = this._getCombination(product);
        const exclusions = product.exclusions;
        const parentExclusions = product.parent_exclusions;
        const archivedCombinations = product.archived_combinations;
        const parentCombination = this._getParentsCombination(product);
        const childProducts = this._getChildProducts(product)
        const ptavList = product.attribute_lines.flat().flatMap(ptal => ptal.attribute_values)
        ptavList.map(ptav => ptav.excluded = false);

        if (exclusions) {
            for(const ptavId of combination) {
                for(const excludedPtavId of exclusions[ptavId]) {
                    ptavList.find(ptav => ptav.id === excludedPtavId).excluded = true;
                }
            }
        }
        if (parentCombination) {
            for(const ptavId of parentCombination) {
                for(const excludedPtavId of (parentExclusions[ptavId]||[])) {
                    ptavList.find(ptav => ptav.id === excludedPtavId).excluded = true;
                }
            }
        }
        if (archivedCombinations) {
            for(const excludedCombination of archivedCombinations) {
                const ptavCommon = excludedCombination.filter((ptav) => combination.includes(ptav));
                if (ptavCommon.length === combination.length) {
                    for(const excludedPtavId of ptavCommon) {
                        ptavList.find(ptav => ptav.id === excludedPtavId).excluded = true;
                    }
                } else if (ptavCommon.length === (combination.length - 1)) {
                    const disabledPtavId = excludedCombination.find(
                        (ptav) => !combination.includes(ptav)
                    );
                    const excludedPtav = ptavList.find(ptav => ptav.id === disabledPtavId)
                    if (excludedPtav) {
                        excludedPtav.excluded = true;
                    }
                }
            }
        }
        for(const optionalProductTmpl of childProducts) {
            this._checkExclusions(optionalProductTmpl);
        }
    }
});


export class QuickView extends ProductConfiguratorDialog {
    static template = "theme_alan.QuickView";
    static components = { Dialog, ...ProductConfiguratorDialog.components, AlanProductBlock};
    static props = {...ProductConfiguratorDialog.props };
}

export default {
    QuickView: QuickView,
    AlanProductBlock: AlanProductBlock,
    AlanProductAttributeLine: AlanProductAttributeLine,
}
