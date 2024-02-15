# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _, tools
from odoo.exceptions import Warning, UserError, ValidationError
import datetime
import json


class CreateCommisionInvoice(models.Model):
    _name = 'create.invoice.commission'
    _description = 'create invoice commission'

    group_by = fields.Boolean('Group By', readonly=False)
    date = fields.Date('Invoice Date', readonly=False)

    def invoice_create(self):
        sale_invoice_ids = self.env['invoice.sale.commission'].browse(self._context.get('active_ids'))

        cancle_commission = sale_invoice_ids.filtered(lambda t: t.state == 'cancel')
        if len(cancle_commission) > 0:
            raise UserError('You can not create invoice of cancled commission')
        else:
            if any(line.invoiced == True for line in sale_invoice_ids):
                raise UserError('Invoiced Lines cannot be Invoiced Again.')

            commission_discount_account = self.env.user.company_id.commission_discount_account
            if not commission_discount_account:
                raise UserError('You have not configured commission Discount Account')

            moves = []
            if self.group_by:
                group_dict = {}
                partner_check = []
                delay_check = True

                for record in sale_invoice_ids:
                    partner_check.append(record.user_id.partner_id.id)
                    group_dict.setdefault(record.user_id.partner_id.id, []).append(record)
                    invoiceable_date = record.date + datetime.timedelta(days=record.invoice_delay)

                    if invoiceable_date > datetime.datetime.today().date():
                        delay_check = False

                check = len(set(partner_check))

                if delay_check:
                    if check == 1:
                        for dict_record in group_dict:
                            inv_lines = []
                            for inv_record in group_dict.get(dict_record):
                                inv_lines.append({
                                    'name': inv_record.name,
                                    'quantity': 1,
                                    'price_unit': inv_record.commission_amount,
                                    'account_id': commission_discount_account.id,
                                })
                            partner = self.env['res.partner'].search([('id', '=', dict_record)])
                            inv_id = self.env['account.move'].create({
                                'move_type': 'in_invoice',
                                'partner_id': partner.id,
                                'invoice_date': self.date if self.date else datetime.datetime.today().date(),
                                'invoice_line_ids': [(0, 0, l) for l in inv_lines],
                            })
                            moves.append(inv_id.id)
                        sale_invoice_ids.write({'invoiced': True, 'invoice_id': moves[0], 'state': 'invoiced'})
                    else:
                        raise UserError('You have not created an invoice with a different salesperson.')
                else:
                    raise UserError("Commission Invoice Date not Reached")
            else:
                delay_check = True
                for commission_record in sale_invoice_ids:
                    invoiceable_date = commission_record.date + datetime.timedelta(days=commission_record.invoice_delay)

                    if invoiceable_date > datetime.datetime.today().date():
                        delay_check = False

                    if delay_check:
                        inv_lines = []
                        inv_lines.append({
                            'name': commission_record.name,
                            'quantity': 1,
                            'price_unit': commission_record.commission_amount,
                            'account_id': commission_discount_account.id,
                        })

                        inv_id = self.env['account.move'].create({
                            'move_type': 'in_invoice',
                            'invoice_line_ids': [(0, 0, l) for l in inv_lines],
                            'partner_id': commission_record.user_id.partner_id.id,
                            'invoice_date': self.date if self.date else datetime.datetime.today().date()
                        })
                        moves.append(inv_id.id)
                        commission_record.write({
                            'invoiced': True,
                            'invoice_id': inv_id.id,
                            'state': 'invoiced'
                        })
                    else:
                        raise UserError("Commission Invoice Date not Reached")


'''New class to handle sales commission configuration.'''


class SaleCommission(models.Model):
    _name = 'sale.commission'
    _rec_name = 'comm_type'
    _description = 'Sale commission'

    user_ids = fields.Many2many('res.users', 'commision_rel_user', 'commision_id', 'user_id', string='Sales Person',
                                help="Select sales person associated with this type of commission",
                                required=True)
    name = fields.Char('Commission Name', required=True)
    comm_type = fields.Selection([
        ('standard', 'Standard'),
        ('partner', 'Partner Based'),
        ('mix', 'Product/Category/Margin Based'),
        ('discount', 'Discount Based'),
    ], 'Commission Type', copy=False, default='standard', help="Select the type of commission you want to apply.")
    affiliated_partner_commission = fields.Float(string="Affiliated Partner Commission percentage")
    nonaffiliated_partner_commission = fields.Float(string="Non-Affiliated Partner Commission percentage")
    exception_ids = fields.One2many('sale.commission.exception', 'commission_id', string='Sales Commission Exceptions',
                                    help="Sales commission exceptions",
                                    )
    rule_ids = fields.One2many('discount.commission.rules', 'commission_id', string='Commission Rules',
                               help="Commission Rules",
                               )
    no_discount_commission_percentage = fields.Float(string="No Discount Commission %",
                                                     help="Related Commission % when No discount", )
    max_discount_commission_percentage = fields.Float(string="Max Discount %", help="Maximum Discount %", )
    gt_discount_commission_percentage = fields.Float(string="Discount > 25% Commission %",
                                                     help="Related Commission % when discount '%' is greater than 25%", )
    dis_commission_percentage = fields.Float(string="Discount >")
    standard_commission = fields.Float(string="Standard Commission percentage")

    @api.constrains('dis_commission_percentage')
    def _check_dis_commission_percentage(self):
        for rule in self.rule_ids:
            if rule.discount_percentage > 0:
                if self.dis_commission_percentage < rule.discount_percentage:
                    raise ValidationError(_('Discount Commission is more then Commission Rules Discount.'))
        if self.max_discount_commission_percentage < self.dis_commission_percentage:
            raise ValidationError(_('Discount Commission is more then Max Discount.'))

    @api.constrains('rule_ids')
    def _check_rule_ids(self):
        for rule in self.rule_ids:
            if rule.discount_percentage > 0:
                if rule.discount_percentage > self.dis_commission_percentage:
                    raise ValidationError(_('Commission Rules Discount is more then Discount Commission.'))

    @api.constrains('max_discount_commission_percentage')
    def _check_max_discount_commission_percentage(self):
        if self.dis_commission_percentage > self.max_discount_commission_percentage:
            raise ValidationError(_('Max Discount is more then Discount Commission.'))

    @api.constrains('user_ids')
    def _check_uniqueness(self):
        '''This method checks constraint for only one commission group for each sales person'''
        for obj in self:
            ex_ids = self.search([('user_ids', 'in', [x.id for x in obj.user_ids])])
            if len(ex_ids) > 1:
                raise UserError('Only one commission type can be associated with each sales person!')
        return True


'''New class to handle sales commission exceptions'''


class SaleCommissionException(models.Model):
    _name = 'sale.commission.exception'
    _rec_name = 'commission_precentage'
    _description = 'Sale Commission Exception'

    based_on = fields.Selection([('Products', 'Products'),
                                 ('Product Categories', 'Product Categories'),
                                 ('Product Sub-Categories', 'Product Sub-Categories')], string="Based On",
                                help="commission exception based on", default='Products',
                                required=True)
    based_on_2 = fields.Selection([('Fix Price', 'Fix Price'),
                                   ('Margin', 'Margin'),
                                   ('Commission Exception', 'Commission Exception')], string="With",
                                  help="commission exception based on", default='Fix Price',
                                  required=True)
    commission_id = fields.Many2one('sale.commission', string='Sale Commission',
                                    help="Related Commission", )
    product_id = fields.Many2one('product.product', string='Product',
                                 help="Exception based on product", )
    categ_id = fields.Many2one('product.category', string='Product Category',
                               help="Exception based on product category")

    sub_categ_id = fields.Many2one('product.category', string='Product Sub-Category',
                                   help="Exception based on product sub-category")
    commission_precentage = fields.Float(string="Commission %")
    below_margin_commission = fields.Float(string="Below Margin Commission %")
    above_margin_commission = fields.Float(string="Above Margin Commission %")
    margin_percentage = fields.Float(string="Target Margin %")
    price = fields.Float(string="Target Price")
    price_percentage = fields.Float(string="Above price Commission %")

    category_store = fields.Many2many('product.category', string="Category store", compute="_compute_all_ids",
                                      store=True)

    ##########################Added By Vishnu##############################

    sale_user_id = fields.Many2one('res.users', string='Salesperson', store=True)
    achieved_percentage = fields.Float(string='Percentage', compute="_calculate_achieved_percentage")
    achieved_amount = fields.Float(string='Achieved Amount', compute='_compute_total_sales')
    target_percentage = fields.Float(string="Target %")
    target_start_date = fields.Datetime(string="Start Date")
    target_end_date = fields.Datetime(string="End Date")
    payout_status = fields.Boolean(string="Payment Status", default=False)
    invoice_delay = fields.Integer(string="Invoice Delay", default=0)
    order_history = fields.Char(string="Visited Orders", default='{"order_id": []}')
    non_invoiced_amount = fields.Float(string="Non Invoiced Amount", default=0)
    last_order = fields.Char(string="last SO ID")
    invoiced_amount = fields.Float(string="Invoiced Amount", default=0)
    cost_price = fields.Float(string="Licensed Cost Price", default=0)

    ##########################Added By Vishnu##############################

    ##########################Added By Vishnu##############################

    @api.constrains('categ_id', 'sale_user_id', 'sub_categ_id', 'based_on')
    def _compute_total_sales(self):
        for record in self:
            if record.based_on == 'Product Sub-Categories':
                if record.target_start_date == False:
                    sales = self.env['sale.order.line'].search([
                        ('product_id.categ_id.complete_name', '=', record.sub_categ_id.complete_name),
                        ('order_id.user_id', '=', record.sale_user_id.id),
                        ('state', '!=', 'cancel'),
                        ('state', '!=', 'draft')
                    ])
                else:
                    sales = self.env['sale.order.line'].search([
                        ('product_id.categ_id.complete_name', '=', record.sub_categ_id.complete_name),
                        ('order_id.user_id', '=', record.sale_user_id.id),
                        ('state', '!=', 'cancel'),
                        ('state', '!=', 'draft'),
                        ('write_date', '>=', record.target_start_date),
                        ('write_date', '<=', record.target_end_date)
                    ])

                if record.sub_categ_id.complete_name.replace(" ", "").split('/')[0] == "Licensed":
                    sub_categ_total_sales = sum(sales.mapped('purchase_price'))
                else:
                    sub_categ_total_sales = sum(sales.mapped('price_total'))
                record.achieved_amount = sub_categ_total_sales


                temp_order_dict = json.loads(record.order_history)
                for order_check in temp_order_dict["order_id"]:
                    if order_check not in sales.mapped("id"):
                        # removes the order id from the order history if the sale order is cancelled
                        temp_order_dict["order_id"].remove(order_check)
                        record.order_history = json.dumps(temp_order_dict)
                        # subtracts the deleted sale order amount from the unpaid invoice amount
                        if record.sub_categ_id.complete_name.replace(" ", "").split('/')[0] == "Licensed":
                            record.non_invoiced_amount = record.non_invoiced_amount - self.env[
                                "sale.order.line"].search([("id", "=", order_check)]).purchase_price
                            record.invoiced_amount = record.invoiced_amount - self.env["sale.order.line"].search(
                                [("id", "=", order_check)]).purchase_price
                        else:
                            record.non_invoiced_amount = record.non_invoiced_amount - self.env[
                                "sale.order.line"].search([("id", "=", order_check)]).price_total
                            record.invoiced_amount = record.invoiced_amount - self.env["sale.order.line"].search(
                                [("id", "=", order_check)]).price_total
                        if record.non_invoiced_amount < 0:
                            record.non_invoiced_amount = 0
                        if record.invoiced_amount < 0:
                            record.invoiced_amount = 0
                        # disables the payout button if the unpaid invoice amount becomes 0
                        if record.non_invoiced_amount == 0:
                            record.payout_status = True

                # To add the newly added amount to the non invoiced amount
                for id_rec in sales.mapped("id"):
                    if id_rec not in temp_order_dict["order_id"]:
                        temp_order_dict["order_id"].append(id_rec)
                        record.order_history = json.dumps(temp_order_dict)
                        if record.sub_categ_id.complete_name.replace(" ", "").split('/')[0] == "Licensed":
                            record.non_invoiced_amount = record.non_invoiced_amount + self.env[
                                "sale.order.line"].search([("id", "=", id_rec)]).purchase_price
                        else:
                            record.non_invoiced_amount = record.non_invoiced_amount + self.env[
                                "sale.order.line"].search([("id", "=", id_rec)]).price_total
                        record.last_order = self.env["sale.order.line"].search([("id", "=", id_rec)]).order_id.id
                        # makes the payout button visible so that it can be used again even after the initial payout
                        record.payout_status = False

            elif record.based_on == 'Product Categories':
                if record.target_start_date == False:
                    categ_sales = self.env['sale.order.line'].search(
                        [('product_id.categ_id.complete_name', 'ilike',
                          "%" + record.categ_id.complete_name.replace(" ", "").split('/')[0] + "%"),
                         ('order_id.user_id', '=', record.sale_user_id.id),
                         ('state', '!=', 'cancel'),
                         ('state', '!=', 'draft')])
                else:
                    categ_sales = self.env['sale.order.line'].search(
                        [('product_id.categ_id.complete_name', 'ilike',
                          "%" + record.categ_id.complete_name.replace(" ", "").split('/')[0] + "%"),
                         ('order_id.user_id', '=', record.sale_user_id.id),
                         ('state', '!=', 'cancel'),
                         ('state', '!=', 'draft'),
                         ('write_date', '>=', record.target_start_date),
                         ('write_date', '<=', record.target_end_date)])

                if record.categ_id.complete_name.replace(" ", "").split('/')[0] == "Licensed":
                    categ_sales_total = sum(categ_sales.mapped('purchase_price'))
                else:
                    categ_sales_total = sum(categ_sales.mapped('price_total'))
                record.achieved_amount = categ_sales_total

                '''stored the previously visited sales order number in an dictionary
                 in order_history fields to allow multiple payouts'''
                temp_order_dict = json.loads(record.order_history)
                for order_check in temp_order_dict["order_id"]:
                    if order_check not in categ_sales.mapped("id"):
                        # removes the order id from the order history if the sale order is cancelled
                        temp_order_dict["order_id"].remove(order_check)
                        record.order_history = json.dumps(temp_order_dict)
                        # subtracts the deleted sale order amount from the unpaid invoice amount
                        if record.categ_id.complete_name.replace(" ", "").split('/')[0] == "Licensed":
                            record.non_invoiced_amount = record.non_invoiced_amount - self.env[
                                "sale.order.line"].search(
                                [("id", "=", order_check)]).purchase_price
                            record.invoiced_amount = record.invoiced_amount - self.env["sale.order.line"].search(
                                [("id", "=", order_check)]).purchase_price
                        else:
                            record.non_invoiced_amount = record.non_invoiced_amount - self.env[
                                "sale.order.line"].search(
                                [("id", "=", order_check)]).price_total
                            record.invoiced_amount = record.invoiced_amount - self.env["sale.order.line"].search(
                                [("id", "=", order_check)]).price_total
                        if record.non_invoiced_amount < 0:
                            record.non_invoiced_amount = 0
                        if record.invoiced_amount < 0:
                            record.invoiced_amount = 0
                        # disables the payout button if the unpaid invoice amount becomes 0
                        if record.non_invoiced_amount == 0:
                            record.payout_status = True

                for id_rec in categ_sales.mapped("id"):
                    if id_rec not in temp_order_dict["order_id"]:
                        temp_order_dict["order_id"].append(id_rec)
                        record.order_history = json.dumps(temp_order_dict)
                        if record.categ_id.complete_name.replace(" ", "").split('/')[0] == "Licensed":
                            record.non_invoiced_amount = record.non_invoiced_amount + self.env["sale.order.line"].search(
                                [("id", "=", id_rec)]).purchase_price
                        else:
                            record.non_invoiced_amount = record.non_invoiced_amount + self.env[
                                "sale.order.line"].search(
                                [("id", "=", id_rec)]).price_total
                        record.last_order = self.env["sale.order.line"].search([("id", "=", id_rec)]).order_id.id
                        record.payout_status = False

                record.payout_status = True

            else:
                record.achieved_amount = 0

    # Function to calculate the achieved percentage
    @api.depends('price', 'achieved_amount', 'achieved_percentage', 'sub_categ_id')
    def _calculate_achieved_percentage(self):
        self.achieved_percentage = 0.0
        for rec in self:
            try:
                rec.achieved_percentage += (rec.achieved_amount / rec.price) * 100
            except ZeroDivisionError:
                rec.achieved_percentage = 0.0

    # Function which runs on click of the payout button
    def Payout_Button(self):
        for rec in self:
            # checks if the achieved percentage is greater than 0 and is greater than the required target percentage
            if rec.achieved_percentage > 0 and rec.achieved_percentage > 0:
                if rec.achieved_percentage >= rec.target_percentage:
                    # calls the invoice sales commission to add the commission to the commission lines
                    invoice_commission_obj = self.env['invoice.sale.commission']
                    # data for the commission lines

                    '''order id and order_line_id intentionally set to False to reduce bugs
                     need to parse from sale.order if order ID is needed for the commission lines'''
                    invoice_commission_data = {'name': False,
                                               'product_id': False,
                                               'commission_id': rec.commission_id.id,
                                               'invoice_delay': rec.invoice_delay,
                                               'categ_id': False,
                                               'sub_categ_id': False,
                                               'user_id': rec.sale_user_id.id,
                                               'type_name': "Test",
                                               'comm_type': "mix",
                                               'commission_amount': False,
                                               'order_id': rec.last_order,
                                               'order_line_id': False,
                                               'date': datetime.datetime.today()}
                    if rec.based_on == 'Product Categories':
                        name = 'Commission Exception' + ' ' + 'with' + ' "' + tools.ustr(
                            rec.based_on_2) + ' "' + ' ' + 'for' + ' ' + tools.ustr(
                            rec.based_on) + ' "' + tools.ustr(
                            rec.categ_id.complete_name.replace(" ", "").split('/')[0]) + '" @' + tools.ustr(
                            rec.commission_precentage) + '%'
                        invoice_commission_data['name'] = name
                        invoice_commission_data['categ_id'] = rec.categ_id.id

                    elif rec.based_on == 'Product Sub-Categories':
                        name = 'Commission Exception' + ' ' + 'with' + ' "' + tools.ustr(
                            rec.based_on_2) + ' "' + ' ' + 'for' + ' ' + tools.ustr(
                            rec.based_on) + ' "' + tools.ustr(
                            rec.sub_categ_id.complete_name) + '" @' + tools.ustr(
                            rec.commission_precentage) + '%'

                        invoice_commission_data['name'] = name
                        invoice_commission_data['sub_categ_id'] = rec.sub_categ_id.id

                    elif rec.based_on == "Products":
                        name = 'Commission Exception' + ' ' + 'with' + ' "' + tools.ustr(
                            rec.based_on_2) + ' "' + ' ' + 'for' + ' ' + tools.ustr(
                            rec.based_on) + ' "' + tools.ustr(
                            rec.product_id.name) + '" @' + tools.ustr(
                            rec.commission_precentage) + '%'

                        invoice_commission_data['name'] = name
                        invoice_commission_data['product_id'] = rec.product_id.id

                    if rec.invoiced_amount < rec.price and rec.invoiced_amount + rec.non_invoiced_amount > rec.price:
                        print("passed if ")
                        over_achieved_amount = rec.non_invoiced_amount + rec.invoiced_amount - rec.price
                        above_price_commission = over_achieved_amount * (
                                rec.price_percentage / 100)
                        commission_amount = ((rec.non_invoiced_amount - over_achieved_amount) * (
                                rec.commission_precentage / 100)) + above_price_commission
                    elif rec.achieved_percentage > 100:
                        print("passed elif")
                        # above_price_commission = rec.non_invoiced_amount * (rec.price_percentage / 100)
                        commission_amount = (rec.non_invoiced_amount * (
                                rec.price_percentage / 100))
                    else:
                        print("passed else")
                        commission_amount = rec.non_invoiced_amount * (rec.commission_precentage / 100)

                    invoice_commission_data['commission_amount'] = commission_amount

                    invoice_commission_obj.create(invoice_commission_data)
                    rec.invoiced_amount = rec.invoiced_amount + rec.non_invoiced_amount
                    rec.non_invoiced_amount = 0
                    rec.payout_status = True

                else:
                    raise UserError("Target Not Achieved")
            else:
                raise UserError("Target Not Achieved")

    ##########################Added By Vishnu##############################

    @api.depends('based_on', 'sub_categ_id', 'categ_id')
    def _compute_all_ids(self):

        for line in self:
            category_lst = []
            if line.based_on == 'Product Categories':
                category_lst.append(line.categ_id.id)

                for child in line.categ_id.child_id:
                    if child.id not in category_lst:
                        category_lst.append(child.id)
                category_store = ''
                for num in category_lst:
                    category_store = category_store + ',' + str(num)
                line.category_store = category_lst
            elif line.based_on == 'Product Sub-Categories':

                for child in line.sub_categ_id.child_id:
                    if child.id not in category_lst:
                        category_lst.append(child.id)

                category_store = ''
                for num in category_lst:
                    category_store = category_store + ',' + str(num)

                line.category_store = category_lst

            else:
                line.category_store = category_lst


'''New class to handle discount based commission'''


class DiscountCommissionRules(models.Model):
    _name = 'discount.commission.rules'
    _rec_name = 'discount_percentage'
    _description = 'Discount Commission Rules'

    commission_id = fields.Many2one('sale.commission', string='Sale Commission',
                                    help="Related Commission", )
    discount_percentage = fields.Float(string="Discount %")
    commission_percentage = fields.Float(string="Commission %")
