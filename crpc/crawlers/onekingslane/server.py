#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
crawlers.onekingslane.server
~~~~~~~~~~~~~~~~~~~

This is the server part of zeroRPC module. Call by client automatically, run on many differen ec2 instances.

"""
import os
import re
import sys
import time
import zerorpc
import lxml.html
import itertools
import pytz

from datetime import datetime, timedelta

from .models import *
from crawlers.common.events import *
from crawlers.common.stash import *

import requests
from requests.packages.urllib3.connectionpool import *
import ssl 
def connect_vnew(self):
    # Add certificate verification
    sock = socket.create_connection((self.host, self.port), self.timeout)

    # Wrap socket using verification with the root certs in
    # trusted_root_certs
    self.sock = ssl.wrap_socket(sock, self.key_file, self.cert_file,
                                cert_reqs=self.cert_reqs,
                                ca_certs=self.ca_certs,
                                ssl_version=ssl.PROTOCOL_TLSv1)
    if self.ca_certs:
        match_hostname(self.sock.getpeercert(), self.host)

VerifiedHTTPSConnection.connect = connect_vnew

headers = {
    'Host': 'www.onekingslane.com',
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:15.2) Gecko/20121028 Firefox/15.2.1 PaleMoon/15.2.1',
    'Referer': 'https://www.onekingslane.com/login',
}

req = requests.Session(prefetch=True, timeout=30, config=config, headers=headers)


class onekingslaneLogin(object):
    """.. :py:class:: onekingslaneLogin
        login, check whether login, fetch page.
    """
    def __init__(self):
        """.. :py:method::
            variables need to be used
        """
        self.login_url = 'https://www.onekingslane.com/login'
        self.data = { 
            'email': login_email,
            'password': login_passwd,
            'keepLogIn': 1,
            'sumbit.x': 54,
            'sumbit.y': 7,
            'returnUrl': '0',
        }   
        self._signin = False

    def login_account(self):
        """.. :py:method::
            use post method to login
        """
        req.post(self.login_url, data=self.data)
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
        ret = req.get(url)

        if ret.ok: return ret.content
        return ret.status_code



class Server(object):
    """.. :py:class:: Server
    
    This is zeroRPC server class for ec2 instance to crawl pages.

    """
    def __init__(self):
        self.siteurl = 'https://www.onekingslane.com'
        self.upcoming_url = 'https://www.onekingslane.com/calendar'
        self.category_url = 'https://www.onekingslane.com/vintage-market-finds'
        self.net = onekingslaneLogin()
        self.extract_eventid = re.compile('https://www.onekingslane.com/sales/(\d+)')
        self.extract_large_img = re.compile('(.*\?)\$.*\$')

        self.get_product_condition = re.compile(r'<strong>Condition:</strong>(.*)</p>')
        self.get_product_era = re.compile(r'<strong>Era:</strong>(.*)</p>')

    def crawl_category(self, ctx):
        """.. :py:method::
            crawl upcoming sales, sales, and shop by category
        """
        debug_info.send(sender=DB + '.category.begin')

        self.upcoming_proc(ctx)
        self.get_sale_list(ctx)
        self.shop_by_category(ctx)
        debug_info.send(sender=DB + '.category.end')

    def get_sale_list(self, ctx):
        """.. :py:method::
            Get all the sales from sale list.
            Sales have a list of products.
        """
        cont = self.net.fetch_page(self.siteurl)
        tree = lxml.html.fromstring(cont)
        nodes = tree.cssselect('body.holiday > div#wrapper > div#okl-content > div#previewWrapper div.eventsContainer > div[id^="salesEventId_"]')
        for node in nodes:
            title = node.cssselect('div.eventInfo > div > h3')[0].text
            short_desc = node.cssselect('div.eventInfo > div > p')[0].text
            l = node.cssselect('a[href]')[0].get('href')
            link = l if l.startswith('http') else self.siteurl + l
            event_id = self.extract_eventid.match(link).group(1)

            event, is_new = Event.objects.get_or_create(event_id=event_id)
            if is_new:
                event.sale_title = title
                event.short_desc = short_desc
                img = node.cssselect('div.eventStatus > a.trackEventPosition > img')[0].get('src')
                image = self.extract_large_img.match(img).group(1) + '$fullzoom$'
                event.image_urls = [image]
                event.urgent = True
                event.combine_url = 'https://www.onekingslane.com/sales/{0}'.format(event_id)
#                event.is_leaf = True
#            else:
#                if not event.is_leaf: # upcoming events
#                    event.urgent = True
            event.update_time = datetime.utcnow()
            event.save()
            common_saved.send(sender=ctx, key=event_id, url=link, is_new=is_new, is_updated=False)


    def upcoming_proc(self, ctx):
        """.. :py:method::
            Get all the upcoming brands info in upcoming url 
        """
        cont = self.net.fetch_page(self.upcoming_url)
        tree = lxml.html.fromstring(cont)
        nodes = tree.cssselect('body.holiday > div#wrapper > div#okl-content > div.calendar-r > div.day')
        for node in nodes:
            date = ' '.join( [d for d in node.cssselect('span.date')[0].text_content().split('\n') if d] )
            all_times = node.cssselect('div.all-times > h3')[0].text_content().split('PT')[0].split()[-1]
            date_begin = time_convert(date + ' ' + all_times + ' ', '%b %d %I%p %Y')
            markets = node.cssselect('div.all-times > ul > li')
            for market in markets:
                link = market.cssselect('h4 > a')[0].get('href')
                link = link if link.startswith('http') else self.siteurl + link
                event_id = self.extract_eventid.match(link).group(1)
                event, is_new = Event.objects.get_or_create(event_id=event_id)
                if is_new:
                    event.events_begin = date_begin
                    img = market.cssselect('h4 > a > img')[0].get('src') + '?$fullzoom$'
                    event.image_urls = [img]
                    event.sale_title = market.cssselect('h4 > a')[0].text_content()
                    event.short_desc = market.cssselect('p.shortDescription')[0].text_content()
                    detail_tree = lxml.html.fromstring(self.net.fetch_page(link))
                    sale_description = detail_tree.cssselect('div#wrapper > div#okl-content > div.sales-event > div#okl-bio > div.event-description .description')
                    if sale_description:
                        event.sale_description = sale_description[0].text.strip()
                    event.urgent = True
                    event.combine_url = 'https://www.onekingslane.com/sales/{0}'.format(event_id)
                
                event.update_time = datetime.utcnow()
                event.save()
                common_saved.send(sender=ctx, key=event_id, url=link, is_new=is_new, is_updated=False)


    def utcstr2datetime(self, date_str):
        """.. :py:method::
            covert time from the format into utcnow()
            '20121105T150000Z'
        """
        fmt = "%Y%m%dT%H%M%S"
        return datetime.strptime(date_str.rstrip('Z'), fmt)

    def shop_by_category(self, ctx):
        """.. :py:method::
        """
        cont = self.net.fetch_page(self.category_url)
        tree = lxml.html.fromstring(cont)
        today = tree.cssselect('div#wrapper > div#okl-content > div#okl-vmf-landing-hd > ul > li.product > a.trackVmfProduct')
        nodes = tree.cssselect('div#wrapper > div#okl-content > div#okl-vmf-landing-bd > ul > li > h4 > a')
        for node in itertools.chain(today, nodes):
            link = node.get('href')
            dept = node.text_content()
            if not dept: dept = link.split('/')[-1]

            event_id = re.compile(r'.*/vintage-market-finds/(.*)').match(link).group(1)
            event, is_new = Event.objects.get_or_create(event_id=event_id)
            event.combine_url = 'https://www.onekingslane.com/vintage-market-finds/{0}'.format(event_id)
            event.dept = [dept]
#            event.is_leaf = True
            event.update_time = datetime.utcnow()
            event.save()
            common_saved.send(sender=ctx, key=event_id, url=link, is_new=is_new, is_updated=False)


    def crawl_listing(self, url, ctx):
        """.. :py:method::
            from url get listing page,
            either category_list or sale_list
        :param url: listing page url
        """
        debug_info.send(sender=DB + '.crawl_list.begin')
        cont = self.net.fetch_page(url)
        if isinstance(cont, int):
            common_failed.send(sender=ctx, url=url, reason=cont)
            return
        tree = lxml.html.fromstring(cont)
        if 'vintage-market-finds' in url:
            self.crawl_category_list(url, tree, ctx)
        else:
            self.crawl_sale_list(url, tree, ctx)
        debug_info.send(sender=DB + '.crawl_list.end')


    def crawl_category_list(self, url, tree, ctx):
        """.. :py:method::
            from url get listing page.
            from listing page get Event's description, number of products.
            Get all product's image, url, title, price, soldout

        :param url: category listing page url
        :param tree: listing page url's lxml tree
        """
        event_id = re.compile(r'.*/vintage-market-finds/(.*)').match(url).group(1)

        event, is_new = Event.objects.get_or_create(event_id=event_id)
        if not event.sale_description:
            event.sale_description = tree.cssselect('div#wrapper > div#okl-content > div#okl-vmf-category-carousel-hd > h3+p')[0].text_content()
        items = tree.cssselect('div#wrapper > div#okl-content > div#okl-vmf-product-list > ul.products > li.trackVmfProduct')
        event.num = len(items)
        event.urgent = False

        for item in items:
            self.crawl_category_list_product(event_id, item, ctx)

        event.save()
        common_saved.send(sender=ctx, key=event_id, url=url, is_new=is_new, is_updated=False, ready='Event')

    def crawl_category_list_product(self, event_id, item, ctx):
        """.. :py:method::
            from lxml node to get category listing page's product.

        :param item: xml node for a product
        """
        l = item.cssselect('a[href]')[0].get('href')
        link = l if l.startswith('http') else self.siteurl + l
        product_id = re.compile(r'https://www.onekingslane.com/vintage-market-finds/product/(\d+)').match(link).group(1)
        product, is_new = Product.objects.get_or_create(pk=product_id)
        is_updated = False
        if is_new:
            product.event_id = [event_id]
            product.image_urls = [item.cssselect('a[href] > img')[0].get('src').replace('medium', 'fullzoom')]
            product.short_desc = item.cssselect('h6')[0].text_content()
            product.title = item.cssselect('h5 > a')[0].text_content()
            product.listprice = item.cssselect('ul > li.retail')[0].text_content()
            product.price = item.cssselect('ul > li:nth-of-type(2)')[0].text_content().replace(',','')
            if item.cssselect('em.sold'): product.soldout = True
            product.updated = False
            product.combine_url = 'https://www.onekingslane.com/vintage-market-finds/product/{0}'.format(product_id)
        else:
            if event_id not in product.event_id:
                product.event_id.append(event_id)
            if product.soldout != True:
                if item.cssselect('em.sold'):
                    product.soldout = True
                    is_updated = True
        product.list_update_time = datetime.utcnow()
        product.save()
        common_saved.send(sender=ctx, key=product_id, url=self.siteurl + '/vintage-market-finds/' + event_id, is_new=is_new, is_updated=is_updated)


    def crawl_sale_list(self, url, tree, ctx):
        """.. :py:method::
            from url get listing page.
            from listing page get Event's description, endtime, number of products.
            Get all product's image, url, title, price, soldout

        :param tree: listing page url's lxml tree
        """
        path = tree.cssselect('div#wrapper > div#okl-content > div.sales-event')[0]
        items = path.cssselect('div#okl-product > ul.products > li[id^="product-tile-"]')
        event_id = self.extract_eventid.match(url).group(1)
        event, is_new = Event.objects.get_or_create(event_id=event_id)
        if not event.sale_description:
            sale_description = path.cssselect('div#okl-bio > div.event-description .description')
            if sale_description:
                event.sale_description = sale_description[0].text.strip()
        if not event.events_end:
            end_date = path.cssselect('div#okl-bio > h2.share')[0].get('data-end')
            event.events_end = self.utcstr2datetime(end_date)
        if not event.sale_title:
            event.sale_title = path.cssselect('div#okl-bio > h2.share > strong')[0].text

        event.num = len(items)
        event.update_time = datetime.utcnow()
        if event.urgent == True:
            event.urgent = False
            ready = 'Event'
        else: ready = None

        for item in items: self.crawl_sale_list_product(event_id, item, ctx)

        event.save()
        common_saved.send(sender=ctx, key=event_id, url=url, is_new=is_new, is_updated=False, ready=ready)


    def crawl_sale_list_product(self, event_id, item, ctx):
        """.. :py:method::
            In listing page, Get all product's image, url, title, price, soldout

        :param event_id: unique key in Event, which we can associate product with event
        :param item: item of xml node
        """
        product_id = item.get('data-product-id')
        product, is_new = Product.objects.get_or_create(pk=product_id)
        is_updated = False
        if is_new:
            product.event_id = [event_id]
            product.title = item.cssselect('h3 > a[data-linkname]')[0].text
            product.sell_rank = int(item.get('data-sortorder'))
            img = item.cssselect('a > img.productImage')[0].get('src')
            image = self.extract_large_img.match(img).group(1) + '$fullzoom$'
            product.image_urls = [image]

            listprice = item.cssselect('ul > li.msrp')
            if listprice:
                product.listprice = listprice[0].text_content().replace(',','').replace('Retail', '').strip()
            price = item.cssselect('ul > li:last-of-type')
            if not price:
                common_failed.send(sender=ctx, url=event_id + '/' + product_id, reason='price not resolve right')
            product.price = price[0].text_content().replace(',','')
            if item.cssselect('a.sold-out'): product.soldout = True
            product.updated = False
            product.combine_url = 'https://www.onekingslane.com/product/{0}/{1}'.format(event_id, product_id)
        else:
            if event_id not in product.event_id:
                product.event_id.append(event_id)
            if product.soldout != True:
                if item.cssselect('a.sold-out'):
                    product.soldout = True
                    is_updated = True
        product.list_update_time = datetime.utcnow()
        product.save()
        common_saved.send(sender=ctx, key=product_id, url=self.siteurl + '/sales/' + event_id, is_new=is_new, is_updated=is_updated)
        debug_info.send(sender=DB + ".crawl_listing", url=self.siteurl + '/sales/' + event_id)


    def crawl_product(self, url, ctx):
        """.. :py:method::
            Got all the product information and save into the database

        :param url: product url
        """
        cont = self.net.fetch_page(url)
        if isinstance(cont, int):
            common_failed.send(sender=ctx, url=url, reason=cont)
            return
        tree = lxml.html.fromstring(cont)
        if 'vintage-market-finds' in url:
            self.crawl_product_vintage(url, tree, ctx)
        else:
            self.crawl_product_sales(url, cont, tree, ctx)


    def crawl_product_vintage(self, url, tree, ctx):
        """.. :py:method::
        :param url: porduct url need to crawl
        """
        product_id = url.split('/')[-1]
        product, is_new = Product.objects.get_or_create(pk=product_id)
        node = tree.cssselect('body > div#wrapper > div#okl-content > div#okl-product')[0]

        vintage = node.cssselect('form#productOverview > dl.vintage')[0]
        era = vintage.cssselect('dd:first-of-type')
        if era: product.era = era[0].text_content()
        condition = vintage.cssselect('dd:nth-of-type(2)')
        if condition: product.condition = condition[0].text_content()

        img = node.cssselect('div#productDescription > div#altImages')
        if img:
            for i in img[0].cssselect('img.altImage'):
                img_url = i.get('data-altimgbaseurl') + '$fullzoom$'
                if img_url not in product.image_urls:
                    product.image_urls.append(img_url)

        product.summary = node.cssselect('div#productDescription > div#description')[0].text_content()
        seller = node.cssselect('div#productDescription > div#okl-vmf-vendor')
        if seller:
            product.seller = seller[0].cssselect('div')[0].text_content()

        list_info = node.cssselect('div#productDetails > dl:first-of-type')[0].text_content()
        product.list_info = list_info if isinstance(list_info, list) else [list_info]
        product.returned = node.cssselect('div#productDetails > dl:nth-of-type(2)')[0].text_content()
        end_date = node.cssselect('div#productDetails > p.endDate')[0].text.split('until')[-1].strip() # '11/10 at 11am EST'
        product.products_end = self.et_time_convert(end_date.rsplit(' ', 1)[0], '%m/%d at %I%p%Y')
        if product.updated == False:
            product.updated = True
            ready = 'Product'
        else: ready = None
        product.full_update_time = datetime.utcnow()
        product.save()
        common_saved.send(sender=ctx, key=product_id, url=url, is_new=is_new, is_updated=not is_new, ready=ready)

    def et_time_convert(self, time_str, time_format):
        """.. :py:method::

        :param time_str: u'SAT OCT 20 9 AM '
        :param time_format: '%a %b %d %I %p %Y'
        :rtype: datetime type utc time
        """
        pt = pytz.timezone('US/Eastern')
        tinfo = time_str + str(pt.normalize(datetime.now(tz=pt)).year)
        endtime = pt.localize(datetime.strptime(tinfo, time_format))
        return endtime.astimezone(pytz.utc)

    def crawl_product_sales(self, url, cont, tree, ctx):
        """.. :py:method::
        :param url: porduct url need to crawl
        """
        product_id = url.split('/')[-1]
        product, is_new = Product.objects.get_or_create(pk=product_id)
        m = self.get_product_condition.search(cont)
        if m:
            product.condition = m.group(1).strip()
        m = self.get_product_era.search(cont)
        if m:
            product.era = m.group(1).strip()

        node = tree.cssselect('body.holiday > div#wrapper > div#okl-content')[0]
        product.list_info = node.cssselect('div#productDetails > dl:first-of-type')[0].text_content().split('\n')
        # shippingDetails maybe under productDetails, maybe under first dl. endDate also have the same problem
        # shipping and endDate may not exist in: https://www.onekingslane.com/product/17014/405312
        shipping = node.cssselect('div#productDetails dl.shippingDetails')
        if shipping: product.returned = shipping[0].text_content()
        endDate = node.cssselect('div#productDetails p.endDate')
        if endDate:
            _date, _time = endDate[0].text_content().strip().split('at')
            time_str = _date.split()[-1] + ' ' +  _time.split()[0] + ' '
            product.products_end = time_convert(time_str, '%m/%d %I%p %Y')
        product.summary = node.cssselect('div#productDescription > div#description')[0].text_content()

        img = node.cssselect('div#productDescription > div#altImages')
        if img:
            for i in img[0].cssselect('img.altImage'):
                img_url = i.get('data-altimgbaseurl') + '$fullzoom$'
                if img_url not in product.image_urls:
                    product.image_urls.append(img_url)

        seller = node.cssselect('div#productDescription > div.ds-vmf-vendor')
        if seller:
            product.seller = seller[0].cssselect('div[class]')[0].text_content()
        if product.updated == False:
            product.updated = True
            ready = 'Product'
        else: ready = None
        product.full_update_time = datetime.utcnow()
        product.save()
        common_saved.send(sender=ctx, key=product_id, url=url, is_new=is_new, is_updated=not is_new, ready=ready)

        

if __name__ == '__main__':
    server = zerorpc.Server(Server())
    server.bind("tcp://0.0.0.0:{0}".format(RPC_PORT))
    server.run()
