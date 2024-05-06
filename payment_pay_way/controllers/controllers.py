import werkzeug
from odoo import http, _
from odoo.http import request
from odoo.addons.payment import utils as payment_utils
from odoo.exceptions import ValidationError
from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing

class PaymentPayway(http.Controller):
    @http.route('/payment/payway/get_provider_info', type='json', auth='public')
    def payway_get_provider_info(self, rec_id, flow, net_amount=0):
        """ Return public information on the provider.

        :param int rec_id: The payment option handling the transaction, as a `payment.provider` or `payment.token` id
        :return: Information on the provider, namely: the state, payment method type, login ID, and
                 public client key
        :rtype: dict
        """
        if flow == "token":
            provider_sudo = request.env['payment.token'].browse(rec_id).provider_id.sudo()
        else:
            provider_sudo = request.env['payment.provider'].sudo().browse(rec_id).exists()
        return {
            'public_key': provider_sudo.payway_public_key,
            'base_url': provider_sudo.payway_get_base_url(),
            'card_tree': provider_sudo.payway_card_installment_tree(float(net_amount)),
            'cybersource': not provider_sudo.payway_cybersource,
        }

    @http.route('/payment/payway/payment', type='json', auth='public')
    def payway_payment(self, reference, partner_id, access_token=None, **kwargs):
        # Check that the transaction details have not been altered
        # if not payment_utils.check_access_token(access_token, reference, partner_id):
        #    raise ValidationError("payway: " + _("Received tampered payment request data."))

        # Make the payment request to payway
        tx_sudo = request.env['payment.transaction'].sudo().search([('reference', '=', reference)])
        fees = float(kwargs['fees'])

        # Sanitarize fees amount round
        # agregamos esto para sanitizar el recargo en casos donde el producto de recargo use impuestos NO inclidos en el precio donde podríamos tener un error de redondeo. Para replicarlo por ej. 
        # una venta sin recargo de  al sacarle el impuesto (para reflejarlo se puede usar una venta de 45.73 + iva 1,21, con recargo del 0.49,
        # eso nos da un recargo de 27.11 que cuando se refleja en odoo quedará de 22,4 + 1.21 = 27,1 (lo que nos produce una diferencia de un centavo)

        if tx_sudo and fees:
            product = tx_sudo.provider_id.product_surcharge_id
            taxes = product.taxes_id.filtered(lambda t: t.company_id.id  == tx_sudo.provider_id.company_id.id)
            if any(not x.price_include for x in taxes):
                total_excluded = taxes.filtered(lambda x: not x.price_include).with_context(force_price_include=True).compute_all(fees, currency=tx_sudo.currency_id)['total_excluded']
                fees = taxes.filtered(lambda x: not x.price_include).compute_all(total_excluded, currency=tx_sudo.currency_id)['total_included']

        tx_sudo.fees = fees
        tx_sudo.amount += fees

        tx_sudo.payway_payment_method = str(kwargs['payway_payment_method'])
        tx_sudo.payway_payment_instalment = int(kwargs['payway_payment_instalment'])

        response_content = tx_sudo._payway_create_transaction_request(kwargs)
        # Handle the payment request response
        feedback_data = {'reference': tx_sudo.reference, 'response': response_content}
        request.env['payment.transaction'].sudo()._handle_notification_data('payway', feedback_data)


    @http.route('/payment/payway_confirmation', type='http', methods=['GET'], auth='public', website=True)
    def payment_confirm(self, tx_id, access_token, **kwargs):
        """ Display the payment confirmation page with the appropriate status message to the user.

        :param str tx_id: The transaction to confirm, as a `payment.transaction` id
        :param str access_token: The access token used to verify the user
        :param dict kwargs: Optional data. This parameter is not used here
        :raise: werkzeug.exceptions.NotFound if the access token is invalid
        """
        tx_id = self._cast_as_int(tx_id)
        if tx_id:
            tx_sudo = request.env['payment.transaction'].sudo().browse(tx_id)

            # Raise an HTTP 404 if the access token is invalid
            if not payment_utils.check_access_token(
                access_token, tx_sudo.partner_id.id, tx_sudo.amount - tx_sudo.fees, tx_sudo.currency_id.id
            ):
                raise werkzeug.exceptions.NotFound  # Don't leak info about existence of an id

            # Fetch the appropriate status message configured on the provider
            if tx_sudo.state == 'draft':
                status = 'info'
                message = tx_sudo.state_message \
                          or _("This payment has not been processed yet.")
            elif tx_sudo.state == 'pending':
                status = 'warning'
                message = tx_sudo.provider_id.pending_msg
            elif tx_sudo.state in ('authorized', 'done'):
                status = 'success'
                message = tx_sudo.provider_id.done_msg
            elif tx_sudo.state == 'cancel':
                status = 'danger'
                message = tx_sudo.provider_id.cancel_msg
            else:
                status = 'danger'
                message = tx_sudo.state_message \
                          or _("An error occurred during the processing of this payment.")

            # Display the payment confirmation page to the user
            PaymentPostProcessing.remove_transactions(tx_sudo)
            render_values = {
                'tx': tx_sudo,
                'status': status,
                'message': message
            }
            return request.render('payment.confirm', render_values)
        else:
            # Display the portal homepage to the user
            return request.redirect('/my/home')

    @staticmethod
    def _cast_as_int(str_value):
        """ Cast a string as an `int` and return it.

        If the conversion fails, `None` is returned instead.

        :param str str_value: The value to cast as an `int`
        :return: The casted value, possibly replaced by None if incompatible
        :rtype: int|None
        """
        try:
            return int(str_value)
        except (TypeError, ValueError, OverflowError):
            return None
