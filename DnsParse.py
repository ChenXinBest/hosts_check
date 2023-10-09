# 调用http://www.ip33.com/的接口解析域名，避免dns污染
import datetime
import json
import platform
import requests
from ping3 import ping

# dns解析用到的api
api = "http://api.ip33.com/dns/resolver"

# 待解析的域名
hosts = ["api.themoviedb.org", "image.tmdb.org", "www.themoviedb.org"]

# dns服务商
dnsProvider = ["156.154.70.1", "208.67.222.222"]

# host文件的位置
hostLocate=""


# 批量ping
def pingBatch(ips):
    if ips is not None and type(ips) == list:
        for ip in ips:
            result = pingIp(ip)
            if not result:
                ips.remove(ip)


# ping ip返回ip是否连通
def pingIp(ip) -> bool:
    result = ping(ip)
    if result is not None:
        print(f"[√] IP:{ip}  可以ping通，延迟为{result}毫秒")
        return True
    else:
        print(f"[×] IP:{ip}  无法ping通")
        return False


# 返回host对饮domain的解析结果列表
def analysis(domain, dns) -> list:
    params = {
        "domain": domain,
        "type": "A",
        "dns": dns
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.60"

    }
    try:
        response = requests.post(url=api, data=params, headers=headers)
        html = response.text
        ipDics = json.loads(html)["record"]
        ips = []
        for dic in ipDics:
            ips.append(dic["ip"])
        return ips
    except Exception as e:
        print("解析dns出错：")
        print(e)


# 写入host信息
def hostWritor(hostDic):
    windows = "C:\\Windows\\System32\\drivers\\etc\\hosts"
    linux = "/etc/hosts"
    if hostLocate is not None:
        hostFile = hostLocate
    else:
        hostFile = ""
    # 没有指定操作系统
    if hostFile is None or len(hostLocate) == 0:
        platInfo = platform.platform().upper()
        if "WINDOWS" in platInfo:
            hostFile = windows
        elif "LINUX" in platInfo:
            hostFile = linux
        else:
            print("未能识别当前操作系统，且用户未指定host文件所在目录！")
    origin = ""
    with open(hostFile, "r", encoding="utf-8") as f:
        # 之前是否已经写过dns信息
        flag = False
        for eachLine in f.readlines():
            if r"###start###" in eachLine:
                flag = True
            elif r"###end###" in eachLine:
                flag = False
            else:
                if not flag:
                    origin = origin + eachLine
        # 写入新的host记录
        origin = origin.strip()
        origin = origin + "\n###start###\n"
        for eachHost in hostDic:
            for eachIp in hostDic[eachHost]:
                origin = origin + eachIp + "\t" + eachHost + "\n"
        origin = origin + "###最后更新时间:%s###\n" % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        origin = origin + "###end###\n"
    with open(hostFile, "w", encoding="utf-8") as f:
        f.write(origin)
    with open("hosts.txt","w",encoding="utf-8") as f:
        f.write(origin)


if __name__ == '__main__':
    resultDic = {}
    for host in hosts:
        for dns in dnsProvider:
            records = analysis(host, dns)
            pingBatch(records)
            if records is not None and len(records) > 0:
                if host not in resultDic:
                    resultDic[host] = records
                else:
                    resultDic[host] += records
    hostWritor(resultDic)
