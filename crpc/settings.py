#!/usr/bin/env python
# -*- coding:utf-8 -*-
from gevent import monkey; monkey.patch_all()

import os
import sys
from itertools import chain

envs = {
    'COMMON': {
        'CRPC_ROOT': os.path.abspath(os.path.dirname(__file__)),
        'ENV_NAME': "crpc", 
        'RPC_PORT': 1234,
    },
    'DEV': {
        'PEERS': ['root@127.0.0.1'],
        'USE_INDEX': '',
        'MONGODB_HOST': '127.0.0.1',
        'REDIS_HOST': '127.0.0.1',
    },
    'HJC': {
        'PEERS': ['root@192.168.56.102','root@192.168.56.103'],
        'USE_INDEX': '',
        'MONGODB_HOST': '192.168.56.101',
        'REDIS_HOST': '192.168.56.101',
    },
    'TEST': {
        'PEERS': [
            'root@ec2-54-245-25-85.us-west-2.compute.amazonaws.com',
            'root@ec2-54-245-31-157.us-west-2.compute.amazonaws.com',
            'root@ec2-50-112-195-236.us-west-2.compute.amazonaws.com',
            'root@ec2-54-245-15-250.us-west-2.compute.amazonaws.com',
        ],
        'USE_INDEX': '',
        'MONGODB_HOST': 'mongodb.favbuy.org',
        'REDIS_HOST': 'mongodb.favbuy.org',
    },
}

env = os.environ.get("ENV")
if not env:
    env = "DEV"

for key, value in chain(envs['COMMON'].iteritems(), envs[env].iteritems()):
    globals()[key] = value

import redisco
redisco.connection_setup(host=REDIS_HOST)
