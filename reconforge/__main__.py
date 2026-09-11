# ============================================================
#  File: reconforge/__main__.py
#  Entry point:  python -m reconforge <target> [options]
# ============================================================
import os
import sys
import json
import time
import argparse
import traceback
from datetime import datetime

from colorama import Fore, Style, init as _init
_init(autoreset=True)

from . import banner, __version__
from .utils import (
    Logger, normalize_url, host_of, ensure_dir, ts,
    require_authorization, human_size,
)
from . import recon
from .cloner import WebsiteCloner
from . import webui


# ------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(
        prog="reconforge",
        description="RECONFORGE // DEDSEC recon & full-site mirror suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python -m reconforge example.com
  python -m reconforge https://example.com --full-ports --max-pages 500
  python -m reconforge example.com --no-clone --no-web
  python -m reconforge example.com --output ./loot --port 9000
        """,
    )
    p.add_argument("target", help="domain or URL to recon & mirror")
    p.add_argument("-o", "--output", default="./reconforge_output",
                   help="output directory (default: ./reconforge_output)")
    p.add_argument("--max-pages", type=int, default=200,
                   help="max pages to mirror (default 200)")
    p.add_argument("--depth", type=int, default=5,
                   help="max crawl depth (default 5)")
    p.add_argument("--threads", type=int, default=12,
                   help="threads for asset downloads (default 12)")
    p.add_argument("--timeout", type=int, default=20,
                   help="HTTP timeout seconds (default 20)")
    p.add_argument("--ports", default=None,
                   help="comma list of ports, or 'top1000' (default: common)")
    p.add_argument("--full-ports", action="store_true",
                   help="scan ports 1-1024")
    p.add_argument("--no-subdomains", action="store_true",
                   help="skip subdomain enumeration")
    p.add_argument("--no-ports", action="store_true",
                   help="skip port scanning")
    p.add_argument("--no-fingerprint", action="store_true",
                   help="skip technology fingerprinting")
    p.add_argument("--no-clone", action="store_true",
                   help="skip website mirroring")
    p.add_argument("--no-web", action="store_true",
                   help="do not launch the web console")
    p.add_argument("--port", type=int, default=8899,
                   help="web console port (default 8899)")
    p.add_argument("--no-browser", action="store_true",
                   help="do not auto-open the browser")
    p.add_argument("--yes", "-y", action="store_true",
                   help="skip the authorization prompt (you confirm you have permission)")
    p.add_argument("--quiet", "-q", action="store_true",
                   help="suppress CLI logs")
    p.add_argument("--version", action="version",
                   version=f"RECONFORGE {__version__} by DEDSEC")
    return p.parse_args()


# ------------------------------------------------------------------
def resolve_ports(args):
    if args.full_ports:
        return recon.TOP_1000
    if args.ports:
        if args.ports.strip().lower() == "top1000":
            return recon.TOP_1000
        out = []
        for chunk in args.ports.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if "-" in chunk:
                a, b = chunk.split("-", 1)
                out.extend(range(int(a), int(b) + 1))
            else:
                out.append(int(chunk))
        return sorted(set(out))
    return sorted(recon.COMMON_PORTS.keys())


# ------------------------------------------------------------------
def run_pipeline(args, logger: Logger) -> dict:
    target = normalize_url(args.target)
    host = host_of(target)

    logger.step(f"Target locked: {target}")
    logger.info(f"Host: {host}")

    started = time.time()
    out_root   = ensure_dir(os.path.abspath(os.path.join(args.output, host)))
    clone_dir  = ensure_dir(os.path.abspath(os.path.join(out_root, "site")))
    logger.info(f"Output dir : {out_root}")
    logger.info(f"Clone dir  : {clone_dir}")

    report = {
        "target": target,
        "host": host,
        "started": datetime.now().isoformat(timespec="seconds"),
        "output_dir": out_root,
        "dns": {},
        "subdomains": [],
        "ports": {"host": host, "scanned": 0, "open": [], "closed": 0, "all_ports": []},
        "technologies": {"url": target, "headers": {}, "technologies": []},
        "clone": {"dir": clone_dir, "entry": "index.html",
                  "pages": [], "assets": [], "errors": [], "total_bytes": 0},
        "logs": [],
    }

    # ---- 1. DNS ---------------------------------------------------
    logger.step("DNS resolution")
    dns = recon.dns_lookup(host)
    report["dns"] = dns
    if dns.get("ip"):
        logger.ok(f"  {host}  →  {dns['ip']}"
                  + (f"  (PTR: {dns['reverse']})" if dns.get("reverse") else ""))
    else:
        logger.err(f"  DNS resolution failed: {dns.get('error')}")

    for rtype, vals in dns.get("records", {}).items():
        logger.data(f"  {rtype:<6} {', '.join(vals[:5])}")

    # ---- 2. Subdomains --------------------------------------------
    if not args.no_subdomains:
        try:
            report["subdomains"] = recon.enumerate_subdomains(host, logger)
        except Exception as e:
            logger.err(f"Subdomain enumeration failed: {e}")
    else:
        logger.info("Subdomain enumeration skipped.")

    # ---- 3. Port scan ---------------------------------------------
    if not args.no_ports:
        try:
            ports = resolve_ports(args)
            report["ports"] = recon.scan_ports(host, logger, ports=ports)
        except Exception as e:
            logger.err(f"Port scan failed: {e}")
    else:
        logger.info("Port scan skipped.")

    # ---- 4. Fingerprint -------------------------------------------
    if not args.no_fingerprint:
        try:
            report["technologies"] = recon.fingerprint(target, logger)
        except Exception as e:
            logger.err(f"Fingerprinting failed: {e}")
    else:
        logger.info("Fingerprinting skipped.")

    # ---- 5. Clone --------------------------------------------------
    if not args.no_clone:
        try:
            cloner = WebsiteCloner(
                base_url=target,
                out_dir=clone_dir,
                logger=logger,
                max_pages=args.max_pages,
                max_depth=args.depth,
                threads=args.threads,
                timeout=args.timeout,
            )
            clone_res = cloner.run()
            report["clone"] = {
                "dir": clone_dir,
                "entry": clone_res["entry"],
                "pages": clone_res["pages"],
                "assets": clone_res["assets"],
                "errors": clone_res["errors"],
                "total_bytes": clone_res["total_bytes"],
            }
        except Exception as e:
            logger.err(f"Cloning failed: {e}")
            traceback.print_exc()
    else:
        logger.info("Cloning skipped.")

    # ---- 6. Wrap up ------------------------------------------------
    elapsed = round(time.time() - started, 2)
    report["duration"] = elapsed
    report["finished"] = datetime.now().isoformat(timespec="seconds")
    report["logs"] = logger.dump()

    report_path = os.path.join(out_root, f"report_{ts()}.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.step("Mission complete")
    logger.ok(f"  Duration      : {elapsed}s")
    logger.ok(f"  Pages         : {len(report['clone']['pages'])}")
    logger.ok(f"  Assets        : {len(report['clone']['assets'])}")
    logger.ok(f"  Subdomains    : {len(report['subdomains'])}")
    logger.ok(f"  Open ports    : {len(report['ports']['open'])}")
    logger.ok(f"  Technologies  : {len(report['technologies']['technologies'])}")
    logger.ok(f"  Report        : {report_path}")
    logger.ok(f"  Mirror        : {clone_dir}")

    return report


# ------------------------------------------------------------------
def main():
    args = parse_args()

    if not args.quiet:
        banner.print_banner(__version__)

    if not require_authorization(args.yes):
        print(Fore.RED + "Authorization not confirmed. Aborting." + Style.RESET_ALL)
        sys.exit(1)

    logger = Logger(verbose=not args.quiet, quiet=False)

    try:
        report = run_pipeline(args, logger)
    except KeyboardInterrupt:
        print(Fore.RED + "\n[!] Interrupted by user." + Style.RESET_ALL)
        sys.exit(130)
    except Exception as e:
        print(Fore.RED + f"\n[!] Fatal error: {e}" + Style.RESET_ALL)
        traceback.print_exc()
        sys.exit(1)

    if not args.no_web:
        print()
        banner.rule()
        banner.print_quote()
        banner.rule()
        try:
            webui.serve(
                report=report,
                clone_dir=report["clone"]["dir"],
                logger=logger,
                port=args.port,
                open_browser=not args.no_browser,
            )
        except KeyboardInterrupt:
            print(Fore.RED + "\n[!] Web console stopped." + Style.RESET_ALL)
    else:
        banner.print_quote()
        print(Fore.GREEN + f"\n[✓] Done. Output: {report['output_dir']}"
              + Style.RESET_ALL)


if __name__ == "__main__":
    main()
