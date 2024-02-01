# -*- coding: utf-8 -*-
from odoo import fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    def action_preview_po(self):
        return {
            'target': 'new',
            'type': 'ir.actions.act_url',
            'url': '/report/pdf/purchase.report_purchaseorder/%s' % self.id
        }