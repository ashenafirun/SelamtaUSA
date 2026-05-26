/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { BarcodePickingModel } from "@stock_barcode/models/barcode_picking_model";

patch(BarcodePickingModel.prototype, {
    /**
     * Override to force lines with same product+lot to show as grouped
     * with dropdown visible from the start (before scanning).
     */
    _getLinesGroupedByProduct(lines) {
        const result = super._getLinesGroupedByProduct(lines);
        return result;
    },

    get groupedLines() {
        const groups = super.groupedLines;
        // For each group, if it has sublines (split packaging), 
        // mark it as collapsed so dropdown shows immediately
        for (const group of groups) {
            if (group.lines && group.lines.length > 1) {
                // Force the group to show as collapsed with dropdown
                group.isExpanded = group.isExpanded ?? false;
            }
        }
        return groups;
    },
});
