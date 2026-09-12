# ============================================================
#  File: reconforge/webui.py
# ============================================================
import os
import json
import threading
import webbrowser
from flask import Flask, render_template, send_from_directory, jsonify, abort

from . import banner


def create_app(report: dict, clone_dir: str, logger) -> Flask:
    here = os.path.dirname(os.path.abspath(__file__))
    clone_dir = os.path.abspath(clone_dir)
    app = Flask(
        __name__,
        template_folder=os.path.join(here, "web", "templates"),
        static_folder=os.path.join(here, "web", "static"),
    )
    app.config["REPORT"] = report
    app.config["CLONE_DIR"] = clone_dir

    # ------------------------------------------------------------------
    @app.route("/")
    def dashboard():
        return render_template(
            "dashboard.html",
            report=json.dumps(report),
            report_obj=report,
            quote=banner.random_quote(),
            logo=banner.LOGO,
            version="1.0.0",
        )

    # Files whose *rendered* content is HTML but whose URL extension
    # would otherwise make the browser download them.
    HTML_LIKE_EXTS = {
        ".html", ".htm", ".xhtml", ".shtml",
        ".jsp", ".jspx", ".jspf",
        ".php", ".php3", ".php4", ".php5", ".phtml", ".phps",
        ".asp", ".aspx", ".ascx", ".ashx", ".asmx",
        ".cgi", ".pl", ".py", ".rb",
        ".do", ".action", ".jsf", ".faces",
        ".mvc", ".razor", ".cshtml",
    }

    def _looks_like_html(path: str, peek: int = 512) -> bool:
        try:
            with open(path, "rb") as f:
                head = f.read(peek).lstrip().lower()
        except Exception:
            return False
        if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
            return True
        # any <html ... > within first 200 bytes
        return b"<html" in head[:200]

    @app.route("/cloned/")
    @app.route("/cloned/<path:filename>")
    def cloned(filename="index.html"):
        root = app.config["CLONE_DIR"]
        if not os.path.isdir(root):
            logger.warn(f"[webui] CLONE_DIR missing: {root}")
            abort(404)

        # normalize
        filename = filename.lstrip("/")
        full = os.path.join(root, filename)

        # --- resolve directory-style URLs to their index.html ---
        # 1) /cloned/about/      → about/index.html
        # 2) /cloned/about       → about/index.html (no extension case)
        if os.path.isdir(full):
            idx = os.path.join(full, "index.html")
            if os.path.isfile(idx):
                filename = filename.rstrip("/") + "/index.html"
                full = idx
            else:
                abort(404)

        if not os.path.isfile(full):
            # try filename + "/index.html"
            alt = full.rstrip(os.sep) + os.sep + "index.html"
            if os.path.isfile(alt):
                filename = filename.rstrip("/") + "/index.html"
                full = alt
            else:
                # try filename + ".html"
                alt2 = full + ".html"
                if os.path.isfile(alt2):
                    filename = filename + ".html"
                    full = alt2
                else:
                    logger.warn(f"[webui] not found: {full}")
                    abort(404)

        # --- decide Content-Type ---
        ext = os.path.splitext(full)[1].lower()
        force_html = False
        if ext in HTML_LIKE_EXTS:
            force_html = True
        elif ext in ("", ".bin"):
            # no useful extension → sniff
            force_html = _looks_like_html(full)

        resp = send_from_directory(root, filename)

        if force_html:
            resp.headers["Content-Type"] = "text/html; charset=utf-8"
            # make sure it renders inline instead of downloading
            resp.headers["Content-Disposition"] = "inline"

        return resp

    @app.route("/api/report")
    def api_report():
        return jsonify(app.config["REPORT"])

    @app.route("/api/logs")
    def api_logs():
        return jsonify(logger.dump())

    @app.errorhandler(404)
    def nf(e):
        return ("<body style='background:#05070a;color:#00ff9c;"
                "font-family:monospace;padding:40px'>"
                "<h1>404 // FILE NOT FORGED</h1>"
                "<p>This path does not exist in the mirror.</p>"
                "<a style='color:#00d4ff' href='/'>← back to RECONFORGE</a>"
                "</body>"), 404

    return app


def serve(report: dict, clone_dir: str, logger, port: int = 8899,
          open_browser: bool = True):
    app = create_app(report, clone_dir, logger)
    url = f"http://127.0.0.1:{port}/"
    logger.step(f"Launching RECONFORGE web console at {url}")
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
