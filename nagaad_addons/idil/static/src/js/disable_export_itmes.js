odoo.define('idil.item.disable_export', function (require) {
    "use strict";

    var ListController = require('web.ListController');

    ListController.include({
        renderButtons: function ($node) {
            this._super.apply(this, arguments);
            if (this.$buttons) {
                // Hide the export button
                this.$buttons.find('.o_button_export').hide();
            }
        },
    });
});
