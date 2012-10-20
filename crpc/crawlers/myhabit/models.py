#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: bishop Liu <miracle (at) gmail.com>
"""
crawlers.myhabit.models
~~~~~~~~~~~~~~~~~~~~~~

Implements Product and Category Model for myhabit 
"""

DB = 'myhabit'
TIMEOUT = 60

from datetime import datetime, timedelta
from mongoengine import *
from settings import MONGODB_HOST
connect(db=DB, host=MONGODB_HOST)

from crawlers.common.models import BaseBrand, BaseProduct


class Category(BaseBrand):
    sale_id = StringField(primary_key=True)
    dept = StringField()
    upcoming_title_img = DictField()
    meta = {
        "indexes": ["soldout"],
    }

    def url(self):
        return 'http://www.myhabit.com/homepage#page=b&dept={0}&sale={1}'.format(self.dept, self.sale_id)


class Product(BaseProduct):
#    key = StringField(unique=True, spare=True)
    dept = StringField()
    sale_id = StringField()
    asin = StringField()
    listprice = StringField()
    soldout = BooleanField()

    list_info = ListField(StringField())
    color = StringField()
    sizes = ListField(StringField())

    video = StringField()
    international_shipping = StringField()
    returned = StringField()
    scarcity = StringField()

    meta = {
        "indexes": ["updated"]
    }

    def url(self):
        return 'http://www.myhabit.com/homepage#page=d&dept={0}&sale={1}&asin={2}&cAsin={3}'.format(self.dept, self.sale_id, self.asin, self.key)
