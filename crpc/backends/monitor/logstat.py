#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    spawn one listener to listen crawlers' signal -- pre_general_update, post_general_update
"""
from crawlers.common.events import *
from crawlers.common.stash import *

from helpers.log import getlogger
import traceback

from backends.monitor.models import Task, Fail, fail
from datetime import datetime, timedelta
from gevent.event import Event
from powers.routine import *

logger = getlogger("crawlerlog")

def get_or_create_task(ctx):
    t = Task.objects(ctx=ctx).first()
    if not t:
        t = Task(ctx=ctx)
        t.site, t.method, dummy = ctx.split('.')
        t.started_at = datetime.utcnow()
        t.save()
    else:
        t.update(set__status=Task.RUNNING, set__updated_at=datetime.utcnow())
    return t

@pre_general_update.bind
def stat_pre_general_update(sender, **kwargs):
    try:
        site, method, dummy = sender.split('.')
        t = get_or_create_task(sender)
        t.save()
    except Exception as e:
        logger.exception(e.message)
        fail(site, method, kwargs.get('key',''), kwargs.get('url',''), traceback.format_exc())
        

@post_general_update.bind
def stat_post_general_update(sender, **kwargs):
    complete = kwargs.get('complete', False)
    reason = repr(kwargs.get('reason', 'undefined'))
    key = kwargs.get('key','')
    url = kwargs.get('url','')
    try:
        site, method, dummy = sender.split('.')
        t = get_or_create_task(sender)
        t.status = Task.FINISHED if complete else Task.FAILED
        if not complete:
            t.fails.append( fail(site, method, key, url, reason) )
        t.save()
    except Exception as e:
        logger.exception(e.message)
        fail(site, method, key, url, traceback.format_exc())


@common_saved.bind
def stat_save(sender, **kwargs):
    @exclusive_lock(sender.rsplit('.', 1)[0])
    def lock_stat_save(sender, is_new, is_updated):
        try:
            site, method, dummy = sender.split('.')
            t = get_or_create_task(sender)

            if is_new:
                t.num_new += 1
            if is_updated:
                t.num_update += 1
            t.num_finish += 1

            t.update(set__num_new=t.num_new, set__num_update=t.num_update, set__num_finish=t.num_finish)
        except Exception as e:
            logger.exception(e.message)
            t.update(push__fails=fail(site, method, key, url, traceback.format_exc()), inc__num_fails=1)

    logger.debug('{0} -> {1}'.format(sender,kwargs.items()))
    key = kwargs.get('key','')
    url = kwargs.get('url','')
    is_new = kwargs.get('is_new', False)
    is_updated = kwargs.get('is_updated', False)

    lock_stat_save(sender, is_new, is_updated)


@common_saved.bind
def process_image(sender, **kwargs):
    logger.debug('process_image.listening:{0} -> {1}'.format(sender,kwargs.items()))
    key = kwargs.get('key', None)
    ready = kwargs.get('ready', None)   # Event or Product
    site, method, dummy = sender.split('.')
    
    if site and key and ready in ('Event', 'Product'):
        logger.info('%s %s %s queries for crawling images' % (site, ready, key))
        from powers.routine import crawl_images
        crawl_images(site, ready, key)
    else:
        logger.info('%s failed to start crawling image', sender)
        # TODO send a process_message error signal.

@common_failed.bind
def stat_failed(sender, **kwargs):
    logger.error('{0} -> {1}'.format(sender,kwargs.items()))
    key  = kwargs.get('key', '')
    url  = kwargs.get('url', '')
    reason = repr(kwargs.get('reason', 'undefined'))

    try:
        site, method, dummy = sender.split('.')
        t = get_or_create_task(sender)
        t.update(push__fails=fail(site, method, key, url, reason), inc__num_fails=1)
    except Exception as e:
        logger.exception(e.message)
        t.update(push__fails=fail(site, method, key, url, traceback.format_exc()), inc__num_fails=1)

if __name__ == '__main__':
    print 'logstat'
