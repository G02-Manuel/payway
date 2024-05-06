from odoo import fields, models, api, _
from odoo.exceptions import UserError
import json
import logging
import requests
import re

_logger = logging.getLogger(__name__)

from odoo.addons.payment_pay_way.models.payway_library import PAYWAY_METHODS, payway_sum_amounts, PAYWAY_ERRORS


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    payway_payment_id = fields.Integer(
        string='payway identification',
    )
    payway_payment_method = fields.Selection(
        PAYWAY_METHODS,
        string='Payment method'
    )
    payway_payment_instalment = fields.Integer(
        string='Instalment'
    )
    payway_ticket = fields.Char(
        string='Ticket',
    )
    payway_card_authorization_code = fields.Char(
        string='Card Authorization code',
    )
    payway_address_validation_code = fields.Char(
        string='Address validation code',
    )

    def payway_get_payment_info(self):
        rtn_txt = ''
        for transaction in self.filtered(lambda t: t.provider_id.provider == 'payway'):
            if transaction.payway_payment_id:
                transaction_info = transaction.provider_id.payway_get_payment_info(
                    transaction.payway_payment_id)
            elif transaction.reference:
                transaction_info = transaction.provider_id.payway_get_payments(
                    siteOperationId=transaction.reference)
                transaction_info = transaction_info['results'][0]

            if 'only_show_data' in self.env.context:
                for item in transaction_info:
                    rtn_txt += "%s: %s\n" % (item, transaction_info[item])
            else:
                transaction.set_payway_data(transaction_info)
                if transaction_info['status'] == 'annulled' \
                   and transaction.state in ['draft', 'authorized', 'done']:
                    transaction.mapped('payment_id').cancel()
                    transaction.write(
                        {'state': 'cancel', 'date': fields.Datetime.now()})
                    transaction._log_payment_transaction_received()

        if 'only_show_data' in self.env.context:
            raise UserError(rtn_txt)

    def _payway_get_error(self,response):
        if 'error' in response:
            return response.get('error',{}).get('reason',{}).get('description','Error en la transaccion')

    def payway_send_payment(self, kwargs):
        self.ensure_one()
        company_name = re.sub(r'\W+', '', self.provider_id.company_id.name)

        payload = {
            'site_transaction_id': self.reference[:40],
            'token': kwargs['token'],
            'payment_method_id': int(kwargs['payway_payment_method']),
            'bin': kwargs['bin'],
            'amount': payway_sum_amounts(self.amount, self.fees),
            'currency': 'ARS',
            'installments': int(kwargs['payway_payment_instalment']),
            'payment_type': 'single',
            'establishment_name': company_name,
            'email': self.partner_id.email,
            'sub_payments': [],

        }
        # add token request
        if self.tokenize and not self.token_id:
            payload['customer'] = {
                    "id": 'odoo_' + str(self.partner_id.id),
                    "email": str(self.partner_id.email)
            }
        payload = json.dumps(payload, indent=None)
        api_url = self.provider_id.payway_get_base_url() + '/payments'
        headers = self.provider_id.payway_get_headers()
        response = requests.post(api_url, data=payload, headers=headers)
        if response.status_code in [200,201]:
            return response.json()

        else:
            response_json = response.json()
            
            if 'validation_errors' in response_json and response_json['validation_errors']:
                errors = ''
                for error in response_json['validation_errors']: 
                    errors += PAYWAY_ERRORS.get(error['code'], error['code']) 
                self._set_error(errors)
                _logger.error(response.text)
            elif 'id' not in response_json and 'message' in response_json:
                self._set_error(response_json['message'])
                self._cr.commit()
                raise UserError(response_json['message'])
            else:
                self._set_error(self._payway_get_error(response_json))
                _logger.error("PAYWAY ERROR: %s" % response_json)

            return response_json

    @api.model
    def _get_tx_from_notification_data(self, provider_code, notification_data):
        if provider_code != 'payway':
            return super()._get_tx_from_notification_data(provider_code, notification_data)
        return self.sudo().search([('reference', '=', notification_data['reference'])])

    def _process_notification_data(self, notification_data):
        self.ensure_one()
        super()._process_notification_data(notification_data)

        if self.provider_id.code != 'payway':
            return
        response = notification_data['response']
        if 'id' not in response:
            self._set_error('Cant process payment')
        self.payway_payment_id = int(response.get('id', 0))
        self.provider_reference = str(response.get('id'))
        self.payway_payment_method = str(response.get('payment_method_id')) if response.get('payment_method_id') else False
        self.payway_payment_instalment = response.get('installments')
        if response.get('status_details') and len(response['status_details']):
            self.payway_card_authorization_code = response['status_details'].get('card_authorization_code')
            self.payway_ticket = response['status_details']['ticket']
            self.payway_address_validation_code = response['status_details'].get('address_validation_code')
        if response.get('status') == 'approved':
            self._set_done()
        if self.tokenize and not self.token_id:
            self.payway_add_token(response)

    def payway_add_token(self, data):
        api_url = self.provider_id.payway_get_base_url() + '/usersite/%s/cardtokens' % data['customer']['id']
        headers = self.provider_id.payway_get_headers()
        payload = {}
        response = requests.get(api_url, params=payload, headers=headers)
        if response.status_code == 200:
            #todo Filtrar
            response_data = response.json()
            for token_info in response_data['tokens']:
                if token_info['token'] == data['customer_token']:
                    method_name = [x[1] for x in PAYWAY_METHODS if x[0] == str(token_info['payment_method_id'])][0]
                    token = {
                        'payment_details': "%s terminada en %s" % (method_name, token_info['last_four_digits']),
                        'partner_id': self.partner_id.id,
                        'provider_id': self.provider_id.id,
                        'provider_ref': token_info['token'],
                        'payway_payment_method': str(token_info['payment_method_id']),
                        'active': True,
                    }
                    self.env['payment.token'].sudo().create(token)


    def _payway_create_transaction_request(self, kwargs):
        self.ensure_one()
        return self.payway_send_payment(kwargs)

    def _send_refund_request(self, amount_to_refund=None, create_refund_transaction=True):
        """ Override of payment to send a refund request to payway.

        Note: self.ensure_one()

        :param float amount_to_refund: The amount to refund
        :param bool create_refund_transaction: Whether a refund transaction should be created or not
        :return: The refund transaction if any
        :rtype: recordset of `payment.transaction`
        """
        self.ensure_one()
        res = super()._send_refund_request(
                amount_to_refund=amount_to_refund,
                create_refund_transaction=create_refund_transaction,
            )
        if self.provider_code == 'payway':
            if self.operation != 'refund':
                payment_id = res.source_transaction_id.payway_payment_id
                new_tx = self.provider_id.payway_refund_payment(payment_id, amount=float(amount_to_refund))

                res.provider_reference = str(new_tx['id'])
                res.payway_payment_id = int(new_tx['id'])
                res.payway_payment_method = res.source_transaction_id.payway_payment_method

                if new_tx['status_details'] and len(new_tx['status_details']):
                    res.payway_card_authorization_code = new_tx['status_details']['card_authorization_code']
                    res.payway_ticket = new_tx['status_details']['ticket']

                res._set_done()
            else:
                payment_id = res.source_transaction_id.source_transaction_id.payway_payment_id
                refund_id = res.source_transaction_id.payway_payment_id
                new_tx = self.provider_id.payway_cancel_refund(payment_id, refund_id)
                _logger.info(new_tx)
                res._set_done()
        return res



    def _set_done(self):
        def get_invoice_vals(invoice_id):
            return {
                'date': fields.Datetime.today(),
                'invoice_date': fields.Datetime.today(),
                'invoice_origin': _('Payment transaction %s') % self.external_id,
                'journal_id': invoice_id.journal_id.id,
                'invoice_user_id': invoice_id.user_id.id,
                'partner_id': invoice_id.partner_id.id,
                'move_type': 'in_invoice',
            }
        payway_fees_tx = self.filtered(lambda p: p.provider_code == 'payway' and p.fees)
        if len(payway_fees_tx):
            product = self.company_id.product_surcharge_id
            if not product:
                _logger.warning(
                    _("To validate payment with payway  is necessary to have a product surcharge in the "
                    "company of the payment transaction. Please check this in the Account Config"))
                return super()._set_done()
            for tx in payway_fees_tx:
                product_line_created = False
                sale_installed = hasattr(tx, 'sale_order_ids')
                taxes = product.taxes_id.filtered(lambda t: t.company_id.id == tx.company_id.id)
                amount_total = taxes.filtered(lambda x: not x.price_include).with_context(force_price_include=True).compute_all(
                    tx.fees, currency=self.currency_id)['total_excluded']
                if sale_installed and len(tx.sale_order_ids.filtered(lambda so: so.state in ('draft', 'sent', 'sale'))):
                    order_ids = tx.sale_order_ids.filtered(lambda so: so.state in ('draft', 'sent', 'sale'))
                    taxes = product.taxes_id.filtered(lambda t: t.company_id.id == tx.company_id.id)
                    order_ids[0].write({'order_line': [(0, 0, {
                        'product_id': product.id,
                        'name': product.display_name,
                        'price_unit': amount_total,
                        'tax_id': [(6, 0, taxes.ids)],
                    })]})
                    product_line_created = True

                elif not product_line_created and len(tx.invoice_ids):
                    draft_invoices = tx.invoice_ids.filtered(lambda inv: inv.state == 'draft')
                    if draft_invoices:
                        draft_invoices[0].write({'invoice_line_ids': [(0, 0, {
                            'product_id': product.id,
                            'price_unit': amount_total,
                            'tax_ids': [(6, 0, taxes.ids)],
                        })]})
                    else:
                        invoice_id = tx.invoice_ids[0]
                        debit_note = {
                            'date': fields.Datetime.today(),
                            'invoice_date': fields.Datetime.today(),
                            'invoice_origin': _('Payment transaction %s') % tx.reference,
                            'journal_id': invoice_id.journal_id.id,
                            'invoice_user_id': invoice_id.user_id.id,
                            'partner_id': invoice_id.partner_id.id,
                            'debit_origin_id':invoice_id.id,
                            'move_type': 'out_invoice',
                            'invoice_line_ids': [(0, 0, {
                                'product_id': product.id,
                                'price_unit': amount_total,
                                'tax_ids': [(6, 0, taxes.ids)],
                            })]
                        }
                        invoice = self.env['account.move'].with_context(
                            company_id=tx.company_id.id,
                            internal_type='debit_note'
                        ).create(debit_note)
                        tx.invoice_ids = [(4, invoice.id)]
                        invoice.action_post()
        
        return super()._set_done()

