# -*- coding: utf-8 -*-
from backends.matching.mechanic_classifier import classify_product_department
from powers.configs import BRAND_EXTRACT
from backends.matching.extractor import Extractor
from powers.brandapi import Extracter
from powers.pipelines import parse_price, unescape
import re
from powers.titlecase import titlecase
from datetime import datetime

from helpers.log import getlogger
logger = getlogger('pipelines', filename='/tmp/deals.log')

EXTRACTER = Extracter()
EXTRACTOR = Extractor()


class ProductPipeline(object):
    def __init__(self, site, product):
        self.site = site
        self.product = product

    def extract_text(self):
        """
        Do some text data cleaning and standardized processing on the product,
        such as titlecase, html tag remove and so on.
        """
        product = self.product

        # This filter changes all title words to Title Caps,
        # and attempts to be clever about uncapitalizing SMALL words like a/an/the in the input.
        if product.title:
            product.title = titlecase(re.sub("&#?\w+;", " ", product.title))
        
        # Clean the html tag.
        pattern = r'<[^>]*>'

        if product.list_info:
            str_info = '\n\n\n'.join(product.list_info)
            str_info = unescape(str_info)
            product.list_info = re.sub(pattern, ' ', str_info).split('\n\n\n')

        if product.shipping:
            product.shipping = re.sub(pattern, ' ',  product.shipping)
            product.shipping = unescape(product.shipping)

        if product.returned:
            product.returned = re.sub(pattern, ' ', product.returned)
            product.returned = unescape(product.returned)

    def extract_brand(self):
        site = self.site
        product = self.product

        crawled_brand = product.brand or ''
        brand = ProductPipeline.EXTRACTER.extract(crawled_brand)

        if not brand:
            brand = ProductPipeline.EXTRACTER.extract(product.title)
            # For Add Brand should not be extract from the title
            if brand in BRAND_EXTRACT['not_title']:
                brand = None

        if brand:
            if brand != product.favbuy_brand:
                product.favbuy_brand = brand
                product.brand_complete=True
                product.update_history['favbuy_brand'] = datetime.utcnow()
                logger.info('product brand extracted -> {0}.{1}'.format(site, product.key))
                return product.favbuy_brand
        else:
            product.update(set__brand_complete=False)
            logger.warning('product brand extract failed -> {0}.{1} {2}'.format(site, product.key, crawled_brand.encode('utf-8')))

        return

    def extract_tag(self, text_list):
        site = self.site
        product = self.product

        favbuy_tag = ProductPipeline.EXTRACTOR.extract( '\n'.join(text_list).encode('utf-8') )
        product.tag_complete = bool(favbuy_tag)

        if product.tag_complete:
            if favbuy_tag != product.favbuy_tag:
                product.favbuy_tag = favbuy_tag
                product.update_history['favbuy_tag'] = datetime.utcnow()
                logger.info('product tag extracted -> {0}.{1} {2}'.format(site, product.key, product.favbuy_tag))
                return product.favbuy_tag
        else:
            logger.warning('product tag extracted failed -> {0}.{1}'.format(site, product.key))

        return

    def extract_dept(self):
        site = self.site
        product = self.product

        favbuy_dept = classify_product_department(site, product)

        if favbuy_dept and favbuy_dept != product.favbuy_dept:
            product.favbuy_dept = favbuy_dept
            product.update_history['favbuy_dept'] = datetime.utcnow()
            product.dept_complete = True
            logger.info(u'product dept extracted -> {0}.{1} {2}'.format(site, product.key, product.favbuy_dept))
            return product.favbuy_dept
        else:
            logger.error(u'product dept extract failed -> {0}.{1}'.format(site, product.key))

        return

    def extract_price(self):
        product = self.product

        favbuy_price = parse_price(product.price)
        if favbuy_price and str(favbuy_price) != product.favbuy_price:
            product.favbuy_price = str(favbuy_price)
            product.update_history['favbuy_price'] = datetime.utcnow()

        listprice = parse_price(product.listprice)
        if listprice and str(listprice) != product.favbuy_listprice:
            product.favbuy_listprice = str(listprice)
            product.update_history['favbuy_listprice'] = datetime.utcnow()
        
        return favbuy_price or listprice

    def clean(self):
        product = self.product

        print 'start to clean deal product -> %s.%s' % (self.site, product.key)

        text_list = []
        text_list.append(product.title or u'')
        text_list.extend(product.list_info or [])
        text_list.append(product.summary or u'')
        text_list.append(product.short_desc or u'')
        text_list.extend(product.tagline or [])

        self.extract_text()
        self.extract_brand()
        self.extract_tag(text_list)
        self.extract_dept()
        self.extract_price()

        return True


ProductPipeline.EXTRACTER = EXTRACTER
ProductPipeline.EXTRACTOR = EXTRACTOR