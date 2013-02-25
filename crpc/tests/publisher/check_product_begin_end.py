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
    print 'begin to query products from mastiff'
    products = db_mastiff.product.find({}, fields=['site_key', 'products_begin', 'products_end'])
    for product in products:
        try:
            site, key = product['site_key'].split('_', 1)
        except Exception as e:
            print e, product.get('site_key')
            continue

        if product.get('starts_at') is None and product.get('ends_at') is None:
            continue
        yield {
            'site': site,
            'key': key,
            'products_begin': product.get('starts_at'),
            'products_end': product.get('ends_at')
        }


def check(site, key, products_begin, products_end):
    print 'begin to check ', site, key

    try:
        db = db_pool_crpc[site]
    except KeyError:
        # It's mastiff's data error, so return true to ignore the error.
        return True

    try:
        prd = db.product.find({'_id': key})[0]
    except IndexError:
        return False

    crpc_prd_begin = prd.get('products_begin')
    crpc_prd_end = prd.get('products_end')

    if prd.get['event_id']: # category
        for event_id in prd['event_id']:
            event = db.event.find({'event_id': event_id})[0]

            if not event['product_ids'] or key not in event['product_ids']: # current product
                continue
            
            if event['events_begin']:
                if not crpc_prd_begin or event['events_begin'] <  crpc_prd_begin:
                    crpc_prd_begin = event['events_begin']

            if event['events_end']:
                if not crpc_prd_end or event['events_end'] >  crpc_prd_end:
                    crpc_prd_end = event['events_end']

    if (not products_end and crpc_prd_end) or \
        (products_end and crpc_prd_end and products_end != crpc_prd_end): # not published or publish not right
        return False

    if (not products_begin and crpc_prd_begin) or \
        (products_begin and crpc_prd_begin and products_begin != crpc_prd_begin):
        return False

    return True


def main():
    for site in picked_crawlers:
        db = conn[site]
        if site not in db_pool_crpc:
            db_pool_crpc[site] = db

    with open(log_path, 'w') as f:
        count = 0
        for mastiff_product in spout_mastiff_products():
            if not check(**mastiff_product):
                count += 1
                f.write(
                    '%s\n%s\n%s\n%s\n\n' % (
                        mastiff_product['site'],
                        mastiff_product['key'],
                        mastiff_product.get('products_begin'),
                        mastiff_product.get('products_end')
                    )
                )
        f.write('Total error: %s' % count)

def check_propagation():
    for site in picked_crawlers:
        col = conn[site].collection_names()
        if 'event' in col:
            prds = conn[site].product.find({}, fields=['event_id', 'products_begin', 'products_end'])
            for prd in prds:
                for event_id in prd['event_id']:
                    ev = conn[site].event.find({'event_id': event_id}, fields=['events_begin', 'events_end'])[0]
                    if ev['events_begin'] > ev['events_end']: # event off sale then on again
                        if prd['products_end'] < ev['events_end']:
                            print '{0} product begin: {1}; product end: {2}'.format(site, prd['products_begin'], prd['products_end'])
                            print '{0} event begin: {1}, event end: {2}'.format(site, ev['events_begin'], ev['events_end'])
                    elif 'products_begin' not in prd:
                        if 'events_begin' in ev:
                            print '{0} event_id: {1}, event begin: {2}, product_id: {3}'.format(site, event_id, ev['events_begin'], prd['_id'])
                    elif 'products_end' not in prd:
                        if 'events_end' in ev:
                            print '{0} event_id: {1}, event end: {2}, product_id: {3}'.format(site, event_id, ev['events_end'], prd['_id'])
                    else:
                        if prd['products_begin'] <= ev['events_begin'] and prd['products_end'] >= ev['events_end']:
                            pass
                        else:
                            print '{0} product begin: {1}; product end: {2}'.format(site, prd['products_begin'], prd['products_end'])
                            print '{0} event begin: {1}, event end: {2}'.format(site, ev['events_begin'], ev['events_end'])


if __name__ == '__main__':
    import sys 
    from optparse import OptionParser

    parser = OptionParser(usage='usage: %prog [options]')
    parser.add_option('-c', '--check', dest='check', action='store_true', help='check products begin end', default=False)
    parser.add_option('-s', '--sync', dest='sync', action='store_true', help='check whether mastiff and crpc products begin end sync', default=False)

    if len(sys.argv) == 1:
        parser.print_help()
        exit()

    options, args = parser.parse_args(sys.argv[1:])
    if options.check:
        check_propagation()
    elif options.sync:
        main()
    elif 'check' in args:
        check_propagation()
    elif 'sync' in args:
        main()
    else:
        parser.print_help()

