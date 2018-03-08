#!/usr/bin/env python

import logging

cache = {}

def todict(obj, classkey=None):
    if isinstance(obj, dict):
        data = {}
        for (k, v) in obj.items():
            data[k] = todict(v, classkey)
        return data
    elif hasattr(obj, "_ast"):
        return todict(obj._ast())
    elif hasattr(obj, "__iter__"):
        return [todict(v, classkey) for v in obj]
    elif hasattr(obj, "__dict__"):
        data = dict([(key, todict(value, classkey)) 
            for key, value in obj.__dict__.items() 
            if not callable(value) and not key.startswith('_')])
        if classkey is not None and hasattr(obj, "__class__"):
            data[classkey] = obj.__class__.__name__
        return data
    else:
        return obj


def get_routes(ip, ip_parser):
    import requests
    import json
    import sys

    if sys.version_info[0] == 3:
        from urllib.parse import urlparse
    else:
        from urlparse import urlparse

    routes = []

    try:
        r = requests.get('http://g3.letv.com/r?uip={uip}&format={format}'.format(uip=ip, format=1), timeout=5000)
        data = json.loads(r.text)
        source = data['remote']

        for node in data.get('nodelist', []):
            try:
                urlparser = urlparse(node['location'])
                source = urlparser[1]
                url = '{scheme}://{netloc}{path}'.format(scheme=urlparser[0], netloc=source, path='/explore-route.json')
                if url in cache:
                    continue

                logging.info("Downloading routes from {}".format(url))
                r = requests.get(url, timeout=5000)
                logging.info("Status code {}, content size {}".format(r.status_code, len(r.text)))

                if r.status_code == 200:
                    cache[url] = True
                    routes.append((
                        {
                            'source': source,
                            'ipinfo': ip_parser(source),
                        },
                        json.loads(r.text)
                    ))
            except Exception as e:
                logging.error(e, exc_info=True)

    except Exception as e:
        logging.error(e, exc_info=True)

    return routes


def parse_ip(api, ip):
    import requests
    import json

    try:
        r = requests.get(api + '/' + ip)
        if r.status_code == 200:
            return json.loads(r.text)
    except Exception as e:
        logging.error(e, exc_info=True)


def parse_routes(routes, ip_parser):
    import tracerouteparser as parser

    for (_, route_items) in routes:
        for i in range(len(route_items)):
            trp = parser.TracerouteParser()
            trp.parse_data(route_items[i])
            trp.dest_ipinfo = ip_parser(trp.dest_ip)

            for hop in trp.hops:
                for probe in hop.probes:
                    if probe.ipaddr:
                        probe.ipinfo = ip_parser(probe.ipaddr)

            route_items[i] = todict(trp)


def main():
    import json
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option('-q', '--ip-api', dest='ip_api', default='http://127.0.0.1:8080')

    (options, args) = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if not args:
        er = __import__('explore-route')
        args = er.targets

    ip_parser = lambda ip: parse_ip(options.ip_api, ip)
    res = []

    for ip in args:
        routes = get_routes(ip, ip_parser)
        parse_routes(routes, ip_parser)
        res.extend(routes)

    if res:
        print(json.dumps(res))


if __name__ == '__main__':
    main()