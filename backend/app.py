"""ChargeSynth AI HTTP routes; all model and queue computation runs on this server."""
from collections import OrderedDict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from threading import Lock
import uuid
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from .generator import IST, SessionGenerator, Settings, to_csv
from .planning import PlanningSettings, assess
from . import assistant

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def create_app(test_config=None):
    app = Flask(
        __name__,
        template_folder=str(ROOT / "frontend/templates"),
        static_folder=str(ROOT / "frontend/static"),
        static_url_path="/static",
    )
    app.config.update(MAX_CONTENT_LENGTH=16 * 1024, JSON_SORT_KEYS=False)
    if test_config:
        app.config.update(test_config)
    app.json.sort_keys = False
    generator = SessionGenerator()
    runs, run_lock = OrderedDict(), Lock()

    @app.before_request
    def same_origin_json():
        if request.path.startswith("/api/") and request.method == "POST":
            origin = request.headers.get("Origin")
            if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
                return jsonify(error="Cross-origin requests are not accepted."), 403
            if not request.is_json:
                return jsonify(error="Send application/json content."), 415

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'")
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(ValueError)
    def bad_input(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(HTTPException)
    def http_error(error):
        if request.path.startswith("/api/"):
            return jsonify(error=error.description), error.code
        return error

    @app.errorhandler(Exception)
    def unexpected(error):
        if app.testing:
            raise error
        app.logger.error("Request failed: %s", type(error).__name__)
        return jsonify(error="The request could not be completed. Please try again."), 500

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/status")
    def status():
        return jsonify(default_settings=asdict(Settings(start_date=datetime.now(IST).date().isoformat())),
                       default_planning=asdict(PlanningSettings()))

    @app.post("/api/generate")
    def generate():
        settings = Settings.parse(request.get_json())
        result = generator.generate(settings)
        run_id = uuid.uuid4().hex
        result.update(run_id=run_id, download_url="/api/download/" + run_id)
        with run_lock:
            runs[run_id] = result
            while len(runs) > 6:
                runs.popitem(last=False)
        return jsonify(result)

    def get_run(run_id):
        with run_lock:
            result = runs.get(run_id)
        if result is None:
            raise ValueError("This sample has expired. Generate sessions again.")
        return result

    @app.get("/api/download/<run_id>")
    def download(run_id):
        result = get_run(run_id)
        filename = f"ChargeSynth_{result['summary']['sessions']}_sessions.csv"
        return Response("\ufeff" + to_csv(result["rows"]), mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.post("/api/plan")
    def plan():
        body = request.get_json()
        if not isinstance(body, dict):
            raise ValueError("Send a scenario request.")
        current = asdict(Settings.parse(body.get("settings", {})))
        planning = asdict(PlanningSettings.parse(body.get("planning", {})))
        return jsonify(assistant.plan_scenario(body.get("prompt"), current, planning))

    def comparison_request():
        body = request.get_json()
        if not isinstance(body, dict) or not isinstance(body.get("run_id"), str):
            raise ValueError("Generate sessions first.")
        result = get_run(body["run_id"])
        planning = PlanningSettings.parse(body.get("planning", {}))
        return result, assess(generator, result, planning)

    @app.post("/api/assess")
    def assess_options():
        _, assessment = comparison_request()
        return jsonify(assessment)

    @app.post("/api/explain")
    def explain():
        result, assessment = comparison_request()
        return jsonify(**assistant.explain_results(result, assessment), assessment=assessment)

    return app


app = create_app()
