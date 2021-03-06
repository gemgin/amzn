#!/usr/bin/env python
# -*- coding: utf-8 -*-
from hashlib import md5
from gevent import monkey; monkey.patch_all()
import tornado.ioloop
import tornado.web
import tornado.httpserver
import tornado.autoreload
from tornado.escape import url_unescape

import jinja2 

from webassets import Environment as AssetsEnvironment, loaders
from webassets.ext.jinja2 import AssetsExtension

import os
import json
import time
import threading
from math import ceil
from slumber import API
import traceback
from datetime import datetime, timedelta
from mongoengine import Q
from cStringIO import StringIO
from collections import Counter
from boto.cloudfront import CloudFrontConnection
from multiprocessing.pool import ThreadPool

from crawlers.common.stash import picked_crawlers
from backends.monitor.events import run_command
from views import get_all_brands, get_brand, update_brand, delete_brand, update_brand_volumn, search_brands
from views import get_all_links, post_link, delete_link
from views import get_all_schedules, update_schedule, delete_schedule, execute as execute_deal
from powers.tools import ImageTool, Image
from powers.configs import AWS_ACCESS_KEY, AWS_SECRET_KEY,S3_IMAGE_BUCKET
from boto.cloudfront import CloudFrontConnection
from StringIO import StringIO
from PIL import Image,ImageOps
import threading
from powers.configs import AWS_ACCESS_KEY, AWS_SECRET_KEY

from backends.webui.views import get_one_site_schedule, get_publish_report, task_all_tasks, task_updates
from backends.monitor.upcoming_ending_events_count import upcoming_events, ending_events
from backends.monitor.publisher_report import wink
from backends.monitor.models import Stat, Fail

_worker = ThreadPool(4)
DISTRIBUTIONID = 'E3QJD92P0IKIG2'

# editlog db
import pymongo
db = pymongo.MongoClient().editlog
db.editlog.ensure_index([('time', -1)])
db_schema =  [
    'time',
    'type',
    'mid',
    'site',
    'key',
]
# end editlog db

import redis
import pickle
cache = redis.Redis(db=13)
def get_cached(func, args=[], kwargs={}, key=None, timeout=300):
    """ cache func(*args) result based on ``key`` and ``timeout``
    
    this function is designed to take care of ``thundering herd`` problem
    by setting an extra ``key_valid`` indicator

    the ``key`` itself doesn't get expired, only ``key_valid`` does
    if ``key_valid`` is invalidated, it revalidate itself really quick and 
    updates the new value to ``key``, much better
    """
    if not key:
        raise ValueError("key cannot be None")

    key_valid = key + '_valid?'
    value = cache.get(key)
    value_valid = cache.get(key_valid)

    if (not value_valid) or (not value):
        cache.setex(key_valid, 'set', timeout)
        value = func(*args, **kwargs)
        value = pickle.dumps(value)
        cache.set(key, value)

    value = pickle.loads(value)

    return value


def invalidate_cloudfront(key):
    threading.Thread(target=_invalidate, args=(key,)).start()

def _invalidate(key):
    while True:
        try:
            conn = CloudFrontConnection(AWS_ACCESS_KEY, AWS_SECRET_KEY)
            conn.create_invalidation_request(DISTRIBUTIONID, [key])
        except:
            import time
            time.sleep(60)
        else:
            break

def get_site_module(site):
    return __import__('crawlers.'+site+'.models', fromlist=['Category', 'Event', 'Product'])

class Pagination(object):
    def __init__(self, page, per_page, total_count):
        self.page = page
        self.per_page = per_page
        self.total_count = total_count

    @property
    def pages(self):
        return int(ceil(self.total_count / float(self.per_page)))

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    def iter_pages(self, left_edge=2, left_current=2,
                   right_current=5, right_edge=2):
        last = 0
        for num in xrange(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and \
                num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num

class Jinja2Environment(jinja2.Environment): 
    def load(self, template_path): 
        tmpl = self.get_template(template_path) 
        if tmpl: 
            setattr(tmpl, "generate", tmpl.render) 
        return tmpl

ROOT = os.path.dirname(__file__)
TEMPLATE_PATH = os.path.join(ROOT+"views")
STATIC_PATH = os.path.join(ROOT+"assets")
from settings import MASTIFF_HOST
api = API(MASTIFF_HOST)

assets_env = AssetsEnvironment(STATIC_PATH, '/assets')
bundles = loaders.YAMLLoader(os.path.join(ROOT, "bundle.yaml")).load_bundles()
for name, bundle in bundles.iteritems():
    assets_env.register(name, bundle)
JINJA2_ENV = Jinja2Environment(extensions=[AssetsExtension],
                                loader=jinja2.FileSystemLoader(TEMPLATE_PATH))
JINJA2_ENV.assets_environment = assets_env

def imagesize(imageobj, wxh):
    if imageobj:
        w, h = wxh.split('x')
        w, h = (int(w), int(h))
        for size in imageobj['resolutions']:
            if h == 0 and w == size[0]:
                h = size[1]
        return imageobj['url'] + '_{0}x{1}'.format(w, h)

def bjtime(timeobj):
    if timeobj:
        return timeobj+timedelta(hours=8)

JINJA2_ENV.filters['imagesize'] = imagesize
JINJA2_ENV.filters['bjtime'] = bjtime

class BaseHandler(tornado.web.RequestHandler): 
    def __init__(self, *args, **kwargs): 
        tornado.web.RequestHandler.__init__( self, *args, **kwargs ) 
        self.jinja2_env = self.settings.get("jinja2_env") 

    def prepare(self):
        if self.request.headers.get("Content-Type") == "application/json":
            self.json_args = json.loads(self.request.body)
        else:
            self.json_args = None

    def get_argument(self,key,default=None):
        try:
            return super(BaseHandler,self).get_argument(key)
        except:
            return default
    
    def get_current_user(self):
        user = self.get_secure_cookie('user')
        return user

    def render_string(self, template_name, **kwargs): 
        # if the jinja2_env is present, then use jinja2 to render templates: 
        if self.jinja2_env: 
            context = {
                'current_user': self.get_current_user,
                'xsrf_form_html': self.xsrf_form_html,
            }
            kwargs.update(context)
            return self.jinja2_env.get_template(template_name).render(**kwargs)
        else:
            return tornado.web.RequestHandler.render_string(self, template_name, **kwargs) 


class AsyncProcessMixIn(BaseHandler):
    """
    refer:  https://gist.github.com/methane/2185380
            http://tornadogists.org/489093/

    """
    def run_background(self, func, callback, argc=(), kwargs={}):
        def _callback(result):
            tornado.ioloop.IOLoop.instance().add_callback(lambda: callback(result))
        _worker.apply_async(func, argc, kwargs, _callback)

class UserActionHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, subpath):
        if not subpath:
            self.redirect('/useraction/overview')
       
        if subpath == 'overview':
            self.overview() 
        elif subpath == 'sitelog':
            self.sitelog()
        elif subpath == 'topusers':
            self.topusers()
        elif subpath == 'userlog':
            self.userlog()
    
    def topusers(self):
        date = int(self.get_argument('date', '0'))
        topusers = api.useraction.get(special='useraction_topusers', date=date)
        self.render("useraction/topusers.html", topusers=topusers)

    def userlog(self):
        page = int(self.get_argument('page', '1'))
        session = self.get_argument('session')
        data = api.useraction.get(session_id=session, order_by='-time', offset=(page-1)*20, limit=20)
        total_count = data['meta']['total_count']
        pagination = Pagination(page, 20, total_count)
        logs = data['objects']
        self.render("useraction/userlog.html", pagination=pagination, logs=logs)

    def overview(self):
        date = int(self.get_argument('date', '0'))
        overview = api.useraction.get(special='useraction_overview', date=date)
        osdata = []
        browserdata = []
        logindata = []
        countrydata = []
        for k in overview['os']:
            osdata.append({'label':k, 'data':overview['os'][k] })
        for k in overview['browser']:
            browserdata.append({'label':k, 'data':overview['browser'][k]}) 
        for k in overview['country']:
            countrydata.append({'label':k, 'data':overview['country'][k]})
        for k in overview['login']:
            logindata.append({'label':k, 'data':overview['login'][k]}) 
        self.render("useraction/overview.html", overview=overview, osdata=osdata, browserdata=browserdata, logindata=logindata, countrydata=countrydata) 

    def sitelog(self):
        site = self.get_argument('site', None)
        if site:
            logs = api.useraction.get(special='recent_useraction_by_site', site=site)
        else:
            logs = api.useraction.get(special='recent_useraction_by_site')
        self.render("useraction/sitelog.html", logs=logs, site=site)

class IndexHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        from backends.matching.feature import sites
        num_view_products_by_site = api.useraction.get(special='num_view_products_by_site')
        yesterday = (datetime.utcnow() - timedelta(days=1)).isoformat().replace('T', ' ')
        num_members = api.user.get(limit=1)['meta']['total_count']
        num_new_members = api.user.get(limit=1, date_joined__gt=yesterday)['meta']['total_count']
        num_events = api.event.get(limit=1)['meta']['total_count']
        num_new_events = api.event.get(limit=1, created_at__gt=yesterday)['meta']['total_count']
        num_products = api.product.get(limit=1)['meta']['total_count']
        num_new_products = api.product.get(limit=1, created_at__gt=yesterday)['meta']['total_count']
        num_buys = api.useraction.get(limit=1, name='click buy')['meta']['total_count']
        num_new_buys = api.useraction.get(limit=1, time__gt=yesterday, name='click buy')['meta']['total_count']
        num_view_products = api.useraction.get(limit=1, name='view product')['meta']['total_count']
        num_new_view_products_a = api.useraction.get(**{'limit':1, 'time__gt':yesterday, 'name':'view product','values.available':'true'})['meta']['total_count']
        num_new_view_products = api.useraction.get(limit=1, time__gt=yesterday, name='view product')['meta']['total_count']
        buys = api.useraction.get(limit=2000, name='click buy', order_by='-time', time__gt=yesterday)['objects']
        #buys = api.useraction.get(limit=1000, name='click buy', order_by='-time')['objects']

        top_buys = {}
        top_buy_sites = Counter()
        c_top_buys = Counter()
        pids = []
        for b in buys:
            c_top_buys[ b['values']['product_id'] ] += 1
            pids.append( b['values']['product_id'] )
        pids = list(set(pids))
        c10_top_buys = c_top_buys.most_common(10)
        for id, count in c10_top_buys:
            top_buys[id] = {'count': count}
        list_products = []
        for i in range((len(pids)-1)/100+1):
            pidsi = pids[i*100:i*100+100]
            list_products.extend( api.product.get(limit=1000, visible_all=1, _id__in=','.join(pidsi))['objects'] )
        for p in list_products:
            top_buy_sites[ p['site_key'].split('_', 1)[0] ] += c_top_buys[ p['id'] ]
            if p['id'] in top_buys:
                top_buys[p['id']]['product'] = p

        top_buys = sorted(top_buys.items(), key=lambda x:x[1]['count'], reverse=True)
        zero_buy_count = [i for i in picked_crawlers if i not in top_buy_sites.keys()]
    
        self.render("index.html",
            utcnow = datetime.utcnow(),
            num_view_products_by_site = num_view_products_by_site,
            num_members = num_members,
            num_new_members = num_new_members,
            num_events = num_events,
            num_new_events = num_new_events,
            num_products = num_products,
            num_new_products = num_new_products,
            num_buys = num_buys,
            num_new_buys = num_new_buys,
            num_view_products = num_view_products,
            num_new_view_products = num_new_view_products,
            num_new_view_products_a = num_new_view_products_a,
            top_buys = top_buys,
            top_buy_sites = top_buy_sites,
            zero_buy_sites = zero_buy_count
        )

class ExampleHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, module):
        self.render('examples/'+module+'.html')

class LoginHandler(BaseHandler):
    def get(self):
        self.render('login.html')

    def post(self):
        username = self.get_argument('username')
        password = self.get_argument('password')
        if username == 'favbuy' and password == 'favbuy0208':
            self.set_secure_cookie('user', username)
        next_url = self.get_argument('next', '/')
        self.redirect(next_url)

class LogoutHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.clear_cookie('user')
        next_url = self.get_argument('next', '/')
        self.redirect(next_url)

class EditDataHandler(BaseHandler):

    def validate_brands(self,brands):
        for brand in brands:
            res  = 0
            try:
                res = api.brand.get(name=brand)['meta']['total_count']
            except Exception,e:
                pass

            if int(res) == 0:
                return 0,brand
        return 1,''

    @tornado.web.authenticated
    def get(self, type, id):
        if type == 'event':
            event = api.event(id).get()
            event['brands'] = ','.join(event.get('brands',[]))
            event['tags'] = ','.join(event.get('tags',[]))
            self.render('editdata/event.html',event=event)
        elif type == 'product':
            product = api.product(id).get()
            product['tags'] = ','.join(product.get('tags') or [])
            product['details'] = '\n'.join(product['details'])
            self.render('editdata/product.html',product=product)

    @tornado.web.authenticated
    def post(self, type, id):
        if type == 'event':
            self._edit_event(id)
        elif type == 'product':
            self._edit_product(id)

    def logedit(self, site, key, type, mid):
        time = datetime.utcnow()
        an_hour_ago = datetime.utcnow() - timedelta(hours=1)
        if not db.editlog.find_one({'time':{'$gt':an_hour_ago}, 'mid': mid}):
            db.editlog.insert({'time':time, 'type':type, 'site':site, 'key':key, 'mid':mid})

    def _edit_event(self,id):
        event               = api.event(id).get()
        site,key            = event['site_key'].split('_',1)
        self.logedit(site, key, 'event', id)

        data = {}
        data['title']       = self.get_argument('title')
        data['description'] = self.get_argument('description','')
        data['tags']        = self.get_argument('tags','').split(',')
        data['departments']   = eval(self.get_argument('departments', '[]'))
        if self.get_argument('score'):
            try:
                data['recommend_score'] = float(self.get_argument('score'))
                data['score'] = data['recommend_score']
            except:
                pass
        brands              = self.get_argument('brands') and self.get_argument('brands').split(',') or None

        # validate brands
        if brands:
            s,t = self.validate_brands(brands)
            if not s:
                message = 'Brand name `{0}` does not exist.'.format(t)
                return self.render('editdata/event.html',message=message)
            else:
                data['brands'] = brands
        else:
            data['brands'] = []
        
        # save to crawler's db
        try:
            m = get_site_module(site)
            e = m.Event.objects.get(event_id=key)
            e.sale_title = data['title']
            e.sale_description = data['description']
            e.favbuy_tag = data['tags']
            e.departments = data['departments']
            e.disallow_classification = True
            e.save()
        except Exception,e:
            message = e.message
            return self.render('editdata/event.html',message=message)
        
        # save to mastiff's db
        try:
            api.event(id).patch(data)
        except Exception,e:
            message = e.message
        else:
            message = 'Success'

        event = api.event(id).get()
        event['brands'] = ','.join(event.get('brands',[]))
        event['tags'] = ','.join(event.get('tags',[]))
        self.render('editdata/event.html',event=event, message=message)

    def _edit_product(self,id):
        # POST
        product               = api.product(id).get()
        site,key              = product['site_key'].split('_',1)
        self.logedit(site, key, 'product', id)

        data = {}
        data['title']         = self.get_argument('title')
        data['details']       = self.get_argument('details')
        data['tags']          = self.get_argument('tags', '').split(',')
        data['brand']         = self.get_argument('brand', '')
        data['department_path']   = eval(self.get_argument('departments', '[]'))
        data['cover_image']   = eval(self.get_argument('cover_image', '{}'))
        data['details']       = self.get_argument('details', '').split('\n')

        # validate
        if data['brand']:
            s,t = self.validate_brands([data['brand']])
            if not s:
                message = 'Brand name`{0}` does not exist.'.format(t)
                return self.render('editdata/product.html',message=message)

        # save to crawler's db
        try:
            m = get_site_module(site)
            p = m.Product.objects.get(key=key)
            p.sale_title = data['title']
            p.list_info = data['details']
            p.brand = data['brand']
            p.tagline = data['tags']
            p.department_path = data['department_path']
            p.disallow_classification = True
            p.save()
        except Exception,e:
            message = e.message
            return self.render('editdata/product.html',message=message)
        
        # save to mastiff
        try:
            api.product(id).patch(data)
        except Exception,e:
            message = e.message
        else:
            message = 'Success'

        product = api.product(id).get()
        product['tags'] = ','.join(product.get('tags') or [])
        product['details'] = '\n'.join(product['details'])
        self.render('editdata/product.html',product=product, message=message)

class ViewDataHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, subpath):
        if not subpath:
            self.redirect('/viewdata/recommend')
        if subpath == 'events':
            self.render_events()
        elif subpath == 'products':
            self.render_products()
        elif subpath == 'classification':
            self.render_classification()
        elif subpath == 'classification_reason.ajax':
            self.render_classification_reason()
        elif subpath == 'reclassify_all.ajax':
            self.render_reclassify_all()
        elif subpath == 'recommend':
            self.render_recommend()
        elif subpath == 'editlog':
            self.render_editlog()

    def render_editlog(self):
        a_week_ago = datetime.utcnow() - timedelta(days=7)
        report = {}
        for daykey in range(7):
            if daykey not in report:
                report[daykey] = {'event':0, 'product':0}
        for log in db.editlog.find({'time':{'$gt':a_week_ago}}):
            daykey = (datetime.utcnow()-log['time']).days
            if log['type'] == 'event':
                report[daykey]['event'] += 1
            else:
                report[daykey]['product'] += 1
        total_count = db.editlog.find().count()
        page = int(self.get_argument('page', '1'))
        pagination = Pagination(page, 20, total_count)
        logs = list(db.editlog.find().sort([('time', -1)]).skip((page-1)*20).limit(20))
        for log in logs:
            if log['type'] == 'event':
                t = api.event(log['mid']).get()
            else:
                t = api.product(log['mid']).get()
            log['image'] = t['cover_image']
            log['title'] = t['title']
            log['departments'] = t.get('departments', []) or t.get('department_path', [])
            
        self.render('viewdata/editlog.html', report=report, logs=logs, pagination=pagination)
    
    def render_reclassify_all(self):
        kwargs = {}
        for k, v in self.request.arguments.iteritems():
            if k != 'departments':
                kwargs[k] = v[0]

        departments = eval(self.get_argument('departments', '[]'))

        try:
            result = api.product.get(**kwargs)
        except:
            result = {'meta':{'total_count':0},'objects':[]}

        for product in result['objects']:
            site, key = product['site_key'].split('_',1)
            m = get_site_module(site)
            m.Product.objects(key=key).update(set__favbuy_dept=departments)
            try:
                api.product(product['id']).patch({'department_path':departments})
            except:
                pass

        self.content_type = 'application/json'
        self.finish(json.dumps({'status':'ok'}))

    def render_classification_reason(self):
        from backends.matching.mechanic_classifier import classify_product_department
        site = self.get_argument('site')
        key = self.get_argument('key')
        m = get_site_module(site)
        p = m.Product.objects.get(key=key)
        dept, reason = classify_product_department(site, p, return_judge=True)
        html = ''
        html += 'TITLE: ' + reason[0] + '<br />'
        for rule in reason[1:]:
            html += 'RULE: ' + str(rule) + '<br />'
        html += 'RESULT: ' + str(dept) + '<br />'
        self.write(html)

    def render_classification(self):
        from backends.matching.feature import sites
        from itertools import chain
        current_site = self.get_argument('site', sites[0])
        key = self.get_argument('key', None)
        offset = self.get_argument('offset', '0')
        limit = self.get_argument('limit', '80')
        offset, limit = int(offset), int(limit)
        page = offset/80+1

        m = get_site_module(current_site)

        if key is None:
            # events
            type = 'event'
            utcnow = datetime.utcnow()
            if hasattr(m, 'Event'):
                ol1 = m.Event.objects(Q(events_end__gt=utcnow) & (Q(events_begin__exists=False) | Q(events_begin__lt=utcnow))).order_by('-create_time')
            else:
                ol1 = []

            if hasattr(m, 'Category'):
                ol2 = m.Category.objects().order_by('-create_time')
            else:
                ol2 = []
        else:
            # current_site, key, products
            type = 'product'
            ol1 = m.Product.objects(event_id=key, updated=True)
            ol2 = m.Product.objects(category_key=key, updated=True)

        num_ol1 = len(ol1)
        if num_ol1 <= offset:
            ol1 = []
            offset -= num_ol1
        elif num_ol1 >= offset+limit:
            ol1 = ol1[offset:offset+limit]
            limit  = 0
        else:
            ol1 = ol1[offset:]
            offset = 0
            limit -= (num_ol1 - offset)

        num_ol2 = len(ol2)
        if limit == 0 or num_ol2 == 0:
            ol2 = []
        else:
            ol2 = ol2[offset:offset+limit]

        object_list = chain(ol1, ol2)
        total_count = num_ol1 + num_ol2
        pagination = Pagination(page, 80, total_count)

        self.render('viewdata/classification.html', sites=sites, current_site=current_site,
            object_list=object_list, pagination=pagination, type=type, key=key)

    def render_products(self):
        from backends.matching.feature import sites
        kwargs = {}
        for k, v in self.request.arguments.iteritems():
            kwargs[k] = v[0]

        offset = kwargs.get('offset', '0')
        limit  = kwargs.get('limit', '20')
        kwargs['offset'] = int(offset)
        kwargs['limit']  = int(limit)
        kwargs['visible_all'] = 1

        try:
            result = api.product.get(**kwargs)
            message = ''
        except:
            message = 'CANNOT Connect to Mastiff!'
            result = {'meta':{'total_count':0},'objects':[]}

        meta = result['meta']
        products = result['objects']
        sites = ['ALL'] + sites
        times = {
           'onehourago': datetime.utcnow()-timedelta(hours=1),
           'onedayago': datetime.utcnow()-timedelta(days=1),
           'oneweekago': datetime.utcnow()-timedelta(days=7),
        }

        pagination = Pagination(int(offset)/20+1, 20, meta['total_count'])
        self.render('viewdata/products.html', meta=meta, products=products, sites=sites, 
            times=times, pagination=pagination, message=message)

    def render_events(self):
        from backends.matching.feature import sites
        kwargs = {}
        for k, v in self.request.arguments.iteritems():
            kwargs[k] = v[0]

        offset = kwargs.get('offset', '0')
        limit = kwargs.get('limit', '20')
        kwargs['offset'] = int(offset)
        kwargs['limit'] = int(limit)
        kwargs['visible_all'] = 1

        try:
            result = api.event.get(**kwargs)
            message = ''
        except:
            message = 'CANNOT Connect to Mastiff!'
            result = {'meta':{'total_count':0},'objects':[]}

        meta = result['meta']
        events = result['objects']
        sites = ['ALL'] + sites
        times = {
           'onehourago': datetime.utcnow()-timedelta(hours=1),
           'onedayago': datetime.utcnow()-timedelta(days=1),
           'oneweekago': datetime.utcnow()-timedelta(days=7),
        }

        pagination = Pagination(int(offset)/20+1, 20, meta['total_count'])
        self.render('viewdata/events.html', meta=meta, events=events, sites=sites, 
            times=times, pagination=pagination, message=message)
    
    def render_recommend(self):
        from backends.matching.feature import sites
        kwargs = {}
        for k, v in self.request.arguments.iteritems():
            kwargs[k] = v[0]

        offset = kwargs.get('offset', '0')
        limit = kwargs.get('limit', '80')
        kwargs['offset'] = int(offset)
        kwargs['limit'] = int(limit)

        try:
            now = datetime.utcnow()
            result= api.event.get(starts_at__lt=now, ends_at__gt=now, order_by='-recommend_score,-score',cover_image__ne="", offset=offset, limit=limit,have_products='true')
            message = ''
        except:
            message = 'CANNOT Connect to Mastiff!'
            result = {'meta':{'total_count':0},'objects':[]}

        meta = result['meta']
        events = result['objects']
        sites = ['ALL'] + sites
        times = {
           'onehourago': datetime.utcnow()-timedelta(hours=1),
           'onedayago': datetime.utcnow()-timedelta(days=1),
           'oneweekago': datetime.utcnow()-timedelta(days=7),
        }

        pagination = Pagination(int(offset)/80+1, 80, meta['total_count'])
        self.render('viewdata/recommend.html', meta=meta, events=events, sites=sites, 
            times=times, pagination=pagination, message=message)

class FeedbackHandler(BaseHandler):
    def get(self,id=None):
        if id:
            return self.render_detail(id)

        page = int(self.get_argument('page', 1))
        limit = 20
        offset = (page-1)*limit
        res = api.feedback.get(limit=limit,offset=offset,order_by='-created_at')
        total_count =  res['meta']['total_count']
        pagination = Pagination(page, limit, total_count)
        self.render('feedback/list.html',results=res['objects'],pagination=pagination)

    def render_detail(self,id):
        r = api.feedback(id).get()
        return self.render('feedback/detail.html',r=r)

class EmailHandler(BaseHandler):
    def get(self,id=None):
        if id:
            return self.render_detail(id)

        page = int(self.get_argument('page', 1))
        limit = 20
        offset = (page-1)*limit
        res = api.email.get(limit=limit,offset=offset,order_by='-created_at')
        total_count =  res['meta']['total_count']
        pagination = Pagination(page, limit, total_count)
        self.render('email/list.html',results=res['objects'],pagination=pagination)

    def render_detail(self,id):
        r = api.email(id).get()
        return self.render('email/detail.html',r=r)

class KeywordHandler(BaseHandler):

    @tornado.web.authenticated
    def get(self,name=''):
        if not name or name == 'list':
            page = int(self.get_argument('page', 1))
            limit = 20
            offset = (page-1)*limit
            res = api.searchkeyword.get(is_deleted=False,limit=limit,offset=offset,order_by='-num_searchs')
            total_count =  res['meta']['total_count']
            pagination = Pagination(page, limit, total_count)
            self.render('keyword/list.html',results=res['objects'],pagination=pagination)

    @tornado.web.authenticated
    def delete(self,id):
        if id:
            response = {'status':0,'info':''}
            api.searchkeyword(id).patch({'is_deleted':True})
            r = api.searchkeyword(id).get()
            if r['is_deleted']:
                response['status'] = 1
                self.write('1')
            else:
                self.write('0')


class BlogHandler(BaseHandler):

    @tornado.web.authenticated
    def get(self,name=None):
        if name == 'add/':
            return self.render_edit()
        elif name.startswith('listing'):
            page = int(self.get_argument('page', 1))
            limit = 20
            offset = (page-1)*limit
            res = api.blog.get(limit=limit,offset=offset,order_by='-created_at')
            total_count =  res['meta']['total_count']
            pagination = Pagination(page, limit, total_count)
            return self.render('blog/list.html',results=res['objects'],pagination=pagination)
        elif name.startswith('detail'):
            id = name.split('/')[1]
            return self.render_detail(id)
        elif name.startswith('edit'):
            id = name.split('/')[1]
            return self.render_edit(id)

    def render_detail(self,id):
        r = api.blog(id).get()
        return self.render('blog/detail.html',r=r)

    def render_edit(self,id=None):
        r = False
        if id:
            r = api.blog(id).get()
        return self.render('blog/edit.html',r=r,xsrf_token=self.xsrf_token)

    @tornado.web.authenticated
    def post(self,name=None):
        """ create a new blog """
        data = {}
        keys = ['title','content']
        for key in keys:
            data[key]  = self.get_argument(key)
        
        if name == 'add/':
            # create new blog
            r = api.blog.post(data)
            id = r['id']

        elif name == 'upload/':
            return self.upload_handle()
        elif name.startswith('edit/'):
            id = name.split('/')[1]
            # edit a blog
            r = api.blog(id).patch(data)

        return self.redirect('/blog/detail/{0}/'.format(id))

    def upload_handle(self):
        response= {'error':1,'message':'test'}
        self.content_type = 'application/json'

        content = self.request.files['imgFile'][0]['body']
        it = ImageTool()
        key = 'blog/{0}.jpg'.format(md5(content).hexdigest())
        try:
            im = Image.open(StringIO(content))
            fileobj = StringIO()
            im.save(fileobj, 'jpeg', quality=100)
            fileobj.seek(0)
            it.upload2s3(fileobj, key)
            invalidate_cloudfront(key)
            url = 'https://s3.amazonaws.com/{0}/{1}'.format(S3_IMAGE_BUCKET,key)
        except Exception,e:
            response['message'] = e.message
            pass
        else:
            response = {'error':0,'url':url}

        self.write(json.dumps(response))
        return

class MonitorHandler(BaseHandler):
    def get(self):
        self.render('monitor.html')

class CrawlerHandler(AsyncProcessMixIn):
    def _get_report(self):
        one_day_ago = datetime.utcnow() - timedelta(days=1)
        report = {}
        sites = set()
        methods = set()
        for fail in Fail.objects(time__gt=one_day_ago).only('site', 'method'):
            sites.add(fail.site)
            methods.add(fail.method)
            rkey = '{}.{}'.format(fail.site, fail.method)
            if rkey not in report:
                report[rkey] = 0
            report[rkey] += 1
        for site in sites:
            report[site+'.all'] = 0
        for method in methods:
            report['all.'+method] = 0
        for rkey in report:
            site, method = rkey.split('.')
            if site != 'all' and method != 'all': 
                report[site+'.all'] += report[rkey]
                report['all.'+method] += report[rkey]
        report['all.all'] = 0
        for site in sites:
            report['all.all'] += report[site+'.all']
        return {'report':report, 'sites':sites, 'methods':methods}

    @tornado.web.authenticated
    @tornado.web.asynchronous
    def get(self, subpath, parameter):
        if not subpath:
            self.redirect('/crawler/tasks')
        if subpath == 'tasks':
            if parameter == 'all':
                offset = self.get_argument('offset', 0)
                limit = self.get_argument('limit', 50)
                offset, limit = int(offset), int(limit)
                return task_all_tasks(offset, limit)
            elif parameter == 'update':
                return task_updates()
            else:
                self.render('crawler/tasks.html')
        elif subpath == 'control':
            self.render('crawler/control.html')

        elif subpath == 'errors':
            one_day_ago = datetime.utcnow() - timedelta(days=1)
            page = int(self.get_argument('page', '1'))
            site = self.get_argument('site', None)
            method = self.get_argument('method', None)
    
            report = {}
            showreport = False
            if site and not method:
                fails = Fail.objects(site=site, time__gt=one_day_ago)
            elif method and not site:
                fails = Fail.objects(method=method, time__gt=one_day_ago)
            elif site and method:
                fails = Fail.objects(site=site, method=method, time__gt=one_day_ago)
            else:
                fails = Fail.objects(time__gt=one_day_ago)
                showreport = True
                report = get_cached(self._get_report, key='get_report')

            fails = fails.order_by('-time').skip(page*20-20).limit(20)
            self.render('crawler/errors.html', fails=fails, page=page, showreport=showreport, **report)
        # publish
        elif subpath == 'publish':
            if parameter == 'chkpub':
                self.render('crawler/chkpub.html')
            elif parameter == 'stats':
                self.render('crawler/stats.html')
            elif parameter == 'report':
                _utcnow = datetime.utcnow()
                if wink(_utcnow):
                    self.run_background( get_publish_report, self.report, (_utcnow.replace(microsecond=0, second=0, minute=0, hour=9),) )
                else:
                    return self.render('crawler/report.html',
                                        date = _utcnow.replace(microsecond=0, second=0, minute=0, hour=9),
                                        event = [],
                                        product = [])

            elif parameter == 'updatereport':
                _utcnow = datetime.utcnow()
                if wink(_utcnow, force=True):
                    self.run_background( get_publish_report, self.updatereport, (_utcnow.replace(microsecond=0, second=0, minute=0, hour=9),) )
                else:
                    return self.render('crawler/updatereport.html',
                                        date = _utcnow.replace(microsecond=0, second=0, minute=0, hour=9),
                                        event = [],
                                        product = [])
            else:
                self.render('crawler/publish.html')

        # history
        elif subpath == 'history':
            self.render('crawler/history.html')
        elif subpath == 'site':
            if parameter:
                self.render("crawler/site.html", tasks = get_one_site_schedule(parameter)['tasks'])
        elif subpath == 'schedule':
            if parameter == 'upcoming':
                self.render("crawler/schedule.html", schedules = upcoming_events())
            elif parameter == 'ending':
                self.render("crawler/schedule.html", schedules = ending_events())

        # graph
        elif subpath == 'graph':
            if not parameter:
                self.render('crawler/graph.html')
            else:
                doctype, site = parameter.split('_')
                if doctype == 'event':
                    stats = Stat.objects(site=site, doctype='event').order_by('interval')
                    graphdata = []
                    graphdata.append({'name':'crawled', 'data':[(int(time.mktime(s.interval.timetuple())*1000), s.crawl_num) for s in stats]})
                    graphdata.append({'name':'image', 'data':[(int(time.mktime(s.interval.timetuple())*1000), s.image_num) for s in stats]})    
                    graphdata.append({'name':'propagated', 'data':[(int(time.mktime(s.interval.timetuple())*1000), s.prop_num) for s in stats]})
                    graphdata.append({'name':'published', 'data':[(int(time.mktime(s.interval.timetuple())*1000), s.publish_num) for s in stats]})
                    return json.dumps(graphdata)
                elif doctype == 'product':
                    stats = Stat.objects(site=site, doctype='product').order_by('interval')
                    graphdata = []
                    graphdata.append({'name':'crawled', 'data':[(int(time.mktime(s.interval.timetuple())*1000), s.crawl_num) for s in stats]})
                    graphdata.append({'name':'image', 'data':[(int(time.mktime(s.interval.timetuple())*1000), s.image_num) for s in stats]})
                    graphdata.append({'name':'published', 'data':[(int(time.mktime(s.interval.timetuple())*1000), s.publish_num) for s in stats]})
                    return json.dumps(graphdata)




    @tornado.web.authenticated
    @tornado.web.asynchronous
    def post(self, subpath, parameter):
        if subpath == 'publish':
            if parameter == 'report':
                dat = self.get_argument('date')
#                print('[{0}], [{1}]'.format(dat, self.request.arguments))
                month, day, year = dat.split('/')
                _thedate = datetime(int(year), int(month), int(day))
                if wink(_thedate):
                    self.run_background( get_publish_report, self.report, (_thedate.replace(hour=9),) )
                else:
                    return self.render('crawler/report.html',
                                    date = _thedate.replace(hour=9),
                                    event = [],
                                    product = [])
            elif parameter == 'updatereport':
                dat = self.get_argument('date')
                month, day, year = dat.split('/')
                _thedate = datetime(int(year), int(month), int(day))
                if wink(_thedate, force=True):
                    self.run_background( get_publish_report, self.updatereport, (_thedate.replace(hour=9),) )
                else:   
                    return self.render('crawler/updatereport.html',
                                    date = _thedate.replace(hour=9),
                                    event = [],
                                    product = [])


    def report(self, ret):
        _utcnow = datetime.utcnow()
        return self.render('crawler/report.html',
                            date = ret['date'],
                            event = ret['event'],
                            product = ret['product'])

    def updatereport(self, ret):
        _utcnow = datetime.utcnow()
        return self.render('crawler/updatereport.html',
                            date = ret['date'],
                            event = ret['event'],
                            product = ret['product'])

class DashboardHandler(BaseHandler):
    def get(self, path):
        if path == 'member_activity.json':
            self.content_type = 'application/json'
            useractions = api.useraction.get(limit=10, order_by='-time')['objects']
            self.finish(json.dumps(useractions))
        elif path == 'email.json':
            self.content_type = 'application/json'
            emails = api.email.get(limit=10,order_by='-created_at')['objects']
            self.finish(json.dumps(emails))
        elif path == 'keyword.json':
            self.content_type = 'application/json'
            res = api.searchkeyword.get(limit=10,order_by='-num_searchs')['objects']
            self.finish(json.dumps(res))
        else:
            self.content_type = 'application/json'
            self.finish(json.dumps(['no content']))

class ScheduleHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, key):
        if not key:
            s = get_all_schedules()
            self.render('schedule.html', schedules=s)
    @tornado.web.authenticated
    def post(self, key):
        d = {k:v[0] for k,v in self.request.arguments.iteritems() if v}

        if key == 'run':
            method = d['method']
            site = d['site']
            run_command.send('admin', site=site, method=method, command_type='deal')
            return self.write(json.dumps({'status':'ok'}))

        r = update_schedule(d)
        return self.write(json.dumps(r))

    @tornado.web.authenticated
    def delete(self, key):
        d = {k:v[0] for k,v in self.request.arguments.iteritems() if v}
        d.update({'pk': key})
        r = delete_schedule(d)
        return self.write(json.dumps(r))

class AffiliateHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, key):
        if not key:
            if self.get_argument('ac') == 'a':
                return self.render('affiliate.html', links=None, sites=picked_crawlers)

            return self.render('affiliate.html', links=get_all_links(), sites=picked_crawlers)

    @tornado.web.authenticated
    def post(self, key):
        arguments = {k:v[0] for k,v in self.request.arguments.iteritems() if v}

        if key:
            arguments['key'] = key
            post_link(patch=True, **arguments)
        
        post_link(**arguments)
        return self.render('affiliate.html', links=get_all_links(), sites=picked_crawlers)

    @tornado.web.authenticated
    def delete(self, key):
        try:
            api.affiliate(key).delete()
            self.write(json.dumps({'status': True, 'message': ''}));
        except:
            self.write(json.dumps({'status': False, 'message': '%s' % traceback.format_exc()}));

class BrandsHandler(BaseHandler):
    def get(self, db):
        page = int(self.get_argument('offset', '1'))
        limit = int(self.get_argument('limit', '100'))

        brands, total = get_all_brands(db, page=page, limit=limit) if db else get_all_brands(page=page, limit=limit)
        pagination = Pagination(page, limit, total)
        data = {'pagination': pagination}

        if db:
            data[db+'_brands'] = brands
        else:
            data['brands'] = brands
        print data.keys()
        self.render('brands.html', **data)

class BrandSearchHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        query = self.get_argument('q')
        brands = search_brands(query) if query else []
        self.render('brands.html', brands=brands)

class BrandHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, brand_title):
        if not brand_title:
            self.render('brand.html')

        brand = get_brand(brand_title, self.get_argument('d'))
        t_page = 'brand_iframe.html' \
                    if self.get_argument('t') == 'iframe' \
                        else 'brand.html'

        self.render(t_page, brand=brand)
    
    @tornado.web.authenticated
    def post(self, brand_title):
        arguments = self.request.arguments
        brand = update_brand(brand_title, arguments)
        self.render('brand.html', brand=brand)

    @tornado.web.authenticated
    def delete(self, brand_title):
        self.write(str(delete_brand(brand_title)))

class PowerBrandHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, brand_title):
        brand = get_brand(brand_title, 'p')
        self.render('brandpower.html', brand=brand)

    @tornado.web.authenticated
    def post(self, brand_title):
        arguments = self.request.arguments
        brand = update_brand_volumn(brand_title, int(arguments['global_searchs'][0]))
        self.render('brandpower.html', brand=brand)

from deals.models import BrandMonitor
class BrandMonitorHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        bms = BrandMonitor.objects()
        print ',,,,,,,,,,,,,,,,,: ', bms.count()
        p = [brand.to_json() for brand in bms]
        print '~~~~~~~~~~~~~~~~~: ', len(p)
        self.render('brandmonitor.html', brands=[brand.to_json() for brand in bms])


DSFILTER = API(MASTIFF_HOST).dsfilter.get()
class DealHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        site = self.get_argument('site')
        if not site:
            self.render('deals.html', products=[], site='')

        import sys
        reload(sys)
        sys.setdefaultencoding('utf-8')
        
        offset = int(self.get_argument('offset', '0'))
        limit = int(self.get_argument('limit', '40'))
        try:
            m = __import__('crawlers.%s.models' % site, fromlist=['Product'])
        except ImportError:
            self.render('deals.html', products=[], site='')


        objects = m.Product.objects
        total_count = objects().count()
        pagination = Pagination(offset/limit+1, limit, total_count)

        products = objects()[offset:(offset+limit)]
        res = [{
            'title': product.title,
            'combine_url': product.combine_url,
            'image': product.image_urls[0] if product.image_urls else '',
            'brand': product.favbuy_brand,
            'price': product.favbuy_price,
            'listprice': product.favbuy_listprice,
            'dept': '-'.join(product.favbuy_dept),
            'discount': float(product.favbuy_price) / float(product.favbuy_listprice) if product.favbuy_listprice else '',
            'medium' : DSFILTER.get('%s.^_^.%s' % \
            (product.favbuy_brand, '-'.join(product.favbuy_dept)), {}).get('medium', 0)
        } for product in products]
        self.render('deals.html', products=res, pagination=pagination, site=site)

class PreferenceHandler(BaseHandler):
    def get(self, path):
        if path == '':
            self.pref_index()
    
    def post(self, path):
        if path == 'update.ajax':
            self.pref_update()
        elif path == 'unset.ajax':
            self.pref_unset()

    def pref_unset(self):
        self.content_type = 'application/json'
        try:
            site = self.get_argument('site')
            field = self.get_argument('unset')
            api.sitepref(site).post({'$unset':{field:1}}) 
        except Exception, e:
            self.write(json.dumps({'status':'failed', 'reason':e.message}))
        else:
            self.write(json.dumps({'status':'ok'})) 

    def pref_index(self):
        try:
            prefs = api.sitepref().get()['objects']
        except:
            prefs = []
        self.render('preference.html', prefs=prefs)

    def pref_update(self):
        self.content_type = 'application/json'
        try:
            d = { k: v[-1] for k, v in self.request.arguments.iteritems() }
            api.sitepref(d['site']).post(d)
        except Exception, e:
            self.write(json.dumps({'status':'failed', 'reason':e.message}))
        else:
            self.write(json.dumps({'status':'ok'})) 

class MemberHandler(BaseHandler):
    def get(self, path):
        if path == '':
            self.user_index()
        elif path == 'recent_activity':
            self.user_recent_activity()

    def post(self, path):
        if path == 'delete_user.ajax':
            self.delete_user()

    def user_recent_activity(self):
        limit = self.get_argument('limit', '50')
        offset = self.get_argument('offset', '0')
        offset, limit = int(offset), int(limit)
        user = self.get_argument('user', '')

        data = api.useraction.get(user=user, order_by='-time', limit=limit)
        activities = data['objects']
        total_count = data['meta']['total_count']
        pagination = Pagination(1+offset/50, 50, total_count)

        self.render('recent_activity.html',
            activities = activities,
            pagination = pagination
        )

    def delete_user(self):
        username = self.get_argument('username')
        self.content_type = 'application/json'
        try:
            api.usermanage(username).delete()
        except Exception, e:
            self.write(json.dumps({'status':'failed', 'reason': e.message }))
        else:
            self.write(json.dumps({'status':'ok'}))

    def user_index(self):
        limit = self.get_argument('limit', '50')
        offset = self.get_argument('offset', '0')
        offset, limit = int(offset), int(limit)

        data = api.usermanage.get(offset=offset, limit=limit, order_by='-date_joined')
        users = data['objects']
        total_count = data['meta']['total_count']
        pagination = Pagination(1+offset/50, 50, total_count)

        self.render('member.html',
            users = users,
            pagination = pagination
        )

class AjaxHandler(BaseHandler):
    def get(self, path):
        if path == 'recrop_image.ajax':
            self.recrop_image()
    
    def post(self, path):
        if path == 'upload_image.ajax':
            self.upload_image()

    def upload_image(self):
        url = self.get_argument('url')
        target_width = int(self.get_argument('target_width'))
        target_height = int(self.get_argument('target_height'))
        key = url.split('/',4)[-1]+'_{0}x{1}'.format(target_width, target_height)
        fs = self.request.files['imagefile']
        it = ImageTool()
        for f in fs:
            content = f['body']
            im = Image.open(StringIO(content))
            im = im.resize((target_width, target_height), Image.ANTIALIAS)
            fileobj = StringIO()
            im.save(fileobj, 'jpeg', quality=95)
            fileobj.seek(0)
            it.upload2s3(fileobj, key)
            invalidate_cloudfront(key)
            break
        self.redirect(self.request.headers.get('Referer'))

    def recrop_image(self):
        try:
            url = self.get_argument('url')
            for name in ['x', 'y', 'w', 'h', 'target_width', 'target_height']:
                globals()[name] = int(self.get_argument(name))
            key = url.split('/',4)[-1]+'_{0}x{1}'.format(target_width, target_height)
            it = ImageTool()
            print 'connected to s3'
            content = it.download(url)
            print 'downloaded'
            im = Image.open(StringIO(content))
            im = im.crop( (x, y, (x+w), (y+h)) )
            im = im.resize((target_width, target_height), Image.ANTIALIAS)
            fileobj = StringIO()
            im.save(fileobj, 'jpeg', quality=95)
            fileobj.seek(0)
            print 'croped'
            it.upload2s3(fileobj, key)
            print 'uploaded'
            invalidate_cloudfront(key)
            print 'invalid request sent'
            self.content_type = 'application/json'
            self.write(json.dumps({'status':'ok'}))
        except:
            self.content_type = 'application/json'
            self.write(json.dumps({'status':'failed'}))


settings = {
    "debug": True,
    "static_path": STATIC_PATH,
    "template_path": TEMPLATE_PATH,
    "cookie_secret": "637d1f5c6e6d1be22ed907eb3d223d858ca396d8",
    "jinja2_env": JINJA2_ENV,
    "login_url": "/login/",
    "xsrf_cookies": True,
}

application = tornado.web.Application([
    (r"/examples/(ui|form|chart|typography|gallery|table|calendar|grid|file-manager|tour|icon|error|login)/", ExampleHandler),
    (r"/login/", LoginHandler),
    (r"/logout/", LogoutHandler),
    (r"/crawler/([^/]*)/?(.*)", CrawlerHandler),
    (r"/monitor/", MonitorHandler),
    (r"/useraction/(.*)", UserActionHandler),
    (r"/dashboard/(.*)", DashboardHandler),
    (r"/viewdata/(.*)", ViewDataHandler),
    (r"/editdata/(.*)/(.*)/", EditDataHandler),
    (r"/schedule/?(.*)/?", ScheduleHandler),
    (r"/affiliate/?(.*)/?", AffiliateHandler),
    (r"/brands/?(.*)", BrandsHandler),
    (r"/brand/power/(.*)", PowerBrandHandler),
    (r"/brand/deal/monitor", BrandMonitorHandler),
    (r"/deal/?", DealHandler),
    (r"/brand/search/", BrandSearchHandler),
    (r"/brand/?(.*)", BrandHandler),
    (r"/feedback/(.*)", FeedbackHandler),
    (r"/email/(.*)", EmailHandler),
    (r"/blog/(.*)", BlogHandler),
    (r"/keyword/(.*)", KeywordHandler),
    (r"/member/(.*)", MemberHandler),
    (r"/sitepref/(.*)", PreferenceHandler),
    (r"/ajax/(.*)", AjaxHandler),
    (r"/", IndexHandler),
    (r"/assets/(.*)", tornado.web.StaticFileHandler, dict(path=settings['static_path'])),
], **settings)

if __name__ == "__main__":
    server = tornado.httpserver.HTTPServer(application)
    server.bind(8888)
    server.start(1)
    ioloop = tornado.ioloop.IOLoop.instance()
    tornado.autoreload.start(ioloop)
    ioloop.start()
