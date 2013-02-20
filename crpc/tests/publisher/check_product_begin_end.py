#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: ethan

import pymongo
import collections
from settings import MONGODB_HOST, MASTIFF_HOST
from crawlers.common.stash import picked_crawlers

log_path = '/tmp/check_prod_begin_end.log'

conn = pymongo.Connection(MONGODB_HOST)
conn_m = pymongo.Connection(MASTIFF_HOST.split(':')[1].replace('//', ''))
db_mastiff = conn_m['mastiff']
db_pool_crpc = {}


def spout_mastiff_products():
    products = db_mastiff.product.find({}, fields=['site_key', 'products_begin', 'products_end'])
    for product in products:
        try:
            site, key = product['site_key'].split('_')
        except ValueError:
            print product['site_key']
        yield {
            'site': site,
            'key': key,
            'products_begin': product.get('products_begin'),
            'products_end': product.get('products_end')
        }


def check(site, key, products_begin, products_end):
    db = db_pool_crpc[site]
    product = db.product.find({'_id': key})[0]
    crpc_products_begin = product.get('products_begin')
    crpc_products_end = product.get('products_end')

    if product.get('event_id'):
        for event_id in product.get('event_id'):
            event = db.event.find({'event_id': event_id})[0]
            if event.get('events_begin'):

                if not crpc_products_begin \
                    or event.get('events_begin') <  crpc_products_begin:
                        crpc_products_begin = event.get('events_begin')

                if not crpc_products_end \
                    or event.get('events_end') >  crpc_products_end:
                        crpc_products_end = event.get('events_end')

    if (not products_begin and crpc_products_begin) \
        or (products_begin > crpc_products_begin ):
            return False

    if (not products_end and crpc_products_end) \
        or (products_end < crpc_products_end ):
            return False

    return True


def main():
    with open(log_path, 'w') as f:
        for mastiff_product in spout_mastiff_products():
            if not check(**mastiff_product):
                f.write(
                    '%s\n%s\n%s\n%s\n\n' % (
                        mastiff_product['site'],
                        mastiff_product['key'],
                        mastiff_product.get('products_begin'),
                        mastiff_product.get('products_end')
                    )
                )


if __name__ == '__main__':
    for site in picked_crawlers:
        db = conn[site]
        if site not in db_pool_crpc:
            db_pool_crpc[site] = db

    main()