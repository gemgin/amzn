#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: bishop Liu <miracle (at) gmail.com>

"""
crawlers.modnique.server
~~~~~~~~~~~~~~~~~~~

This is the server part of zeroRPC module. Call by client automatically, run on many differen ec2 instances.
need to investigate whether 'the-shops' in category, not event.
"""
import lxml.html
from datetime import datetime, timedelta

from models import *
from crawlers.common.events import common_saved, common_failed
from crawlers.common.stash import *


class Server(object):
    def __init__(self):
        self.siteurl = 'http://www.modnique.com'
        self.eventurl = 'http://www.modnique.com/all-sale-events'
        self.extract_slug_id = re.compile('.*/saleevent/(.+)/(\w+)/seeac/gseeac')
        self.extract_slug_product = re.compile('.*/product/.+/\w+/(.+)/(\w+)/color/.*size/seeac/gseeac')
        self.headers = {
            'Host':' www.modnique.com',
            # 'Referer':' http://www.modnique.com/',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.4 (KHTML, like Gecko) Ubuntu/12.10 Chromium/22.0.1229.94 Chrome/22.0.1229.94 Safari/537.4',
        }

    def crawl_category(self, ctx='modnique.crawl_category.xxxxx'):
        """.. :py:method::
            categories should be ['apparel', 'jewelry-watches', 'handbags-accessories', 'shoes', 'beauty', 'men']
        """
        content = fetch_page(self.eventurl, self.headers)
        if content is None or isinstance(content, int):
            content = fetch_page(self.eventurl, self.headers)
        tree = lxml.html.fromstring(content)
        self.upcoming_proc(tree, ctx)

        events = tree.cssselect('div.bgDark > div.mbm > div > div.page > ul#nav > li.fCalc:first-of-type')[0]
        dept_link = {} # get department, link
        for e in events.cssselect('ul.subnav > li.eventsMenuWidth > ul.pbm > li.unit > a.pvn'):
            link = e.get('href')
            dept_link[ link.rsplit('/', 1)[-1] ] = link
        
        # get all events under all the departments
        for e in events.cssselect('ul.subnav > li.eventsMenuWidth > ul.pbm > li.unit > div[title]'):
            sale_title = e.get('title')
            link = e.cssselect('a')[0].get('href')
            slug, event_id = self.extract_slug_id.match(link).groups()
            link = link if link.startswith('http') else self.siteurl + link
            dept = e.xpath('./preceding-sibling::a[contains(@class, "pvn")]/@href')[0].rsplit('/', 1)[-1]

            event, is_new, is_updated = self.get_event_from_db(event_id, link, slug, sale_title)
            if dept not in event.dept: event.dept.append(dept)
            event.save()
            common_saved.send(sender=ctx, obj_type='Event', key=event_id, url=link, is_new=is_new, is_updated=is_updated)

        # get 'the-shops' category
        link = tree.cssselect('div.bgDark > div.mbm > div > div.page > ul#nav > li.fCalc:nth-of-type(2) > a.phl')[0].get('href')
        dept_link[ link.rsplit('/', 1)[-1] ] = link

        # http://www.modnique.com/saleevent/Daily-Deal/2000/seeac/gseeac
        sale = tree.cssselect('div.bgDark > div.mbm > div > div.page > ul#nav > li.fCalc:nth-of-type(3) > a.phl')[0].get('href')

        for dept, link in dept_link.iteritems():
            self.crawl_dept(dept, link, ctx)

    def crawl_dept(self, dept, url, ctx):
        """.. :py:method::
            dept can't not add to event here, because all the dept page have all the events.
            Other depts' event is not displayed through js

        :param str dept: department
        :param str url: department url
        """
        content = fetch_page(url, self.headers)
        if content is None or isinstance(content, int):
            content = fetch_page(url, self.headers)
        tree = lxml.html.fromstring(content)
        if dept == 'the-shops':
            nodes = tree.cssselect('div.bgShops > div#content > div#sales > div.pbm > div.page > ul.bannerfix > li > div.shop_thumb > div.media')
        else:
            nodes = tree.cssselect('div.bgDark > div#content > div.sales > div.pbm > div.page > ul.bannerfix > li#saleEventContainer > div.sale_thumb > div.media')
        _utcnow = datetime.utcnow()
        for node in nodes:
            link = node.cssselect('a.sImage')[0].get('href')
            slug, event_id = self.extract_slug_id.match(link).groups()
            link = link if link.startswith('http') else self.siteurl + link
            img = node.cssselect('a.sImage > img')[0].get('data-original')
            if img is None: img = node.cssselect('a.sImage > img')[0].get('src')
            if dept == 'the-shops': image_urls = [img]
            else: image_urls = [img.replace('B.jpg', 'A.jpg'), img]
            sale_title = node.cssselect('div.sDefault > div > a > span')[0].text_content().strip()

            if dept == 'the-shops':
                events_end = None
            else:
                day, hour, minute = node.cssselect('div.sRollover > div > a > span.title_time_banner')[0].text_content().split('Ends')[-1].strip().split()
                ends = timedelta(days=int(day[:-1]), hours=int(hour[:-1]), minutes=int(minute[:-1])) + _utcnow
                hour = ends.hour + 1 if ends.minute > 50 else ends.hour
                events_end = datetime(ends.year, ends.month, ends.day, hour)

            event, is_new, is_updated = self.get_event_from_db(event_id, link, slug, sale_title)
            if dept == 'the-shops' and dept not in event.dept: event.dept.append(dept)
            [event.image_urls.append(img) for img in image_urls if img not in event.image_urls]
            if events_end: event.events_end = events_end
            event.save()
            common_saved.send(sender=ctx, obj_type='Event', key=event_id, url=link, is_new=is_new, is_updated=is_updated)

    def upcoming_proc(self, tree, ctx):
        """.. :py:method::
        """
        _utcnow = datetime.utcnow()
        nodes = tree.cssselect('div#content > div#upcoming_sales li#upcoming_sales_container > div.sale_thumb > div.media')
        for node in nodes:
            link = node.cssselect('div.sRollover > div.mbs > a')[0].get('href')
            slug, event_id = self.extract_slug_id.match(link).groups()
            link = link if link.startswith('http') else self.siteurl + link
            img = node.cssselect('a.sImage > img')[0].get('data-original')
            if img is None:
                img = node.cssselect('a.sImage > img')[0].get('src')
            image_urls = [img.replace('M.jpg', 'A.jpg'), img.replace('M.jpg', 'B.jpg')]
            sale_title = node.cssselect('a.sImage')[0].get('title')

            day, hour, minute = node.cssselect('div#sDefault_{0} > div'.format(event_id))[0].text_content().split('in')[-1].strip().split()
            begins = timedelta(days=int(day[:-1]), hours=int(hour[:-1]), minutes=int(minute[:-1])) + _utcnow
            hour = begins.hour + 1 if begins.minute > 50 else begins.hour
            events_begin = datetime(begins.year, begins.month, begins.day, hour)

            event, is_new, is_updated = self.get_event_from_db(event_id, link, slug, sale_title)
            [event.image_urls.append(img) for img in image_urls if img not in event.image_urls]
            event.events_begin = events_begin
            event.save()
            common_saved.send(sender=ctx, obj_type='Event', key=event_id, url=link, is_new=is_new, is_updated=is_updated)


    def get_event_from_db(self, event_id, link, slug, sale_title):
        """.. :py:method::
            get a event object from database
        :param str event_id:
        :param str link: event link
        :param str slug: slug in link
        :param str sale_title: event sale title
        :rtype: list of `event, is_new, is_updated`
        """
        is_new, is_updated = False, False
        event = Event.objects(event_id=event_id).first()
        if not event:
            is_new = True
            event = Event(event_id=event_id)
            event.urgent = True
            event.combine_url = link
            event.slug = slug
            event.sale_title = sale_title
        event.update_time = datetime.utcnow()
        return event, is_new, is_updated


    def crawl_listing(self, url, ctx='modnique.crawl_listing.xxxxx'):
        """.. :py:method::
        """
        slug, event_id = self.extract_slug_id.match(url).groups()
        content = fetch_page(url, self.headers)
        if content is None or isinstance(content, int):
            content = fetch_page(url, self.headers)
            if content is None or isinstance(content, int):
                common_failed.send(sender=ctx, key=event_id, url=url,
                    reason='download listing url error, {0}'.format(content))
                return
        tree = lxml.html.fromstring(content)
        nodes = tree.cssselect('div.line > div.page > div#items > ul#products > li.product')
        for node in nodes:
            abandon, color = node.get('id').rsplit('_', 1) # item_57185525_gunmetal
            color = '' if color.isdigit() else color
            title = node.cssselect('div.item_thumb2 > div.itemTitle > h6.neutral')[0].text_content().strip()
            link = node.cssselect('div.item_thumb2 > div#itemThumb > a[href]')[0].get('href')
            link = link if link.startswith('http') else self.siteurl + link
            slug, key = self.extract_slug_product.match(link).groups()

            price = node.cssselect('div.item_thumb2 > div > div.media > div.bd > p > span.price')[0].text_content().replace('modnique', '').strip()
            listprice = node.cssselect('div.item_thumb2 > div > div.media > div.bd > p > span.bare')
            listprice = listprice[0].text_content().replace('retail', '').strip() if listprice else ''
            soldout = True if node.cssselect('div.item_thumb2 > div.soldSticker') else False

            is_new, is_updated = False, False
            product = Product.objects(key=key).first()
            if not product:
                is_new = True
                product = Product(key=key)
                product.updated = False
                product.combine_url = link
                product.color = color
                product.title = title
                product.slug = slug
                product.listprice = listprice
                product.price = price
                product.soldout = soldout
            else:
                if soldout and product.soldout != True:
                    product.soldout = True
                    is_updated = True
            if event_id not in product.event_id: product.event_id.append(event_id)
            product.list_update_time = datetime.utcnow()
            product.save()
            common_saved.send(sender=ctx, obj_type='Product', key=key, url=link, is_new=is_new, is_updated=is_updated)

        event = Event.objects(event_id=event_id).first()
        if not event: event = Event(event_id=event_id)
        if event.urgent == True:
            event.urgent = False
            event.update_time = datetime.utcnow()
            event.save()
            common_saved.send(sender=ctx, obj_type='Event', key=event_id, is_new=False, is_updated=False, ready=True)


    def crawl_product(self, url, ctx=''):
        """.. :py:method::
        """
        slug, key = self.extract_slug_product.match(url).groups()
        content = fetch_page(url, self.headers)
        if content is None or isinstance(content, int):
            common_failed.send(sender=ctx, key=key, url=url,
                    reason='download product url error, {0}'.format(content))
            return
        tree = lxml.html.fromstring(content)
        nav = tree.cssselect('div > div.ptl > div.page > div.line')[0] # bgDark or bgShops
        images = nav.cssselect('div > div#product_gallery > div.line > div#product_imagelist > a')
        image_urls = []
        for img in images:
            image_urls.append( img.get('href') )
        shipping = nav.cssselect('div.lastUnit > div.line form div#item_content_wrapper > div#item_wrapper > div#product_delivery')[0].text_content()
        info = nav.cssselect('div.lastUnit > div.line div#showcase > div.container')[0]
        list_info = []
        nodes = info.cssselect('div.tab_container > div#tab1 p')
        for node in nodes:
            list_info.append( node.text_content().strip() )
        brand = info.cssselect('div#tab4')[0].text_content()
        returned = info.cssselect('div#tab5')[0].text_content()

        is_new, is_updated = False, False
        product = Product.objects(key=key).first()
        if not product:
            is_new = True
            product = Product(key=key)
        [product.image_urls.append(img) for img in image_urls if img not in product.image_urls]
        product.shipping = shipping
        product.list_info = list_info
        product.brand = brand
        product.returned = returned
        product.full_update_time = datetime.utcnow()
        if product.updated == False:
            product.updated = True
            ready = True
        else: ready = False
        product.save()
        common_saved.send(sender=ctx, obj_type='Product', key=key, url=url, is_new=is_new, is_updated=is_updated, ready=ready)


if __name__ == '__main__':
    import zerorpc
    from settings import CRAWLER_PORT
    server = zerorpc.Server(Server(), heartbeat=None)
    server.bind('tcp://0.0.0.0:{0}'.format(CRAWLER_PORT))
    server.run()
