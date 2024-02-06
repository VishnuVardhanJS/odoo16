from odoo import api, fields, models, _
from odoo import tools

class product_category(models.Model):
    _inherit = "product.category"

    total_sales = fields.Float(string='Achieved Amount', compute='_compute_total_sales')

    def _compute_total_sales(self):
        exception_line = self.env['sale.commission.exception']

        # for record in exception_line:
        #     if record.based_on == 'Product Sub-Categories':
        #         sales = self.env['sale.order.line'].search([
        #             ('product_id.categ_id', '=', record.sub_categ_id.id),
        #             ('order_id.user_id', '=', record.sale_user_id.id),
        #             ('state', '!=', 'cancel')
        #         ])
        #         total = sum(sales.mapped('price_total'))
        #         self.achieved_amount = total
        #     elif record.based_on == 'Product Categories':
        #         categ_sales = self.env['sale.order.line'].search(
        #             [('product_id.categ_id.complete_name', 'ilike', "%" + record.categ_id.complete_name.replace(" ", "").split('/')[0] + "%"),
        #              ('order_id.user_id', '=', record.sale_user_id.id),
        #              ('state', '!=', 'cancel')])
        #         categ_sales_total = sum(categ_sales.mapped('price_total'))
        #         self.achieved_amount = categ_sales_total
        #     else:
        #         self.achieved_amount = 0

        for record in self:
            if "/" in record.complete_name:
                sales = self.env['sale.order.line'].search([
                    ('product_id.categ_id', '=', record.sub_categ_id.id),
                    ('order_id.user_id', '=', record.sale_user_id.id),
                    ('state', '!=', 'cancel')
                ])
                total = sum(sales.mapped('price_total'))
                self.achieved_amount = total


