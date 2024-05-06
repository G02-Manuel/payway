from odoo import fields, models
from odoo.addons.payment_pay_way.models.payway_library import PAYWAY_METHODS

import logging

_logger = logging.getLogger(__name__)


class PaymentToken(models.Model):
    _inherit = 'payment.token'

    payway_payment_method = fields.Selection(
        PAYWAY_METHODS,
        string='payway payment method',
    )
    payway_bin = fields.Char(
        string='Bin'
    )
