# ============================================================
#  File: reconforge/recon.py
# ============================================================
import re
import ssl
import json
import socket
import threading
import concurrent.futures as cf
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from .utils import Logger, host_of, normalize_url

requests.packages.urllib3.disable_warnings()

# ------------------------------------------------------------------
#  Common ports / services
# ------------------------------------------------------------------
COMMON_PORTS = {
    20: "ftp-data", 21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp",
    53: "dns", 67: "dhcp", 68: "dhcp", 69: "tftp", 80: "http",
    110: "pop3", 111: "rpcbind", 119: "nntp", 123: "ntp", 135: "msrpc",
    137: "netbios-ns", 138: "netbios-dgm", 139: "netbios-ssn", 143: "imap",
    161: "snmp", 162: "snmptrap", 179: "bgp", 194: "irc", 389: "ldap",
    443: "https", 445: "microsoft-ds", 465: "smtps", 500: "isakmp",
    514: "syslog", 515: "printer", 543: "klogin", 544: "kshell",
    548: "afpovertcp", 554: "rtsp", 587: "submission", 631: "ipp",
    636: "ldaps", 646: "ldp", 873: "rsync", 902: "vmware",
    989: "ftps-data", 990: "ftps", 993: "imaps", 995: "pop3s",
    1025: "nfs-or-iis", 1080: "socks", 1194: "openvpn", 1433: "mssql",
    1434: "mssql-m", 1521: "oracle", 1701: "l2tp", 1723: "pptp",
    1883: "mqtt", 2049: "nfs", 2082: "cpanel", 2083: "cpanel-ssl",
    2181: "zookeeper", 2375: "docker", 2376: "docker-ssl",
    2483: "oracle", 3000: "dev-http", 3128: "squid", 3260: "iscsi",
    3306: "mysql", 3389: "rdp", 3690: "svn", 4000: "dev-http",
    4443: "https-alt", 5000: "upnp", 5432: "postgresql", 5555: "adb",
    5601: "kibana", 5672: "amqp", 5900: "vnc", 5901: "vnc",
    5984: "couchdb", 6379: "redis", 6443: "kubernetes",
    7001: "weblogic", 7077: "spark", 8000: "http-alt", 8008: "http-alt",
    8080: "http-proxy", 8081: "http-alt", 8086: "influxdb",
    8088: "http-alt", 8443: "https-alt", 8500: "consul",
    8888: "http-alt", 9000: "http-alt", 9001: "tor-or-http",
    9042: "cassandra", 9090: "http-alt", 9092: "kafka",
    9200: "elasticsearch", 9300: "elasticsearch", 9418: "git",
    10000: "webmin", 11211: "memcached", 27017: "mongodb",
    27018: "mongodb", 28017: "mongodb-web", 50000: "sap",
    50070: "hadoop", 61616: "activemq",
}

TOP_1000 = list(range(1, 1025))


# ------------------------------------------------------------------
#  DNS
# ------------------------------------------------------------------
def dns_lookup(host: str) -> dict:
    result = {"host": host, "ip": None, "reverse": None, "records": {}}
    try:
        result["ip"] = socket.gethostbyname(host)
    except Exception as e:
        result["error"] = str(e)
        return result
    try:
        result["reverse"] = socket.gethostbyaddr(result["ip"])[0]
    except Exception:
        pass

    try:
        import dns.resolver  # optional
        for rtype in ("A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"):
            try:
                ans = dns.resolver.resolve(host, rtype, lifetime=4)
                result["records"][rtype] = [str(r).strip('"') for r in ans]
            except Exception:
                pass
    except ImportError:
        pass
    return result


# ------------------------------------------------------------------
#  Subdomain enumeration
# ------------------------------------------------------------------
DEFAULT_SUBDOMAINS = [
    "www", "mail", "remote", "blog", "webmail", "server", "ns1", "ns2",
    "smtp", "secure", "vpn", "m", "shop", "ftp", "mail2", "test",
    "portal", "ns", "ww1", "host", "support", "dev", "web", "bbs",
    "mx", "email", "cloud", "1", "2", "3", "mail1", "dns", "api",
    "cdn", "app", "admin", "beta", "staging", "stage", "demo", "git",
    "gitlab", "github", "jenkins", "ci", "cd", "jira", "confluence",
    "wiki", "docs", "status", "monitor", "grafana", "kibana", "prometheus",
    "db", "mysql", "postgres", "redis", "mongo", "elastic", "kafka",
    "auth", "sso", "login", "account", "accounts", "id", "oauth",
    "static", "assets", "img", "images", "media", "video", "files",
    "download", "downloads", "upload", "uploads", "backup", "old",
    "new", "v1", "v2", "v3", "internal", "intranet", "extranet",
    "partner", "partners", "client", "clients", "customer", "crm",
    "erp", "hr", "finance", "sales", "marketing", "analytics",
    "metrics", "log", "logs", "trace", "debug", "sandbox", "lab",
    "proxy", "gateway", "router", "fw", "firewall", "lb", "edge",
    "us", "eu", "asia", "uk", "de", "fr", "in", "au", "ca",
    "us-east-1", "us-west-2", "eu-west-1", "ap-south-1",
    "origin", "origin-www", "direct", "legacy", "tmp", "temp",
    "dev-api", "staging-api", "test-api", "api-v1", "api-v2",
    "mobile", "ios", "android", "wap", "sms", "push", "notify",
    "pay", "payment", "payments", "checkout", "billing", "invoice",
    "store", "cart", "orders", "order", "ship", "shipping",
    "help", "helpdesk", "ticket", "tickets", "forum", "community",
    "chat", "live", "meet", "conference", "zoom", "teams",
    "news", "press", "events", "careers", "jobs", "about", "contact",
    "search", "catalog", "catalogue", "products", "product",
    "s3", "storage", "bucket", "backups", "archive", "archives",
    "ns3", "ns4", "dns1", "dns2", "resolver", "anycast",
]


def enumerate_subdomains(domain: str, logger: Logger,
                         wordlist: list | None = None,
                         threads: int = 80,
                         timeout: float = 2.0) -> list:
    words = wordlist or DEFAULT_SUBDOMAINS
    found = []
    logger.step(f"Subdomain enumeration ({len(words)} candidates)")

    def check(sub):
        fqdn = f"{sub}.{domain}"
        try:
            socket.setdefaulttimeout(timeout)
            ip = socket.gethostbyname(fqdn)
            return {"name": fqdn, "ip": ip}
        except Exception:
            return None

    with cf.ThreadPoolExecutor(max_workers=threads) as pool:
        for res in pool.map(check, words):
            if res:
                found.append(res)
                logger.ok(f"  + {res['name']}  →  {res['ip']}")

    logger.ok(f"Subdomains discovered: {len(found)}")
    return sorted(found, key=lambda x: x["name"])


# ------------------------------------------------------------------
#  Port scanning
# ------------------------------------------------------------------
def _grab_banner(host: str, port: int, timeout: float = 1.5) -> str:
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(timeout)
            try:
                s.sendall(b"\r\n")
            except Exception:
                pass
            try:
                data = s.recv(256)
                return data.decode("utf-8", "ignore").strip().replace("\n", " ")[:120]
            except Exception:
                return ""
    except Exception:
        return ""


def scan_ports(host: str, logger: Logger,
               ports: list | None = None,
               threads: int = 300,
               timeout: float = 1.0,
               grab_banners: bool = True) -> list:
    port_list = ports or sorted(COMMON_PORTS.keys())
    logger.step(f"Port scan on {host} ({len(port_list)} ports)")

    open_ports = []
    lock_ = threading.Lock()

    def probe(port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                rc = s.connect_ex((host, port))
                if rc == 0:
                    svc = COMMON_PORTS.get(port, "unknown")
                    banner = _grab_banner(host, port) if grab_banners else ""
                    entry = {
                        "port": port,
                        "state": "open",
                        "service": svc,
                        "banner": banner,
                    }
                    with lock_:
                        open_ports.append(entry)
                        logger.ok(f"  + {port}/tcp open  {svc}"
                                  + (f"  [{banner[:50]}]" if banner else ""))
                    return entry
        except Exception:
            pass
        return None

    with cf.ThreadPoolExecutor(max_workers=threads) as pool:
        list(pool.map(probe, port_list))

    open_ports.sort(key=lambda x: x["port"])
    closed = len(port_list) - len(open_ports)
    logger.ok(f"Open ports: {len(open_ports)}   Closed/Filtered: {closed}")

    return {
        "host": host,
        "scanned": len(port_list),
        "open": open_ports,
        "closed": closed,
        "all_ports": [{"port": p, "state": "open" if any(o["port"] == p for o in open_ports) else "closed",
                       "service": COMMON_PORTS.get(p, "unknown")} for p in port_list],
    }


# ------------------------------------------------------------------
#  Technology fingerprinting (Wappalyzer-style, static)
# ------------------------------------------------------------------
SIGNATURES = [
    # --- Web servers / infra
    {"name": "nginx", "cats": ["Web servers"], "headers": {"Server": r"nginx"} },
    {"name": "Apache", "cats": ["Web servers"], "headers": {"Server": r"Apache"} },
    {"name": "Apache Tomcat", "cats": ["Web servers", "Java"], "headers": {"Server": r"Tomcat"}},
    {"name": "IIS", "cats": ["Web servers"], "headers": {"Server": r"Microsoft-IIS"}},
    {"name": "LiteSpeed", "cats": ["Web servers"], "headers": {"Server": r"LiteSpeed"}},
    {"name": "Caddy", "cats": ["Web servers"], "headers": {"Server": r"Caddy"}},
    {"name": "OpenResty", "cats": ["Web servers"], "headers": {"Server": r"openresty"}},
    {"name": "Cloudflare", "cats": ["CDN", "Security"], "headers": {"Server": r"cloudflare", "CF-RAY": r".*"}},
    {"name": "Amazon CloudFront", "cats": ["CDN"], "headers": {"Via": r"CloudFront", "X-Amz-Cf-Id": r".*"}},
    {"name": "Akamai", "cats": ["CDN"], "headers": {"Server": r"AkamaiGHost"}},
    {"name": "Fastly", "cats": ["CDN"], "headers": {"X-Served-By": r"cache-", "Fastly-Debug-Digest": r".*"}},
    {"name": "Varnish", "cats": ["Caching"], "headers": {"X-Varnish": r".*", "Via": r"varnish"}},
    {"name": "Gunicorn", "cats": ["Web servers", "Python"], "headers": {"Server": r"gunicorn"}},
    {"name": "Werkzeug", "cats": ["Web servers", "Python"], "headers": {"Server": r"Werkzeug"}},
    {"name": "uvicorn", "cats": ["Web servers", "Python"], "headers": {"Server": r"uvicorn"}},

    # --- Languages / frameworks via headers
    {"name": "PHP", "cats": ["Programming languages"], "headers": {"X-Powered-By": r"PHP"}},
    {"name": "ASP.NET", "cats": ["Web frameworks"], "headers": {"X-Powered-By": r"ASP\.NET", "X-AspNet-Version": r".*"}},
    {"name": "Express", "cats": ["Web frameworks", "Node.js"], "headers": {"X-Powered-By": r"Express"}},
    {"name": "Next.js", "cats": ["Web frameworks", "Node.js"], "headers": {"X-Powered-By": r"Next\.js", "X-Nextjs-Cache": r".*"}},
    {"name": "Nuxt.js", "cats": ["Web frameworks", "Node.js"], "headers": {"X-Powered-By": r"Nuxt"}},
    {"name": "Drupal", "cats": ["CMS"], "headers": {"X-Generator": r"Drupal", "X-Drupal-Cache": r".*"}},
    {"name": "Ruby on Rails", "cats": ["Web frameworks"], "headers": {"X-Powered-By": r"Phusion Passenger", "Server": r"Passenger"}},
    {"name": "Google Web Server", "cats": ["Web servers"], "headers": {"Server": r"gws"}},

    # --- Cookies
    {"name": "PHP", "cats": ["Programming languages"], "cookies": {"PHPSESSID": r".*"}},
    {"name": "Java", "cats": ["Programming languages"], "cookies": {"JSESSIONID": r".*"}},
    {"name": "ASP.NET", "cats": ["Web frameworks"], "cookies": {"ASP.NET_SessionId": r".*"}},
    {"name": "Laravel", "cats": ["Web frameworks", "PHP"], "cookies": {"laravel_session": r".*", "XSRF-TOKEN": r".*"}},
    {"name": "Django", "cats": ["Web frameworks", "Python"], "cookies": {"csrftoken": r".*", "sessionid": r".*"}},
    {"name": "WordPress", "cats": ["CMS"], "cookies": {"wordpress_": r".*", "wp-settings": r".*"}},
    {"name": "Shopify", "cats": ["E-commerce"], "cookies": {"_shopify_": r".*"}},
    {"name": "Cloudflare", "cats": ["CDN", "Security"], "cookies": {"__cfduid": r".*", "__cf_bm": r".*"}},
    {"name": "Google Analytics", "cats": ["Analytics"], "cookies": {"_ga": r".*", "_gid": r".*"}},

    # --- HTML / JS fingerprints
    {"name": "WordPress", "cats": ["CMS"], "html": [r"wp-content", r"wp-includes", r"/wp-json"]},
    {"name": "WooCommerce", "cats": ["E-commerce"], "html": [r"woocommerce", r"wc-ajax"]},
    {"name": "Elementor", "cats": ["Page builders"], "html": [r"elementor"]},
    {"name": "Drupal", "cats": ["CMS"], "html": [r"sites/default/files", r"drupalSettings", r"/core/misc/drupal"]},
    {"name": "Joomla", "cats": ["CMS"], "html": [r"/media/jui/", r"com_content", r"joomla"]},
    {"name": "Magento", "cats": ["E-commerce"], "html": [r"Magento", r"mage/cookies", r"/static/version"]},
    {"name": "Shopify", "cats": ["E-commerce"], "html": [r"cdn\.shopify\.com", r"Shopify\.theme"]},
    {"name": "Wix", "cats": ["Site builders"], "html": [r"static\.wixstatic\.com", r"wix\.com"]},
    {"name": "Squarespace", "cats": ["Site builders"], "html": [r"static1\.squarespace\.com", r"squarespace\.com"]},
    {"name": "Webflow", "cats": ["Site builders"], "html": [r"webflow\.com", r"data-wf-"]},
    {"name": "Ghost", "cats": ["CMS", "Blog"], "html": [r"ghost\.org", r"ghost-url"]},
    {"name": "HubSpot", "cats": ["Marketing"], "html": [r"hs-scripts\.com", r"hubspot"]},
    {"name": "Salesforce", "cats": ["CRM"], "html": [r"salesforce\.com", r"force\.com"]},
    {"name": "Bootstrap", "cats": ["UI frameworks"], "html": [r"bootstrap(\.min)?\.(css|js)", r"col-(xs|sm|md|lg)"]},
    {"name": "Tailwind CSS", "cats": ["UI frameworks"], "html": [r"tailwind", r"class=\"[^\"]*\b(flex|grid|px-\d|text-\w+-\d)"]},
    {"name": "jQuery", "cats": ["JavaScript libraries"], "html": [r"jquery(\.min)?\.js", r"jQuery\.(extend|fn)"], "script_src": [r"jquery"]},
    {"name": "React", "cats": ["JavaScript frameworks"], "html": [r"react(-dom)?(\.production)?(\.min)?\.js", r"data-reactroot", r"__REACT_DEVTOOLS"]},
    {"name": "Vue.js", "cats": ["JavaScript frameworks"], "html": [r"vue(\.runtime)?(\.min)?\.js", r"data-v-[0-9a-f]{8}"]},
    {"name": "Angular", "cats": ["JavaScript frameworks"], "html": [r"ng-version=", r"angular(\.min)?\.js"]},
    {"name": "Next.js", "cats": ["JavaScript frameworks"], "html": [r"/_next/static", r"__NEXT_DATA__"]},
    {"name": "Nuxt.js", "cats": ["JavaScript frameworks"], "html": [r"/_nuxt/", r"__NUXT__"]},
    {"name": "Svelte", "cats": ["JavaScript frameworks"], "html": [r"svelte-[0-9a-z]{6}", r"__svelte"]},
    {"name": "Alpine.js", "cats": ["JavaScript frameworks"], "html": [r"alpine(\.min)?\.js", r"x-data="]},
    {"name": "Google Font API", "cats": ["Font scripts"], "html": [r"fonts\.googleapis\.com", r"fonts\.gstatic\.com"]},
    {"name": "Font Awesome", "cats": ["Font scripts"], "html": [r"font-?awesome", r"fa-[a-z]+"]},
    {"name": "Google Analytics", "cats": ["Analytics"], "html": [r"google-analytics\.com/analytics\.js", r"gtag\(", r"googletagmanager\.com/gtag"]},
    {"name": "Google Tag Manager", "cats": ["Tag managers"], "html": [r"googletagmanager\.com/gtm\.js", r"GTM-[A-Z0-9]+"]},
    {"name": "Facebook Pixel", "cats": ["Analytics"], "html": [r"connect\.facebook\.net", r"fbq\("]},
    {"name": "Hotjar", "cats": ["Analytics"], "html": [r"static\.hotjar\.com", r"hj\("]},
    {"name": "Sentry", "cats": ["Error monitoring"], "html": [r"sentry-cdn\.com", r"@sentry/browser"]},
    {"name": "Stripe", "cats": ["Payment processors"], "html": [r"js\.stripe\.com", r"Stripe\("]},
    {"name": "PayPal", "cats": ["Payment processors"], "html": [r"paypal\.com/sdk", r"paypalobjects\.com"]},
    {"name": "reCAPTCHA", "cats": ["Security"], "html": [r"google\.com/recaptcha", r"g-recaptcha"]},
    {"name": "hCaptcha", "cats": ["Security"], "html": [r"hcaptcha\.com", r"h-captcha"]},
    {"name": "Cloudflare Turnstile", "cats": ["Security"], "html": [r"challenges\.cloudflare\.com/turnstile"]},
    {"name": "Disqus", "cats": ["Comment systems"], "html": [r"disqus\.com", r"disqus_thread"]},
    {"name": "Intercom", "cats": ["Live chat"], "html": [r"widget\.intercom\.io", r"intercomSettings"]},
    {"name": "Zendesk", "cats": ["Live chat"], "html": [r"zdassets\.com", r"zendesk"]},
    {"name": "Crisp", "cats": ["Live chat"], "html": [r"client\.crisp\.chat"]},
    {"name": "Tawk.to", "cats": ["Live chat"], "html": [r"embed\.tawk\.to"]},
    {"name": "Cloudflare CDN", "cats": ["CDN"], "html": [r"cdnjs\.cloudflare\.com"]},
    {"name": "jsDelivr", "cats": ["CDN"], "html": [r"cdn\.jsdelivr\.net"]},
    {"name": "unpkg", "cats": ["CDN"], "html": [r"unpkg\.com"]},
    {"name": "Modernizr", "cats": ["JavaScript libraries"], "html": [r"modernizr"]},
    {"name": "Lodash", "cats": ["JavaScript libraries"], "html": [r"lodash(\.min)?\.js"]},
    {"name": "Moment.js", "cats": ["JavaScript libraries"], "html": [r"moment(\.min)?\.js"]},
    {"name": "Axios", "cats": ["JavaScript libraries"], "html": [r"axios(\.min)?\.js"]},
    {"name": "GSAP", "cats": ["JavaScript libraries"], "html": [r"gsap(\.min)?\.js", r"TweenMax"]},
    {"name": "Swiper", "cats": ["JavaScript libraries"], "html": [r"swiper(\.min)?\.(js|css)"]},
    {"name": "AOS", "cats": ["JavaScript libraries"], "html": [r"aos\.(js|css)", r"data-aos="]},
    {"name": "Open Graph", "cats": ["Miscellaneous"], "html": [r'property="og:']},
    {"name": "PWA", "cats": ["Miscellaneous"], "html": [r'rel="manifest"']},
    {"name": "HTTP/3", "cats": ["Miscellaneous"], "headers": {"Alt-Svc": r"h3"}},
    {"name": "HSTS", "cats": ["Security"], "headers": {"Strict-Transport-Security": r".*"}},
    {"name": "CSP", "cats": ["Security"], "headers": {"Content-Security-Policy": r".*"}},
]


def fingerprint(url: str, logger: Logger) -> dict:
    logger.step("Technology fingerprinting")
    session = requests.Session()
    session.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/122.0 Safari/537.36 ReconForge/1.0"),
    })
    session.verify = False

    try:
        r = session.get(url, timeout=20, allow_redirects=True)
    except Exception as e:
        logger.err(f"Fingerprint fetch failed: {e}")
        return {"url": url, "technologies": [], "headers": {}, "server": None}

    headers = {k: v for k, v in r.headers.items()}
    cookies = {c.name: c.value for c in r.cookies}
    html = r.text or ""
    soup = BeautifulSoup(html, "html.parser")

    script_srcs = " ".join(
        s.get("src", "") for s in soup.find_all("script")
    )
    link_hrefs = " ".join(
        l.get("href", "") for l in soup.find_all("link")
    )
    metas = " ".join(
        f'{m.get("name","")}={m.get("content","")}'
        for m in soup.find_all("meta")
    )
    generator = ""
    g = soup.find("meta", attrs={"name": re.compile("^generator$", re.I)})
    if g:
        generator = g.get("content", "")

    haystack = f"{html}\n{script_srcs}\n{link_hrefs}\n{metas}"

    found = []
    for sig in SIGNATURES:
        evidence = []
        conf = 0

        for hk, pattern in sig.get("headers", {}).items():
            for actual_k, actual_v in headers.items():
                if actual_k.lower() == hk.lower() and re.search(pattern, actual_v, re.I):
                    evidence.append(f"header {actual_k}: {actual_v}")
                    conf = max(conf, 100)

        for ck, pattern in sig.get("cookies", {}).items():
            for actual_k in cookies:
                if actual_k.lower().startswith(ck.lower()) and re.search(pattern, cookies[actual_k], re.I):
                    evidence.append(f"cookie {actual_k}")
                    conf = max(conf, 90)

        for pattern in sig.get("html", []):
            if re.search(pattern, haystack, re.I):
                evidence.append(f"html ~ /{pattern}/")
                conf = max(conf, 80)

        for pattern in sig.get("script_src", []):
            if re.search(pattern, script_srcs, re.I):
                evidence.append(f"script ~ /{pattern}/")
                conf = max(conf, 80)

        if sig["name"] == "WordPress" and generator and "wordpress" in generator.lower():
            evidence.append(f"meta generator: {generator}")
            conf = 100

        if evidence:
            found.append({
                "name": sig["name"],
                "categories": sig["cats"],
                "confidence": conf,
                "evidence": "; ".join(sorted(set(evidence))[:3]),
            })

    # de-duplicate by name, keeping highest confidence
    merged = {}
    for f in found:
        if f["name"] not in merged or f["confidence"] > merged[f["name"]]["confidence"]:
            merged[f["name"]] = f
    techs = sorted(merged.values(), key=lambda x: (-x["confidence"], x["name"]))

    for t in techs:
        logger.ok(f"  + {t['name']:<28} {t['confidence']:>3}%  ({', '.join(t['categories'])})")

    logger.ok(f"Technologies detected: {len(techs)}")
    return {
        "url": url,
        "final_url": r.url,
        "status": r.status_code,
        "server": headers.get("Server"),
        "headers": headers,
        "cookies": list(cookies.keys()),
        "technologies": techs,
    }
