#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import html5lib # noqa
import os
import re
import requests
import sys

from bs4 import BeautifulSoup
from pathlib import Path
from random import randint
from requests_html import HTMLSession, AsyncHTMLSession
from time import sleep
from urllib.parse import urlparse, urljoin

try:
    from excludes import known_thirdparties
except ImportError:
    pass


class HttpError(Exception):
    pass


def savefile(url, src):
    global args

    uri = urlparse(url)

    path = f"{args.mirror}{uri.path}"

    try:
        directory = os.path.dirname(path)
        if not os.path.exists(directory):
            os.makedirs(directory)

        Path(path).write_bytes(src)
    except PermissionError as e:
        print(e, file=sys.stderr)
    except IsADirectoryError:
        savefile(f"{url}/index.tmp", src)


def browse(url):
    global args, session

    r = requests.get(url, stream=True)
    if r.status_code == 200:
        if r.headers['content-type'] == 'text/css':
            m = re.findall(r'url\([\'"]?(.+?)[\'"]?\)', r.text)
            for path in m:
                u = urlparse(urljoin(url, path))

                if u.netloc != '' and u.netloc != base_url.netloc:
                    continue

                ur = u.geturl()

                if ur in cache_url:
                    continue

                cache_url.append(ur)

                try:
                    browse(ur)
                except HttpError as e:
                    print(e, file=sys.stderr)

        if args.mirror != '':
            savefile(url, r.content)

    elif r.status_code >= 400:
        raise HttpError(str(r.status_code) + ': ' + url)

    if args.progress is True:
        print(f"{url} ({r.status_code})")


def get_elements(soup, parser, tag, attr):
    global args, base_url, cache_url, session

    for el in soup.find_all(tag):
        uri = urlparse(el.get(attr))

        # Known third parties
        try:
            if known_thirdparties(uri, tag) is True:
                continue
        except NameError:
            pass

        if uri.netloc != '' and uri.netloc != base_url.netloc:
            continue

        if (uri.path == '' and uri.query == ''):
            continue

        if (re.match(r'^\./', uri.path)):
            uri = uri._replace(path=re.sub(r'^\./', '', uri.path))

        if uri.path == '':
            uri = uri._replace(path='/')
        else:
            uri = urlparse(urljoin(parser.geturl(), uri.path))

        url = base_url._replace(path=uri.path,
                                query=uri.query,
                                fragment=uri.fragment).geturl()
        url = re.sub(r'/+\.?$', '/', url)

        if url in cache_url:
            continue

        cache_url.append(url)

        try:
            browse(url)
        except HttpError as e:
            print(e, file=sys.stderr)


async def rendering(url):
    global session
    r = await session.get(url)
    if re.match('text/html', r.headers['content-type']):
        await r.html.arender()
    return r


def crawl(url):
    global args, base_url, cache_url, session

    if url in cache_url:
        return

    cache_url.append(url)

    r = None
    source = ''

    try:
        if args.noscript is True:
            r = requests.get(url)
            r.encoding = r.apparent_encoding
            source = r.text
        else:
            if args.asyncr is not True:
                r = session.get(url)
                if re.match('text/html', r.headers['content-type']):
                    r.html.render()
            else:
                r = session.run(lambda url=url: rendering(url))[0]
            r.encoding = r.apparent_encoding
            source = r.html.html
    except Exception as e:
        print(e, file=sys.stderr)
        return

    if r.status_code >= 400:
        raise HttpError(str(r.status_code) + ': ' + url)

    if r.url.replace(url, '') == '/':
        url = r.url

    # detect default index
    if re.search('/$', url) is not None:
        for index in ['index.html', 'index.htm']:
            idx = url + index
            res = requests.head(idx, allow_redirects=False)
            if res.status_code == 200 or res.status_code == 302:
                url = idx
                break

    soup = BeautifulSoup(source, 'html5lib')

    tmp = urlparse(url)

    if args.progress is True:
        print(f"{tmp.geturl()} ({r.status_code})")

    # get parts
    get_elements(soup, tmp, 'img', 'src')
    get_elements(soup, tmp, 'link', 'href')
    get_elements(soup, tmp, 'script', 'src')

    if args.mirror != '':
        savefile(url, r.content)

    interval = randint(0, args.interval)
    if interval > 0:
        sleep(interval)

    # recurse
    if args.recursive is True:
        for a in soup.find_all('a'):
            uri = urlparse(a.get('href'))

            if uri.scheme.lower() == 'mailto':
                continue

            if uri.netloc != '' and uri.netloc != base_url.netloc:
                continue

            if (uri.path == '' and uri.query == ''):
                continue

            if (re.match(r'^\./', uri.path)):
                uri = uri._replace(path=re.sub(r'^\./', '', uri.path))

            if uri.path == '':
                uri = uri._replace(path='/')
            else:
                uri = urlparse(urljoin(tmp.geturl(), uri.path))

            url = base_url._replace(path=uri.path,
                                    query=uri.query,
                                    fragment=uri.fragment).geturl()
            url = re.sub(r'/+\.?$', '/', url)

            try:
                crawl(url)
            except HttpError as e:
                print(e, file=sys.stderr)


def main():
    global args, base_url, cache_url, session

    p = argparse.ArgumentParser()
    p.add_argument('-a', '--async', action='store_true', dest='asyncr',
                   help='Async crawling')
    p.add_argument('-i', '--interval', nargs='?', default=0, type=int,
                   help='Crawl interval')
    p.add_argument('-m', '--mirror', nargs='?', default='',
                   help='Mirroring path')
    p.add_argument('-n', '--noscript', action='store_true',
                   help='Noscript')
    p.add_argument('-p', '--progress', action='store_true',
                   help='Progress crawling')
    p.add_argument('-r', '--recursive', action='store_true',
                   help='Crawl recursive')
    p.add_argument('url', nargs='?', help='URL')
    args = p.parse_args()

    if args.mirror != '':
        args.mirror = (os.path.expanduser(args.mirror)
                       if re.match('~', args.mirror)
                       else os.path.abspath(args.mirror))

    if args.noscript is not True:
        session = (HTMLSession()
                   if args.asyncr is not True
                   else AsyncHTMLSession())

    base_url = urlparse(args.url)

    # remove fragment
    base_url = base_url._replace(fragment='')

    if base_url.path == '':
        base_url = base_url._replace(path='/')

    crawl(base_url.geturl())

    if args.mirror == '':
        cache_url.sort()
        print('-- Crawled -------------------------------------')
        for url in cache_url:
            print(url)


if __name__ == '__main__':
    args = None
    base_url = None
    cache_url = []
    session = None
    try:
        main()
    except KeyboardInterrupt:
        sys.exit()
