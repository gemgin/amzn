#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: bishop Liu <miracle (at) gmail.com>

import lxml.html
import json
from datetime import datetime, timedelta

from crawlers.common.events import common_saved, common_failed
from crawlers.common.stash import *
from models import *


class lot18Login(object):
    """.. :py:class:: lot18Login
        login, check whether login, fetch page.
    """
    def __init__(self):
        """.. :py:method::
            variables need to be used
        """
        self.login_url = 'http://www.lot18.com/login'
        self.data = {
            'email': login_email,
            'password': login_passwd,
        }

        self._signin = False

    def login_account(self):
        """.. :py:method::
            use post method to login
        """
        request.get(self.login_url)
        request.post(self.login_url, self.data)
        self._signin = True

    def check_signin(self):
        """.. :py:method::
            check whether the account is login
        """
        if not self._signin:
            self.login_account()

    def fetch_page(self, url):
        """.. :py:method::
            fetch page.
            check whether the account is login, if not, login and fetch again
        """
        ret = request.get(url)

        if 'http://www.lot18.com/login' in ret.url:
            self.login_account()
            ret = request.get(url)
        if ret.ok: return ret.content

        return ret.status_code

    def post_to_get(self, url, data):
        ret = request.post(url, data=data)
        return ret.content


class Server(object):
    def __init__(self):
        self.net = lot18Login()
        self.post_url = 'http://www.lot18.com/collection.json'

    def crawl_category(self, ctx=''):
        is_new, is_updated = False, False
        category = Category.objects(sale_title='lot18').first()
        if not category:
            is_new = True
            category = Category(sale_title='lot18')
            category.is_leaf = True
            category.cats = ['wine']
        category.update_time = datetime.utcnow()
        category.save()
        common_saved.send(sender=ctx, obj_type='Category', key='', url='', is_new=is_new, is_updated=is_updated)

    def crawl_listing(self, url, ctx=''):
        """.. :py:method::
            url is useless in here
        :param str url: None
        """
        self.net.check_signin()
        data = { 'attributes': '', 'page': 1, 'price_per_bottle': '' }
        ret = self.net.post_to_get(self.post_url, data)
        d = json.loads(ret)['data']
        for prd in d['products']:
            self.build_listing_product(prd, ctx)
        for i in xrange( 2, int(d['page_count'])+1 ):
            data['page'] = i
            ret = self.net.post_to_get(self.post_url, data)
            d = json.loads(ret)['data']
            for prd in d['products']:
                self.build_listing_product(prd, ctx)

    def build_listing_product(self, prd, ctx):
        """.. :py:method::
            save the field to database
        """
        is_new, is_updated = False, False
        product = Product.objects(key=prd['id']).first()
        if not product:
            is_new = True
            product = Product(key=prd['id'])
            product.combine_url = 'http://www.lot18.com/product/{0}'.format(prd['id'])
            product.updated = False
            product.title = prd['title']
            product.image_urls = ['http:' + prd['images']['large'], 'http:' + prd['images']['xlarge']]
            if prd['bottle_count'] == 0:
                product.listprice = prd['prices']['msrp']
            else:
                product.bottle_count = prd['bottle_count']
                product.listprice = str( float(prd['prices']['msrp']) * prd['bottle_count'] )
            product.price = prd['prices']['price']
            product.short_desc = prd['headline']
            product.soldout = prd['is_soldout']
        else:
            if prd['is_soldout'] and product.soldout != True:
                product.soldout = True
                is_updated = True

        if prd['type'] not in product.dept: product.dept.append(prd['type'])
        _utcnow = datetime.utcnow()
        # False, in [1-9] days/day/hours
        if prd['expires']:
            drop, num, period = prd['expires'].split()
            if 'day' in period:
                products_end = _utcnow + timedelta(days=int(num))
            elif 'hour' in period:
                products_end = _utcnow + timedelta(hours=int(num))
            elif 'minute' in period:
                products_end = _utcnow + timedelta(minutes=int(num))
            else:
                pass
            if products_end.minute > 55:
                products_end = products_end.replace(hour=products_end.hour + 1, minute=0)
            else:
                products_end = products_end.replace(minute=0)
            product.products_end = products_end.replace(second=0, microsecond=0)
        product.list_update_time = _utcnow
        product.save()
        common_saved.send(sender=ctx, obj_type='Product', key=prd['id'], url=product.combine_url, is_new=is_new, is_updated=is_updated)


    def crawl_product(self, url, ctx=''):
        """.. :py:method::
        """
        pass
