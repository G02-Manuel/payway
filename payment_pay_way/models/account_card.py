from odoo import models, fields
from odoo.addons.payment_pay_way.models.payway_library import PAYWAY_METHODS


class AccountCard(models.Model):

    _inherit = 'account.card'

    payway_method = fields.Selection(
        PAYWAY_METHODS,
        string='payway',
    )

    def map_card_values(self):
        self.ensure_one()
        res = super().map_card_values()
        res['payway_method'] = self.payway_method
        return res
