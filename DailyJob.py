# 调用http://www.ip33.com/的接口解析域名，避免dns污染
import datetime
import json
import platform
import requests
from ping3 import ping

# dns解析用到的api
api = "http://api.ip33.com/dns/resolver"

# 待解析的域名
hosts = ["api.themoviedb.org", "image.tmdb.org", "www.themoviedb.org","alive.github.com","api.github.com","assets-cdn.github.com","avatars.githubusercontent.com","avatars0.githubusercontent.com","avatars1.githubusercontent.com","avatars2.githubusercontent.com","avatars3.githubusercontent.com","avatars4.githubusercontent.com","avatars5.githubusercontent.com","camo.githubusercontent.com","central.github.com","cloud.githubusercontent.com","codeload.github.com","collector.github.com","desktop.githubusercontent.com","favicons.githubusercontent.com","gist.github.com","github-cloud.s3.amazonaws.com","github-com.s3.amazonaws.com","github-production-release-asset-2e65be.s3.amazonaws.com","github-production-repository-file-5c1aeb.s3.amazonaws.com","github-production-user-asset-6210df.s3.amazonaws.com","github.blog","github.com","github.community","github.githubassets.com","github.global.ssl.fastly.net","github.io","github.map.fastly.net","githubstatus.com","live.github.com","media.githubusercontent.com","objects.githubusercontent.com","pipelines.actions.githubusercontent.com","raw.githubusercontent.com","user-images.githubusercontent.com","vscode.dev","education.github.com","private-user-images.githubusercontent.com"]

# dns服务商
dnsProvider = ["156.154.70.1", "208.67.222.222"]



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
    origin = ""
    origin = origin + "###start###\n"
    for eachHost in hostDic:
        for eachIp in hostDic[eachHost]:
            origin = origin + eachIp + "\t" + eachHost + "\n"
    origin = origin + "###最后更新时间:%s###\n" % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    origin = origin + "###end###\n"
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
