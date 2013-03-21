#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: Ethan <ethan@favbuy.com>
"""
crawlers.macys.models
~~~~~~~~~~~~~~~~~~~~~~

Implements Product for macys
"""

from mongoengine import *
from settings import MONGODB_HOST
DB = 'macys'
connect(db=DB, alias=DB, host=MONGODB_HOST)

from crawlers.common.models import BaseCategory, LuxuryProduct


class Category(BaseCategory):
    key = StringField(unique=True)
    combine_url = StringField()
    hit_time = DateTimeField()

    meta = {
        'db_alias': DB,
    }

    def url(self):
        pass


class Product(LuxuryProduct):
    deal_type = True
    hit_time = DateTimeField()
    
    meta = {
        "db_alias": DB,
    }
    
    def url(self):
        return self.combine_url
