"""
调用 http://www.ip33.com/ 的接口解析域名，避免 DNS 污染
顺便添加 GitHub 的域名解析
"""
import datetime
import json
from collections import defaultdict
from typing import Optional

import requests

API = "http://api.ip33.com/dns/resolver"

HOSTS = [
    "api.themoviedb.org", "image.tmdb.org", "www.themoviedb.org",
    "alive.github.com", "api.github.com", "assets-cdn.github.com",
    "avatars.githubusercontent.com", "avatars0.githubusercontent.com",
    "avatars1.githubusercontent.com", "avatars2.githubusercontent.com",
    "avatars3.githubusercontent.com", "avatars4.githubusercontent.com",
    "avatars5.githubusercontent.com", "camo.githubusercontent.com",
    "central.github.com", "cloud.githubusercontent.com", "codeload.githubusercontent.com",
    "collector.github.com", "desktop.githubusercontent.com",
    "favicons.githubusercontent.com", "gist.github.com",
    "github-cloud.s3.amazonaws.com", "github-com.s3.amazonaws.com",
    "github-production-release-asset-2e65be.s3.amazonaws.com",
    "github-production-repository-file-5c1aeb.s3.amazonaws.com",
    "github-production-user-asset-6210df.s3.amazonaws.com",
    "github.blog", "github.com", "github.community", "github.githubassets.com",
    "github.global.ssl.fastly.net", "github.io", "github.map.fastly.net",
    "githubstatus.com", "live.github.com", "media.githubusercontent.com",
    "objects.githubusercontent.com", "pipelines.actions.githubusercontent.com",
    "raw.githubusercontent.com", "user-images.githubusercontent.com",
    "vscode.dev", "education.github.com", "private-user-images.githubusercontent.com",
]

DNS_PROVIDERS = ["156.154.70.1", "208.67.222.222"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def check_ip_reachable(ip: str, domain: str, timeout: float = 5.0) -> bool:
    """通过HTTP HEAD请求检查IP是否可达"""
    try:
        # 使用IP直连，Host header指明域名（用于虚拟主机场景）
        url = f"http://{ip}"
        response = requests.head(url, headers={"Host": domain}, timeout=timeout, allow_redirects=True)
        # 2xx, 3xx 都算可达
        reachable = 200 <= response.status_code < 400
        status = "√" if reachable else "×"
        print(f"[{status}] IP:{ip} ({domain}) {'可达' if reachable else '不可达'} [HTTP {response.status_code}]")
        return reachable
    except requests.exceptions.Timeout:
        print(f"[×] IP:{ip} ({domain}) 连接超时")
        return False
    except requests.exceptions.ConnectionError:
        print(f"[×] IP:{ip} ({domain}) 连接被拒绝")
        return False
    except Exception as e:
        print(f"[×] IP:{ip} ({domain}) 检查异常: {e}")
        return False


def filter_reachable_ips(ips: list[str], domain: str) -> list[str]:
    """过滤出可达的IP"""
    return [ip for ip in ips if check_ip_reachable(ip, domain)]


def resolve_domain(domain: str, dns: str) -> Optional[list[str]]:
    """解析域名返回IP列表，解析失败返回None"""
    try:
        response = requests.post(
            API,
            data={"domain": domain, "type": "A", "dns": dns},
            headers=HEADERS,
            timeout=10,
        )
        return [record["ip"] for record in json.loads(response.text)["record"]]
    except Exception as e:
        print(f"解析 DNS 出错 ({domain}, {dns}): {e}")
        return None


def write_hosts_file(host_dict: dict[str, list[str]], filepath: str = "hosts.txt") -> None:
    """写入 hosts 信息到文件"""
    lines = ["###start###\n"]
    for host, ips in host_dict.items():
        lines.extend(f"{ip}\t{host}\n" for ip in ips)
    lines.append(f"###最后更新时间:{datetime.datetime.now():%Y-%m-%d %H:%M:%S}###\n")
    lines.append("###end###\n")

    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(lines)


def main() -> None:
    """主函数"""
    result_dict: dict[str, list[str]] = defaultdict(list)

    for host, dns in [(h, d) for h in HOSTS for d in DNS_PROVIDERS]:
        ips = resolve_domain(host, dns)
        if not ips:
            continue

        reachable_ips = filter_reachable_ips(ips, host)
        if reachable_ips:
            result_dict[host].extend(reachable_ips)

    write_hosts_file(dict(result_dict))
    print(f"写入完成，共 {len(result_dict)} 个域名")


if __name__ == "__main__":
    main()
