# ============================================================
#  File: reconforge/cloner.py
# ============================================================
import os
import re
import time
import threading
import concurrent.futures as cf
from collections import deque
from urllib.parse import urlparse, urljoin, urlsplit, urlunparse, unquote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from .utils import (
    Logger, ensure_dir, is_asset_url, same_site, sha1_short, safe_filename,
)

requests.packages.urllib3.disable_warnings()

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36 ReconForge/1.0"
)

LINK_TAGS = [
    ("a", "href"),
    ("link", "href"),
    ("script", "src"),
    ("img", "src"),
    ("img", "data-src"),
    ("source", "src"),
    ("source", "srcset"),
    ("video", "src"),
    ("video", "poster"),
    ("audio", "src"),
    ("iframe", "src"),
    ("embed", "src"),
    ("object", "data"),
    ("form", "action"),
    ("input", "src"),
    ("use", "href"),
    ("use", "xlink:href"),
]

CSS_URL_RE = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""", re.I)


class WebsiteCloner:
    """Full recursive website mirror with asset rewriting."""

    def __init__(
        self,
        base_url: str,
        out_dir: str,
        logger: Logger,
        max_pages: int = 200,
        max_depth: int = 5,
        threads: int = 12,
        timeout: int = 20,
        include_external_assets: bool = False,
    ):
        self.base_url = base_url
        self.out_dir = ensure_dir(out_dir)
        self.log = logger
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.threads = threads
        self.timeout = timeout
        self.include_external_assets = include_external_assets

        self.url_map = {}          # absolute url -> local relative path
        self.pages = []            # list of dicts
        self.assets = []           # list of dicts
        self.asset_queue = set()
        self.errors = []
        self._lock = threading.Lock()

        self.session = self._make_session()

    # ------------------------------------------------------------------
    def _make_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({
            "User-Agent": DEFAULT_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        retry = Retry(total=2, backoff_factor=0.4,
                      status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry, pool_connections=32,
                              pool_maxsize=32)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        s.verify = False
        return s

    # ------------------------------------------------------------------
    #  Local path resolution
    # ------------------------------------------------------------------
    def _local_for(self, url: str) -> str:
        with self._lock:
            if url in self.url_map:
                return self.url_map[url]

            split = urlsplit(url)
            path = unquote(split.path or "/")

            if is_asset_url(url):
                ext = os.path.splitext(path)[1] or ".bin"
                local = f"_assets/{sha1_short(url)}{ext}"
            else:
                if path.endswith("/"):
                    path += "index.html"
                elif "." not in os.path.basename(path):
                    path += "/index.html"
                local = path.lstrip("/") or "index.html"

            self.url_map[url] = local
            return local

    @staticmethod
    def _rel(from_local: str, to_local: str) -> str:
        base = os.path.dirname(from_local) or "."
        rel = os.path.relpath(to_local, base)
        return rel.replace(os.sep, "/")

    def _abs_path(self, local: str) -> str:
        return os.path.join(self.out_dir, local.replace("/", os.sep))

    def _write(self, local: str, data: bytes):
        full = self._abs_path(local)
        ensure_dir(os.path.dirname(full))
        with open(full, "wb") as f:
            f.write(data)

    # ------------------------------------------------------------------
    #  Rewriting
    # ------------------------------------------------------------------
    def _rewrite_html(self, html: str, page_url: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        page_local = self._local_for(page_url)

        for tag, attr in LINK_TAGS:
            for el in soup.find_all(tag):
                val = el.get(attr)
                if not val or val.startswith(("data:", "javascript:", "mailto:",
                                              "tel:", "#", "about:")):
                    continue

                if attr == "srcset":
                    parts = []
                    for chunk in val.split(","):
                        chunk = chunk.strip()
                        if not chunk:
                            continue
                        bits = chunk.split()
                        u = bits[0]
                        absu = urljoin(page_url, u)
                        if self._in_scope(absu):
                            local = self._local_for(absu)
                            bits[0] = self._rel(page_local, local)
                            self._queue_asset(absu)
                        parts.append(" ".join(bits))
                    el[attr] = ", ".join(parts)
                    continue

                absu = urljoin(page_url, val)
                if not self._in_scope(absu):
                    continue
                local = self._local_for(absu)
                el[attr] = self._rel(page_local, local)
                if is_asset_url(absu):
                    self._queue_asset(absu)

        # inline <style> blocks
        for style in soup.find_all("style"):
            if style.string:
                style.string = self._rewrite_css_text(style.string, page_url,
                                                      page_local)
        return str(soup)

    def _rewrite_css_text(self, text: str, css_url: str, css_local: str) -> str:
        def repl(m):
            quote, u = m.group(1), m.group(2)
            if u.startswith(("data:", "http://", "https://", "//")):
                if u.startswith("//"):
                    absu = "https:" + u
                elif u.startswith(("http://", "https://")):
                    absu = u
                else:
                    return m.group(0)
            else:
                absu = urljoin(css_url, u)
            if not self._in_scope(absu):
                return m.group(0)
            local = self._local_for(absu)
            self._queue_asset(absu)
            return f"url({quote}{self._rel(css_local, local)}{quote})"

        return CSS_URL_RE.sub(repl, text)

    def _in_scope(self, url: str) -> bool:
        if url.startswith(("data:", "javascript:", "mailto:", "tel:", "blob:")):
            return False
        if same_site(url, self.base_url):
            return True
        return bool(self.include_external_assets and is_asset_url(url))

    def _queue_asset(self, url: str):
        with self._lock:
            self.asset_queue.add(url)

    # ------------------------------------------------------------------
    #  Fetching
    # ------------------------------------------------------------------
    def _fetch(self, url: str):
        try:
            r = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            return r
        except Exception as e:
            with self._lock:
                self.errors.append({"url": url, "error": str(e)})
            return None

    # ------------------------------------------------------------------
    #  Crawl
    # ------------------------------------------------------------------
    def crawl(self):
        self.log.step(f"Mirroring {self.base_url}")
        visited = set()
        queue = deque([(self.base_url, 0)])
        visited.add(self.base_url)

        while queue and len(self.pages) < self.max_pages:
            url, depth = queue.popleft()

            r = self._fetch(url)
            if r is None:
                self.log.warn(f"  ✗ unreachable: {url}")
                continue
            if r.status_code >= 400:
                self.log.warn(f"  ✗ HTTP {r.status_code}: {url}")
                continue

            ctype = r.headers.get("Content-Type", "").lower()
            if "html" not in ctype and "xhtml" not in ctype:
                continue

            page_local = self._local_for(url)
            rewritten = self._rewrite_html(r.text, url)
            self._write(page_local, rewritten.encode("utf-8", "ignore"))

            size = len(rewritten)
            self.pages.append({
                "url": url,
                "local": page_local,
                "status": r.status_code,
                "size": size,
                "depth": depth,
                "title": self._title(r.text),
            })
            self.log.ok(f"  [{len(self.pages):>3}] {url}  →  {page_local}  "
                        f"({size/1024:.1f} KB)")

            if depth >= self.max_depth:
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                link = urljoin(url, a["href"])
                link = link.split("#")[0]
                if not link or link in visited:
                    continue
                if not same_site(link, self.base_url):
                    continue
                if is_asset_url(link):
                    self._queue_asset(link)
                    continue
                visited.add(link)
                queue.append((link, depth + 1))

        self.log.ok(f"Pages mirrored: {len(self.pages)}")
        return self.pages

    @staticmethod
    def _title(html: str) -> str:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        return re.sub(r"\s+", " ", m.group(1)).strip()[:120] if m else ""

    # ------------------------------------------------------------------
    #  Assets
    # ------------------------------------------------------------------
    def download_assets(self):
        urls = sorted(self.asset_queue)
        if not urls:
            self.log.info("No assets queued.")
            return

        self.log.step(f"Downloading {len(urls)} assets")
        done = 0
        total = len(urls)
        lock = threading.Lock()

        def worker(u):
            nonlocal done
            r = self._fetch(u)
            if r is None or r.status_code >= 400:
                return
            local = self._local_for(u)
            content = r.content

            if local.lower().endswith(".css"):
                try:
                    text = content.decode(r.encoding or "utf-8", "ignore")
                    text = self._rewrite_css_text(text, u, local)
                    content = text.encode("utf-8", "ignore")
                except Exception:
                    pass

            self._write(local, content)
            with lock:
                done += 1
                self.assets.append({
                    "url": u,
                    "local": local,
                    "size": len(content),
                    "type": r.headers.get("Content-Type", ""),
                })
                if done % 10 == 0 or done == total:
                    self.log.info(f"  assets {done}/{total}")

        with cf.ThreadPoolExecutor(max_workers=self.threads) as pool:
            list(pool.map(worker, urls))

        self.log.ok(f"Assets saved: {len(self.assets)}")

    # ------------------------------------------------------------------
    def run(self) -> dict:
        t0 = time.time()
        self.crawl()
        self.download_assets()
        elapsed = time.time() - t0

        total_bytes = sum(a["size"] for a in self.assets) + \
                      sum(p["size"] for p in self.pages)
        entry = self._local_for(self.base_url)

        self.log.step("Mirror complete")
        self.log.ok(f"  pages={len(self.pages)}  assets={len(self.assets)}  "
                    f"size={total_bytes/1024:.1f} KB  time={elapsed:.1f}s")

        return {
            "base_url": self.base_url,
            "out_dir": self.out_dir,
            "entry": entry,
            "pages": self.pages,
            "assets": self.assets,
            "errors": self.errors,
            "total_bytes": total_bytes,
            "elapsed": round(elapsed, 2),
        }
