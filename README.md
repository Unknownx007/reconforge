# RECONFORGE
### DEDSEC // Recon & Mirror Suite

> *"We are the ghost in the machine."*

Full-spectrum reconnaissance and website mirroring toolkit.
CLI-first, with a local web console for reviewing results.

---

## Features

| Module | What it does |
|---|---|
| **DNS** | A/AAAA/MX/NS/TXT/CNAME/SOA + reverse lookup |
| **Subdomains** | 170+ wordlist, threaded DNS resolution |
| **Port scan** | ~120 common ports (or 1-1024 / custom), banner grabbing |
| **Fingerprint** | Wappalyzer-style: 80+ signatures across headers, cookies, HTML, scripts |
| **Mirror** | Recursive crawl, assets download, link + CSS `url()` rewriting |
| **Web console** | Local Flask dashboard with embedded browser, tabs, full logs |

---

## Install

```bash
git clone https://github.com/Unknownx007/reconforge
cd reconforge
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

*Requires Python 3.9+. Works on Linux, macOS and Windows.*

## Usage

**Warning ! DONT RUN THESE COMMANDS INTO THE 'SUBFOLDER' "reconforge", RUN THESE COMMANDS DIRECLTY (OUTSIDE THE SUBFOLDER) IF YOU DONT KNOW HOW TO USE SCRIPTS AS AN MODULE**
```
# Basic full run
python -m reconforge example.com

# Deep mirror, full port range, custom output
python -m reconforge https://example.com \
    --max-pages 500 --depth 8 --full-ports -o ./loot

# Recon only, no mirror
python -m reconforge example.com --no-clone

# Mirror only, skip scanning
python -m reconforge example.com --no-ports --no-subdomains --no-fingerprint

# Custom ports + web console on port 9000, don't auto-open browser
python -m reconforge example.com --ports 22,80,443,8080-8090 \
    --port 9000 --no-browser

# Skip the authorization prompt (you confirm you have permission)
python -m reconforge example.com -y
```

## Options
```
-o, --output DIR      Output directory (default ./reconforge_output)
--max-pages N         Max pages to mirror          (default 200)
--depth N             Max crawl depth              (default 5)
--threads N           Asset download threads       (default 12)
--timeout N           HTTP timeout in seconds      (default 20)
--ports LIST          Comma list / ranges / top1000
--full-ports          Scan 1–1024
--no-subdomains       Skip subdomain enumeration
--no-ports            Skip port scanning
--no-fingerprint      Skip technology fingerprinting
--no-clone            Skip website mirroring
--no-web              Don't launch the web console
--port N              Web console port             (default 8899)
--no-browser          Don't auto-open the browser
-y, --yes             Skip the authorization prompt
-q, --quiet           Suppress CLI output
--version             Print version
```

## Output layout
```
reconforge_output/
└── example.com/
    ├── site/                     ← mirrored website
    │   ├── index.html
    │   ├── about/index.html
    │   ├── _assets/              ← css/js/img/fonts (sha1-named)
    │   └── ...
    └── report_20250101_120000.json

```

## Web console
After the run, RECONFORGE serves a dark-themed dashboard at
http://127.0.0.1:8899/ with:

- MIRROR — embedded browser showing the cloned site offline

- TECHNOLOGIES — fingerprint table with confidence bars + evidence

- PORTS — open/closed table with service names and banners

- SUBDOMAINS — resolved hostnames + IPs

- PAGES / ASSETS — every mirrored file with size and local path

- HEADERS — raw HTTP response headers

- LOGS — the full colored operation log


# Legal
```
RECONFORGE performs active reconnaissance and full site mirroring.
Running it against systems you do not own or lack explicit written
authorization to test is illegal in most jurisdictions.

The tool displays an authorization gate before every run. You are
solely responsible for your actions.
```
**DEDSEC** is not liable for misuse.

*Crafted by DEDSEC — "We don't break in. We were never locked out."*



## Core Workflow & Interaction

ReconForge runs a five-stage pipeline: normalize the target URL, resolve DNS and enumerate subdomains, scan common ports with banner grabbing, fingerprint technologies via Wappalyzer-style signatures, and mirror the entire site with recursive crawling and asset rewriting. The CLI shows a live, color-coded log of every action, while the local web console (default http://127.0.0.1:8899) presents results in a dark, terminal-inspired dashboard with tabs for mirror, technologies, ports, subdomains, pages/assets, headers, and logs. An embedded browser lets you view the cloned site offline, and every mirrored page and asset is saved locally with relative paths—so it works without network access. An authorization gate appears before each run to enforce ethical use.

---

**Optimization Tip:** You can customize the subdomain wordlist by editing the `DEFAULT_SUBDOMAINS` list inside `reconforge/recon.py`, and add your own technology signatures in the `SIGNATURES` list in the same file. Both are plain Python lists, making them easy to extend.

