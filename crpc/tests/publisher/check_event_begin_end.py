#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: bishop Liu <miracle (at) gmail.com>

import pymongo
import collections
from settings import MONGODB_HOST, MASTIFF_HOST
from crawlers.common.stash import picked_crawlers

conn = pymongo.Connection(MONGODB_HOST)
conn_m = pymongo.Connection(MASTIFF_HOST.split(':')[1].replace('//', ''))


def check_events_begin_end(data=collections.defaultdict(dict)):
    for site in picked_crawlers:
        col = conn[site].collection_names()
        if 'event' in col:
            if site not in data: data[site] = {}
            ev = conn[site].event.find({}, fields=['event_id', 'events_begin', 'events_end'])
            for e in ev:
                begin = "" if 'events_begin' not in e else e['events_begin']
                end = "" if 'events_end' not in e else e['events_end']
                data[site][e['event_id']] = [begin, end]

    ev = conn_m.mastiff.event.find({}, fields=['site_key', 'starts_at', 'ends_at'])
    for e in ev:
        try:
            site, key = e['site_key'].split('_')
        except KeyError:
            print e
            continue
        
        if data[site][key][0] and data[site][key][0] != e['starts_at']: # publish will add now as default
            print 'events_begin error: {0}, {1}'.format(site, key)
        if data[site][key][1] and data[site][key][1] != e['ends_at']: # events off sale then on again
            print 'events_end error: {0}, {1}'.format(site, key)

def sync_time_mastiff_to_mongodb(data=collections.defaultdict(dict)):
    ev = conn_m.mastiff.event.find({}, fields=['site_key', 'starts_at', 'ends_at'])
    for e in ev:
        try:
            site, key = e['site_key'].split('_')
        except KeyError:
            print e
            continue

        if site not in data: data[site] = {}
        data[site][key] = [e['starts_at'], e['ends_at']]

    for site in picked_crawlers:
        col = conn[site].collection_names()
        if 'event' in col:
            ev = conn[site].event.find({}, fields=['event_id', 'events_begin', 'events_end'])
            for e in ev:
                if e['event_id'] not in data[site]: continue
                conn[site].event.update({'event_id': e['event_id']}, {'$set': {'events_begin': data[site][e['event_id']][0], 'events_end': data[site][e['event_id']][1]}}, upsert=False, multi=False)
#               # These 3 lines will clear this record to only events_id, events_begin, events_end 3 fields
#                e['events_begin'] = data[site][e['event_id']][0]
#                e['events_end'] = data[site][e['event_id']][1]
#                conn[site].event.save(e)


if __name__ == '__main__':
    import sys
    from optparse import OptionParser

    parser = OptionParser(usage='usage: %prog [options]')
    parser.add_option('-c', '--check', dest='check', action='store_true', help='check events begin end', default=False)
    parser.add_option('-s', '--sync', dest='sync', action='store_true', help='sync events begin end from mastiff to mongodb', default=False)

    if len(sys.argv) == 1:
        parser.print_help()
        exit()

    options, args = parser.parse_args(sys.argv[1:])
    if options.check:
        check_events_begin_end()
    elif options.sync:
        sync_time_mastiff_to_mongodb()
    elif 'check' in args:
        check_events_begin_end()
    elif 'sync' in args:
        sync_time_mastiff_to_mongodb()
    else:
        parser.print_help()
