#!/usr/bin/env python
# -*- coding: utf-8 -*-
import re
import sys
import sklearn.feature_extraction
import operator
from itertools import izip
from pprint import pprint
from stopwords import stopwords

tables = ['myhabit','hautelook', 'gilt', 'nomorerack', 'ruelala', 'zulily']

def get_site_module(site):
    return __import__('crawlers.'+site+'.models', fromlist=['Category', 'Event', 'Product'])

def normalize(s):
    if isinstance(s, list):
        return '\n'.join(x.encode('utf-8') for x in s if x)
    elif s:
        return s.encode('utf-8')
    else:
        return ''

def get_document_list():
    dl = []
    for crawler in tables:
        m = get_site_module(crawler)
        for p in m.Product.objects():
            doc = normalize(p.title) + '\n' + normalize(p.list_info) + normalize(p.summary)
            doc = doc.strip()
            if doc:
                dl.append(doc)
                sys.stdout.write('.')       
                sys.stdout.flush()
    return dl

words = re.compile(ur'\b\w\w+\b')
def adjacent_words_tokenizer(doc):
    l = words.findall(doc)
    for w in l:
        yield w
    for i in range(len(l)-1):
        yield l[i]+' '+l[i+1] 
    for i in range(len(l)-2):
        yield l[i]+' '+l[i+1]+' '+l[i+2]
    for i in range(len(l)-3):
        yield l[i]+' '+l[i+1]+' '+l[i+2]+' '+l[i+3]

def do_counts():
    vectorizer = sklearn.feature_extraction.text.TfidfVectorizer(tokenizer=adjacent_words_tokenizer)
    topkw = {}

    print 'generating document list from database'
    document_list = get_document_list()
    print 'document generated'

    print 'creating dimension', len(document_list), 'matrix'
    matrix = vectorizer.fit_transform(document_list)
    print 'matrix generated'

    print 'collecting term frequency'
    terms = vectorizer.get_feature_names()
    means = matrix.mean(0).tolist()[0]
    for term, mean in izip(terms, means):
        topkw[term] = mean
    print 'term frequency collected'
    
    print 'sorting dict'
    topkw_list = sorted(topkw.iteritems(), key=operator.itemgetter(1), reverse=True)

    with open('topkeywords.txt','w') as f:
        for term, score in topkw_list[:5000]:
            if term in stopwords:
                continue
            f.write('%-30s%s\n' % (term.encode('utf-8'), score))

if __name__ == '__main__':
    #get_document_list()
    do_counts()
