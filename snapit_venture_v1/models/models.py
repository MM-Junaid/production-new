# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools, _
from odoo.exceptions import except_orm, ValidationError
import logging
import datetime
from datetime import timedelta, date
import math
import _sqlite3
import requests
_logger = logging.getLogger(__name__)

class PurchaseOrder(models.Model):
    _inherit='purchase.order'
    qc_by=fields.Many2many('res.users','purchase_order_user_rel','po_id','user_id','QC By')

class SaleOrder(models.Model):
    _inherit='sale.order'
    total_weight=fields.Float('Total Weight',compute='_cal_total_weight',store=True)
    delivery_status=fields.Selection([('In Process','In Process'),('Shipped','Shipped'),('Delivered','Delivered')],'Delivery Status',default='In Process',tracking=True)
    my_activity_date_deadline=fields.Datetime()
    qc_by=fields.Many2many('res.users','sale_order_user_rel','order_id','user_id','QC By')
            
    
    @api.depends('order_line')
    def _cal_total_weight(self):
        for each in self:
            total_weight=0
            if each.order_line:
                for line in each.order_line:
                    total_weight+=line.x_studio_weight
            each.total_weight=total_weight
    
    def action_confirm(self):
        super(SaleOrder, self).action_confirm()
        model_obj=self.env['ir.model'].search([('model','=',self._name)])
        user_obj=self.company_id.auto_schedule_user
        if user_obj:
            activity_vals={'res_model_id':model_obj.id,
                           'res_model':self._name,
                           'res_id':self.id,
                           'res_name':self.name,
                           'activity_type_id':4,
                           'summary':'Dispatch Order',
                           'note':'Order No.'+str(self.name)+' has been verified. please go for further process',
                           'date_deadline':date.today() + timedelta(days=5),
                           'user_id':user_obj.id,
                           }
            mail_activity=self.env['mail.activity'].sudo().create(activity_vals) 

class Account(models.Model):
    _inherit='account.account'
    limit_applicable=fields.Boolean('Limit Applicable')
    limit=fields.Float('Amount Limit')


class AccountMove(models.Model):
    _inherit='account.move'
    approval_applicable=fields.Boolean('Approval Applicable',compute='_cal_approval_applicable')
    approved=fields.Boolean('Approved')
    approval_date=fields.Date('Approval Date')
    approved_by=fields.Many2one('res.users','Approved By')
    
    @api.depends('invoice_line_ids')
    def _cal_approval_applicable(self):
        for each in self:
            each.approval_applicable=False
            year=each.date.year
            month=each.date.strftime("%B")            
            for line in each.invoice_line_ids:
                move_line_obj=self.env['account.move.line'].search([('year','=',year),('month','=',month),('account_id','=',line.account_id.id)])
                total_amount=0
                for move in move_line_obj:
                    total_amount+=move.price_subtotal
                if line.account_id.limit_applicable and total_amount+line.price_subtotal>line.account_id.limit:
                    each.approval_applicable=True
                else:
                    each.approval_applicable=False
    def action_post(self):
        if self.approval_applicable and not self.approved:
            raise ValidationError('Please get approved this record to proceed.')
        else:
            super(AccountMove, self).action_post()
    def approve_bill(self):
        self.write({'approved':True,
                    'approval_date':fields.Datetime.now(),
                    'approved_by':self.env.user.id})

class AccountMoveLine(models.Model):
    _inherit='account.move.line'
    year=fields.Char('Year',compute='_get_year',store=True)
    month=fields.Char('Month',compute='_get_year',store=True)
     
    @api.depends('date')
    def _get_year(self):
        for each in self:
            if each.date:
                each.year=each.date.year
                each.month=each.date.strftime("%B")
            else:
                each.year=''
                each.month=''
class Picking(models.Model):
    _inherit = "stock.picking"
    delivery_status=fields.Selection([('In Process','In Process'),('Shipped','Shipped'),('Delivered','Delivered')],'Delivery Status',default='In Process',tracking=True)
    
    def set_shipped(self):
        self.write({'delivery_status':'Shipped'})
        self.sale_id.write({'delivery_status':'Shipped'})
        
    def set_delivered(self):
        self.write({'delivery_status':'Delivered'})
        self.sale_id.write({'delivery_status':'Delivered'})
    
    
    def button_validate(self):
        for each in self.check_ids:
            if each.quality_state=='fail':
                raise ValidationError("""Sorry you are not allowed to proceed, Quality check for '"""+str(each.product_id.name)+"""' has been failed.""")
        return super(Picking,self).button_validate()
    
class QualityChecklistCategory(models.Model):
    _name='quality.checklist.category'
    name=fields.Char('Category',required=True)

class QualityChecklistCriteria(models.Model):
    _name='quality.checklist.criteria'
    name=fields.Char('Criteria',required=True)
    quality_points=fields.Float('Quality Points',required=True)
    
class QualityChecklist(models.Model):
    _name='quality.checklist'
    category_id=fields.Many2one('quality.checklist.category','Category',required=True)
    criteria_id=fields.Many2one('quality.checklist.criteria','Criteria')
    decision=fields.Boolean('Decision')
    quality_check_id=fields.Many2one('quality.check','Quality Check')
    quality_point_id=fields.Many2one('quality.point','Quality Point')
class QualityPoints(models.Model):
    _inherit='quality.point'
    quality_checklist_ids=fields.One2many('quality.checklist','quality_point_id','Quality Check List')
    max_tolerance=fields.Float('Max. Tolerance (%)')
    

class QualityCheck(models.Model):
    _inherit='quality.check'
    quality_checklist_ids=fields.One2many('quality.checklist','quality_check_id','Quality Check List',compute='_get_quality_checklist',store=True)
    max_tolerance=fields.Float('Max. Tolerance (%)',related='point_id.max_tolerance')
    total_points=fields.Float('Total Quality Points',compute='_cal_quality_points')
    qc_by=fields.Many2many('res.users','quality_checks_user_rel','check_id','user_id','QC By')
    
    def do_pass(self):
        res=super(QualityCheck,self).do_pass()
        if self.picking_id:
            qc_by_list = []
            for qc in self.qc_by:
                qc_by_list.append(qc.id)
            stock_move_obj=self.env['stock.move'].search([('picking_id','=',self.picking_id.id)])
            if stock_move_obj.sale_line_id:
                stock_move_obj.sale_line_id.order_id.write({'qc_by':[(6,0,qc_by_list)]})
            elif stock_move_obj.purchase_line_id:
                stock_move_obj.purchase_line_id.order_id.write({'qc_by':[(6,0,qc_by_list)]})
        return res
    
    def do_fail(self):
        res=super(QualityCheck,self).do_fail()
        if self.picking_id:
            qc_by_list = []
            for qc in self.qc_by:
                qc_by_list.append(qc.id)
            stock_move_obj=self.env['stock.move'].search([('picking_id','=',self.picking_id.id)])
            if stock_move_obj.sale_line_id:
                stock_move_obj.sale_line_id.order_id.write({'qc_by':[(6,0,qc_by_list)]})
            elif stock_move_obj.purchase_line_id:
                stock_move_obj.purchase_line_id.order_id.write({'qc_by':[(6,0,qc_by_list)]})
        return res
    
    @api.depends('point_id')
    def _get_quality_checklist(self):
        for each in self:
            if each.point_id:
                if not each.quality_checklist_ids:
                    for checklist in each.point_id.quality_checklist_ids:
                        checklist_vals={'category_id':checklist.category_id.id,
                                        'criteria_id':checklist.criteria_id.id,
                                        'quality_check_id':each.id}
                        self.env['quality.checklist'].sudo().create(checklist_vals)
    
    @api.depends('quality_checklist_ids')
    def _cal_quality_points(self):
        for each in self:
            total_points=0
            for checklist in each.quality_checklist_ids:
                if checklist.decision==True:
                    total_points+=checklist.criteria_id.quality_points
            each.total_points=total_points


class NonMovingProducts(models.Model):
    _name='stock.nonmoving.products'
    name=fields.Char('Name',required=True)
    no_of_days=fields.Integer('No. of Days',required=True)
    no_of_sales=fields.Integer('Minimum No. of Sales',required=True)
    valid_users=fields.Many2many('res.users','rel_nonmoving_products_users','nomoving_id','user_id','Send Notification to Users',required=True)
    
    
    def get_leopards_shipment_number(self):
        import json
        data={
        'api_key':'DC6A25D9B75AAB28495CF3675724471A',
        'api_password':'ZIVNI@123456',
        'shipment_order_id':['#5042']
        }
        my_json_string = json.dumps(data)
        abc_headers={
       'Content-Type': 'application/json',
       }
        result = requests.post('http://new.leopardscod.com/webservice/getShipmentDetailsByOrderID/format/json/',headers=abc_headers,data=my_json_string)
        error=result.json().get('error')
        for each in result.json().get('data'):
            print (each['track_number'])
        
    def send_email_of_non_moving_products(self):
        non_moving_products_config=self.env['stock.nonmoving.products'].search([],limit=1)
        if non_moving_products_config:
            product_list=[]
            lines = []
            sale_obj = self.env['sale.order.line']
            product_obj = self.env['product.product']
            all_product_id = self.env['product.product'].search([])
            product_ids = []
            final_list = []
            final_list_pro = []
            sale_order_line_list = []
            create_date=date.today() - timedelta(days=non_moving_products_config.no_of_days)
    #         body="""<table>
    #             <tbody>
    #             
    #             <tr>
    #             
    #             <th style="width:135px">Product description</th>
    #             
    #             <th style="width: 85px;">Qty Shipped</td>
    #             
    #             <th style="width: 125px;">Date Shipped</th>
    #             
    #             </tr>"""
            for product in all_product_id:
                sale_ids = sale_obj.search([('order_id.state','in',['sale','done']),('create_date','>=', create_date),('product_id','=',product.id)])
                if len(sale_ids)<non_moving_products_config.no_of_sales:
                    product_ids.append({'product_name':product.name,})
            body = """<p><strong>Dear Sir,</strong></p>
            <p>Here is the details of the non moving products given below.</p>
            <table border='1'>
            <tr><th>Product Name</th></tr>"""
            for row in product_ids:
                body = body + "<tr>"
                for col in row.values():
                    body = body + "<td>" + str(col)+ "</td>"
                body = body + "</tr>"
            body = body + "</table><p>Regards</p>"
            subject="""Non-Moving Products List of """+str(date.today())
            to_email=''
            for user in non_moving_products_config.valid_users:
                if to_email:
                    to_email+=','+user.login
                else:
                    to_email+=user.login
            if to_email:
                    self.generate_email(subject,body,to_email)
        else:
            raise ValidationError('Non-Moving Products configuration is missing.')

    def generate_email(self,subject,body,to_email):
        mail_values = {
#         'email_from':'ali.alkbar@kics.edu.pk',
        'subject':subject,
        'body_html':body,
        'email_to':to_email,
#         'email_cc':email_cc
        }
        self.env['mail.mail'].create(mail_values).send()

class ResCompany(models.Model):
    _inherit='res.company'
    auto_schedule_user=fields.Many2one('res.users','Auto Schedule Activity Account')
    stock_receive_upper_limit=fields.Float('Upper Limit (%)')
    stock_receive_lower_limit=fields.Float('Lower Limit (%)')
    
    stock_dispatch_upper_limit=fields.Float('Upper Limit (%)')
    stock_dispatch_lower_limit=fields.Float('Lower Limit (%)')
class KsProductTemplate(models.Model):
    _inherit='ks.shopify.product.template'
    
    def update_product_details_from_shopify(self):
        active_ids = self.env.context.get("active_ids")
        records = self.browse(active_ids)
        ks_product_templ_obj = self.env['ks.shopify.product.template'].search([('id', 'in', records.ids)])
        for tmpl in ks_product_templ_obj:
            product_template=self.env['product.template'].search([('id','=',tmpl.ks_shopify_product_template.id)])
            for product in product_template:
                product.sudo().write({'barcode':tmpl.ks_barcode})
            ks_product_variant_obj=self.env['ks.shopify.product.variant'].search([('ks_shopify_product_tmpl_id','=',tmpl.id)])
            if product_template:
                for ks_product in ks_product_variant_obj:
                    product_varient=self.env['product.product'].search([('product_tmpl_id','=',product.id),('id','=',ks_product.ks_shopify_product_variant.id)])
                    for varient in product_varient:
                            varient.sudo().write({'barcode':ks_product.ks_barcode,
                                                  'weight':ks_product.ks_weight,
                                                  'lst_price':ks_product.ks_shopify_regular_price,
                                              'default_code':ks_product.ks_default_code})
    
class Product(models.Model):
    _inherit='product.product'
    
    @api.onchange('barcode')
    def onchange_product_barcode(self):
        if self.barcode:
            ks_product_template=self.env['ks.shopify.product.template'].sudo().search([('ks_shopify_product_template','=',self.product_tmpl_id.id)])
            for each in ks_product_template:
                each.write({'ks_barcode':self.barcode})
     
    
class ProductTemplate(models.Model):
    _inherit='product.template'
    margin=fields.Float('Margin (%)',compute='_cal_margin',store=True)
    website_published = fields.Selection([('unpublished', 'Unpublished'), ('published_web', 'Published in Web Only'),
                                          ('published_global', 'Published in Web and POS')],
                                         default='unpublished', copy=False, string="Published ?")
    my_activity_date_deadline=fields.Datetime()
    product_published=fields.Char('Product Published')
    
    
    def update_product_details_to_shopify(self):
        active_ids = self.env.context.get("active_ids")
        records = self.browse(active_ids)
        product_templ_obj = self.env['product.template'].search([('id', 'in', records.ids)])
        for tmpl in product_templ_obj:
            ks_product_template=self.env['ks.shopify.product.template'].search([('ks_shopify_product_template','=',tmpl.id)])
            for shopify_prodcut in ks_product_template:
                shopify_prodcut.sudo().write({'ks_barcode':tmpl.barcode})
            product_obj=self.env['product.product'].search([('product_tmpl_id','=',tmpl.id)])
            if ks_product_template:
                for product in product_obj:
                    ks_product_varient=self.env['ks.shopify.product.variant'].search([('ks_shopify_product_tmpl_id','=',shopify_prodcut.id),('ks_shopify_product_variant','=',product.id)])
                    for varient in ks_product_varient:
                            varient.sudo().write({'ks_barcode':product.barcode,
                                                  'ks_weight':product.weight,
                                              'ks_default_code':product.default_code})

    @api.depends('list_price','standard_price')
    def _cal_margin(self):
        for each in self:
            if each.list_price and each.standard_price:
                each.margin=((each.list_price-each.standard_price)/each.list_price)*100
            else:
                each.margin=0
    
#     def _get_product_status(self):
#         for each in self:
#             shopify_product=self.env['shopify.product.template.ept'].search([('product_tmpl_id','=',each.id)])
#             if shopify_product:
#                 for product in shopify_product:
#                     if product.website_published=='published_web' or product.website_published=='published_global':
#                         each.product_published=product.website_published
#                         each.write({'website_published':product.website_published})
#                     else:
#                         each.product_published='unpublished'
#                         each.write({'website_published':product.website_published})
#             else:
#                 each.product_published='unpublished'
#                 each.write({'website_published':'unpublished'})
    
#     @api.depends('product_published')
#     def _cal_product_published(self):
#         for each in self:
#             if each.product_published:
#                
#             else:
#                 each.write({'website_published':'unpublished'})
                
class StockMove(models.Model):
    _inherit='stock.move'
    
    def write(self,vals):
        res=super(StockMove,self).write(vals)
        for each in self:
            if each.purchase_line_id:
                upper_limit=self.company_id.stock_receive_upper_limit
                lower_limit=self.company_id.stock_receive_lower_limit
                done_qty=each.quantity_done
                demand_qty=each.product_uom_qty
                receive_percentage=0
                if done_qty and demand_qty:
                    receive_percentage=((done_qty/demand_qty)*100)-100
                if receive_percentage!=0:
                    if receive_percentage>upper_limit:
                            raise ValidationError('Done quantity should not be greater than allowed upper limit.')
                    if receive_percentage<lower_limit:
                        raise ValidationError('Done quantity should not be less than allowed lower limit.')
            elif each.sale_line_id:
                upper_limit=self.company_id.stock_dispatch_upper_limit
                lower_limit=self.company_id.stock_dispatch_lower_limit
                done_qty=each.quantity_done
                demand_qty=each.product_uom_qty
                dispatch_percentage=0
                if done_qty and demand_qty:
                    dispatch_percentage=((done_qty/demand_qty)*100)-100
                if dispatch_percentage!=0:
                    if dispatch_percentage>upper_limit:
                        raise ValidationError('Done quantity should not be greater than allowed upper limit.')
                    if dispatch_percentage<lower_limit:
                        raise ValidationError('Done quantity should not be less than allowed lower limit.')

class StockQuant(models.Model):
    _inherit='stock.quant'
    internal_refrence=fields.Char('Internal Refrence',related='product_id.product_tmpl_id.default_code')
    barcode=fields.Char('Barcode',related='product_id.barcode')
    prodcut_brand_id=fields.Many2one('common.product.brand.ept',related='product_id.product_tmpl_id.product_brand_id',store=True)
    cost=fields.Float('Cost',compute='_get_cost_price')
    
    @api.depends('value','available_quantity')
    def _get_cost_price(self):
        for each in self:
            if each.value and each.available_quantity:
                each.cost=each.value/each.available_quantity
            else:
                each.cost=0