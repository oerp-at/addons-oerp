# -*- coding: utf-8 -*-
__name__ = "migrate current purchase orders"

def migrate(cr,v):
    cr.execute("UPDATE purchase_order SET recv_confirm = true WHERE state='approved'")
