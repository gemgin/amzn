# -*- coding: utf-8 -*-
"""
Tools for server to processing data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is the server part of zeroRPC module. Call by client automatically, run on many differen ec2 instances.

"""
from configs import *
from backends.matching.extractor import Extractor
from backends.matching.classifier import SklearnClassifier

import boto
from boto.s3.key import Key
from boto.s3.connection import S3Connection

import os
import re
import requests
from PIL import Image
from StringIO import StringIO

CURRDIR = os.path.dirname(__file__)

class ImageTool:
    """
    The class about images to power image data to the front-end.
    * Grab the picture from the url of other websites and uplaod it to storage server, such as S3.
    * Thumbnail the picture and uplaod it to the storage server, such as S3 .
    * Provide the picture url to the front-end after dealt wit.
    
    * To use PIL in ubuntu, several steps as followed should be done:
    # sudo apt-get install libjpeg8-dev
    # sudo ln -s /usr/lib/x86_64-linux-gnu/libjpeg.so ~/.virtualenvs/crpc/lib/
    # pip install PIL
    """
    def __init__(self, s3conn=None, bucket_name=S3_IMAGE_BUCKET):
        self.__s3conn = s3conn or S3Connection(AWS_ACCESS_KEY, AWS_SECRET_KEY)
        try:
            bucket = self.__s3conn.get_bucket(bucket_name)
        except boto.exception.S3ResponseError, e:
            if str(e).find('404 Not Found'):
                bucket = self.__s3conn.create_bucket(bucket_name)
            else:
                raise
        self.__key = Key(bucket)
        self.__image_path = []
        self.__thumbnails = []

    @property
    def image_path(self):
        return self.__image_path

    @property
    def thumbnails(self):
        return self.__thumbnails
  
    def crawl(self, image_urls=[], site='', doctype='', key='', thumb=False):
        self.__image_path = []
        print "images crawling ---> {0}.{1}.{2}\n".format(site, doctype, key)

        for image_url in image_urls:
            path, filename = os.path.split(image_url)
            image_name = '%s_%s' % (image_urls.index(image_url), filename)
            s3key= os.path.join(site, doctype, key, image_name)
            self.__key.key = s3key

            if self.__key.exists():
                s3_url = '{0}/{1}'.format(S3_IMAGE_URL, self.__key.key)
                print 'grab existing image from s3 ---> {0}\n'.format(s3_url)
                self.__image_path.append(s3_url)
                continue

            image_content = self.download(image_url)
            s3_url = self.upload2s3(StringIO(image_content), self.__key.key)
            if s3_url:
                self.__image_path.append(s3_url)
            else:
                self.__image_path = []
                break

        if thumb:
            thumbnail_size = self.thumbnail(doctype, StringIO(image_content), key)
            self.__thumbnails.append(thumbnail_size)
            pass

    def download(self, image_url):
        print 'downloading image ---> {0}'.format(image_url)
        r = requests.get(image_url)
        r.raise_for_status()
        return r.content

    def upload2s3(self, image, key):
        print 'upload2s3 ---> {0}'.format(key)
        self.__key.key = key
        self.__key.set_contents_from_file(image)
        self.__key.make_public()

        image_url = '{0}/{1}'.format(S3_IMAGE_URL, self.__key.key)
        print 'generate s3 image url ---> {0}\n'.format(image_url)
        return image_url

    def thumbnail(self, doctype, image, image_name):
        thumb_picts = {}
        im = Image.open(image)
        for size in IMAGE_SIZE[doctype.capitalize()]:
            width = size.get('width')
            height = size.get('height')
            fluid = size.get('fluid')

            width_rate = 1.0 * width / im.size[0]
            height_rate = 1.0 * height / im.size[1]
            rate = max(width_rate, height_rate)

            print 'thumbnail %s with size width: %s, heigh: %s' % (im.size, width, height)           
            pict = self.resize_by_rate(rate, im) \
                    if fluid == True or width == 0 or height == 0 \
                        else self.resize_by_crop(width=width, height=height, im=im)

            thumbnail_url = self.upload2s3(pict, '%sx%s_%s' % (width, height, image_name))
            if thumbnail_url:
                thumb_picts['%sx%s' % (width, height)] = thumbnail_url

        return thumb_picts

    def resize(self, box, im):
        thumbnail = im.resize(box)
        tempfile = StringIO()
        thumbnail.save(tempfile, im.format)
        tempfile.seek(0)
        return tempfile

    def resize_by_rate(self, rate, im):
        width, height = im.size
        size = tuple([int(i * rate) for i in im.size])
        return self.resize(size, im)

    def resize_by_crop(self, width=0, height=0, im=None):
        width_rate = 1.0 * width / im.size[0]
        height_rate = 1.0 * height / im.size[1]
        rate = max(width_rate, height_rate)

        (im.size[0]*rate, im.size[1]*rate)
        thumnail = im.resize( tuple( [int(i*rate) for i in im.size] ) )
        left = (thumnail.size[0] - width) / 2  if (thumnail.size[0] - width) > 0 else 0
        upper = (thumnail.size[1] - height) / 2 if (thumnail.size[1] - height) > 0 else 0
        right = left + width
        lower = upper + height
        box = (left, upper, right, lower)
        region = thumnail.crop(box)

        tempfile = StringIO()
        region.save(tempfile, im.format)
        tempfile.seek(0)
        return tempfile


def parse_price(price):
    amount = 0
    pattern = re.compile(r'^\$?(\d+(\.\d+|\d*))$')
    match = pattern.search(price)
    if match:
        amount_list = (price_match.groups()[0]).split(',')
        amount = float(''.join(amount_list))
    return amount

    # $1,200.00
    # lowest_discount = 1-0.8
    # highest_discount = 1-0.4

class Propagator(object):
    def __init__(self, site, event_id):
        print 'init propogate %s event %s' % (site, event_id)
        m = __import__('crawlers.{0}.models'.format(site), fromlist=['Event'])
        self.site = site
        self.event = m.Event.objects(event_id=event_id).first()
        self.extractor = Extractor()
        self.classifier = SklearnClassifier()
        self.classifier.load_from_database()

    def propagate(self):
        """
        * Tag, Dept extraction and propagation
        * Event brand propagation
        * Event (lowest, highest) discount, (lowest, highest) price propagation
        * Event & Product begin_date, end_date
        * Event soldout
        """
        if not self.event:
            return self.event

        event_brands = set()
        tags = set()
        depts = set()
        lowest_price = 0
        highest_price = 0
        lowest_discount = 0
        highest_discount = 0
        events_begin = self.event.events_begin if hasattr(self.event, 'events_begin') else ''
        events_end = self.event.events_end if hasattr(self.event, 'events_end') else ''
        soldout = True

        m = __import__('crawlers.{0}.models'.format(self.site), fromlist=['Product'])
        products = m.Product.objects(event_id=self.event.event_id)
        print 'start to propogate %s event %s' % (self.site, self.event.event_id)

        if not len(products):
            return self.event

        for product in products:
            print 'start to propogate from  %s product %s' % (self.site, product.key)

            # Tag, Dept extraction and propagation
            source_infos = product.list_info or []
            source_infos.append(product.title or '')
            source_infos.append(product.summary or '')
            source_infos.append(product.short_desc or '')
            source_infos.extend(product.tagline or [])

            product.favbuy_tag = self.extractor.extract('\n'.join(source_infos).encode('utf-8'))
            source_infos.extend(product.dept)
            product.favbuy_dept = list(self.classifier.classify( '\n'.join(source_infos) ))

            product.tag_complete = True
            product.dept_complete = True

            tags = tags.union(product.favbuy_tag)
            depts = depts.union([ product.favbuy_dept[0] ])

            # Event brand propagation
            if hasattr(product, 'favbuy_brand') and product.favbuy_brand:
                event_brands.add(product.favbuy_brand)

            # Event & Product begin_date, end_date
            if not hasattr(product, 'products_begin') \
                or not product.products_begin:
                    product.products_begin = events_begin
            if not hasattr(product, 'products_end') \
                or not product.products_end:
                    product.products_end = events_end

            if not events_begin and product.products_begin:
                events_begin = product.products_begin
            if not events_end and product.products_end:
                events_end = product.products_end

            if events_begin and product.products_begin:
                events_begin = min(events_begin, product.products_begin)
            if events_end and product.products_end:
                events_end = max(events_end, product.products_end)

            # (lowest, highest) discount, (lowest, highest) price propagation
            # TODO the regex not correct
            pattern = re.compile(r'^\$?(\d+(\.\d+|\d*))$')
            price_match = pattern.search(product.price)
            listprice_match = pattern.search(product.listprice)
            
            price = float(price_match.groups()[0]) if price_match else 0
            listprice = float(listprice_match.groups()[0]) if listprice_match else 0
            product.favbuy_price = str(price)
            product.favbuy_listprice = str(listprice)

            highest_price = max(price, highest_price) if highest_price else price
            lowest_price = (min(price, lowest_price) or lowest_price) if lowest_price else price

            discount = 1.0 * price / listprice if listprice else 0
            lowest_discount = max(discount, highest_discount)
            highest_discount = min(discount, lowest_discount) or discount

            # soldout
            if soldout and (hasattr(product, 'soldout') and not product.soldout):
                soldout = False

            product.save()

        self.event.favbuy_brand = list(event_brands)
        self.event.brand_complete = True
        
        self.event.favbuy_tag = list(tags)
        if self.event.dept:
            depts.add(self.classifier.classify('\n'.join(self.event.dept))[0])
        self.event.favbuy_dept = list(depts)
        self.event.lowest_price = str(lowest_price)
        self.event.highest_price = str(highest_price)
        self.event.lowest_discount = str(1.0 - lowest_discount)
        self.event.highest_discount = str(1.0 - highest_discount)
        self.event.events_begin = events_begin
        self.event.events_end = events_end
        self.event.soldout = soldout
        self.event.propagation_complete = True
        self.event.save()

        return self.event.propagation_complete


def test_image():
    url1 = 'http://cdn1.giltcdn.com/images/share/uploads/0000/0001/7209/172096646/orig.jpg'
    url2 = 'http://cdn1.giltcdn.com/images/share/uploads/0000/0001/7212/172129909/orig.jpg'
    url3 = 'http://cdn1.giltcdn.com/images/share/uploads/0000/0001/7212/172126886/orig.jpg'
    url4 = 'http://cdn1.giltcdn.com/images/share/uploads/0000/0001/7215/172150826/orig.jpg'
    it = ImageTool()
    it.crawl([url1, url2], 'gilt', 'event', 'abc123', thumb=False)
    print 'image path ---> {0}'.format(it.image_path)
    print 'thumbnails ---> {0}\n'.format(it.thumbnails)
    it.crawl([url3, url4], 'gilt', 'product', '123456', thumb=False)
    print 'image path ---> {0}'.format(it.image_path)
    print 'thumbnails ---> {0}\n'.format(it.thumbnails)

def test_propagate(site, event_id):
    p = Propagator(site, event_id)
    p.propogate()


if __name__ == '__main__':
    pass

    import time, sys
    start = time.time()
    if len(sys.argv) > 1:
        if sys.argv[1] == '-i':
            f = test_image
            f()
        elif sys.argv[1] == '-p':
            f = test_propagate
            f()
    print time.time() - start, 's'
