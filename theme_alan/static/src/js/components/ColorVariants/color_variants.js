/** @odoo-module alias=theme_alan.ColorVariant **/

import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

export class ColorVariant extends Component {
    static template = "theme_alan.ColorVariant";
    static components = { Dialog };
    static props = {
        close: Function,
        body: String,
    };
}

export default {
    ColorVariant: ColorVariant
}