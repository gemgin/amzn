#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: bishop Liu <miracle (at) gmail.com>

"""
UTC 09:00 = EST 4AM = PST 1AM
          = EDT 5AM = PDT 2AM

"""
from datetime import datetime, timedelta
from crawlers.common.stash import picked_crawlers
from backends.monitor.models import ProductReport, EventReport

def get_site_module(site):
    if not hasattr(get_site_module, 'mod'):
        setattr(get_site_module, 'mod', {})

    if not get_site_module.mod:
        for crawler in picked_crawlers:
            module = __import__('crawlers.' + crawler + '.models', fromlist=['Category', 'Event', 'Product'])
    return get_site_module.mod[site]


def report_product(site, today_date, module):
    product_num = module.Product.objects(create_time__lt=today_date, create_time__gte=today_date-timedelta(days=1)).count()
    published_num = module.Product.objects(create_time__lt=today_date, create_time__gte=today_date-timedelta(days=1), publish_time__exists=True).count()

    product = ProductReport.objects(today_date=today_date, site=site).first()
    if not product: product = ProductReport(today_date=today_date, site=site)
    if product_num != published_num:
        no_image_url = 0
        no_image_path = 0
        no_dept = 0
        event_not_ready = 0
        unknown = 0
        for prd in module.Product.objects(create_time__lt=today_date, create_time__gte=today_date-timedelta(days=1), publish_time__exists=False):
            if not prd.image_urls:
                no_image_url += 1
            elif not prd.image_path:
                no_image_path += 1
            elif not prd.dept_complete:
                no_dept += 1
            elif prd.event_type and \
                [ev for ev in [module.Event.objects(event_id=evi).first() for evi in prd.event_id] if ev.publish_time]:
                    event_not_ready += 1
            else:
                unknown += 1
        product.no_image_url_num = no_image_url
        product.no_image_path_num = no_image_path
        product.no_dept_num = no_dept
        product.event_not_ready = event_not_ready
        product.unknown = unknown

    product.site = site
    product.product_num = product_num
    product.published_num = published_num
    product.save()


def report_event(site, today_date, module):
    event_num = module.Event.objects(create_time__lt=today_date, create_time__gte=today_date-timedelta(days=1)).count()
    published_num = module.Event.objects(create_time__lt=today_date, create_time__gte=today_date-timedelta(days=1), publish_time__exists=True).count()

    event = EventReport.objects(today_date=today_date, site=site).first()
    if not event: event = EventReport(today_date=today_date, site=site)
    if event_num != published_num:
        not_leaf = 0
        upcoming_no_image_url = 0
        upcoming_no_image_path = 0
        onsale_no_product = 0
        onsale_no_image_url = 0
        onsale_no_image_path = 0
        onsale_propagation_not_complete = 0
        unknown = 0
        for ev in module.Event.objects(create_time__lt=today_date, create_time__gte=today_date-timedelta(days=1), publish_time__exists=False):
            if ev.is_leaf == False:
                not_leaf += 1
            elif ev.events_begin and ev.events_begin >= today_date:
                if not ev.image_urls:
                    upcoming_no_image_url += 1
                elif not ev.image_path:
                    upcoming_no_image_path += 1
            elif module.Product.objects(event_id=ev.event_id).count() == 0:
                onsale_no_product += 1
            elif not ev.image_urls:
                onsale_no_image_url += 1
            elif not ev.image_path:
                onsale_no_image_path += 1
            elif not ev.propagation_complete:
                onsale_propagation_not_complete += 1
            else:
                unknown += 1
        event.not_leaf_num = not_leaf
        event.upcoming_no_image_url_num = upcoming_no_image_url
        event.upcoming_no_image_path_num = upcoming_no_image_path
        event.onsale_no_product_num = onsale_no_product
        event.onsale_no_image_url_num = onsale_no_image_url
        event.onsale_no_image_path_num = onsale_no_image_path
        event.onsale_propagation_not_complete = onsale_propagation_not_complete
        event.unknown = unknown

    event.site = site
    event.event_num = event_num
    event.published_num = published_num
    event.save()


def wink(_thedate=datetime.utcnow()):
    _utcnow = datetime.utcnow()
    if _utcnow.date == _thedate.date and _thedate.hour < 9: # today
        return

    the_date = _thedate.replace(microsecond=0, second=0, minute=0, hour=9)
    for site in picked_crawlers:
        prd = ProductReport.objects(today_date=the_date, site=site).first()
        if not prd:
            module = get_site_module(site)
            report_product(site, the_date, module)
            if hasattr(module, 'Event'):
                report_event(site, the_date, module)

if __name__ == '__main__':
    wink()
