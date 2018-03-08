#!/usr/bin/env python

targets = [
    # Unicom, China-North
    '202.106.196.115', # BJ
    '202.99.96.68', # TJ
    '202.99.160.68', # HeBei
    '202.99.192.66', # TaiYuan, ShanXi
    '202.99.224.68', # NMG

    # Unicom, China-Middle
    '202.102.224.68', # HeNan
    '218.104.111.114', # HuBei
    '58.20.127.170', # HuNan

    # Unicom, China-South
    '221.7.128.68', # GX
    '210.21.4.130', # GD
    '221.11.132.2', # HaiNan

    # Unicom, China-East
    '210.22.70.3', # SH
    '202.102.128.68', # SD
    '221.6.4.66', # JS
    '218.104.78.2', # AH
    '221.12.1.227', # ZJ
    '58.22.96.66', # FZ
    '220.248.192.12', # JX

    # Unicom, North-West
    '221.7.1.20', # XJ
    '221.207.58.58', # QH
    '221.7.34.10', # GS
    '221.199.12.158', # NX
    '221.11.1.89', # XiAn, ShanXi

    # Unicom, South-West
    '221.13.65.34', # XZ
    '124.161.97.242', # SC
    '221.5.203.98', # CQ
    '221.13.28.234', # GZ
    '221.3.154.61', # YN

    # Unicom, North-East
    '218.7.7.14', # HLJ
    '202.98.0.82', # JL
    '202.96.64.68', # LN
]


def traceroute(host, out, sema):
    import subprocess

    try:
        sema.acquire()
        pipe = subprocess.Popen(["traceroute", "-m", "30", "-U", host],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        data, err = pipe.communicate()
        if pipe.returncode != 0:
            raise Exception(err.decode('utf-8'))

        out.append(data)
    except Exception as e:
        import sys
        sys.stderr.write(str(e))
    finally:
        sema.release()


def report(url, data):
    import requests
    import zlib
    import json

    s = json.dumps(data)

    if not url:
        print(s)
        return

    r = requests.post(url, 
        data=zlib.compress(s),
        headers={"Content-Encoding": "gzip"},
    )
    print(r.text)


def main():
    import sys
    import threading

    params = []
    sema = threading.BoundedSemaphore(value=10) 

    for host in targets:
        out = [] 
        t = threading.Thread(target=traceroute, args=(host, out, sema))
        params.append((out, t))
        t.start()

    results = []
    for out, t in params:
        t.join()
        if out:
            results.append(out[0])

    report(sys.argv[1] if len(sys.argv) > 1 else None, results)


if __name__ == "__main__":
    main()