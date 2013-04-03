#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: bishop Liu <miracle (at) gmail.com>

import re
import requests
import lxml.html
from datetime import datetime

from models import *
from crawlers.common.stash import *

req = requests.Session(prefetch=True, timeout=30, config=config, headers=headers)

class Server(object):
    def __init__(self):
        self.siteurl = 'http://www.bloomingdales.com'

    def fetch_page(self, url):
        ret = req.get(url)
        if ret.ok:
            return ret.content
        else:
            return ret.status_code

    def crawl_category(self, ctx='', **kwargs):
        ret = self.fetch_page(self.siteurl)
        tree = lxml.html.fromstring(ret)
        for d in tree.cssselect('div#bl_nav_top_menu div[class^="bl_nav_top_section_navigation_options"]'):
            link = d.cssselect('a.white')[0].get('href')
            dept = d.cssselect('a img')[0].get('alt')
            if dept.lower() == 'designers':
                self.crawl_designers_category(dept, link)
                continue
            self.crawl_to_leaf_directory(self, dept, url)

    def crawl_designers_category(self, dept, url):
        ret = self.fetch_page(url)
        base_url = re.compile('blm_insecureServer.put\("(.+)"\);').search(ret).group(1)
        pattern_url = re.compile('blm_nav_linkURL.put\("(.+)"\);').search(ret).group(1)
        for sub_dept in re.findall('blm_nav_items.put\({topCategory : "(.+?)",', ret):
            link = '{0}{1}'.format(base_url, pattern_url.replace('designerCat2', sub_dept).replace('designerCat', sub_dept))
            self.crawl_designer_category(dept, sub_dept, link)

    def crawl_designer_category(self, dept, sub_dept, url):
        ret = self.fetch_page(url)
        tree = lxml.html.fromstring(ret)
        for designer in tree.cssselect('div#se_localContentContainer div.se_designerColumn li.se_designerColumn a'):
            link = designer.get('href')
            link = link if link.startswith('http') else self.siteurl + link
            brand = designer.text_content().strip()

            is_new = is_updated = False
            category = Category.objects(key=brand).first()
            if not category:
                is_new = True
                categroy = Category(key=brand)
                category.is_leaf = True
                category.cats = [dept, sub_dept, brand]
            category.combine_url = link + '&resultsPerPage=96'
            category.update_time = datetime.utcnow()
            category.save()
            common_saved.send(sender=ctx, obj_type='Category', key=brand, url=link, is_new=is_new, is_updated=is_updated)

    def crawl_to_leaf_cateogory(self, dept, url):
        ret = self.fetch_page(url)
        tree = lxml.html.fromstring(ret)
        for nav in tree.cssselect('div#gn_left_nav_container div.gn_left_nav_section'):
            sub_dep = nav.cssselect('div.gn_left_nav_top')[0].text_content().strip()


    def crawl_listing(self, url, ctx='', **kwargs):
        pass

    def crawl_product(self, url, ctx='', **kwargs):
        pass

if __name__ == '__main__':
    ss = Server()
    ss.crawl_category()
