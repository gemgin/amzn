#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: bishop Liu <miracle (at) gmail.com>
"""
crawlers.beyondtherack.server
~~~~~~~~~~~~~~~~~~~

This is the server part of zeroRPC module. Call by client automatically, run on many differen ec2 instances.

"""

import re
import json
import pytz
import lxml.html
from datetime import datetime, timedelta

from models import *
from crawlers.common.stash import *
from crawlers.common.events import common_saved, common_failed

header = {
    'Host': 'www.beyondtherack.com',
    'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:16.0) Gecko/20100101 Firefox/16.0',
}

req = requests.Session(prefetch=True, timeout=30, config=config, headers=header)

class beyondtherackLogin(object):
    """.. :py:class:: beyondtherackLogin
        login, check whether login, fetch page.
    """
    def __init__(self):
        """.. :py:method::
            variables need to be used
        """
        self.login_url = 'https://www.beyondtherack.com/auth/login'
        self.data = {
            'email': login_email[DB],
            'passwd': login_passwd,
            'keepalive': 1,
            '_submit': 1,
        }

        self.current_email = login_email[DB]
        self._signin = {}

    def login_account(self):
        """.. :py:method::
            use post method to login
        """
        self.data['email'] = self.current_email
        req.post(self.login_url, data=self.data)
        self._signin[self.current_email] = True


    def check_signin(self, username=''):
        """.. :py:method::
            check whether the account is login
        """
        if username == '': 
            self.login_account()
        elif username not in self._signin:
            self.current_email = username
            self.login_account()
        else:
            self.current_email = username

    def fetch_page(self, url):
        """.. :py:method::
            fetch page.
            check whether the account is login, if not, login and fetch again
        """
        ret = req.get(url)

        if 'https://www.beyondtherack.com/auth/' in ret.url: #login or register
            self.login_account()
            ret = req.get(url)
        if ret.ok: return ret.content

        return ret.status_code

    def fetch_listing_page(self, url):
        """.. :py:method::
        """
        ret = req.get(url)

        if 'https://www.beyondtherack.com/auth/' in ret.url: #login or register
            self.login_account()
            ret = req.get(url)
        if ret.ok and 'sku' in ret.url:
            return [ret.url, ret.content] 
        elif ret.ok and 'http://www.beyondtherack.com/event/calendar' in ret.url: # redirect to homepage
            return -302
        elif ret.ok:
            return ret.content

        return ret.status_code

    def fetch_product_page(self, url):
        """.. :py:method::
        """
        ret = req.get(url)

        if 'https://www.beyondtherack.com/auth/' in ret.url: #login or register
            self.login_account()
            ret = req.get(url)
        if ret.ok and ret.url == 'http://www.beyondtherack.com/event/calendar':
            return -302
        elif ret.ok:
            return ret.content

        return ret.status_code

class Server(object):
    """.. :py:class:: Server

        This is zeroRPC server class for ec2 instance to crawl pages.

    """
    def __init__(self):
        self.siteurl = 'http://www.beyondtherack.com'
        self.all_event_url = 'http://www.beyondtherack.com/event/calendar'
        self.net = beyondtherackLogin()
        self.et = pytz.timezone('US/Eastern')
        self.dept_link = {
            'women':        'http://www.beyondtherack.com/event/calendar?category=1',
            'men':          'http://www.beyondtherack.com/event/calendar?category=2',
            'kids':         'http://www.beyondtherack.com/event/calendar?category=3',
            'home':         'http://www.beyondtherack.com/event/calendar?category=4',
            'curvy_closet': 'http://www.beyondtherack.com/event/calendar?category=10',
        }

        self.extract_event_id = re.compile('.*/event/showcase/(\d+)\??.*')
        self.extract_image_url = re.compile('background-image: url\(\'(.*)\'\);')


    def crawl_category(self, ctx='', **kwargs):
        if kwargs.get('login_email'): self.net.check_signin( kwargs.get('login_email') )
        else: self.net.check_signin()

        self.crawl_category_text_info(self.all_event_url, ctx)

        for dept, url in self.dept_link.iteritems():
            self.crawl_one_dept_image(dept, url, ctx)

    def get_or_create_event(self, event_id):
        is_new, is_updated = False, False
        event = Event.objects(event_id=event_id).first()
        if not event:
            is_new = True
            event = Event(event_id=event_id)
            event.urgent = True
            event.combine_url = 'http://www.beyondtherack.com/event/showcase/{0}'.format(event_id)
        return event, is_new, is_updated

    def crawl_category_text_info(self, url, ctx):
        """.. :py:method::
            Get all the events' text info from main url

        :param url: the main url of this site
        """
        content = self.net.fetch_page(url)
        if content is None or isinstance(content, int):
            common_failed.send(sender=ctx, key='', url=url,
                    reason='download error or {1} return'.format(content))
            return
        tree = lxml.html.fromstring(content)
        upcoming_data = json.loads( re.compile('var event_data *= *({.*});').search(content).group(1) )

        upcomings = tree.cssselect('div.pageframe table.upcomingEvents > tbody > tr > td.data-row > div.item')
        for up in upcomings:
            event_id = up.get('data-event')
            sale_title = up.text_content().strip()
#            uptime = up.xpath('./following-sibling::span[@class="time"]/text()')[0] #'Fri. Dec 14'
#            events_begin = time_convert(uptime+' 9 ', '%a. %b %d %H %Y', 'ET')
#            _utcnow = datetime.now(pytz.utc)
#            if events_begin.day == _utcnow.day and events_begin < _utcnow:
#                if '5PM' in sale_title or '5pm' in sale_title:
#                    events_begin += timedelta(hours=8)
#                else:
#                    events_begin += timedelta(hours=1)

            events_begin = self.et.localize( datetime.strptime(upcoming_data[event_id]['start_time'], '%Y-%m-%d %X') ).astimezone(pytz.utc)
            events_end = self.et.localize( datetime.strptime(upcoming_data[event_id]['end_time'], '%Y-%m-%d %X') ).astimezone(pytz.utc)
            events_begin = datetime(events_begin.year, events_begin.month, events_begin.day, events_begin.hour, events_begin.minute)
            events_end = datetime(events_end.year, events_end.month, events_end.day, events_end.hour, events_end.minute)
            image_urls = upcoming_data[event_id]['images'].values()
            event, is_new, is_updated = self.get_or_create_event(event_id)
            if not event.sale_title: event.sale_title = sale_title
            if event.events_begin != events_begin:
                event.update_history.update({ 'events_begin': datetime.utcnow() })
                event.events_begin = events_begin
            if event.events_end != events_end:
                event.update_history.update({ 'events_end': datetime.utcnow() })
                event.events_end = events_end
            if image_urls != event.image_urls:
                event.image_urls = image_urls
                event.update_history.update({ 'image_urls': datetime.utcnow() })
            event.update_time = datetime.utcnow()
            event.save()
            common_saved.send(sender=ctx, obj_type='Event', key=event_id, url=event.combine_url, is_new=is_new, is_updated=is_updated)

#        for dept in self.dept_link.keys():
#            self.crawl_one_dept_text_info(dept, tree, ctx)
#
#
#    def crawl_one_dept_text_info(self, dept, tree, ctx):
#        """.. :py:method::
#
#            event ending soon. This section is not exist in the beyondtherack anymore
#        :param dept: dept of this site
#        :param tree: the xpath tree of main page
#        """
#        items = tree.cssselect('div.headerframe ul#nav > li.menu_item_{0} > div.submenu > table td > div.submenu-section > a'.format(dept))
#        for item in items:
#            link = item.get('href')
#            event_id = self.extract_event_id.match(link).group(1)
#            ending_soon = item.cssselect('div.menu-item-ending-soon')
#            if ending_soon:
#                sale_title = ending_soon[0].cssselect('div.link')[0].text_content()
#            else:
#                sale_title = item.cssselect('div.menu-item')[0].text_content()
#
#            event, is_new, is_updated = self.get_or_create_event(event_id)
#
#            event.sale_title = sale_title
#            event.update_time = datetime.utcnow()
#            event.save()
#            common_saved.send(sender=ctx, obj_type='Event', key=event_id, url=event.combine_url, is_new=is_new, is_updated=is_updated)


    def crawl_one_dept_image(self, dept, url, ctx):
        content = self.net.fetch_page(url)
        if content is None or isinstance(content, int):
            common_failed.send(sender=ctx, key=dept, url=url,
                    reason='download error \'{0}\' or {1} return'.format(dept, content))
            return
        tree = lxml.html.fromstring(content)
        items = tree.cssselect('div.pageframe > div.mainframe > a[href]')
        for item in items:
            link = item.get('href')
            if 'facebook' in link: continue
            event_id = self.extract_event_id.match(link).group(1)
            image_text = item.get('style')
            image_url = self.extract_image_url.search(image_text).group(1)
        
            event, is_new, is_updated = self.get_or_create_event(event_id)

            if dept not in event.dept: event.dept.append(dept)

            if image_url not in event.image_urls:
                event.image_urls.insert(0, image_url)
                event.update_history.update({ 'image_urls': datetime.utcnow() })

            if 'image_urls' not in event.update_history.keys():
                event.update_history.update({ 'image_urls': datetime.utcnow() })
            elif not event.events_begin:
                event.events_begin = datetime.utcnow()
                event.update_history.update({ 'image_urls': datetime.utcnow() })
            elif event.events_begin + timedelta(minutes=10) < datetime.utcnow() and event.events_begin + timedelta(minutes=1) > event.update_history['image_urls']:
                event.update_history.update({ 'image_urls': datetime.utcnow() })

            event.update_time = datetime.utcnow()
            event.save()
            common_saved.send(sender=ctx, obj_type='Event', key=event_id, url=event.combine_url, is_new=is_new, is_updated=is_updated)


    def crawl_listing(self, url, ctx='', **kwargs):
        if kwargs.get('login_email'): self.net.check_signin( kwargs.get('login_email') )
        else: self.net.check_signin()

        event_id = url.rsplit('/', 1)[-1]
        content = self.net.fetch_listing_page(url)
        if isinstance(content, list):
            self.crawl_event_is_product(event_id, content[0], content[1], ctx)
            return
            
        if content is None or isinstance(content, int):
            common_failed.send(sender=ctx, key='', url=url,
                    reason='download listing error or {0} return'.format(content))
            return
        tree = lxml.html.fromstring(content)
        segment = tree.cssselect('div.mainframe')[0]
        events_end = tree.cssselect('div#eventTTL')
        if events_end:
            events_end = datetime.utcfromtimestamp( float(events_end[0].get('eventttl')) )
        # both button and nth-last-of-type condition
        page_nums = segment.cssselect('div.clearfix form[method=get] > div.pagination > div.button:nth-last-of-type(1)')
        if page_nums:
            page_nums = int( page_nums[0].text_content() )
        sale_title = tree.cssselect('title')[0].text_content()
        
        product_ids = []
        prds = segment.cssselect('form[method=post] > div#product-list > div.product-row > div.product > div.section')
        for prd in prds:
            product_key = self.crawl_every_product_in_listing(event_id, url, prd, ctx)
            if product_key: product_ids.append(product_key)

        if isinstance(page_nums, int):
            for page_num in range(2, page_nums+1):
                page_url = '{0}?page={1}'.format(url, page_num)
                ret = self.get_next_page_in_listing(event_id, page_url, page_num, ctx)
                if ret: product_ids.extend(ret)

        event = Event.objects(event_id=event_id).first()
        if not event: event = Event(event_id=event_id)
        if event.urgent == True:
            event.urgent = False
            ready = True
        else: ready = False

        # some page return 'event has ended', but actually not.I keep record it.
        if events_end:
            if event.events_end != events_end:
                event.update_history.update({ 'events_end': datetime.utcnow() })
                event.events_end = events_end
        if isinstance(page_nums, int): event.num = page_nums
        if not event.sale_title: event.sale_title = sale_title
        event.product_ids = product_ids
        event.update_time = datetime.utcnow()
        event.save()
        common_saved.send(sender=ctx, obj_type='Event', key=event_id, is_new=False, is_updated=False, ready=ready)


    def crawl_every_product_in_listing(self, event_id, url, prd, ctx):
        soldout = True if prd.cssselect('div.section-img > div.showcase-overlay > a > div') else False
        link = prd.cssselect('div.section-img > a[href]')
        if link:
            link = link[0].get('href')
        else: # blank place in the last few products' place
            return
        key = re.compile('.*/event/sku/{0}/(\w+)\??.*'.format(event_id)).match(link).group(1)

        brand = prd.cssselect('div.clearfix > h4.brand')[0].text_content()
        title = prd.cssselect('div.clearfix > div[style]:first-of-type')[0].text_content()
        listprice = prd.cssselect('div.clearfix > div > div.product-price-prev')[0].text_content()
        price = prd.cssselect('div.clearfix > div > div.product-price')[0].text_content()
        size_nodes = prd.cssselect('div.clearfix > div > div > select.size-selector > option')
        sizes = []
        for size in size_nodes:
            sizes.append( size.text_content().strip() )
        combine_url = 'http://www.beyondtherack.com/event/sku/{0}/{1}'.format(event_id, key)

        is_new, is_updated = False, False
        product = Product.objects(key=key).first()
        if not product:
            is_new = True
            product = Product(key=key)
            product.updated = False
            product.combine_url = combine_url
            product.soldout = soldout
            product.brand = brand
            product.title = title
            product.listprice = listprice
            product.price = price
            product.sizes = sizes
        else:
            if product.soldout != soldout: # beyondtherack can change back
                product.soldout = soldout
                is_updated = True
                product.update_history.update({ 'soldout': datetime.utcnow() })
            if product.combine_url != combine_url:
                product.combine_url = combine_url
                product.update_history.update({ 'combine_url': datetime.utcnow() })
            if not product.title: product.title = title
            if product.price != price:
                product.price = price
                product.update_history.update({ 'price': datetime.utcnow() })
            if product.listprice != listprice:
                product.listprice = listprice
                product.update_history.update({ 'listprice': datetime.utcnow() })
        if event_id not in product.event_id: product.event_id.append(event_id)
        product.list_update_time = datetime.utcnow()
        product.save()
        common_saved.send(sender=ctx, obj_type='Product', key=key, url=link, is_new=is_new, is_updated=is_updated)
        return key


    def get_next_page_in_listing(self, event_id, page_url, page_num, ctx):
        content = self.net.fetch_listing_page(page_url)
        if content is None or isinstance(content, int):
            common_failed.send(sender=ctx, key='', url=page_url,
                    reason='download listing error or {0} return'.format(content))
            return
        product_ids = []
        tree = lxml.html.fromstring(content)
        segment = tree.cssselect('div.mainframe')[0]
        prds = segment.cssselect('form[method=post] > div#product-list > div.product-row > div.product > div.section')
        for prd in prds:
            product_key = self.crawl_every_product_in_listing(event_id, page_url, prd, ctx)
            if product_key: product_ids.append(product_key)
        return product_ids


    def crawl_event_is_product(self, event_id, product_url, content, ctx):
        """.. :py:method::

            event listing page url redirect to product page
        :param event_id: event id
        :param product_url: redirect to the product_url
        :param content: product_url's content
        """
        key = re.compile('http://www.beyondtherack.com/event/sku/\w+/(\w+)\??.*').match(product_url).group(1)
        tree = lxml.html.fromstring(content)
        events_end = tree.cssselect('div.pageframe > div.mainframe div#eventTTL')
        events_end = datetime.utcfromtimestamp( float(events_end[0].get('eventttl')) )
        event = Event.objects(event_id=event_id).first()
        title = event.sale_title
        if event.events_end != events_end:
            event.update_history.update({ 'events_end': datetime.utcnow() })
            event.events_end = events_end
        event.update_time = datetime.utcnow()
        if event.urgent == True:
            event.urgent = False
            ready = True
        else: ready = False
        
        listprice = tree.cssselect('div.pageframe > div.mainframe > div.clearfix div.clearfix span.product-price-prev')[0].text_content()
        price = tree.cssselect('div.pageframe > div.mainframe > div.clearfix div.clearfix span.product-price')[0].text_content()
        list_info, summary, shipping, returned, image_urls = self.parse_product_info(tree)

        is_new, is_updated = False, False
        product = Product.objects(key=key).first()
        if not product:
            is_new = True
            product = Product(key=key)
        product.title = title
        product.listprice = listprice
        product.price = price
        product.summary = summary
        product.list_info = list_info
        product.shipping = shipping
        product.returned = returned
        product.image_urls = image_urls
        if event_id not in product.event_id: product.event_id.append(event_id)
        product.full_update_time = datetime.utcnow()
        product.updated = True
        if is_new: ready = True
        else: ready = False
        product.save()
        common_saved.send(sender=ctx, obj_type='Product', key=key, url=product_url, is_new=is_new, is_updated=is_updated, ready=ready)

        event.product_ids = [key]
        event.save()
        common_saved.send(sender=ctx, obj_type='Event', key=event_id,
                url='http://www.beyondtherack.com/event/showcase/{0}'.format(event_id),
                is_new=False, is_updated=False, ready=ready)

    def crawl_product(self, url, ctx='', **kwargs):
        if kwargs.get('login_email'): self.net.check_signin( kwargs.get('login_email') )
        else: self.net.check_signin()

        key = url.rsplit('/', 1)[-1]
        content = self.net.fetch_product_page(url)
        if content == -302:
            common_failed.send(sender=ctx, key=key, url=url, reason='download product redirect to homepage')
            return
        if content is None or isinstance(content, int):
            common_failed.send(sender=ctx, key=key, url=url,
                    reason='download product error or {0} return'.format(content))
            return
        tree = lxml.html.fromstring(content)
        list_info, summary, shipping, returned, image_urls = self.parse_product_info(tree)

        is_new, is_updated = False, False
        product = Product.objects(key=key).first()
        if not product:
            is_new = True
            product = Product(key=key)
        product.summary = summary
        product.list_info = list_info
        product.shipping = shipping
        product.returned = returned
        product.image_urls = image_urls
        product.full_update_time = datetime.utcnow()
        if product.updated == False:
            product.updated = True
            ready = True
        else: ready = False
        product.save()
        common_saved.send(sender=ctx, obj_type='Product', key=key, url=url, is_new=is_new, is_updated=is_updated, ready=ready)
            
    def parse_product_info(self, tree):
        """.. :py:method::

        :param tree: element tree of product page
        """
        nav = tree.cssselect('div.pageframe > div.mainframe > div.clearfix')[0]
        list_info = []
        for li in nav.xpath('./div/div/ul[@style]/li'):
            list_info.append( li.text_content().strip() )
        summary, list_info = '; '.join(list_info), []
        for li in nav.xpath('./div/ul[@style]/li'):
            list_info.append( li.text_content().strip() )
        shipping = nav.xpath('.//div[@style]/div/a[@id="ship_map"]/parent::div[@style]')
        if shipping:
            shipping = shipping[0].text_content() 
        else:
            shipping = nav.xpath('.//div[@style="text-align: left;"]/div[3]')[0].text_content()
        returned = ''
        for r in nav.xpath('.//div[@style="text-align: left;"]/div[@class="dark-gray-text"]'):
            if r.text_content().strip():
                returned += r.text_content().strip() + ' '
        image_urls = []
        for img in nav.cssselect('div[style] > div > a.cloud-zoom-gallery > img'):
            image_urls.append( img.get('src').replace('small', 'large') )
        return list_info, summary, shipping, returned, image_urls

    def check(self, old):
        count = 0
        content = self.net.fetch_page('http://www.beyondtherack.com/event/calendar')
        tree = lxml.html.fromstring(content)
        upcoming_data = json.loads( re.compile('var event_data *= *({.*});').search(content).group(1) )
        upcomings = tree.cssselect('div.pageframe table.upcomingEvents > tbody > tr > td.data-row > div.item')
        for up in upcomings:
            event_id = up.get('data-event')
            sale_title = up.text_content().strip()
            if event_id == '34271':
                image_urls = upcoming_data[event_id]['images'].values()
                image = image_urls[0]
                if image != old:
                    old = image
                    open('{0}.jpg'.format(count), 'w').write(requests.get(old).content)
                    open('a.log', 'a').write('{0}   {1}   {2}\n'.format(old, count, datetime.utcnow() ))
                    count += 1
                    return old
        return old


if __name__ == '__main__':
    ss = Server()
    ss.crawl_category()
    exit()
    import time
    image = ''
    while True:
        image = ss.check(image)
        time.sleep(500)
