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
    '58.22.96.66', # FJ
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

    # Telecom, China-North
    '219.141.136.10', # BJ
    '219.150.32.132', # TJ
    '124.238.251.165', # HeBei
    '219.149.135.188', # TaiYuan, ShanXi
    '219.148.162.31', # NMG

    # Telecom, China-Middle
    '222.85.85.85', # HeNan
    '202.103.24.68', # HuBei
    '222.246.129.80', # HuNan

    # Telecom, China-South
    '202.103.224.68', # GX
    '202.96.128.86', # GD
    '202.100.192.68', # HaiNan

    # Telecom, China-East
    '202.96.209.133', # SH
    '219.146.1.66', # SD
    '218.2.2.2', # JS
    '61.132.163.68', # AH
    '202.101.172.35', # ZJ
    '218.85.157.99', # FJ
    '202.101.224.69', # JX

    # Telecom, North-West
    '61.128.114.133', # XJ
    '202.100.138.68', # QH
    '202.100.64.68', # GS
    '202.100.96.68', # NX
    '218.30.19.40', # XiAn, ShanXi

    # Telecom, South-West
    '202.98.224.68', # XZ
    '61.139.2.69', # SC
    '61.128.192.68', # CQ
    '202.98.192.67', # GZ
    '222.172.200.68', # YN

    # Telecom, North-East
    '219.147.198.230', # HLJ
    '219.149.194.55', # JL
    '59.46.69.66', # LN

    # Mobile, China-North
    '211.136.28.228', # BJ
    '211.137.160.5', # TJ
    '211.138.13.66', # HeBei
    '211.138.106.3', # TaiYuan, ShanXi
    '211.138.91.2', # NMG

    # Mobile, China-Middle
    '211.138.30.66', # HeNan
    '211.137.58.20', # HuBei
    '211.142.210.100', # HuNan

    # Mobile, China-South
    '211.138.240.100', # GX
    '211.136.192.6', # GD
    '221.176.88.95', # HaiNan

    # Mobile, China-East
    '211.136.112.50', # SH
    '211.137.191.26', # SD
    '221.131.143.69', # JS
    '211.138.180.2', # AH
    '211.140.13.188', # ZJ
    '211.138.151.161', # FJ
    '211.141.85.68', # JX

    # Mobile, North-West
    '218.202.152.130', # XJ
    '211.138.75.123', # QH
    '218.203.160.194', # GS

    # Mobile, South-West
    '211.139.73.34', # XZ
    '211.137.82.4', # SC
    '218.201.4.3', # CQ
    '211.139.5.29', # GZ
    '211.139.29.68', # YN

    # Mobile, North-East
    '211.137.241.34', # HLJ
    '211.141.0.99', # JL
    '211.137.32.178', # LN

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


def main():
    import json
    import threading

    params = []
    sema = threading.BoundedSemaphore(value=10) 

    for host in targets:
        if not host:
            continue

        out = [] 
        t = threading.Thread(target=traceroute, args=(host, out, sema))
        params.append((out, t))
        t.start()

    results = []
    for out, t in params:
        t.join()
        if out:
            results.append(out[0])

    if results:
        print(json.dumps(results))


if __name__ == "__main__":
    main()
