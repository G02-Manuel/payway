from odoo import models, _
from odoo.exceptions import UserError
from odoo.addons.payment_pay_way.models.payway_library import PROD_BASE_API_URL, TEST_BASE_API_URL
import logging
import requests

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    def payway_get_base_url(self):
        self.ensure_one()

        if self.state == 'enabled':
            return PROD_BASE_API_URL
        elif self.state == 'test':
            return TEST_BASE_API_URL
        else:
            raise UserError(_("Decidir is disabled"))

    def payway_healthcheck(self):
        api_url = self. payway_get_base_url() + '/healthcheck'
        response = requests.get(api_url, data={})
        if response.status_code == 200:
            res = response.json()
            # to do oki?
        else:
            raise UserError(_("Decidir healthcheck error"))

    def payway_get_headers(self):
        return {
            'apikey': self.payway_secret_key,
            'content-type': "application/json",
            'cache-control': "no-cache"
        }

    def payway_cancel_refund(self, payment_id, refund_id):
        # merchantId
        api_url = self.payway_get_base_url() + '/payments/%i/refunds/%i' % (payment_id, refund_id)
        headers = self.payway_get_headers()
        payload = '{}'
        response = requests.delete(api_url, data=payload, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            raise UserError(_("No puedo recuperar este pago"))

    def payway_refund_payment(self, payment_id, amount=0):
        # merchantId
        api_url = self.payway_get_base_url() + '/payments/' + str(payment_id) + '/refunds'
        headers = self.payway_get_headers()
        payload = '{}'
        if (amount):
            payload = '{"amount": %i}' % int(amount * 100)

        response = requests.post(api_url, data=payload, headers=headers)
        if response.status_code == 201:
            return response.json()
        if response.status_code == 400:
            res = response.json()
            raise UserError("ERROR \n" + str(res))
        else:
            raise UserError(_("No puedo devolver este pago"))

    def payway_get_payment_info(self, payment_id):
        # merchantId
        api_url = self.payway_get_base_url() + '/payments/' + str(payment_id)
        headers = self.payway_get_headers()
        payload = {}
        response = requests.get(api_url, params=payload, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            raise UserError(_("No puedo recuperar este pago"))

    def payway_get_payments(self, dateFrom=False, dateTo=False, siteOperationId=False, offset=0):
        api_url = self.payway_get_base_url() + '/payments'
        headers = self.payway_get_headers()
        payload = {
            'pageSize': 50,
            'offset': 0,
        }
        if (dateFrom):
            payload['dateFrom'] = dateFrom
        if (dateTo):
            payload['dateTo'] = dateTo
        if (siteOperationId):
            payload['siteOperationId'] = siteOperationId
        response = requests.get(api_url, params=payload, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            raise UserError(_("No puedo recuperar este pago"))


    def payway_card_installment_tree(self, net_amount=0):
        # TODO: Esto deberia ser por aquirer_id y publicadas?
        installment_ids = self.env['account.card.installment'].search([
            ('card_id.payway_method', '!=', False),
            ('card_id.company_id', '=', self.company_id.id)
        ])
        return installment_ids.card_installment_tree(net_amount)
