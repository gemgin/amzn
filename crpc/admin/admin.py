#!/usr/bin/env python
# -*- coding: utf-8 -*-
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
from math import ceil
from slumber import API
from datetime import datetime, timedelta
from mongoengine import Q

from views import get_all_brands, get_brand, update_brand, delete_brand

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

JINJA2_ENV.filters['imagesize'] = imagesize

class BaseHandler(tornado.web.RequestHandler): 
    def __init__(self, *args, **kwargs): 
        tornado.web.RequestHandler.__init__( self, *args, **kwargs ) 
        self.jinja2_env = self.settings.get("jinja2_env") 

    def prepare(self):
        if self.request.headers.get("Content-Type") == "application/json":
            self.json_args = json.loads(self.request.body)
        else:
            self.json_args = None
    
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

class IndexHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        self.render("index.html")

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
        if username == 'favbuy' and password == 'tempfavbuy':
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
    def get(self, type,id):
        if type == 'event':
            event = api.event(id).get()
            event['brands'] = ','.join(event['brands'])
            event['tags'] = ','.join(event['tags'])
            self.render('editdata/event.html',event=event)
        elif type == 'product':
            product = api.product(id).get()
            product['tags'] = ','.join(product['tags'])
            product['details'] = '\n'.join(product['details'])
            self.render('editdata/product.html',product=product)

    @tornado.web.authenticated
    def post(self,type,id):
        if type == 'event':
            self._edit_event(id)
        elif type == 'product':
            self._edit_product(id)

    def _edit_event(self,id):
        data = {}
        data['title']       = self.get_argument('title')
        data['description'] = self.get_argument('description')
        data['tags']        = self.get_argument('tags').split(',')
        brands              = self.get_argument('brands').split(',')

        # validate
        s,t = self.validate_brands(brands)
        if not s:
            message = 'Brand name`{0}` does not exist.'.format(t)
            return self.render('editdata/event.html',message=message)
        else:
            data['brands'] = brands

        
        # save to mastiff
        try:
            api.event(id).patch(data)
        except Exception,e:
            message = e.message
            return self.render('editdata/event.html',message=message)
        
        else:
            self.redirect('/editdata/event/{0}/'.format(id))

    def _edit_product(self,id):
        # POST
        data = {}
        data['title']         = self.get_argument('title')
        data['details']       = self.get_argument('details')
        data['tags']          = self.get_argument('tags').split(',')
        data['brand']         = self.get_argument('brand')
        data['cover_image']   = eval(self.get_argument('cover_image'))
        data['details']       = self.get_argument('details').split('\n')

        # validate
        s,t = self.validate_brands([data['brand']])
        if not s:
            message = 'Brand name`{0}` does not exist.'.format(t)
            return self.render('editdata/product.html',message=message)
        
        # save to mastiff
        try:
            api.product(id).patch(data)
        except Exception,e:
            message = e.message
            return self.render('editdata/product.html',message=message)
        else:
            self.redirect('/editdata/product/{0}/'.format(id))

class ViewDataHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, subpath):
        if not subpath:
            self.redirect('/viewdata/events')
        if subpath == 'events':
            self.render_events()
        elif subpath == 'products':
            self.render_products()
        elif subpath == 'classification':
            self.render_classification()
        elif subpath == 'classification_reason.ajax':
            self.render_classification_reason()

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
        limit  = kwargs.get('limit', '20')
        kwargs['offset'] = int(offset)
        kwargs['limit'] = int(limit)

        try:
            result = api.event.get(**kwargs)
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

class MonitorHandler(BaseHandler):
    def get(self):
        self.render('monitor.html')

class CrawlerHandler(BaseHandler):
    def get(self):
        self.render('crawler.html')

class BrandsHandler(BaseHandler):
    def get(self):
        brands = get_all_brands()
        self.render('brands.html', brands=brands)

class BrandHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self, brand_title):
        brand = get_brand(url_unescape(brand_title))
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
    (r"/viewdata/(.*)", ViewDataHandler),
    (r"/editdata/(.*)/(.*)/", EditDataHandler),
    (r"/monitor/", MonitorHandler),
    (r"/crawler/", CrawlerHandler),
    (r"/brands/", BrandsHandler),
    (r"/brand/(.*)", BrandHandler),
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
