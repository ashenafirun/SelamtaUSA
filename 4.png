/** @odoo-module **/
import { ListController } from "@web/views/list/list_controller";
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";

export class OverstockListController extends ListController {
    /**
     * Handles the click event for the custom Print PDF button.
     */
    async onPrintPdf() {
        // Access the print method from the action's context
        const printMethod = this.props.context.print_method;

        // Access the correct model name
        const modelName = this.model.root.resModel;

        if (!printMethod) {
            console.warn("No 'print_method' found in context. Check your Server Action.");
            return;
        }

        // Use the ORM service to call the Python method
        // We pass an empty list [] as the first argument because it's a model-level method
        await this.model.orm.call(modelName, printMethod, [[]], {
            context: this.props.context,
        }).then((action) => {
            // If the Python method returns an action (like a report trigger), execute it
            if (action && typeof action === 'object') {
                this.actionService.doAction(action);
            }
        });
    }
}

registry.category("views").add("overstock_print_list", {
    ...listView,
    Controller: OverstockListController,
    buttonTemplate: "forecasting_auto_replenishment.OverstockButtons",
});