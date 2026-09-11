# ============================================================
#  File: reconforge/utils.py
# ============================================================
import os
import re
import sys
import json
import socket
import hashlib
import time
from datetime import datetime
from urllib.parse import urlparse, urljoin, urlunparse, urlsplit
from colorama import Fore, Style, init as _init

_init(autoreset=True)

# ------------------------------------------------------------------
#  Logger
# ------------------------------------------------------------------
class Logger:
    """
    Pretty CLI logger that also keeps a structured record list
    so the web UI can replay every step.
    """

    COLORS = {
        "INFO":  Fore.CYAN,
        "OK":    Fore.GREEN,
        "WARN":  Fore.YELLOW,
        "ERR":   Fore.RED,
        "STEP":  Fore.MAGENTA,
        "DATA":  Fore.WHITE,
    }

    def __init__(self, verbose: bool = True, quiet: bool = False):
        self.verbose = verbose
        self.quiet = quiet
        self.records = []
        self.started = time.time()

    # ---- internal ------------------------------------------------
    def _emit(self, level: str, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.records.append({"ts": ts, "level": level, "msg": msg})
        if self.quiet or not self.verbose:
            return
        color = self.COLORS.get(level, Fore.WHITE)
        tag = f"{color}[{level:^4}]{Style.RESET_ALL}"
        print(f"{Fore.WHITE}{Style.DIM}{ts}{Style.RESET_ALL} {tag} {msg}")

    # ---- public --------------------------------------------------
    def info(self, m):  self._emit("INFO", m)
    def ok(self, m):    self._emit("OK",   m)
    def warn(self, m):  self._emit("WARN", m)
    def err(self, m):   self._emit("ERR",  m)
    def step(self, m):  self._emit("STEP", m)
    def data(self, m):  self._emit("DATA", m)

    def dump(self) -> list:
        return list(self.records)


# ------------------------------------------------------------------
#  URL helpers
# ------------------------------------------------------------------
ASSET_EXTS = {
    ".css", ".js", ".mjs", ".jsx", ".ts", ".map",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
    ".ico", ".bmp", ".avif", ".tiff",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp4", ".webm", ".ogg", ".mp3", ".wav", ".mov",
    ".pdf", ".zip", ".rar", ".7z", ".tar", ".gz",
    ".json", ".xml", ".txt", ".csv", ".rss", ".atom",
}


def normalize_url(target: str) -> str:
    """Turn 'example.com' into 'https://example.com/'."""
    target = target.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target):
        target = "https://" + target
    p = urlsplit(target)
    if not p.netloc:
        raise ValueError(f"Invalid target: {target}")
    path = p.path or "/"
    return urlunparse((p.scheme, p.netloc, path, "", p.query, ""))


def host_of(url: str) -> str:
    return urlsplit(url).netloc.split("@")[-1].split(":")[0]


def is_asset_url(url: str) -> bool:
    path = urlsplit(url).path.lower()
    ext = os.path.splitext(path)[1]
    return ext in ASSET_EXTS


def registrable_domain(host: str) -> str:
    """Very small eTLD+1 helper (good enough for scope checks)."""
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    # handle common two-level TLDs
    two_level = {"co.uk", "co.jp", "com.au", "co.in", "com.br", "co.za",
                 "org.uk", "gov.uk", "ac.uk", "com.mx", "co.kr"}
    if ".".join(parts[-2:]) in two_level and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def same_site(a: str, b: str) -> bool:
    return registrable_domain(host_of(a)) == registrable_domain(host_of(b))


def sha1_short(text: str, n: int = 16) -> str:
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:n]


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def human_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.1f}{unit}"
        num /= 1024.0
    return f"{num:.1f}TB"


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._\-]", "_", name)[:120] or "file"


def ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ------------------------------------------------------------------
#  Authorization gate
# ------------------------------------------------------------------
AUTH_BANNER = f"""{Fore.RED}{Style.BRIGHT}
╔══════════════════════════════════════════════════════════════╗
║                    ⚠   L E G A L   N O T I C E   ⚠           ║
╠══════════════════════════════════════════════════════════════╣
║  RECONFORGE performs active reconnaissance, port scanning,   ║
║  technology fingerprinting and full site mirroring.          ║
║                                                              ║
║  Using this tool against systems you do NOT own or have      ║
║  explicit WRITTEN permission to test is ILLEGAL in most      ║
║  jurisdictions and violates computer-misuse laws.            ║
║                                                              ║
║  You are solely responsible for your actions.                ║
╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
"""


def require_authorization(auto_yes: bool = False) -> bool:
    if auto_yes:
        return True
    print(AUTH_BANNER)
    try:
        ans = input(f"{Fore.YELLOW}Type 'I HAVE PERMISSION' to continue: {Style.RESET_ALL}").strip()
    except (EOFError, KeyboardInterrupt):
        return False
    return ans.upper() == "I HAVE PERMISSION"
