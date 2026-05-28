/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { BarcodePickingModel } from "@stock_barcode/models/barcode_picking_model";
import { PickingBarcodeHandler } from "@stock_barcode/barcode_handlers/picking_barcode_handler";

// Patch the model to add markLotLinesPicked action
patch(BarcodePickingModel.prototype, {

    async markLotLinesPicked() {
        // Call the server method to toggle is_picked on lot-tracked moves
        const pickingId = this.currentState.id;
        if (!pickingId) return;

        try {
            await this.orm.call(
                'stock.picking',
                'action_mark_lot_lines_picked_barcode',
                [[pickingId]],
            );
            // Refresh the barcode view
            await this.refreshCache();
            this.trigger('refresh');
        } catch (e) {
            console.error('markLotLinesPicked error:', e);
        }
    },
});
