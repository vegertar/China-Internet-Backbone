#!/usr/bin/env python

import logging

cache = {}


def coordinate(ip_info):
    return [float(ip_info['Lng']), float(ip_info['Lat'])]


class Point(object):
    def __init__(self, ip_info, **properties):
        for network in ip_info['Networks']:
            properties['AS{}'.format(network['ASN'])] = network['ASName']

        self.type = 'Feature'
        self.geometry = {
            'type': 'Point',
            'coordinates': coordinate(ip_info),
        }
        self.properties = properties

    def update(self, point):
        self.properties.update(point.properties)

    def to_object(self):
        return vars(self)
    
    def __hash__(self):
        return hash('point:' + ','.join([str(c) for c in self.geometry['coordinates']]))


class Line(object):
    def __init__(self, *points, **properties):
        coordinates = []
        for point in points:
            if coordinates:
                last_point = coordinates[-1]
                if hash(last_point) == hash(point):
                    last_point.update(point)
                    continue
            
            coordinates.append(point)

        if len(coordinates) == 1:
            raise Exception('Cannot draw a line')

        self.type = 'Feature'
        self.geometry = {
            'type': 'LineString',
            'coordinates': [point.geometry['coordinates'] for point in coordinates],
        }
        self.properties = properties

    def update(self, line):
        self.properties.update(line.properties)

    def to_object(self):
        return vars(self)

    def __hash__(self):
        s = []
        for item in self.geometry['coordinates']:
            s.extend([str(c) for c in item])

        return hash('line:' + ','.join(s))


 
class GeoJSON(object):
    def __init__(self):
        self.type = "FeatureCollection"
        self.features = {}

    def add_route(self, source, source_info, target, target_info, hops):
        ttl = 0
        last_phases, final_phases = [], []
        if source_info:
            point = self.add_point(source, source_info)
            if point:
                last_phases.append((point, 0, ttl))
        if target_info:
            point = self.add_point(target, target_info)
            if point:
                import sys
                final_phases.append((point, sys.maxsize, ttl))

        for probes in hops:
            ttl += 1

            phases = []
            for probe in probes:
                if not probe:
                    continue

                hop, rtt, hop_info = probe
                point = self.add_point(hop, hop_info)
                if not point:
                    continue

                phases.append((point, rtt, ttl))

            if phases:
                for a in last_phases:
                    for b in phases:
                        self.add_line(a[0], b[0])

                last_phases = phases

        if final_phases:
            for a in last_phases:
                for b in final_phases:
                    self.add_line(a[0], b[0])

    def add_point(self, ip, ip_info, **properties):
        try:
            point = Point(ip_info, **properties)
            k = hash(point)
            v = self.features.get(k)
            if v:
                v.update(point)
            else:
                self.features[k] = point

            return point
        except Exception as err:
            logging.error('add point for {} failed: {}'.format(ip, err), exc_info=True)

    def add_line(self, *points):
        try:
            line = Line(*points)
            k = hash(line)
            v = self.features.get(k)
            if v:
                v.update(line)
            else:
                self.features[k] = line

            return line
        except Exception as err:
            logging.error('add line failed: {}'.format(err), exc_info=True)

    def to_object(self):
        features = []
        for v in self.features.values():
            features.append(v.to_object())

        return {
            'type': self.type,
            'features': features,
        }

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
            return json.loads(r.read().decode('utf8'))
    except Exception as e:
        logging.error(e, exc_info=True)


def parse_traceroute(ip_parser, *items):
    import parser
    from functools import reduce

    for data in items:
        trp = parser.TracerouteParser()
        trp.parse_data(data)

        hops = []
        for hop in trp.hops:
            probes = []
            for probe in hop.probes:
                value = None
                if probe.ipaddr:
                    ipinfo = cache.get(probe.ipaddr)
                    if not ipinfo:
                        ipinfo = ip_parser(probe.ipaddr)
                        cache[probe.ipaddr] = ipinfo
                    value = (probe.ipaddr, probe.rtt, ipinfo)

                probes.append(value)

            hops.append(probes)

        for i in range(-1, -len(hops)-1, -1):
            n = reduce(lambda x, y: int(bool(x)) + int(bool(y)), hops[i])
            if n > 0:
                if i != -1:
                    hops = hops[:i+1]
                break

        yield (trp.dest_ip, hops)


def get_routes(ip, ip_parser):
    import json
    import sys

    if sys.version_info[0] >= 3:
        from urllib.parse import urlparse
        from urllib.request import urlopen
    else:
        from urlparse import urlparse
        from urllib2 import urlopen

    try:
        r = urlopen('http://g3.letv.com/r?uip={uip}&format={format}'.format(uip=ip, format=1), timeout=5)
        data = json.loads(r.read().decode('utf8'))

        for node in data.get('nodelist', []):
            try:
                urlparser = urlparse(node['location'])
                source = urlparser[1]
                url = '{scheme}://{netloc}{path}'.format(scheme=urlparser[0], netloc=source, path='/explore-route.json')
                if url in cache:
                    continue

                logging.info("Downloading routes from {}".format(url))
                r = urlopen(url, timeout=5)
                text = r.read().decode('utf8')
                status_code = r.getcode()
                logging.info("Status code {}, content size {}".format(status_code, len(text)))

                if status_code == 200:
                    cache[url] = True
                    data = json.loads(text)
                    source_info = cache.get(source)
                    if not source_info:
                        source_info = ip_parser(source)
                        cache[source] = source_info

                    for (target, hops) in parse_traceroute(ip_parser, *data):
                        target_info = cache.get(target)
                        if not target_info:
                            target_info = ip_parser(target)
                            cache[target] = target_info

                        yield (source, source_info, target, target_info, hops)
            except Exception as e:
                logging.error(e, exc_info=True)

    except Exception as e:
        logging.error(e, exc_info=True)


def match(patterns, ip_info):
    def get_values(d):
        v = []
        t = type(d)

        if t == dict:
            for item in d.values():
                v.extend(get_values(item))
        elif t == list:
            for item in d:
                v.extend(get_values(item))
        else:
            v.append(str(d))

        return v

    if ip_info:
        values = get_values(ip_info)
        matched = 0

        for pattern in patterns:
            for item in values:
                if pattern.search(item):
                    matched += 1
                    break
        return matched == len(patterns)

    return False


def main():
    import os
    import json
    import pickle
    import re
    from optparse import OptionParser

    parser = OptionParser()
    parser.add_option('-q', '--ip-api', 
                      dest='ip_api', 
                      default='http://127.0.0.1:8080',
                      help='HTTP API to retrieve IP info.')
    parser.add_option('-f', '--file',
                      default='route.pickle',
                      help='Use the pickled routes')
    parser.add_option('-u', '--update',
                      action="store_true",
                      default=False,
                      help='Update routes')
    parser.add_option('--source-network',
                      dest='source_network',
                      action='append',
                      help='Regex of source network pattern')
    parser.add_option('--target-network',
                      dest='target_network',
                      action='append',
                      help='Regex of target network pattern')

    (options, args) = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format='[%(levelname)1.1s %(asctime)s %(module)s:%(lineno)d] %(message)s')

    if not args:
        import explore
        args = explore.targets

    ip_parser = lambda ip: parse_ip(options.ip_api, ip)

    source_network = []
    for pattern in options.source_network:
        logging.info('Using source pattern: ' + pattern)
        source_network.append(re.compile(pattern, re.IGNORECASE))

    target_network = []
    for pattern in options.target_network:
        logging.info('Using target pattern: ' + pattern)
        target_network.append(re.compile(pattern, re.IGNORECASE))

    routes = []
    if not options.update:
        try:
            routes = pickle.load(open(options.file, 'rb'))
        except Exception as e:
            logging.error(e, exc_info=True)

    if not routes:
        logging.info("Fetching routes.")
        for ip in args:
            for route in get_routes(ip, ip_parser):
                routes.append(route)

        logging.info('Dumping routes into {}'.format(options.file))
        tmp_filename = options.file + '.tmp'
        tmp = open(tmp_filename, 'wb')
        pickle.dump(routes, tmp, protocol=2)
        os.rename(tmp_filename, options.file)

    geo_json = GeoJSON()
    for route in routes:
        if not match(source_network, route[1]) or not match(target_network, route[3]):
            continue

        geo_json.add_route(*route)

    print(json.dumps(geo_json.to_object()))


if __name__ == '__main__':
    main()
