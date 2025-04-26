/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import BarcodeModel from '@stock_barcode/models/barcode_model';

patch(BarcodeModel.prototype, {
    get groupedLinesByLocation() {
        console.log("patched")
        const lines = [].concat(this.groupedLines, this.packageLines);
        const linesByLocations = []
        const linesByLocation = {};
        for (const line of lines) {
            const lineLoc = line.location_id;
            if (!linesByLocation[lineLoc.id]) {
                linesByLocation[lineLoc.id] = {
                    location: lineLoc,
                    lines: [],
                };
            }
            if (!linesByLocations.includes(linesByLocation[lineLoc.id])) {
                linesByLocations.push(linesByLocation[lineLoc.id]);
            }
            linesByLocation[lineLoc.id].lines.push(line);
        }
        // Sorts groups to ensure that locations will always follow the alphabetical order.
        linesByLocations.sort((lblA, lblB) => {
            const [locNameA, locNameB] = [lblA.location.removal_sequence, lblB.location.removal_sequence];
            return locNameA < locNameB ? -1 : locNameA > locNameB ? 1 : 0;
        });
        return linesByLocations
    }
});
