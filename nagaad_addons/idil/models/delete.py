from odoo import models, fields, api
import logging


class ModelA(models.Model):
    _name = 'model.a'
    _description = 'Model A'

    _logger = logging.getLogger(__name__)

    # Other fields definition

    @api.model
    def delete_other_models_data(self, *args, **kwargs):
        models_to_delete = [
            'idil.vendor_transaction',
            'idil.vendor_payment',
            'idil_commission',
            'idil.manufacturing.order.line',
            'idil.manufacturing.order',

            'idil.purchase_order.line',
            'idil.purchase_order',




            'idil.kitchen.cook.line',
            'idil.kitchen.cook.process',

            'idil.kitchen.transfer.line',
            'idil.kitchen.transfer',

            'idil.journal.entry.line',
            'idil.journal.entry',

            'idil.transaction_bookingline',
            'idil.transaction_booking',

             'idil.item.movement',

            # 'pos.payment',
            # 'pos.order',
            # 'pos.session',
            # 'pos.config',
        ]

        deletion_summary = []

        for model_name in models_to_delete:
            try:
                records = self.env[model_name].search([])
                if records:
                    record_count = len(records)
                    records.unlink()
                    message = f"Successfully deleted {record_count} records from {model_name}."
                    self._logger.info(message)
                    deletion_summary.append(message)
                else:
                    message = f"No records found in {model_name} to delete."
                    self._logger.info(message)
                    deletion_summary.append(message)
            except Exception as e:
                message = f"Error deleting records from {model_name}: {e}"
                self._logger.error(message)
                deletion_summary.append(message)

        # Join the summary into a single string to return
        return "\n".join(deletion_summary)

    @api.model
    def delete_other_models_setup(self, *args, **kwargs):
        models_to_delete = [


            'idil.customer.type.registration',
            'idil.customer.registration',

            'idil.item',
            'idil.unit.measure',
            'idil.item.category',

            'idil.kitchen',
            'idil.payment.method',

            'my_product.product',

            'idil.vendor.registration',

            'idil.chart.account',
            'idil.chart.account.subheader',
            'idil.chart.account.header',

        ]

        deletion_summary = []

        for model_name in models_to_delete:
            try:
                records = self.env[model_name].search([])
                if records:
                    record_count = len(records)
                    records.unlink()
                    message = f"Successfully deleted {record_count} records from {model_name}."
                    self._logger.info(message)
                    deletion_summary.append(message)
                else:
                    message = f"No records found in {model_name} to delete."
                    self._logger.info(message)
                    deletion_summary.append(message)
            except Exception as e:
                message = f"Error deleting records from {model_name}: {e}"
                self._logger.error(message)
                deletion_summary.append(message)

        # Join the summary into a single string to return
        return "\n".join(deletion_summary)
