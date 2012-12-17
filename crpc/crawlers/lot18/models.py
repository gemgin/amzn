#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: bishop Liu <miracle (at) gmail.com>

from mongoengine import *
from settings import MONGODB_HOST
DB = 'lot18'
connect(db=DB, alias=DB, host=MONGODB_HOST)

from crawlers.common.models import BaseCategory, LuxuryProduct

class Category(BaseCategory):
    meta = {
        'db_alias': DB,
    }

    def url(self):
        pass

class Product(LuxuryProduct):
    meta = {
        'db_alias': DB,
    }

    def url(self):
        pass