# -*- coding: utf-8 -*-

from settings import MONGODB_HOST

from mongoengine import *
from mongoengine import signals
from datetime import datetime
DB = 'power'
connect(db=DB, alias=DB, host=MONGODB_HOST)

class Brand(Document):
    title           =   StringField(unique = True)
    title_edit      =   StringField()
    title_checked   =   BooleanField(default = False)
    alias           =   ListField(StringField(), default=list())
    keywords        =   StringField(default = '')
    url             =   StringField(default = '')
    url_checked     =   BooleanField(default = False)
    blurb           =   StringField(default = '')
    images          =   ListField(StringField())
    level           =   IntField(default = 0) # luxrious or not 
    dept            =   ListField(StringField(max_length = 30))
    is_delete       =   BooleanField(default = False)
    done            =   BooleanField(default = False)
    global_searchs  =   IntField(default=0)
    local_searchs   =   IntField(default=0)
    created_at      =   DateTimeField(default=datetime.now())
 
    meta = {
        'db_name': DB,
        'db_alias': DB,
        'indexes': ['title', 'title_checked', 'is_delete', 'done', 'created_at'],
        'ordering': ['title']
    }
        
    def __unicode__(self):
        return self.title

    def to_json(self):
        return {
            'title'           :   self.title,
            'title_edit'      :   self.title_edit,
            'title_checked'   :   self.title_checked,
            'alias'           :   self.alias,
            'keywords'        :   self.keywords,
            'url'             :   self.url,
            'url_checked'     :   self.url_checked,
            'blurb'           :   self.blurb,
            'images'          :   self.images,
            'level'           :   self.level,
            'dept'            :   self.dept,
            'is_delete'       :   self.is_delete,
            'done'            :   self.done,
            'global_searchs'  :   self.global_searchs,
            'local_searchs'   :   self.local_searchs,
            'created_at'      :   str(self.created_at)
        }