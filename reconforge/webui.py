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

    @app.route("/cloned/")
    @app.route("/cloned/<path:filename>")
    def cloned(filename="index.html"):
        root = app.config["CLONE_DIR"]
        full = os.path.join(root, filename)
        if not os.path.isdir(root):
            logger.warn(f"[webui] CLONE_DIR missing: {root}")
            abort(404)
        if not os.path.isfile(full):
            logger.warn(f"[webui] file not found: {full}")
            abort(404)
        return send_from_directory(root, filename)

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
