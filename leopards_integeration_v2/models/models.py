# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools, _
from odoo.exceptions import except_orm, ValidationError
import logging
import datetime
from datetime import timedelta, date
import math
import _sqlite3
import requests
import json

_logger = logging.getLogger(__name__)

class ShopifyConnectorInstance(models.Model):
    _inherit='ks.shopify.connector.instance'
    get_cn_url=fields.Char('Webservice URL',default='http://new.leopardscod.com/webservice/getShipmentDetailsByOrderID/format/json/')
    leopards_tracking_url=fields.Char('CN Tracking URL',default='https://leopards.developifyapps.com/track')
    leopards_api_key=fields.Char('API Key',default='DC6A25D9B75AAB28495CF3675724471A')
    leopards_api_password=fields.Char('Password',default='ZIVNI@123456')

class Account_move(models.Model):
    _inherit='account.move'
    leopards_tracking_url=fields.Char('Tracking URL')
    shipment_status=fields.Char('Shipment Status')
    city=fields.Char('City')
    leopards_weight=fields.Float('Leopards Weight')

class SaleOrder(models.Model):
    _inherit='sale.order'
    leopards_tracking_url=fields.Char('Tracking URL')
    shipment_status=fields.Char('Shipment Status')
    city=fields.Char('City')
    leopards_weight=fields.Float('Leopards Weight')
    
    
    def get_shipment_details(self):
        shopify_instance=self.env['ks.shopify.connector.instance'].search([('id','=',self.ks_shopify_instance.id)])
        if shopify_instance:
            data={
            'api_key':str(shopify_instance.leopards_api_key),
            'api_password':str(shopify_instance.leopards_api_password),
            'shipment_order_id':[str(self.name)]
            }
            my_json_string = json.dumps(data)
            abc_headers={
           'Content-Type': 'application/json',
           }
            result = requests.post(str(shopify_instance.get_cn_url),headers=abc_headers,data=my_json_string)
            error=result.json().get('error')
            if not error:
                for each in result.json().get('data'):
                    tracking_number=each['track_number']
                    shipment_status=each['booked_packet_status']
                    city=each['destination_city']
                    leopards_weight=each['booked_packet_weight']
                self.write({'leopards_tracking_url':str(shopify_instance.leopards_tracking_url)+"/"+tracking_number,
                                    'shipment_status':shipment_status,
                                    'city':city,
                                    'leopards_weight':leopards_weight})
                account_move_obj=self.env['account.move'].search([('invoice_origin','=',self.name)])
                for inv in account_move_obj:
                    inv.write({'leopards_tracking_url':str(shopify_instance.leopards_tracking_url)+"/"+tracking_number,
                                    'shipment_status':shipment_status,
                                    'city':city,
                                    'leopards_weight':leopards_weight})
    
    
class Picking(models.Model):
    _inherit = "stock.picking"
        
    def set_shipped(self):
        shopify_instance=self.env['ks.shopify.connector.instance'].search([('id','=',self.sale_id.ks_shopify_instance.id)])
        if shopify_instance:
            data={
            'api_key':str(shopify_instance.leopards_api_key),
            'api_password':str(shopify_instance.leopards_api_password),
            'shipment_order_id':[str(self.sale_id.name)]
            }
            my_json_string = json.dumps(data)
            abc_headers={
           'Content-Type': 'application/json',
           }
            result = requests.post(str(shopify_instance.get_cn_url),headers=abc_headers,data=my_json_string)
            error=result.json().get('error')
            if not error:
                for each in result.json().get('data'):
                    tracking_number=each['track_number']
                    shipment_status=each['booked_packet_status']
                    city=each['destination_city']
                    leopards_weight=each['booked_packet_weight']
                    
                self.sale_id.write({'leopards_tracking_url':str(shopify_instance.leopards_tracking_url)+"/"+tracking_number,
                                    'shipment_status':shipment_status,
                                    'city':city,
                                    'leopards_weight':leopards_weight})
                account_move_obj=self.env['account.move'].search([('invoice_origin','=',self.sale_id.name)])
                for inv in account_move_obj:
                    inv.write({'leopards_tracking_url':str(shopify_instance.leopards_tracking_url)+"/"+tracking_number,
                                        'shipment_status':shipment_status,
                                        'city':city,
                                        'leopards_weight':leopards_weight})
        
        
        return super(Picking,self).set_shipped()

class SaleReport(models.Model):
    _inherit = "sale.report"
    shipment_status=fields.Char('Shipment Status')
    city=fields.Char('City')
    
    def _query(self, with_clause='', fields={}, groupby='', from_clause=''):
        with_ = ("WITH %s" % with_clause) if with_clause else ""

        select_ = """
            coalesce(min(l.id), -s.id) as id,
            l.product_id as product_id,
            t.uom_id as product_uom,
            CASE WHEN l.product_id IS NOT NULL THEN sum(l.product_uom_qty / u.factor * u2.factor) ELSE 0 END as product_uom_qty,
            CASE WHEN l.product_id IS NOT NULL THEN sum(l.qty_delivered / u.factor * u2.factor) ELSE 0 END as qty_delivered,
            CASE WHEN l.product_id IS NOT NULL THEN sum(l.qty_invoiced / u.factor * u2.factor) ELSE 0 END as qty_invoiced,
            CASE WHEN l.product_id IS NOT NULL THEN sum(l.qty_to_invoice / u.factor * u2.factor) ELSE 0 END as qty_to_invoice,
            CASE WHEN l.product_id IS NOT NULL THEN sum(l.price_total / CASE COALESCE(s.currency_rate, 0) WHEN 0 THEN 1.0 ELSE s.currency_rate END) ELSE 0 END as price_total,
            CASE WHEN l.product_id IS NOT NULL THEN sum(l.price_subtotal / CASE COALESCE(s.currency_rate, 0) WHEN 0 THEN 1.0 ELSE s.currency_rate END) ELSE 0 END as price_subtotal,
            CASE WHEN l.product_id IS NOT NULL THEN sum(l.untaxed_amount_to_invoice / CASE COALESCE(s.currency_rate, 0) WHEN 0 THEN 1.0 ELSE s.currency_rate END) ELSE 0 END as untaxed_amount_to_invoice,
            CASE WHEN l.product_id IS NOT NULL THEN sum(l.untaxed_amount_invoiced / CASE COALESCE(s.currency_rate, 0) WHEN 0 THEN 1.0 ELSE s.currency_rate END) ELSE 0 END as untaxed_amount_invoiced,
            count(*) as nbr,
            s.name as name,
            s.date_order as date,
            s.state as state,
            s.partner_id as partner_id,
            s.user_id as user_id,
            s.company_id as company_id,
            s.campaign_id as campaign_id,
            s.medium_id as medium_id,
            s.source_id as source_id,
            extract(epoch from avg(date_trunc('day',s.date_order)-date_trunc('day',s.create_date)))/(24*60*60)::decimal(16,2) as delay,
            t.categ_id as categ_id,
            s.pricelist_id as pricelist_id,
            s.analytic_account_id as analytic_account_id,
            s.team_id as team_id,
            p.product_tmpl_id,
            partner.country_id as country_id,
            partner.industry_id as industry_id,
            partner.commercial_partner_id as commercial_partner_id,
            CASE WHEN l.product_id IS NOT NULL THEN sum(p.weight * l.product_uom_qty / u.factor * u2.factor) ELSE 0 END as weight,
            CASE WHEN l.product_id IS NOT NULL THEN sum(p.volume * l.product_uom_qty / u.factor * u2.factor) ELSE 0 END as volume,
            l.discount as discount,
            CASE WHEN l.product_id IS NOT NULL THEN sum((l.price_unit * l.product_uom_qty * l.discount / 100.0 / CASE COALESCE(s.currency_rate, 0) WHEN 0 THEN 1.0 ELSE s.currency_rate END))ELSE 0 END as discount_amount,
            s.id as order_id,
            s.city,
            s.shipment_status
        """

        for field in fields.values():
            select_ += field

        from_ = """
                sale_order_line l
                      right outer join sale_order s on (s.id=l.order_id)
                      join res_partner partner on s.partner_id = partner.id
                        left join product_product p on (l.product_id=p.id)
                            left join product_template t on (p.product_tmpl_id=t.id)
                    left join uom_uom u on (u.id=l.product_uom)
                    left join uom_uom u2 on (u2.id=t.uom_id)
                    left join product_pricelist pp on (s.pricelist_id = pp.id)
                %s
        """ % from_clause

        groupby_ = """
            l.product_id,
            l.order_id,
            t.uom_id,
            t.categ_id,
            s.name,
            s.date_order,
            s.partner_id,
            s.user_id,
            s.state,
            s.company_id,
            s.campaign_id,
            s.medium_id,
            s.source_id,
            s.pricelist_id,
            s.analytic_account_id,
            s.team_id,
            p.product_tmpl_id,
            partner.country_id,
            partner.industry_id,
            partner.commercial_partner_id,
            l.discount,
            s.id %s
        """ % (groupby)

        return '%s (SELECT %s FROM %s GROUP BY %s)' % (with_, select_, from_, groupby_)

    def init(self):
        # self._table = sale_report
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""CREATE or REPLACE VIEW %s as (%s)""" % (self._table, self._query()))
    