# -*- coding: utf-8 -*-
from gevent import monkey; monkey.patch_all()
from settings import POWER_PORT

import zerorpc
from gevent.coros import Semaphore

from tools import ImageTool
from brandapi import Extracter
from powers.events import *
from powers.binds import *

#process_image_lock = Semaphore(1)

class PowerServer(object):
    def process_image(self, args=(), kwargs={}):
        print 'accept', args, kwargs
        return self._process_image(*args, **kwargs)
    
    def _process_image(self, site, image_urls, ctx, doctype,  **kwargs):
        """ doctype is either ``event`` or ``product`` """
        key = kwargs.get('event_id', kwargs.get('key'))
        m = __import__("crawlers."+site+'.models', fromlist=['Event', 'Product'])
        image_tool = ImageTool()
        image_path = image_tool.crawl(image_urls, site, key)
        if len(image_path):

            if doctype == 'event':
                m.Event.objects(event_id=key).update(set__image_path=image_path)
            elif doctype == 'product':
                m.Product.objects(key=key).update(set__image_path=image_path)
            image_crawled.send(sender=ctx, site=site, key=key, model=doctype.capitalize(), num=len(image_path))
        else:
            # TODO image_crawled_failed or need try except
            pass

    def extract_brand(self, args=(), kwargs={}):
        """
        @param: kwargs contains several keys as followed:
        * site
        * key
        * title
        * brand
        * doctype
        * combine_url
        """
        site = kwargs.get('site', '')
        doctype = kwargs.get('doctype', '')
        key = kwargs.get('key', '')
        crawled_brand = kwargs.get('brand', '')

        #TO REMOVE
        import time
        print site,' ' + doctype + ' ',  key + ' ', 'brand-<'+crawled_brand+'>  ',  'title-<'+ kwargs.get('title', ' ') +'>'+ ':'
        
        m = __import__('crawlers.'+site+'.models', fromlist=[doctype])
        extracter = Extracter()
        brand = extracter.extract(crawled_brand)

        if brand:
            if doctype == 'Event':
                m.Event.objects(event_id=key).update(set__favbuy_brand=brand, set__brand_complete=True)
            elif doctype == 'Product':
                m.Product.objects(key=key).update(set__favbuy_brand=brand, set__brand_complete=True)

            kwargs['favbuy_brand'] = brand
            brand_extracted.send('%s_%s_%s_brand' % (site, doctype, key), **kwargs)
        else:
            if doctype == 'Event':
                m.Event.objects(event_id=key).update(set__brand_complete=False)
            elif doctype == 'Product':
                m.Product.objects(key=key).update(set__brand_complete=False)
            
            brand_extracted_failed.send('%s_%s_%s_brand' % (site, doctype, key), **kwargs)


def test():
    from crawlers.gilt.models import Event
    event = Event.objects().first()
    image_urls = event.image_urls
    site='gilt'
    ctx = site+event.event_id
    doctype = 'event'
    APIServer().process_image(site, image_urls, ctx, doctype, event_id=event.event_id)

if __name__ == '__main__':
    zs = zerorpc.Server(PowerServer(), pool_size=50) 
    zs.bind("tcp://0.0.0.0:{0}".format(POWER_PORT))
    zs.run()

