# -*- coding: utf-8 -*-
# -*- encoding: utf-8 -*-

#############################################################################
#
#    Copyright (c) 2007 Martin Reisenhofer <martin.reisenhofer@funkring.net>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp.osv import fields, osv
from openerp.tools.translate import _
import re

class account_invoice(osv.osv):
    
    def _ubl_compute_lines(self, cr, uid, lines, qty=None, context=None):
        """
        RETURN: {
                'total': 0.0,                # Total without taxes
                'total_included: 0.0,        # Total with taxes
                'taxes': { 'tax_id' : { 'amount' : 0.0, 
                                        'base' : 0.0 } }
            }
        """
        
        res = {
          "total" : 0.0,
          "total_included" : 0.0,
          "taxes" : {}       
        }
               
        tax_obj =  self.pool.get("account.tax")
        total_tax = 0.0
        for line in lines:
            line_qty = line.quantity
            if not qty is None:
                line_qty = qty
            if not res.get("currency"):
                res["currency"]=line.invoice_id.currency_id.name
            tax_calc = tax_obj.compute_full(cr, uid, line.invoice_line_tax_id, line.price_unit * (1-(line.discount or 0.0)/100.0), line_qty, line.product_id, line.partner_id, precision=4)
            res["total"]=res["total"]+round(tax_calc["total"],4)
            res["total_included"]=res["total_included"]+round(tax_calc["total_included"],4)
            for tax_line in tax_calc["taxes"]:
                tax = tax_obj.browse(cr,uid,tax_line["id"],context)
                res_tax = res["taxes"].get(tax.amount)
                if res_tax is None:
                    res_tax = {"name" : tax.name,
                               "percent" : tax.amount}  
                    res["taxes"][tax.amount]=res_tax
                tax_amount = round(tax_line.get("amount",0.0),4)
                total_tax += tax_amount
                res_tax["amount"] = res_tax.get("amount",0.0) + tax_amount
                res_tax["base"] = res_tax.get("base",0.0) + round((tax_line.get("price_unit",0.0) * line.quantity),4)
        
        if not res.get("currency"):
            currency = self.pool.get("res.currency").browse(cr,uid,self._get_currency(self, cr, uid, context),context=context)
            res["currency"] = currency.name
            
        res["total_tax"] = total_tax     
        return res
    
    def _ubl_add_comment(self, cr, uid, ubl_list, inv, profile, context=None):
        note = []
        if inv.comment:
          note.append(inv.comment)
        if profile and profile.payment_note:
          note.append(profile.payment_note)
        if note:
          ubl_list.append(("cbc:Note","\n\n".join(note)))
            
    def _ubl_add_order_ref(self, cr, uid, ubl_list, inv, context=None):
        ubl_ref = context.get("ubl_ref")
        if not ubl_ref and not inv.ubl_ref and not inv.name:
            raise osv.except_osv(_("Error"), _("No Order Reference!"))
        ubl_list.append(("cac:OrderReference",[("cbc:ID",ubl_ref or inv.ubl_ref or inv.name)]))
        
    def _ubl_add_country(self, cr, uid, ubl_list, country, context=None):
        if country:
            ubl_list.append(
                ("cac:Country", ("cbc:IdentificationCode",country.code))
            )
        
    def _ubl_add_address(self, cr, uid, ubl_list, partner, context=None, tag="cac:PostalAddress"):
        ubl_addr = []
        
        if partner.street:
            ubl_addr.append(("cbc:StreetName",partner.street))
        if partner.street2:
            ubl_addr.append(("cbc:AdditionalStreetName",partner.street2))
        if partner.city:
            ubl_addr.append(("cbc:CityName",partner.city))
        if partner.zip:
            ubl_addr.append(("cbc:PostalZone",partner.zip))
        
        self._ubl_add_country(cr, uid, ubl_addr, partner.country_id, context)
        ubl_list.append((tag,ubl_addr))
    
    def _ubl_add_contact(self, cr, uid, ubl_list, partner, context=None):
        ubl_contact = []
        if partner.phone:
            number = partner.phone
            number = number.replace("(0)","")
            number = re.sub(r"[^0-9+]","",number)
            ubl_contact.append(("cbc:Telephone",number))
        if partner.email:
            ubl_contact.append(("cbc:ElectronicMail",partner.email))        
        ubl_list.append(("cac:Contact",ubl_contact))
    
    def _ubl_add_vat(self, cr, uid, ubl_list, partner, context=None):
        ubl_vat =[]
        ubl_vat.append(("cbc:CompanyID",partner.vat or "ATU00000000"))        
        ubl_vat.append(("cac:TaxScheme",("cbc:ID","VAT",{ "schemeAgencyID" : 6, "schemeID" : "UN/ECE 5153"})))
        ubl_list.append(("cac:PartyTaxScheme",ubl_vat))
        
    def _ubl_profile(self, cr, uid, inv, context):
        profile = self.pool.get("ubl.profile")._get_ubl(cr, uid, context)
        if not profile:
            raise osv.except_osv(_("Error"), _("No UBL Profile defined!"))
        return profile
    
    def _ubl_add_accounting_supplier(self, cr, uid, ubl_list, inv, context):
        company = inv.company_id
        profile = self._ubl_profile(cr, uid, inv, context)
        
        ubl_party = [("cac:PartyName",("cbc:Name",company.partner_id.name))]
        self._ubl_add_address(cr, uid, ubl_party, company.partner_id, context)
        self._ubl_add_vat(cr, uid, ubl_party, company.partner_id, context)
        self._ubl_add_contact(cr, uid, ubl_party, company.partner_id, context)
        
        ubl_list.append(("cac:AccountingSupplierParty",[
          ("cbc:CustomerAssignedAccountID",profile.code),
          ("cac:Party",ubl_party)
        ]))
                
    def _ubl_add_accounting_customer(self, cr, uid, ubl_list, inv, context):
        partner = inv.partner_id
        
        customer_id=context.get("customer_id")
        if customer_id:
            partner = self.pool.get("res.partner").browse(cr,uid, customer_id, context)
                        
        ubl_party = [("cac:PartyName",("cbc:Name",partner.name))]
        self._ubl_add_address(cr, uid, ubl_party, partner, context)
        self._ubl_add_vat(cr, uid, ubl_party, partner, context)
        self._ubl_add_contact(cr, uid, ubl_party, partner, context)
        
        ubl_list.append(("cac:AccountingCustomerParty",
          [("cbc:SupplierAssignedAccountID",inv.partner_id.ref),
           ("cac:Party",ubl_party)]
        ))
    
    def _delivery_info(self, cr, uid, inv, context):
        return {
            "date" : inv.date_invoice,
            "address" :  inv.partner_id    
        }
        
    def _ubl_add_delivery(self, cr, uid, ubl_list, inv, context):
        delivery_info = self._delivery_info(cr, uid, inv, context)

        ubl_delivery_loc = [("cbc:Description",inv.partner_id.name),
                            ("cbc:Name",inv.partner_id.name)]
        
        if not context.get("no_delivery_address",False):
            self._ubl_add_address(cr, uid, ubl_delivery_loc, inv.partner_id, context, tag="cac:Address")
        
        ubl_delivery = [("cbc:ActualDeliveryDate",delivery_info["date"]),
                        ("cac:DeliveryLocation",ubl_delivery_loc)]
        
        ubl_list.append(("cac:Delivery", ubl_delivery))
    
    def _ubl_add_payment_means(self, cr, uid, ubl_list, inv, profile, context):
        ubl_means = []
        ubl_means.append(("cbc:PaymentMeansCode",31))
        ubl_means.append(("cbc:PaymentDueDate",inv.date_due))
        ubl_means.append(("cbc:PaymentChannelCode","IBAN"))
        
        payment_note = []
        if inv.payment_term:            
            if inv.payment_term.note:
              payment_note.append(inv.payment_term.note)
            elif inv.payment_term.name:
              payment_note.append(inv.payment_term.name)
                          
        if profile and profile.payment_note:
          payment_note.append(profile.payment_note)
        
        if payment_note:
          ubl_means.append(("cbc:InstructionNote","\n\n".join(payment_note)))
        
        bank = inv.company_id.partner_id.bank_ids
        if bank:
            bank = bank[0]
        if not bank:
            raise osv.except_osv(_("Error"), _("There is no bank account for the company partner defined"))
        
        ubl_means.append(("cac:PayeeFinancialAccount",[
                            ("cbc:ID",bank.acc_number, {"schemeID":"IBAN"} ),
                            ("cac:FinancialInstitutionBranch",[
                                ("cac:FinancialInstitution",[
                                    ("cbc:ID",bank.bank.bic)                                                             
                                ])
                            ])
                        ]))
                
        ubl_list.append(("cac:PaymentMeans",ubl_means))
    
    def _payment_discount(self, cr, uid, inv, context):
        if inv.payment_term:
            term_obj = self.pool.get("account.payment.term")
            payment_amounts = term_obj.compute(cr, uid, inv.payment_term.id, inv.amount_total, date_ref=inv.date_invoice, context=context)
            index = len(payment_amounts)-2
            if index>=0:
                term_line = self.pool.get("account.payment.term.line").browse(cr,uid,payment_amounts[index][2],context)
                if term_line.value == "procent":
                    return {
                      "line" : term_line,
                      "percent" : term_line.value_amount*100,
                      "date" : payment_amounts[index][0],
                      "amount" : payment_amounts[index][1],     
                    }           
        return None
    
    def _ubl_add_payment_terms(self, cr, uid, ubl_list, inv, context):        
        payment_discount = self._payment_discount(cr, uid, inv, context)
        if payment_discount:
            ubl_list.append(("cac:PaymentTerms",[
                    ("cbc:ID",payment_discount["line"].id),
                    ("cbc:Note",payment_discount["line"].name),
                    ("cbc:SettlementDiscountPercent",payment_discount["percent"]),
                    ("cac:SettlementPeriod",[
                          ("cbc:StartDate",inv.date_invoice),
                          ("cbc:EndDate",payment_discount["date"])                     
                    ])                    
                ])) 
        
    def _ubl_tax(self, cr, uid, ubl_list, lines, context):
        tax_all = self._ubl_compute_lines(cr, uid, lines, context=context)
        
        ubl_taxes = [("cbc:TaxAmount", tax_all["total_tax"], {"currencyID" : tax_all["currency"]})]        
        for tax_value in tax_all["taxes"].values():
            ubl_taxes.append(
                ("cac:TaxSubtotal",[
                  ("cbc:TaxableAmount",tax_value["base"],{"currencyID" : tax_all["currency"]}),
                  ("cbc:TaxAmount",tax_value["amount"],{"currencyID" : tax_all["currency"]}),
                  ("cac:TaxCategory",[
                     ("cbc:ID","S",{"schemeAgencyID":6,"schemeID":"UN/ECE 5305"}),
                     ("cbc:Percent",int(tax_value["percent"]*100)),
                     ("cac:TaxScheme",[
                        ("cbc:ID","VAT",{"schemeAgencyID":6,"schemeID":"UN/ECE 5153"})
                     ])
                  ])                  
                ])
            )
                    
        ubl_list.append(("cac:TaxTotal",ubl_taxes))
    
    def _ubl_total(self, cr, uid, ubl_list, inv, context):
        #payment_discount = self._payment_discount(cr, uid, inv, context)
        ubl_list.append(("cac:LegalMonetaryTotal",[
                          #("cbc:LineExtensionAmount", payment_discount and payment_discount["amount"] or inv.amount_untaxed, {"currencyID" : inv.currency_id.name}),
                          ("cbc:LineExtensionAmount", inv.amount_untaxed, {"currencyID" : inv.currency_id.name}),
                          ("cbc:TaxExclusiveAmount", inv.amount_untaxed, {"currencyID" : inv.currency_id.name}),
                          ("cbc:TaxInclusiveAmount", inv.amount_total, {"currencyID" : inv.currency_id.name}),
                          ("cbc:PayableAmount", inv.amount_total, {"currencyID" : inv.currency_id.name})
                        ]))
   
    def _ubl_unit(self, cr, uid, uom, context=None):
        if uom:
            ubl_uom_obj = self.pool.get("ubl.uom")
            uom_ids = ubl_uom_obj.search(cr, uid, [("uom_id","=",uom.id)], context=context)
            if uom_ids:
                return ubl_uom_obj.browse(cr, uid, uom_ids[0], context).name
        return "EA"
    
    def _ubl_invoice(self, cr, uid, inv, profile=None, context=None):
        ubl_list = [("cbc:UBLVersionID","2.0"),
                    ("cbc:CustomizationID","urn:www.cenbii.eu:transaction:biicoretrdm010:ver1.0:#urn:www.peppol.eu:bis:peppol4a:ver1.0", {"schemeID" : "PEPPOL" }),
                    ("cbc:ProfileID","urn:www.cenbii.eu:profile:bii04:ver1.0" ),
                    ("cbc:ID",inv.number),
                    ("cbc:IssueDate", inv.date_invoice),
                    ("cbc:InvoiceTypeCode",380)
                   ]
        
        self._ubl_add_comment(cr, uid, ubl_list, inv, profile, context)
        
        ubl_list.append(("cbc:DocumentCurrencyCode",inv.currency_id.name))
        
        self._ubl_add_order_ref(cr, uid, ubl_list, inv, context)
        self._ubl_add_accounting_supplier(cr, uid, ubl_list, inv, context)
        self._ubl_add_accounting_customer(cr, uid, ubl_list, inv, context)
        self._ubl_add_delivery(cr, uid, ubl_list, inv, context)
        self._ubl_add_payment_means(cr, uid, ubl_list, inv, profile, context)
        self._ubl_add_payment_terms(cr, uid, ubl_list, inv, context)
        self._ubl_tax(cr, uid, ubl_list, inv.invoice_line, context)
        self._ubl_total(cr, uid, ubl_list, inv, context)
        
        for line in inv.invoice_line:
            product = line.product_id
            uom = line.uos_id or (product and product.uos_id) or None
            uom_code = self._ubl_unit(cr, uid, uom, context)
            
            lineCompute = self._ubl_compute_lines(cr, uid, [line], context=context)
            priceCompute = self._ubl_compute_lines(cr, uid, [line], qty=1, context=context)
            
            order_ref = 1
            so_line = line.sale_order_line_ids
            if so_line:
                so_line = so_line[0]
                for so_line2 in so_line.order_id.order_line:
                    if so_line2.id == so_line.id:
                        break
                    order_ref+=1
              
            res_line = [("cbc:ID",line.id),
                        ("cbc:InvoicedQuantity",line.quantity,{"unitCode" : uom_code }),
                        ("cbc:LineExtensionAmount",lineCompute["total"], {"currencyID" : inv.currency_id.name}),
                        ("cac:OrderLineReference",[
                            ("cbc:LineID",order_ref)
                        ])]
            
            self._ubl_tax(cr, uid, res_line, [line], context)
            
            res_line.append(("cac:Item",[
                ("cbc:Description",line.note or line.name),
                ("cbc:Name",line.name)
            ]))
               
            res_line.append(("cac:Price",[
                ("cbc:PriceAmount",  priceCompute["total"] ,{"currencyID":inv.currency_id.name}),
                ("cbc:BaseQuantity", 1, {"unitCode":inv.currency_id.name})
            ]))
            
            ubl_list.append(("cac:InvoiceLine",res_line))
                    
        return("Invoice", ubl_list, 
               { "xmlns" : "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
                 "xmlns:cac" : "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
                 "xmlns:cbc" : "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" })
            
#     def action_date_assign(self, cr, uid, ids, context=None):
#         ubl_invoice_ids = []
#         for invoice in self.browse(cr, uid, ids, context=context):
#             ubl_profile = self._ubl_profile(cr, uid, invoice, context)
#             if ubl_profile and not invoice.ubl_status:
#                 ubl_invoice_ids.append(invoice.id)
#         if ubl_invoice_ids:
#             self.write(cr, uid, ubl_invoice_ids, {"ubl_status": "prepare"}, context=context)
#         return super(account_invoice, self).action_date_assign(cr, uid, ids, context=context)

    _name = "account.invoice"
    _inherit = "account.invoice"
    _columns = {
        "ubl_ref" : fields.char("UBL Reference", readonly=True, select=True, copy=False),
        "ubl_status" : fields.selection([("prepare","Preparation"),
                                         ("sent","Sent"),
                                         ("except","Exception")], string="UBL Status", select=True, readonly=True, copy=False)
    }
