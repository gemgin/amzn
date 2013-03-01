import requests
import lxml.html
import re
from datetime import datetime
from models import Product


class Ruelala(object):
    def __init__(self):
        self.s = requests.session()
        self.login_url = 'http://www.ruelala.com/access/gate'
        self.s.get(self.login_url)
        self.s.post('http://www.ruelala.com/access/formSetup', data={'userEmail':'','CmsPage':'/access/gate','formType':'signin'})
        self.data = {
            'email': '2012luxurygoods@gmail.com',
            'password': 'abcd1234',
            'loginType': 'gate',
            'rememberMe': 1, 
        }       
        self.s.post('https://www.ruelala.com/registration/login', data=self.data)
    
    def check_product_right(self):
        utcnow = datetime.utcnow()
        obj = Product.objects(products_end__gt=utcnow).timeout(False)
        print 'Ruelala have {0} products.'.format(obj.count())

        redirect_count = 0
        error_page = 0
        for prd in obj:
            ret = self.s.get(prd.combine_url)
            if ret.url == 'http://www.ruelala.com/event':
                redirect_count += 1
                continue
            if ret.url == 'http://www.ruelala.com/common/errorGeneral':
                error_page += 1
                continue
            cont = ret.content
            tree = lxml.html.fromstring(cont)
            try:
                title = tree.cssselect('h2#productName')[0].text_content().strip()
                if title.lower() != prd.title.lower():
                    print 'ruelala product[{0}] title error: [{1}, {2}]'.format(prd.combine_url, title, prd.title)
            except IndexError:
                print '\n\n ruelala product[{0}] title not extract right. return url: {1}\n\n'.format(prd.combine_url, ret.url)

            try:
                listprice = tree.cssselect('span#strikePrice')[0].text_content().strip()
                if listprice != prd.listprice:
                    print 'ruelala product[{0}] listprice error: [{1}, {2}]'.format(prd.combine_url, listprice, prd.listprice)
            except IndexError:
                print '\n\n ruelala product[{0}] listprice error. {1}'.format(prd.combine_url, ret.url)
            price = tree.cssselect('span#salePrice')[0].text_content().strip()
            soldout = tree.cssselect('span#inventoryAvailable')
            if price != prd.price:
                print 'ruelala product[{0}] price error: [{1}, {2}]'.format(prd.combine_url, price, prd.price)
        print 'ruelala have {0} products redirect, {1} products page error.'.format(redirect_count, error_page)


    def get_product_abstract_by_url(self, url):
        content = self.s.get(url).content
        product_id = re.compile(r'/product/(\d+)').search(url).group(1)
        t = lxml.html.fromstring(content)
        title = t.xpath('//*[@id="productName"]')[0].text
        description = ''
        for li in t.xpath('//*[@id="info"]/ul/li'):
            description += li.text_content() + '\n'
        return 'ruelala_'+product_id, title+'_'+description

if __name__ == '__main__':
    Ruelala().check_product_right()
