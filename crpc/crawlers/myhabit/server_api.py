#!/usr/bin/env python
# -*- coding: utf-8 -*-
""" Myhabit's crawling using API """
from gevent import monkey; monkey.patch_all()
import gevent.pool

import requests
import json
import re
from pprint import pprint
from datetime import datetime, timedelta

from models import Product, Event
from crawlers.common.events import common_saved

def time2utc(t):
    """ convert myhabit time format (json) to utc """
    return datetime.utcfromtimestamp(t['time']//1000)
   

class Server(object):
    def __init__(self):
        self.rooturl = 'http://www.myhabit.com/request/getAllPrivateSales'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_2) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11',
            'Cookie': 'session-id=178-9157968-0478701; session-id-time=19807407421; session-token="f+qT7qj0v+IRz8TvLgLWRc3HRcHcVop9FOmKAt3sgEsUe3lJYBuJIGNobc0VJ0i6vpx1yDcadTg3NHVIzIRJBg7jbM1bOtMEx/y0sBGApDYzmsULdEyGAGT67NZkm9DX8XlrJnPlhQ/Fagv8mq+PD74d1kBfubeOzN/XDCWzeUkobmdlBDSH4WSoeC07sd3iJbZF7i61SjG9k3DxC29q0+tGNgXskOAYFBDvI+jBcFQ="; ct-main="gx?vzAAVNmUyzY55jaGNtIIb?wiE@M1P"; ubid-main=188-4772784-7788317',
            'x-amzn-auth': '178-9157968-0478701',
        }

    def crawl_category(self, ctx=''):
        r = requests.get(self.rooturl, headers=self.headers)
        data = json.loads(r.text)

        for event_data in data['sales']:
            self._parse_event(event_data, ctx)

    def _parse_event(self, event_data, ctx):
        """.. :py:method::
            get product detail page by {asin: {url: url_str}},
            update soldout info by {casin: {soldout: 1/0, }}, can update them when crawl_listing
        """
        event_id = event_data['id']
        info = event_data['saleProps']

        is_new, is_updated = False, False
        event = Event.objects(event_id=event_id).first()
        if not event:
            is_new = True
            event = Event(event_id=event_id)
            event.urgent = True
            event.combine_url = 'http://www.myhabit.com/homepage#page=b&sale={0}'.format(event_id)
            event.sale_title = info['primary']['title']
            event.sale_description = info['primary']['desc']
            event.image_urls = [ info['prefix']+val for key, val in info['primary']['imgs'].items() if key == 'hero']
            event.image_urls.extend( [ info['prefix']+val for key, val in info['primary']['imgs'].items() if key in ['desc', 'sale']] )
            if 'brandUrl' in info['primary']:
                event.brand_link = info['primary']['brandUrl']

            event.listing_url = event_data['prefix'] + event_data['url']
        # updating fields
        event.events_begin = time2utc(event_data['start'])
        event.events_end = time2utc(event_data['end'])
        [event.dept.append(dept) for dept in event_data['departments'] if dept not in event.dept]
        event.soldout = True if 'soldOut' in event_data and event_data['soldOut'] == 1 else False
        event.update_time = datetime.utcnow()

        event.asin_detail_page = event_data['asins']
        event.casin_soldout_info = event_data['cAsins']
        event.save()
        common_saved.send(sender=ctx, obj_type='Event', key=event.event_id, url=event.combine_url, is_new=is_new, is_updated=is_updated)


    def crawl_listing(self, url, ctx=''):
        prefix_url = url.rsplit('/', 1)[0] + '/'
        r = requests.get(url, headers=self.headers)
        event_id, data = re.compile(r'parse_sale_(\w+)\((.*)\);$').search(r.text).groups()
        data = json.loads(data)

        event = Event.objects(event_id=event_id).first()
        if not event: event = Event(event_id=event_id)

        for product_data in data['asins']:
            self._parse_product(event_id, event.asin_detail_page, casin_soldout_info, prefix_url, product_data, ctx):

        if event.urgent == True:
            event.urgent = False
            event.update_time = datetime.utcnow()
            event.save()
            common_saved.send(sender=ctx, obj_type='Event', key=event_id, is_new=False, is_updated=False, ready=True)


    def _parse_product(self, event_id, asins, cAsins, prefix_url, product_data, ctx):
        """ no video info, list_info, summary

        :param event_id: this product belongs to the event's id
        :param asins: all asins info in this event
        :param cAsins: all casins info in this event
        :param prefix_url: image and js prefix_url, probably 'http://z-ecx.images-amazon.com/images/I/'
        :param product_data: product data in this product
        """
        asin = product_data['asin']
        casin = product_data['cAsin']
        title = product_data['title'] # color is in title
        image_urls = [product_data['image']] + product_data['altImages'] # one picture, altImages is []
        listprice = product_data['listPrice']['display'] # or 'amount', if isRange: True, don't know what 'amount' will be
        price = product_data['ourPrice']['display']
        sizes = []
        if product_data['teenagers']: # no size it is {}
            for k, v in product_data['teenagers']:
                if v['size'] not in sizes: sizes.append(v['size'])
        tag = product_data['productGL'] # 'apparel', 'home', 'jewelry'
        soldout = True if casin in cAsins and cAsins[casin]['soldOut'] == 1 else False
        jslink = prefix_url + asins[asin]['url'] if asin in asins else ''

        is_new, is_updated = False, False
        product = Product.objects(key=casin).first()
        if not product:
            is_new = True
            product = Product(key=casin)
            product.asin = asin
            product.title = title
            product.image_urls = image_urls
            product.listprice = listprice
            product.price = price
            product.sizes = sizes
            product.soldout = soldout
            product.updated = False
        else:
            if soldout and product.soldout != soldout:
                product.soldout = True
                is_updated = True
        if tag not in product.tagline: product.tagline.append(tag)
        if event_id not product.event_id: product.event_id.append(event_id)
        product.jslink = jslink
        product.list_update_time = datetime.utcnow()
        product.save()
        common_saved.send(sender=ctx, obj_type='Product', key=casin, is_new=is_new, is_updated=is_updated)


    def crawl_product(self, url, casin, ctx=''):
        r = requests.get(url, headers=self.headers)
        data = re.compile(r'parse_asin_\w+\((.*)\);$').search(r.text).group(1)
        data = json.loads(data)

        asin = d['detailJSON']['asin']
        summary = data['productDescription']['shortProdDesc']
        list_info = data['productDescription']['bullets'][0]['bulletsList']
        brand = data['detailJSON']['brand']
        international_shipping = str(data['detailJSON']['intlShippable']) # 1
        returned = data['detailJSON']['returnPolicy']

        video = ''
        for p in data['detailJSON']['asins']:
            if p['asin'] == casin:
                video = p['videos'][0]['url']
                break

        is_new, is_updated = False, False
        product = Product.objects(key=casin).first()
        if not product:
            is_new = True
            product = Product(key=casin)
        product.summary = summary
        product.list_info = list_info
        product.brand = brand
        product.international_shipping = international_shipping
        product.returned = returned
        product.video = video
        product.full_update_time = datetime.utcnow()

        if product.updated == False:
            product.updated = True
            ready = True
        else: ready = False
        product.save()
        common_saved.send(sender=ctx, obj_type='Product', key=casin, url=url, is_new=is_new, is_updated=is_updated, ready=ready)


if __name__ == '__main__':
    server = zerorpc.Server(Server())
    server.bind('tcp://0.0.0.0:{0}'.format(CRAWLER_PORT))
    server.run()