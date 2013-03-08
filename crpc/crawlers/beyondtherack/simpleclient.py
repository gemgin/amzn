#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: bishop Liu <miracle (at) gmail.com>

import lxml.html
from datetime import datetime

from server import beyondtherackLogin
from models import Product, Event

class CheckServer(object):
    def __init__(self):
        self.net = beyondtherackLogin()
        self.net.check_signin()

    def check_onsale_product(self, id, url):
        prd = Product.objects(key=id).first()
        if prd is None:
            print '\n\nbeyondtherack {0}, {1}\n\n'.format(id, url)
            return

        cont = self.net.fetch_product_page(url)
        if cont == -302:
            print '\n\nbeyondtherack product[{1}] sale end.'.format(id, url)
            if not prd.products_end or prd.products_end > datetime.utcnow():
                prd.products_end = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
                prd.update_history.update({ 'products_end': datetime.utcnow() })
                prd.save()
                return

        elif cont is None or isinstance(cont, int):
            cont = self.net.fetch_product_page(url)
            if cont is None or isinstance(cont, int):
                print '\n\nbeyondtherack product[{0}] download error.\n\n'.format(url)
                return

        tree = lxml.html.fromstring(cont)
        node = tree.cssselect('div#product-detail-wrapper div#product-details')[0]
        title = node.cssselect('div.left h1')[0].text_content().encode('utf-8')
        price = node.cssselect('div.left h3')[0].text_content().replace('$', '').replace(',', '').strip()
        listprice = node.cssselect('div.left p span.linethrough')
        listprice = listprice[0].text_content().replace('$', '').replace(',', '').strip() if listprice else ''
        soldout = tree.cssselect('div#product-detail-wrapper div#product-images div#img-div div.soldout-wrapper')
        soldout = True if soldout else False

        if prd.title.encode('utf-8').lower() != title.lower():
            print 'beyondtherack product[{0}] title error: [{1} vs {2}]'.format(url, prd.title.encode('utf-8'), title)
        if listprice and prd.listprice.replace('$', '').replace(',', '').strip() != listprice:
            print 'beyondtherack product[{0}] listprice error: [{1} vs {2}]'.format(url, prd.listprice.replace('$', '').replace(',', '').strip(), listprice)
            prd.listprice = listprice
            prd.update_history.update({ 'listprice': datetime.utcnow() })
            prd.save()

        if prd.price.replace('$', '').replace(',', '').strip() != price:
            print 'beyondtherack product[{0}] price error: [{1} vs {2}]'.format(url, prd.price.replace('$', '').replace(',', '').strip(), price)
            prd.price = price
            prd.update_history.update({ 'price': datetime.utcnow() })
            prd.save()

        if prd.soldout != soldout:
            print 'beyondtherack product[{0}] soldout error: [{1} vs {2}]'.format(url, prd.soldout, soldout)
            prd.soldout = soldout
            prd.update_history.update({ 'soldout': datetime.utcnow() })
            prd.save()


    def check_offsale_product(self, id, url):
        pass

    def check_onsale_event(self, id, url):
        pass

    def check_offsale_event(self, id, url):
        pass

if __name__ == '__main__':
    CheckServer().check_onsale_product('','')
