#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: bishop Liu <miracle (at) gmail.com>

import lxml.html
from datetime import datetime
from server import req


class CheckServer(object):
    def __init__(self):
        pass

    def fetch_page(self, url):
        ret = req.get(url)
        if ret.ok: return ret.content
        else: return ret.status

    def check_onsale_product(self, id, url):
        prd = Product.objects(key=id).first()
        if prd is None:
            print '\n\nblooming dales {0}, {1}\n\n'.format(id, url)
            return

        ret = self.fetch_page(url)
        if isinstance(ret, int):
            print("\n\nbloomingdales download product page error: {0}".format(url))
            return

        tree = lxml.html.fromstring(ret)
        price_node = tree.cssselect('div#PriceDisplay div.priceSale')
        price = price_node.cssselect('span.priceSale')[0].text_content().replace(',', '').replace('$', '').strip()
        listprice = price_node.cssselect('span.priceBig')[0].text_content().replace(',', '').replace('$', '').strip()

        if listprice and prd.listprice != listprice:
            prd.listprice = listprice
            prd.update_history.update({ 'listprice': datetime.utcnow() })
        if prd.price != price:
            prd.price = price
            prd.update_history.update({ 'price': datetime.utcnow() })
        prd.save()


    def check_offsale_product(self, id, url):
        pass

    def check_onsale_event(self, id, url):
        pass

    def check_offsale_event(self, id, url):
        pass


if __name__ == '__main__':
    pass

