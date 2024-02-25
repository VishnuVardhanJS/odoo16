from odoo import models, fields, api


class SendCustomEmail(models.TransientModel):
    _name = 'send.mail.wizard'
    _description = 'My Wizard'

    '''
    Add newly added custom email template record id with the name in the below Selection field
    '''
    selection_field = fields.Selection([
        ('account.tax_invoice_template', 'Tax Invoice'),
        ('account.license_invoice_template', 'Tax License'),
        ('account.resource_invoice_template', 'Tax Resource'),
    ], string='Select Option', required=True)

    move_id = fields.Many2one('account.move', string='Account Move', readonly=True)

    @api.model
    def default_get(self, fields):
        res = super(SendCustomEmail, self).default_get(fields)
        context = dict(self._context or {})
        if 'active_id' in context and 'active_model' in context and context['active_model'] == 'account.move':
            res['move_id'] = context.get('active_id')
        return res

    @api.depends('selection_field', 'move_id')
    def confirm_selection(self):
        selected_option = self.selection_field

        '''
            Add an new condition if the selected option equals email template id call the send function with the 
            selected email template record id
        '''

        if selected_option == 'account.tax_invoice_template':
            self.env.ref("account.tax_invoice_template").send_mail(self.move_id.id)
        elif selected_option == 'account.license_invoice_template':
            self.env.ref("account.license_invoice_template").send_mail(self.move_id.id)
        elif selected_option == 'account.resource_invoice_template':
            self.env.ref("account.resource_invoice_template").send_mail(self.move_id.id)
        # return {'type': 'ir.actions.act_window_close'}

        last_outgoing_email = self.env['mail.mail'].sudo().search([
            ('create_uid', '=', self.env.user.id),
        ], order='id desc', limit=1)

        if last_outgoing_email:
            return {
                'name': 'Email Templates',
                'type': 'ir.actions.act_url',
                'url': f'/web#id={last_outgoing_email.id}&cids=1&menu_id=4&model=mail.mail&view_type=form',
                'target': 'self',
            }
        else:
            return {
                'name': 'Email Templates',
                'type': 'ir.actions.act_url',
                'url': '/web#model=mail.mail&view_type=list&cids=1&menu_id=4',
                'target': 'self',
            }
