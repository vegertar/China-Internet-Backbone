#!/usr/bin/env python

import logging

cache = {}

def get_routes(ip, ip_parser):
    import json
    import sys

    if sys.version_info[0] >= 3:
        from urllib.parse import urlparse
        from urllib.request import urlopen
    else:
        from urlparse import urlparse
        from urllib2 import urlopen

    routes = []

    try:
        r = urlopen('http://g3.letv.com/r?uip={uip}&format={format}'.format(uip=ip, format=1), timeout=5)
        data = json.load(r)
        source = data['remote']

        for node in data.get('nodelist', []):
            try:
                urlparser = urlparse(node['location'])
                source = urlparser[1]
                url = '{scheme}://{netloc}{path}'.format(scheme=urlparser[0], netloc=source, path='/explore-route.json')
                if url in cache:
                    continue

                logging.info("Downloading routes from {}".format(url))
                r = urlopen(url, timeout=5)
                text = r.read()
                status_code = r.getcode()
                logging.info("Status code {}, content size {}".format(status_code, len(text)))

                if status_code == 200:
                    cache[url] = True
                    routes.append((
                        {
                            'source': source,
                            'ipinfo': ip_parser(source),
                        },
                        json.loads(text)
                    ))
            except Exception as e:
                logging.error(e, exc_info=True)

    except Exception as e:
        logging.error(e, exc_info=True)

    return routes


def parse_ip(api, ip):
    import json
    import sys

    if sys.version_info[0] >= 3:
        from urllib.request import urlopen
    else:
        from urllib2 import urlopen

    try:
        r = urlopen(api + '/' + ip)
        if r.getcode() == 200:
            return json.load(r)
    except Exception as e:
        logging.error(e, exc_info=True)


def parse_routes(routes, ip_parser):
    import tracerouteparser as parser

    for (_, route_items) in routes:
        for i in range(len(route_items)):
            result = {}
            trp = parser.TracerouteParser()
            trp.parse_data(route_items[i])

            hops = []
            for hop in trp.hops:
                probes = []
                for probe in hop.probes:
                    probes.append({
                        'ipaddr' : probe.ipaddr,
                        'ipinfo': ip_parser(probe.ipaddr) if probe.ipaddr else None,
                        'rtt': probe.rtt,
                        'anno': probe.anno,
                        'name': probe.name,
                    })

                hops.append(dict(probes=probes))

            route_items[i] = {
                'dest_ip': trp.dest_ip,
                'dest_name': trp.dest_name,
                'dest_ipinfo': ip_parser(trp.dest_ip),
                'hops': hops,
            }


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
