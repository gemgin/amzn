#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
crawlers.hautelook.server
~~~~~~~~~~~~~~~~~~~

This is the server part of zeroRPC module. Call by client automatically, run on many differen ec2 instances.

"""
#from crawlers.common.imageprocessor import *
from crawlers.common.events import *
from crawlers.common.stash import *
from models import *
from datetime import datetime, timedelta

import requests
import json
import itertools


header = { 
    'Accept': 'application/json',
    'Accept-Charset': 'UTF-8,*;q=0.5',
    'Accept-Encoding': 'gzip,deflate,sdch',
    'Accept-Language': 'zh-CN,en-US;q=0.8,en;q=0.6',
    'Auth': 'HWS a5a4d56c84b8d8cd0e0a0920edb8994c',
    'Connection': 'keep-alive',
    'Content-encoding': 'gzip,deflate',
    'Content-type': 'application/json',
    'Cookie': 'optimizelyEndUserId=oeu1351564948213r0.9653669202234596; __qca=P0-1416793214-1351564948681; __cmbU=ABJeb1_oimQsnSgmYYnlsRbGiezTpUBCqvvAcIYXER0O_FQtbdIuS6-xxZaNg5SIUXZza2QPCLxmq-8ahyoGiOcjXi6aMX1e8w; PHPSESSID=t5b3ek6en6hbv1aulpjeeg57g6; hlmt=50c1c156d269d; hlma=8b1e440bca4bae1316c7f404d2c0d140; HLMEMBER=1; gaCamp[member_id]=11147317; gaCamp[sid]=100; s_vi=[CS]v1|28479F4A851D3270-4000010160002C9E[CE]; hauteLookMember=%7B%22member_id%22%3A11147317%2C%22first_name%22%3A%22helena%22%2C%22last_name%22%3A%22rak%22%2C%22invitation_code%22%3A%22hrak981%22%2C%22role%22%3A1%2C%22gender%22%3A%22F%22%2C%22email%22%3A%222012luxurygoods@gmail.com%22%2C%22msa%22%3A%22New%20York-Northern%20New%20Jersey-Long%20Island%20NY-NJ-PA%22%2C%22credits%22%3A%220.00%22%2C%22cart_count%22%3A0%2C%22category_order%22%3A%5B%5D%2C%22join_date%22%3A%222012-12-07T00%3A49%3A56-08%3A00%22%2C%22meta%22%3A%7B%22promos%22%3A%5B%5D%7D%2C%22timezone%22%3A%22PST%22%2C%22cart%22%3A0%7D; og=F; cartStamp=nQUemSi; __cmbDomTm=0; __cmbTpvTm=285; __ar_v4=NZUMLDQBFJBCDJO5RYMUQ4%3A20130002%3A5%7C5KKAPNHCHZEFVNM564VIHM%3A20130002%3A5%7C5OCYHSCF4FFDXA7XMFQMH3%3A20130002%3A5; __cmbCk={"eid":"ABJeb1_i2bNio6jHgJqEDvioiLkAsjSb_JNM-vfwWZR_CLFo1uNrMlRcHY7PgbeHo4Zn63OTTjPAmN4JjDU2uzyl71XGHg-EMQ","slt":1354875226149,"cbt":1714,"tp":10653}; optimizelySegments=%7B%7D; optimizelyBuckets=%7B%7D; __utma=116900255.1463618077.1351564949.1354849531.1354875205.38; __utmb=116900255.6.10.1354875205; __utmc=116900255; __utmz=116900255.1351564949.1.1.utmcsr=(direct)|utmccn=(direct)|utmcmd=(none); __utmv=116900255.|5=User%20ID=11147317=1; optimizelyPendingLogEvents=%5B%5D; s_sess=%20s_cc%3Dtrue%3B%20s_sq%3D%3B;',
    'Host': 'www.hautelook.com',
    'Referer': 'http://www.hautelook.com',
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.4 (KHTML, like Gecko) Ubuntu/12.10 Chromium/22.0.1229.94 Chrome/22.0.1229.94 Safari/537.4',
    'X-Requested-With': 'XMLHttpRequest',
}

req = requests.Session(prefetch=True, timeout=30, config=config, headers=header)


class Server(object):
    """.. :py:class:: Server
    
    This is zeroRPC server class for ec2 instance to crawl pages.

    """
    def __init__(self):
        self.siteurl = 'http://www.hautelook.com'
        self.event_url = 'http://www.hautelook.com/v3/events'
        self.login_url = 'https://www.hautelook.com/login'
        self.post_url = 'https://www.hautelook.com/v3/credential'
        self.data = { # If want to login, maybe need more header to masquerading like a browser
            "email": login_email[DB],
            "password": login_passwd,
            "meta": {
                "screen_resolution": {"height":768, "width":1366}
            }
        }

    def convert_time(self, date_str):
        """.. :py:method::
            covert time from the format into utcnow()
            '2012-10-31T08:00:00-07:00'
        """
        date, Time = date_str.split('T')
        time_str = date + '-' + Time.split('-')[0]
        fmt = "%Y-%m-%d-%X"
        hours, minutes = Time.split('-')[1].split(':')
        return datetime.strptime(time_str, fmt) + timedelta(hours=int(hours), minutes=int(minutes))

    def crawl_category(self, ctx='', **kwargs):
        """.. :py:method::
            from self.event_url get all the events
        """
        debug_info.send(sender=DB + '.category.begin')

        resp = req.get(self.event_url)
        try:
            data = json.loads(resp.text)
        except ValueError:
            resp = req.get(self.event_url)
            data = json.loads(resp.text)
        lay1 = data['events']
        lay2_upcoming, lay2_ending_soon, lay2_today = lay1['upcoming'], lay1['ending_soon'], lay1['today']

        for event in itertools.chain(lay2_upcoming, lay2_ending_soon, lay2_today):
            info = event['event']
            event_id = info['event_id']
            event_code = info['event_code']
            sale_title = info['title']
            dept = [i['name'] for i in info['event_types']]
            tagline = []
            if info['tagline']: tagline.append(info['tagline'])
            if info['category']: tagline.append(info['category'])

            # new upcoming, new now, old upcoming, old now
            events_begin = self.convert_time( info['start_date'] )
            events_end = self.convert_time( info['end_date'] )
            _utcnow = datetime.utcnow()
            sale_description = requests.get(info['info']).text.strip().replace('&mdash;', '—'.decode('utf-8')) if events_begin < _utcnow else ''

            is_leaf = True
            # "Daily Deal" only have product on webpage, but whole process in API
            # "Regular" may have children, but its children maybe not displayed on webpage
            # "Nested Parent Child" have official child event
            if info['event_display_format'] == 'Nested Parent Child':
                children = info['meta']['nested']['children']
                if children:
                    for child in children:
                        self.save_child_event(child['event_id'], events_begin, events_end, sale_title, sale_description, dept, tagline, ctx)
                        is_leaf = False

            grid_img = 'http://www.hautelook.com/assets/{0}/grid-large.jpg'.format(event_code)
#            pop_img = 'http://www.hautelook.com/assets/{0}/pop-large.jpg'.format(event_code)
            pop_img = 'http://www.hautelook.com/assets/{0}/event-square.jpg'.format(event_code)
            is_new, is_updated = False, False
            event = Event.objects(event_id=event_id).first()
            if not event:
                is_new = True
                event = Event(event_id=event_id)
                event.sale_title = sale_title
                event.dept = dept
                event.tagline = tagline
                event.urgent = True
                event.combine_url = 'http://www.hautelook.com/event/{0}'.format(event_id)
                event.is_leaf = is_leaf
            if sale_description and not event.sale_description:
                event.sale_description = sale_description
#            if grid_img not in event.image_urls: event.image_urls.append(grid_img)
            if pop_img not in event.image_urls: event.image_urls.append(pop_img)
            if event.events_begin != events_begin:
                event.update_history.update({ 'events_begin': datetime.utcnow() })
                event.events_begin = events_begin
            if event.events_end != events_end:
                event.update_history.update({ 'events_end': datetime.utcnow() })
                event.events_end = events_end
            event.update_time = _utcnow
            event.save()
            common_saved.send(sender=ctx, obj_type='Event', key=event_id,
                    url='{0}/event/{1}'.format(self.siteurl, event_id), is_new=is_new, is_updated=is_updated)
        debug_info.send(sender=DB + '.category.end')


    def save_child_event(self, event_id, events_begin, events_end, sale_title, sale_description, dept, tagline, ctx):
        """
            save a child event
        """
        ret = req.get('http://www.hautelook.com/v3/event/{0}'.format(event_id))
        event_code = json.loads(ret.content)['event']['event_code']
        pop_img = 'http://www.hautelook.com/assets/{0}/event-square.jpg'.format(event_code)
        is_new, is_updated = False, False
        event = Event.objects(event_id=event_id).first()
        if not event:
            is_new = True
            event = Event(event_id=event_id)
            event.sale_title = sale_title
            event.dept = dept
            event.tagline = tagline
            event.urgent = True
            event.combine_url = 'http://www.hautelook.com/event/{0}'.format(event_id)
        if pop_img not in event.image_urls:
            event.image_urls.append(pop_img)
        if sale_description and not event.sale_description:
            event.sale_description = sale_description
        if event.events_begin != events_begin:
            event.update_history.update({ 'events_begin': datetime.utcnow() })
            event.events_begin = events_begin
        if event.events_end != events_end:
            event.update_history.update({ 'events_end': datetime.utcnow() })
            event.events_end = events_end
        event.update_time = datetime.utcnow()
        event.save()
        common_saved.send(sender=ctx, obj_type='Event', key=event_id,
                url='{0}/event/{1}'.format(self.siteurl, event_id), is_new=is_new, is_updated=is_updated)


    def crawl_listing(self, url, ctx='', **kwargs):
        """.. :py:method::
            not useful
        :param url: event url with event_id 
        """
        resp = req.get(url)
        try:
            data = json.loads(resp.text)
        except ValueError:
            resp = req.get(url)
            data = json.loads(resp.text)
        if data.keys()[0] != 'availabilities':
            resp = req.get(url)
            data = json.loads(resp.text)
        if data.keys()[0] != 'availabilities':
            common_failed.send(sender=ctx, key='get availabilities twice, both error', url=url, reason=data)
            return

        product_ids = []
        event_id = re.compile('http://www.hautelook.com/v3/catalog/(.+)/availability').match(url).group(1)
        event = Event.objects(event_id=event_id).first()
        if not event: event = Event(event_id=event_id)
        if not event.image_urls: # child events don't fill up image_urls in crawl_category, until following code block
            resp = req.get('http://www.hautelook.com/v3/event/{0}'.format(event_id))
            jsd = json.loads(resp.content)
            image_url = jsd['event']['image_url'].replace('event-small', 'pop-large')
            event.sale_title = jsd['event']['title']
            event.image_urls = [image_url, jsd['event']['image_url']]
            event.update_time = datetime.utcnow()
            event.save()

        for item in data['availabilities']:
            info = item['availability']
            key = info['inventory_id']
            color = '' if info['color'].lower() == 'no color' else info['color']
            scarcity = reduce(lambda x, y: x+y, (size['size']['remaining'] for size in info['sizes']))
            scarcity = str(scarcity)
            combine_url = 'http://www.hautelook.com/product/{0}'.format(key)

            product, is_new = Product.objects.get_or_create(pk=key)
            is_updated = False
            if is_new:
                if color: product.color = color
                product.event_id = [event_id]
                product.updated = False
                product.scarcity = scarcity
                if scarcity == '0': product.soldout = True
                product.combine_url = combine_url
            else:
                if product.scarcity != scarcity:
                    product.scarcity = scarcity
                    if int(scarcity) < 1:
                        product.soldout = True
                        is_updated = True
                        product.update_history.update({ 'soldout': datetime.utcnow() })
                if product.combine_url != combine_url:
                    product.combine_url = combine_url
                    product.update_history.update({ 'combine_url': datetime.utcnow() })
                if event_id not in product.event_id: product.event_id.append(event_id)
            product.list_update_time = datetime.utcnow()
            product.save()
            common_saved.send(sender=ctx, obj_type='Product', key=key, url=combine_url, is_new=is_new, is_updated=is_updated)
            product_ids.append(key)

        if event.urgent == True:
            event.urgent = False
            ready = True
        else: ready = False
        event.product_ids = product_ids
        event.update_time = datetime.utcnow()
        event.save()
        common_saved.send(sender=ctx, obj_type='Event', key=event_id, url=url, is_new=False, is_updated=False, ready=ready)



    def crawl_product(self, url, ctx='', **kwargs):
        """.. :py:method::
            Got all the product information and save into the database
        :param url: product url, with product id
        """
        resp = req.get(url)
        try:
            data = json.loads(resp.text)['data']
        except ValueError:
            resp = req.get(url)
            try:
                data = json.loads(resp.text)['data']
            except ValueError:
                common_failed.send(sender=ctx, key='get product twice, url has nothing', url=url, reason='url has nothing 404')
                return

#        event_id = [str(data['event_id'])]
        title = data['title']
        list_info, brand = [], ''
        if 'copy' in data and data['copy']:
            list_info = data['copy'].replace('<br />', '').split('\n')

        if data['event_display_brand_name']:
            if data['event_title'] != data['brand_name']:
                brand = data['brand_name']


        product_id = url.rsplit('/', 1)[-1]
        color, price, listprice = '', '', ''
        # same product with different colors, all in the same product id
        price_flage = True
        for color_str,v in data['prices'].iteritems():
            if not price_flage: break
            if isinstance(v, list):
                for val in v:
                    if product_id == str(val['inventory_id']):
                        price = str(val['sale_price'])
                        listprice = str(val['retail_price'])
                        price_flage = False
                        color = color_str
                        break
                else:
                    price = str(val['sale_price'])
                    listprice = str(val['retail_price'])
            elif isinstance(v, dict):
                for size, val in v.iteritems():
                    if product_id == str(val['inventory_id']):
                        price = str(val['sale_price'])
                        listprice = str(val['retail_price'])
                        price_flage = False
                        color = color_str
                        break
                else:
                    price = str(val['sale_price'])
                    listprice = str(val['retail_price'])

        is_new, is_updated = False, False
        product = Product.objects(key=url.split('/')[-1]).first()
        if not product:
            is_new = True
            product = Product(key=url.split('/')[-1])
        if data['add_info']: product.additional_info = data['add_info'].split('\n')
        if data['care']: product.care_info = data['care']
        if data['fiber']: product.fiber = data['fiber']

        product.sizes = [sz['name'] for sz in data['collections']['size']] # OS -- no size info
        product.arrives = data['arrives']
        product.title = title
        product.list_info = list_info
        product.brand = brand
        product.returned = 'Returnable for refund or HauteLook credit.' if data['returnable'] else 'Final sale - This item is not returnable.' # bool
        # product.shipping = str(int(data['international'])) bool, international always 0
        product.delivery_date = ' to '.join((data['estimated_delivery']['start_date'], data['estimated_delivery']['end_date']))
        product.choke_hazard = str(int(data['choke_hazard'])) # bool
        product.price = price
        product.listprice = listprice

        image_urls = []
        if color:
            # color: find the color, associate it to get the right images
            for color_info in data['collections']['color']:
                if color_info['name'] == color:
                    image_urls = data['collections']['images'][ color_info['image'] ]['large']
        elif product.color:
            for color_info in data['collections']['color']:
                if color_info['name'] == product.color:
                    image_urls = data['collections']['images'][ color_info['image'] ]['large']
        else:
            # if product_id not in color, don't crawl it later, set a default price, listprice.
            # image_urls may not get
            pass

        for img in image_urls: # http://www1.hautelookcdn.com/images/app/modules/default/product/noavail_large.gif
            if img.endswith('noavail_large.gif'):
                image_urls = []
                break
        product.image_urls = image_urls

        if product.updated == False:
            product.updated = True
            ready = True
        else: ready = False
        product.full_update_time = datetime.utcnow()
        product.save()
#        if ready:
#            product.image_path = process_image(product.image_urls, DB, 'product', url.split('/')[-1])
#            product.save()
        common_saved.send(sender=ctx, obj_type='Product', key=url.split('/')[-1], url=url, is_new=is_new, is_updated=is_updated, ready=ready)


if __name__ == '__main__':
    server = zerorpc.Server(Server())
    server.bind("tcp://0.0.0.0:{0}".format(CRAWLER_PORT))
    server.run()
