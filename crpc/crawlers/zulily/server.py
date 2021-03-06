#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
crawlers.zulily.server
~~~~~~~~~~~~~~~~~~~

This is the server part of zeroRPC module. Call by client automatically, run on many differen ec2 instances.

"""
from gevent import monkey
monkey.patch_all()
from gevent.pool import Pool

import os
import re
import sys
import time
import zerorpc
import lxml.html
import pytz
import ConfigParser

from urllib import quote, unquote
from datetime import datetime, timedelta
from random import SystemRandom

from models import *
from crawlers.common.events import *
from crawlers.common.stash import *



SLEEP = 2
alphabet = ['0','1','2','3','4','5','6','7','8','9','a','b','c','d','e','f','g','h','i','j','k','l','m','n','o','p','q','r','s','t','u','v','w','x','y','z']

header = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Charset': 'UTF-8,*;q=0.5',
    'Accept-Encoding': 'gzip,deflate,sdch',
    'Accept-Language': 'zh-CN,en-US;q=0.8,en;q=0.6',
    'Host': 'www.zulily.com',
    'Referer': 'http://www.zulily.com/',
    'User-Agent': 'Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)',
}
req = requests.Session(prefetch=True, timeout=30, config=config, headers=header)

class zulilyLogin(object):
    """.. :py:class:: zulilyLogin
        login, check whether login, fetch page.
    """
    def __init__(self):
        """.. :py:method::
            variables need to be used
        """
        self.login_url = 'https://www.zulily.com/auth'
        self.badpage_url = re.compile('.*zulily.com/z/.*html')
        self.rd = SystemRandom()
        self.conf = ConfigParser.ConfigParser()
        self.data = {
            'login[username]': get_login_email('zulily'),
            'login[password]': login_passwd
        }
        self.current_email = self.data['login[username]']
        # self.reg_check = re.compile(r'https://www.zulily.com/auth/create.*') # need to authentication
        self._signin = {}

    def create_new_account(self):
        regist_url = 'https://www.zulily.com/auth/create/'
        regist_data = {
            'firstname': 'first',
            'lastname': 'last',
            'email': ''.join( self.rd.sample(alphabet, 10) ) + '@gmail.com',
            'password': login_passwd,
            'confirmation': login_passwd,
        }
        ret = req.post(regist_url, data=regist_data)
        return ret.url, regist_data['email']

    def change_username(self):
        """
        Already signed up.
        https://www.zulily.com/auth/?email=abcd1234%40gmail.com&firstname=first&lastname=last


        Could not process your sign up. Please try again.
        https://www.zulily.com/auth/create/?email=tty1tty1%40gmail.com&firstname=first&lastname=last
        """
        returl, email = self.create_new_account()
        times = 0
        while returl.startswith('https://www.zulily.com/auth/'):
            returl, email = self.create_new_account()
            times += 1
            if times >= 3:
                time.sleep(600)
                times = 0

        self.conf.read( os.path.join(os.path.dirname(__file__), '../common/username.ini') )
        self.conf.set('username', DB, email)
        self.conf.write(open(os.path.join(os.path.dirname(__file__), '../common/username.ini'), 'w'))
        return email


    def whether_itis_badpage(self, url):
        if self.badpage_url.match(url):
            self.logout_account()
            email = self.change_username()
            self.current_email = email
            self.login_account()
            return True
        else: return False

    def login_account(self):
        """.. :py:method::
            use post method to login
        """
        self.data['login[username]'] = self.current_email
        req.post(self.login_url, data=self.data)
        self._signin[self.current_email] = True

    def logout_account(self):
        req.get('https://www.zulily.com/auth/logout/')

    def check_signin(self, username=''):
        """.. :py:method::
            check whether the account is login
        """
        if username == '':
            self.logout_account()
            self.login_account()
        elif username not in self._signin:
            self.current_email = username
            self.logout_account()
            self.login_account()
        else:
            self.current_email = username

    def fetch_page(self, url):
        """.. :py:method::
            fetch page.
            check whether the account is login, if not, login and fetch again
        """
        ret = req.get(url)
        time.sleep(SLEEP)

        if self.whether_itis_badpage(ret.url):
            ret = req.get(url)

        if ret.url == u'http://www.zulily.com/oops-event':
            return -404
        if ret.url == 'http://www.zulily.com/?tab=new-today':
            self.logout_account()
            self.login_account()
            ret = req.get(url)
        if ret.ok: return ret.content
        return ret.status_code

    def fetch_listing_page(self, url):
        """.. :py:method::
            fetch page.
            check whether the account is login, if not, login and fetch again
        """
        ret = req.get(url)
        time.sleep(SLEEP)

        if self.whether_itis_badpage(ret.url):
            ret = req.get(url)

        if ret.url == u'http://www.zulily.com/oops-event':
            return -404
        if ret.url == u'http://www.zulily.com/' or 'http://www.zulily.com/brand/' in ret.url:
            return -302
        if ret.url == 'http://www.zulily.com/?tab=new-today':
            self.logout_account()
            self.login_account()
            ret = req.get(url)
        if ret.ok: return ret.content
        return ret.status_code


class Server(object):
    """.. :py:class:: Server
    
    This is zeroRPC server class for ec2 instance to crawl pages.

    """
    def __init__(self):
        self.siteurl = 'http://www.zulily.com'
        self.upcoming_url = 'http://www.zulily.com/upcoming_events'
        self.net = zulilyLogin()
        self.extract_event_id = re.compile(r'(http://www.zulily.com/e/(.*).html).*')
        self.extract_event_img = re.compile(r'(http://mcdn.zulily.com/images/cache/event/)\d+x\d+/(.+)')
        self.extract_product_img = re.compile(r'(http://mcdn.zulily.com/images/cache/product/)\d+x\d+/(.+)')
        self.extract_product_re = re.compile(r'http://www.zulily.com/p/(.+).html.*')

        self.returned_re = re.compile(r'<strong>Return Policy:</strong>(.*)<')
        self.shipping_re = re.compile(r'<strong>Shipping:</strong>(.*)<')

    def crawl_category(self, ctx='', **kwargs):
        """.. :py:method::
            From top depts, get all the events
        """
#        if kwargs.get('login_email'): self.net.check_signin( kwargs.get('login_email') )
#        else: self.net.check_signin()

        depts = ['girls', 'boys', 'women', 'baby-maternity', 'toys-playtime', 'home']
        debug_info.send(sender=DB + '.category.begin')

        self.upcoming_proc(ctx)
        for dept in depts:
            link = 'http://www.zulily.com/?tab={0}'.format(dept)
            self.get_event_list(dept, link, ctx)
        debug_info.send(sender=DB + '.category.end')

    def get_event_list(self, dept, url, ctx):
        """.. :py:method::
            Get all the brands from brand list.
            Brand have a list of product.

        :param dept: dept in the page
        :param url: the dept's url
        """
        cont = self.net.fetch_page(url)
        tree = lxml.html.fromstring(cont)
        nodes = tree.xpath('//div[@class="container"]/div[@id="main"]/div[@id="home-page-content"]/div[@class="clearfix"]//div[starts-with(@id, "eid_")]')
        
        for node in nodes:
            link = node.cssselect('a.wrapped-link')[0].get('href')
            m = self.extract_event_id.match(link)
            # the error: it is an event, but also a product page
            if not m:
                # common_failed.send(sender=ctx, url=url, reason='the link[{0}] can not extract event_id'.format(link))
                continue
            link, event_id = m.groups()
            text = node.xpath('./a/span[@class="txt"]')[0]
            img = node.xpath('./a/span[@class="homepage-image"]/img/@src')[0]
            m = self.extract_event_img.match(img)
            if m: image = ''.join( m.groups() )
            else: image = img
            sale_title = text.xpath('./span[@class="category-name"]/span/text()')[0]

            brand, is_new = Event.objects.get_or_create(event_id=event_id)
            if is_new:
                brand.sale_title = sale_title.encode('utf-8')
                brand.urgent = True
                brand.combine_url = 'http://www.zulily.com/e/{0}.html'.format(event_id)
            if image not in brand.image_urls: brand.image_urls.append(image)
            brand.short_desc = text.xpath('.//span[@class="description-highlights"]/text()')[0].strip()
            brand.start_end_date = text.xpath('./span[@class="description"]/span[@class="start-end-date"]')[0].text_content().strip()
            if dept not in brand.dept: brand.dept.append(dept) # events are mixed in different category
            brand.update_time = datetime.utcnow()
            brand.save()
            common_saved.send(sender=ctx, obj_type='Event', key=event_id, url=url, is_new=is_new, is_updated=False)


    def upcoming_proc(self, ctx):
        """.. :py:method::
            Get all the upcoming brands info 
        """
        upcoming_list = []
        cont = self.net.fetch_page(self.upcoming_url)
        tree = lxml.html.fromstring(cont)
        nodes = tree.xpath('//div[@class="event-content-list-wrapper"]/ul/li/a')
        for node in nodes:
            link = node.get('href')
            text = node.text_content()
            upcoming_list.append( (text, link) )
        self.upcoming_detail(upcoming_list, ctx)

    def upcoming_detail(self, upcoming_list, ctx):
        """.. :py:method::
            zulily will on sale the events in advance, maybe 10~30 minutes,
            so events_begin - timedelta(minutes=5) as the events_begin time
        """
        for pair in upcoming_list:
            cont = self.net.fetch_page(pair[1])
            tree = lxml.html.fromstring(cont)
            node = tree.cssselect('div.event-content-wrapper')[0]
            calendar_file = node.cssselect('div.upcoming-date-reminder a.reminder-ical')[0].get('href')
            ics_file = self.net.fetch_page(calendar_file)
            img = node.cssselect('div.event-content-image img')[0].get('src')
            m = self.extract_event_img.match(img)
            if m: image = ''.join( m.groups() )
            else: image = img
            if 'placeholder.jpg' in image:
                image = ''
            sale_title = node.cssselect('div.event-content-copy h1')[0].text_content()
            sale_description = node.cssselect('div.event-content-copy div#desc-with-expanded')[0].text_content().strip()
            m = re.compile(r'URL:http://www.zulily.com/(e|p)/(.+).html.*').search(ics_file)
            if m is None:
                common_failed.send(sender=ctx, key='upcoming event', url=pair[1], reason='parse event_id in ics_file failed.')
                continue
            event_id = m.group(2)

            event, is_new = Event.objects.get_or_create(event_id=event_id)
            if is_new:
                event.urgent = True
                event.combine_url = 'http://www.zulily.com/e/{0}.html'.format(event_id)
                event.sale_title = sale_title.encode('utf-8')
                event.sale_description = sale_description.encode('utf-8')
            if image and image not in event.image_urls: event.image_urls.append(image)
            start_time = node.cssselect('div.upcoming-date-reminder span.reminder-text')[0].text_content() # 'Starts Sat 10/27 6am pt - SET REMINDER'
            ev_begin = time_convert( ' '.join( start_time.split(' ', 4)[1:-1] ), '%a %m/%d %I%p%Y' ) - timedelta(minutes=5) #'Sat 10/27 6am'
            events_begin = datetime(ev_begin.year, ev_begin.month, ev_begin.day, ev_begin.hour, ev_begin.minute)
            if event.events_begin != events_begin:
                event.events_begin = events_begin
                event.update_history.update({ 'events_begin': datetime.utcnow() })
            if event.events_end != None:
                event.events_end = None
                event.update_history.update({ 'events_end': datetime.utcnow() })
            if event.product_ids != []: 
                event.product_ids = []
                event.update_history.update({ 'product_ids': datetime.utcnow() })

            event.update_time = datetime.utcnow()
            event.save()
            common_saved.send(sender=ctx, obj_type='Event', key=event_id, url=pair[1], is_new=is_new, is_updated=False)
            

    def crawl_listing(self, url, ctx='', **kwargs):
        """.. :py:method::
            from url get listing page.
            from listing page get Eventi's description, endtime, number of products.
            Get all product's image, url, title, price, soldout

            Time events_end:
                If remains in [0 - 0:29:59:999], the words is 'Sales ends in ';
                If remains in [0:30 - 1:0), the words is 'Sales ends in 1 hour'
                * Our algorithm is: {time(words) + utcnow + 0:29:59:999}, then eliminate the minutes and seconds

        :param url: listing page url
        """
#        if kwargs.get('login_email'): self.net.check_signin( kwargs.get('login_email') )
#        else: self.net.check_signin()

        event_id = self.extract_event_id.match(url).group(2)
        cont = self.net.fetch_listing_page(url)
        if isinstance(cont, int):
            common_failed.send(sender=ctx, key=event_id, url=url, reason='crawl_listing url error: {0}'.format(cont))
            return

        product_ids = []
        tree = lxml.html.fromstring(cont)
        node = tree.cssselect('div.container > div#main > div#category-view')[0]
        event, is_new = Event.objects.get_or_create(event_id=event_id)
        if not event.sale_description:
            sale_description = node.cssselect('div#category-description>div#desc-with-expanded')
            if not sale_description:
                sale_description = node.cssselect('div#category-view-brand > div.category-description-bg > div.category-view-brand-description > p:first-of-type')
            if sale_description:
                event.sale_description = sale_description[0].text_content().strip().encode('utf-8')

        items = node.cssselect('div#products-grid li.item')
        end_date = node.cssselect('div#new-content-header > div.end-date')[0].text_content().strip()
        if 'in' in end_date: # 'on zulily every day'
            end_date = end_date[end_date.find('in')+2:].strip() # '2 hours' or '1 day(s) 3 hours' or ''
            days = int(end_date.split()[0]) if 'day' in end_date else 0
            hours = int(end_date.split()[-2]) if 'hour' in end_date else 0
            events_end = datetime.utcnow() + timedelta(days=days, hours=hours) + timedelta(minutes=29, seconds=59, microseconds=999999)
            events_end = datetime(events_end.year, events_end.month, events_end.day, events_end.hour)
            if event.events_end != events_end:
                event.events_end = events_end
                event.update_history.update({ 'events_end': datetime.utcnow() })
#        event.num = len(items)

        for item in items:
            product_id = self.crawl_list_product(event_id, item, ctx)
            product_ids.append(product_id)
        page_num = 1
        next_page_url = self.detect_list_next(node, page_num + 1)
        if next_page_url:
            ret = self.crawl_list_next(url, next_page_url, page_num + 1, event_id, ctx)
            product_ids.extend(ret)

        if event.urgent == True:
            event.urgent = False
            ready = True
        else: ready = False
        event.product_ids = product_ids
        event.update_time = datetime.utcnow()
        event.save()
        common_saved.send(sender=ctx, obj_type='Event', key=event_id, url=url, is_new=is_new, is_updated=False, ready=ready)

    def detect_list_next(self, node, page_num):
        """.. :py:method::
            detect whether the listing page have a next page

        :param node: the node generate by crawl_listing
        :param page_num: page number of this event
        """
        next_page = node.cssselect('div#pagination>a[href]') # if have next page
        if next_page:
            next_page_relative_url = next_page[-1].get('href')
            if str(page_num) in next_page_relative_url:
                return next_page_relative_url

    def crawl_list_next(self, url, page_text, page_num, event_id, ctx):
        """.. :py:method::
            crawl listing page's next page, that is page 2, 3, 4, ...

        :param url: listing page url
        :param page_text: this page's relative url
        :param page_num: page number of this event
        :param event_id: unique key in Event, which we can associate product with event
        """
        cont = self.net.fetch_listing_page(url + page_text)
        tree = lxml.html.fromstring(cont)
        node = tree.cssselect('div.container>div#main>div#category-view')[0]
        items = node.cssselect('div#products-grid li.item')

        product_ids = []
        for item in items:
            product_id = self.crawl_list_product(event_id, item, ctx)
            product_ids.append(product_id)
        next_page_url = self.detect_list_next(node, page_num + 1)
        if next_page_url:
            ret = self.crawl_list_next(url, next_page_url, page_num + 1, event_id, ctx)
            product_ids.extend(ret)
        return product_ids

    def crawl_list_product(self, event_id, item, ctx):
        """.. :py:method::
            In listing page, Get all product's image, url, title, price, soldout

        :param event_id: unique key in Event, which we can associate product with event
        :param item: item of xml node
        """
        title_link = item.cssselect('div.product-name>a[title]')[0]
        title = title_link.get('title').strip()
        link = title_link.get('href')
        slug = self.extract_product_re.match(link).group(1)
        product, is_new = Product.objects.get_or_create(pk=slug)
        price_box = item.cssselect('a>div.price-boxConfig')
        is_updated = False
        if is_new:
            product.event_id = [event_id]
            img = item.cssselect('a.product-image>img')[0].get('src')
            image = ''.join( self.extract_product_img.match(img).groups() )
            product.image_urls = [image]
            product.title = title
            if price_box:
                product.price = price_box[0].cssselect('div.special-price')[0].text_content().strip().replace('$','').replace(',','')
                product.listprice = price_box[0].cssselect('div.old-price')[0].text_content().replace('original','').strip().replace('$','').replace(',','')
            else:
                product.price = item.cssselect('a.nohover')[0].text_content().strip().replace('$','').replace(',','')
            soldout = item.cssselect('a.product-image>span.sold-out')
            if soldout: product.soldout = True
            product.updated = False
            product.combine_url = 'http://www.zulily.com/p/{0}.html'.format(slug)
        else:
            if event_id not in product.event_id:
                product.event_id.append(event_id)

            soldout = item.cssselect('a.product-image>span.sold-out')
            if price_box:
                special_price = price_box[0].cssselect('div.special-price')[0].text_content().strip().replace('$','').replace(',','')
            else:
                special_price = item.cssselect('a.nohover')[0].text_content().strip().replace('$','').replace(',','')
            if product.price != special_price:
                product.price = special_price
                is_updated = True
                product.update_history.update({ 'price': datetime.utcnow() })
            if soldout and product.soldout != True:
                product.soldout = True
                is_updated = True
                product.update_history.update({ 'soldout': datetime.utcnow() })
        product.list_update_time = datetime.utcnow()
        product.save()
        common_saved.send(sender=ctx, obj_type='Product', key=slug, url=self.siteurl + '/e/' + event_id + '.html', is_new=is_new, is_updated=is_updated)
        debug_info.send(sender=DB + ".crawl_listing", url=self.siteurl + '/e/' + event_id + '.html')
        return slug

#        counter = 0
#        if is_new:
#            print 'new', self.siteurl + '/e/' + event_id + '.html', self.siteurl + '/p/' + slug + '.html'
#            counter += 1
#        if is_updated:
#            if counter != 0:
#                print 'ERROR{0}'.format(counter), self.siteurl + '/e/' + event_id + '.html', self.siteurl + '/p/' + slug + '.html'
#            else:
#                print 'update', self.siteurl + '/e/' + event_id + '.html', self.siteurl + '/p/' + slug + '.html'
#            counter += 1
#        if not is_new and not is_updated:
#            if counter != 0:
#                print 'ERROR{0}'.format(counter), self.siteurl + '/e/' + event_id + '.html', self.siteurl + '/p/' + slug + '.html'
#            else:
#                print 'NO', self.siteurl + '/e/' + event_id + '.html', self.siteurl + '/p/' + slug + '.html'


    def crawl_product(self, url, ctx='', **kwargs):
        """.. :py:method::
            Got all the product information and save into the database

        :param url: product url
        """
#        if kwargs.get('login_email'): self.net.check_signin( kwargs.get('login_email') )
#        else: self.net.check_signin()

        cont = self.net.fetch_page(url)
        if isinstance(cont, int):
            common_failed.send(sender=ctx, key='product', url=url, reason=cont)
            return
        tree = lxml.html.fromstring(cont)
        node = tree.cssselect('div.container>div#main>div#product-view')[0]
        info = node.cssselect('div#product-info')[0]
        list_info, image_urls, out_of_stocks, also_like, sizes_scarcity = [], [], [], [], []

#        summary = info.cssselect('div#product-description>div.description p:first-child')[0].text_content()
        summary = info.cssselect('div#product-description>div.description')
        description = summary[0].text_content().strip() if summary else ''
        for info in info.cssselect('div#product-description>div.description>ul>li'):
            list_info.append(info.text_content())
#        return_shipping = info.cssselect('ul#product-bullets>li')  # not work
#        returned = return_shipping[0].text_content()
#        shipping = return_shipping[1].text_content()
        returned = self.returned_re.search(cont).group(1).strip()
        m = self.shipping_re.search(cont)
        shipping = m.group(1).strip() if m else ''
        size_scarcity = info.cssselect('div.options-container-big div#product-size-dropdown>select>option[data-inventory-available]')
        for s_s in size_scarcity:
            sizes_scarcity.append( (s_s.text_content().strip(), s_s.get('data-inventory-available')) )
        for out_of_stock in info.cssselect('div#out-of-stock-notices>div.size-out-of-stock'):
            out_of_stocks.append( out_of_stock.text )

        images = node.cssselect('div#product-media>div#MagicToolboxSelectorsContainer>ul.reset>li>a>img')
        for img in images:
            picture = ''.join( self.extract_product_img.match(img.get('src')).groups() )
            image_urls.append(picture)
        also_like_items = node.cssselect('div#product-media>div#you-may-also-like>ul>li>a')
        for a_l in also_like_items:
            also_like.append( (a_l.get('title'), a_l.get('href')) )

        slug = self.extract_product_re.match(url).group(1)
        is_updated = False
        product, is_new = Product.objects.get_or_create(pk=slug)
        if description: product.summary = description
        if list_info: product.list_info = list_info
        product.returned = returned
        if shipping: product.shipping = shipping
        if sizes_scarcity: product.sizes_scarcity = sizes_scarcity
        if out_of_stocks: product.out_of_stocks = out_of_stocks
        if image_urls: product.image_urls = image_urls

        if product.updated == False:
            product.updated = True
            ready = True
        else: ready = False
        product.full_update_time = datetime.utcnow()
        product.save()
        common_saved.send(sender=ctx, obj_type='Product', key=slug, url=url, is_new=is_new, is_updated=is_updated, ready=ready)


if __name__ == '__main__':
    from optparse import OptionParser

    parser = OptionParser(usage='usage: %prog [options]')
    parser.add_option('-l', '--listing', dest='listing', help='test of list page', default=False)
    parser.add_option('-p', '--product', dest='product', help='test of product page', default=False)
    parser.add_option('-d', '--daemon', dest='daemon', help='run as a rpc server daemon', default=False)

    if len(sys.argv) == 1:
        parser.print_help()
        exit()

    options, args = parser.parse_args(sys.argv[1:])
    if options.daemon:
        server = zerorpc.Server(Server(), heartbeat=None)
        server.bind("tcp://0.0.0.0:{0}".format(options.daemon))
        server.run()
    elif options.listing:
        Server().crawl_listing(options.listing)
    elif options.product:
        Server().crawl_product(options.product)
    else:
        parser.print_help()
