#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import html5lib
import os
import re
import requests
import sys

from bs4 import BeautifulSoup
from pathlib import Path
from urllib.parse import urlparse, urljoin

from requests_html import HTMLSession, AsyncHTMLSession

def savefile(url, src):
    global args

    uri = urlparse(url)

    path = f"{args.mirror}{uri.path}"

    directory = os.path.dirname(path)
    if not os.path.exists(directory):
        os.makedirs(directory)

    binary = False

    if binary == True:
        Path(path).write_bytes(src)
    else:
        Path(path).write_text(src)

def get_elements(soup, parser, tag, attr):
    global args, base_url, cache_url, session

    for el in soup.find_all(tag):
        uri = urlparse(el.get(attr))

        if uri.netloc != '' and uri.netloc != base_url.netloc:
            continue

        if (uri.path == '' and uri.query == ''):
            continue

        if (re.match('^\./', uri.path)):
            uri = uri._replace(path=re.sub('^\./', '', uri.path))

        if uri.path == '':
            uri = uri._replace(path='/')
        elif re.match('^\.\./', uri.path) is not None:
            uri = urlparse(urljoin(parser.geturl(), uri.path))

        url = base_url._replace(path=uri.path, query=uri.query, fragment=uri.fragment).geturl()
        url = re.sub('/+\.?$', '/', url)

        if url in cache_url:
            continue

        cache_url.append(url)

        r = requests.get(url, stream=True) if args.noscript == True else session.get(url, stream=True)
        if r.status_code == 200:
            if r.headers['content-type'] == 'text/css':
                m = re.findall('url\([\'"]?(.+?)[\'"]?\)', r.text)
                for path in m:
                    u = urlparse(urljoin(url, path))

                    if u.netloc != '' and u.netloc != base_url.netloc:
                        continue

                    ur = u.geturl()

                    if ur in cache_url:
                        continue

                    cache_url.append(ur)
                    ri = requests.get(ur, stream=True) if args.noscript == True else session.get(ur, stream=True)
                    if ri.status_code == 200:
                        if args.mirror != '':
                            savefile(ur, ri.content)

                    if args.progress == True:
                        print(f"{ur} ({ri.status_code})")

            if args.mirror != '':
                savefile(url, r.content)

        if args.progress == True:
            print(f"{url} ({r.status_code})")

async def rendering(url):
    global session
    r = await session.get(url)
    await r.html.arender()
    return r

def crawl(url):
    global args, base_url, cache_url, session

    if url in cache_url:
        return

    cache_url.append(url)

    r = None
    source = ''

    if args.noscript == True:
        r = requests.get(url)
        r.encoding = r.apparent_encoding
        source = r.text
    else:
        if args.asyncr != True:
            r = session.get(url)
            r.html.render()
        else:
            r = asession.run(lambda url=url: rendering(url))[0]
        r.encoding = r.apparent_encoding
        source = r.html.html

    if r.status_code >= 400:
        print(str(r.status_code) + ':' + url)
        return

    # detect default index
    if re.search('/$', url) is not None:
        for index in ['index.html', 'index.htm']:
            idx = url + index
            res = requests.head(idx, allow_redirects=False) if args.noscript == True else session.head(idx, allow_redirects=False)
            if res.status_code == 200 or res.status_code == 302:
                url = idx
                break

    soup = BeautifulSoup(source, 'html5lib')

    tmp = urlparse(url)

    if args.progress == True:
        print(f"{tmp.geturl()} ({r.status_code})")

    # get parts
    get_elements(soup, tmp, 'img', 'src')
    get_elements(soup, tmp, 'link', 'href')
    get_elements(soup, tmp, 'script', 'src')

    if args.mirror != '':
        savefile(url, r.text)

    # recurse
    if args.recursive == True:
        for a in soup.find_all('a'):
            uri = urlparse(a.get('href'))

            if uri.scheme.lower() == 'mailto':
                continue

            if uri.netloc != '' and uri.netloc != base_url.netloc:
                continue

            if (uri.path == '' and uri.query == ''):
                continue

            if (re.match('^\./', uri.path)):
                uri = uri._replace(path=re.sub('^\./', '', uri.path))

            if uri.path == '':
                uri = uri._replace(path='/')
            elif re.match('^\.\./', uri.path) is not None:
                uri = urlparse(urljoin(tmp.geturl(), uri.path))

            url = base_url._replace(path=uri.path, query=uri.query, fragment=uri.fragment).geturl()
            url = re.sub('/+\.?$', '/', url)

            crawl(url)

def main():
    global args, base_url, cache_url, session

    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--async', action='store_true', dest='asyncr', help='Async crawling')
    parser.add_argument('-m', '--mirror', nargs='?', default='', help='Mirroring path')
    parser.add_argument('-n', '--noscript', action='store_true', help='Noscript')
    parser.add_argument('-p', '--progress', action='store_true', help='Progress crawling')
    parser.add_argument('-r', '--recursive', action='store_true', help='Crawl recursive')
    parser.add_argument('url', nargs='?', help='URL')
    args = parser.parse_args()

    if args.mirror != '':
        args.mirror = os.path.expanduser(args.mirror) if re.match('~', args.mirror) else os.path.abspath(args.mirror)

    if args.noscript != True:
        session = HTMLSession() if args.asyncr != True else AsyncHTMLSession()

    base_url = urlparse(args.url)

    # remove fragment
    base_url = base_url._replace(fragment='')

    if base_url.path == '':
        base_url = base_url._replace(path='/')

    crawl(base_url.geturl())

    if args.mirror == '':
        cache_url.sort()
        for url in cache_url:
            print(url)

if __name__ == '__main__':
    args = None
    base_url = None
    cache_url = []
    session = None
    main()
