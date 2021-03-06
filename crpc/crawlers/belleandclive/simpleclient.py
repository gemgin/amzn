#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: bishop Liu <miracle (at) gmail.com>

import slumber
import lxml.html
from datetime import datetime, timedelta

from server import belleandcliveLogin
from models import Product, Event
from settings import MASTIFF_HOST

api = slumber.API(MASTIFF_HOST)

class CheckServer(object):
    def __init__(self):
        self.net = belleandcliveLogin()
        self.net.check_signin()

    def offsale_update(self, muri):
        _id = muri.rsplit('/', 2)[-2]
        utcnow = datetime.utcnow()
        var = api.product(_id).get()
        if 'ends_at' in var and var['ends_at'] > utcnow.isoformat():
            api.product(_id).patch({ 'ends_at': utcnow.isoformat() })
        if 'ends_at' not in var:
            api.product(_id).patch({ 'ends_at': utcnow.isoformat() })

    def check_onsale_product(self, id, url):
        prd = Product.objects(key=id).first()
        if prd is None:
            print '\n\nbelleandclive {0}, {1}\n\n'.format(id, url)
            return

        cont = self.net.fetch_product_page(url)
        if cont == -302:
            if prd.muri:
                self.offsale_update(prd.muri)
            if not prd.products_end or prd.products_end > datetime.utcnow():
                prd.products_end = datetime.utcnow()
                prd.update_history.update({ 'products_end': datetime.utcnow() })
                prd.save()
                print '\n\nbelleandclive product[{0}] redirect, sale end.'.format(url)
            return

        elif cont is None or isinstance(cont, int):
            cont = self.net.fetch_product_page(url)
            if cont is None or isinstance(cont, int):
                print '\n\nbelleandclive product[{0}] download error.\n\n'.format(url)
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
            print 'belleandclive product[{0}] title error: [{1} vs {2}]'.format(url, prd.title.encode('utf-8'), title)
        if listprice and prd.listprice.replace('$', '').replace(',', '').strip() != listprice:
            print 'belleandclive product[{0}] listprice error: [{1} vs {2}]'.format(url, prd.listprice.replace('$', '').replace(',', '').strip(), listprice)
            prd.listprice = listprice
            prd.update_history.update({ 'listprice': datetime.utcnow() })
            prd.save()

        if prd.price.replace('$', '').replace(',', '').strip() != price:
            print 'belleandclive product[{0}] price error: [{1} vs {2}]'.format(url, prd.price.replace('$', '').replace(',', '').strip(), price)
            prd.price = price
            prd.update_history.update({ 'price': datetime.utcnow() })
            prd.save()

        if prd.soldout != soldout:
            print 'belleandclive product[{0}] soldout error: [{1} vs {2}]'.format(url, prd.soldout, soldout)
            prd.soldout = soldout
            prd.update_history.update({ 'soldout': datetime.utcnow() })
            prd.save()


    def check_offsale_product(self, id, url):
        prd = Product.objects(key=id).first()
        if prd is None:
            print '\n\nbelleandclive {0}, {1}\n\n'.format(id, url)
            return

        cont = self.net.fetch_product_page(url)
        if cont == -302:
            return
        elif cont is None or isinstance(cont, int):
            cont = self.net.fetch_product_page(url)
            if cont is None or isinstance(cont, int):
                print '\n\nbelleandclive product[{0}] download error.\n\n'.format(url)
                return
        else:
            tree = lxml.html.fromstring(cont)
            time = tree.cssselect('#sub-header p.countdown')[0].get('data-countdown')[:-3]
            if time:
                products_end = datetime.utcfromtimestamp( float(time) )
            else:
                products_end = datetime.utcnow() + timedelta(days=3)
            if prd.products_end != products_end:
                prd.products_end = products_end
                prd.update_history.update({ 'products_end': datetime.utcnow() })
                prd.on_again = True
                prd.save()
                print '\n\nbelleandclive product[{0}] on sale again.'.format(url)



    def check_onsale_event(self, id, url):
        pass

    def check_offsale_event(self, id, url):
        pass

if __name__ == '__main__':
    check = CheckServer()

    obj = Product.objects(products_end__lt=datetime.utcnow()).timeout(False)
    print 'have {0} off sale event products.'.format(obj.count())
    obj2 = Product.objects(products_end__exists=False).timeout(False)
    print 'have {0} off sale category products.'.format(obj2.count())

    for o in obj:
        check.check_offsale_product( o.key, o.url() )

    for o in obj2:
        check.check_offsale_product( o.key, o.url() )

