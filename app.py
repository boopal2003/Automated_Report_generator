# app.py -- Flask web UI that calls the LLM orchestrator (PRG + result files)
import sys
import os
import uuid
import json
import glob

# ensure vendored packages are loaded first
BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(BASE_DIR, "packages"))
sys.path.insert(0, BASE_DIR)

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from llm import LLMOrchestrator
from utils.logger import app_logger, exec_logger, sql_error_logger

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret-change-me")

# result files directory (temporary store for PRG)
RESULTS_DIR = os.path.join(BASE_DIR, "logs", "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# instantiate LLM orchestrator once
orch = LLMOrchestrator()


def _save_result(token: str, payload: dict):
    path = os.path.join(RESULTS_DIR, f"{token}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, default=str)


def _load_result(token: str):
    path = os.path.join(RESULTS_DIR, f"{token}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/", methods=["GET"])
def index():
    # If query param id is present, load result for display
    token = request.args.get("id")
    result = None
    if token:
        result = _load_result(token)

    # show latest example tokens for convenience (list recent result files)
    recent = sorted(glob.glob(os.path.join(RESULTS_DIR, "*.json")), key=os.path.getmtime, reverse=True)[:5]
    recent_ids = [os.path.splitext(os.path.basename(p))[0] for p in recent]

    return render_template("index.html", result=result, recent_ids=recent_ids)


@app.route("/query", methods=["POST"])
def query():
    """
    Accept form POST (PRG): form field name expected: 'nl_query'
    Saves result to RESULTS_DIR/<uuid>.json and redirects back to index?id=<uuid>
    """
    user_q = request.form.get("nl_query", "").strip()
    if not user_q:
        flash("Please enter a natural-language query.", "warning")
        return redirect(url_for("index"))

    app_logger.info("Received user query (UI): %s", user_q)

    try:
        result = orch.run_query(user_q)
    except Exception as e:
        app_logger.exception("Orchestrator run failed")
        flash("Internal error while processing the query. Check logs.", "danger")
        token = str(uuid.uuid4())
        _save_result(token, {"ok": False, "error": str(e), "attempts": [], "query": user_q})
        return redirect(url_for("index", id=token))

    if not result.get("ok"):
        app_logger.warning("Query pipeline failed: %s", result.get("attempts"))
        flash("Sorry — I couldn't complete that request. Check logs for details.", "danger")
        # still save the failed attempt for debugging
        token = str(uuid.uuid4())
        _save_result(token, {"ok": False, "error": result.get("error"), "attempts": result.get("attempts"), "query": user_q})
        return redirect(url_for("index", id=token))

    # Save result as JSON and redirect (PRG)
    token = str(uuid.uuid4())
    # include df_records so UI/JS can render charts
    payload = {
        "ok": True,
        "summary": result.get("summary"),
        "table_html": result.get("df_html"),
        "meta": result.get("meta") or {},
        "sql": result.get("sql"),
        "attempts": result.get("attempts"),
        "query": user_q,
        "df_records": result.get("df_records", [])  # list of dicts
    }
    _save_result(token, payload)

    # Optionally log execution summary
    try:
        exec_logger.info("Saved result token=%s query=%s rows=%s", token, user_q, payload["meta"].get("row_count"))
    except Exception:
        app_logger.exception("Failed to write exec log for saved result.")

    return redirect(url_for("index", id=token))

# add to app.py (below the /query route or near health)
from flask import jsonify

@app.route("/api/query", methods=["POST"])
def api_query():
    """
    JSON API for Ajax calls. Accepts either form-encoded or JSON body:
      { "nl_query": "Show package counts..." }
    Returns JSON response with saved token and result payload (no redirect).
    """
    # try JSON first, fall back to form
    payload = {}
    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        payload = {}
    user_q = (payload.get("nl_query") or request.form.get("nl_query") or "").strip()

    if not user_q:
        return jsonify({"ok": False, "error": "Missing nl_query"}), 400

    app_logger.info("Received API query (UI): %s", user_q)

    try:
        result = orch.run_query(user_q)
    except Exception as e:
        app_logger.exception("Orchestrator run failed (api_query)")
        token = str(uuid.uuid4())
        err_payload = {"ok": False, "error": str(e), "attempts": [], "query": user_q}
        _save_result(token, err_payload)
        return jsonify({"ok": False, "error": "Internal error", "token": token}), 500

    # Save and return
    token = str(uuid.uuid4())
    saved = {
        "ok": result.get("ok", False),
        "summary": result.get("summary"),
        "table_html": result.get("df_html"),
        "meta": result.get("meta") or {},
        "sql": result.get("sql"),
        "attempts": result.get("attempts"),
        "query": user_q,
        "df_records": result.get("df_records", []),
    }
    _save_result(token, saved)

    if not result.get("ok"):
        return jsonify({"ok": False, "error": result.get("error"), "token": token, "attempts": result.get("attempts")}), 200

    return jsonify({"ok": True, "token": token, "result": saved}), 200



@app.route("/clear_recent", methods=["POST"])
def clear_recent():
    # delete all stored results (admin convenience)
    for f in glob.glob(os.path.join(RESULTS_DIR, "*.json")):
        try:
            os.remove(f)
        except Exception:
            app_logger.exception("Failed to remove result file: %s", f)
    flash("Cleared recent results.", "info")
    return redirect(url_for("index"))


@app.route("/health", methods=["GET"])
def health():
    """
    Basic health check endpoint: checks DB connectivity and LLM ping.
    Returns JSON status describing components.
    """
    status = {"ok": True, "components": {}}

    # DB check
    try:
        from db import get_connection
        conn = get_connection()
        try:
            conn.close()
        except Exception:
            pass
        status["components"]["db"] = {"ok": True}
    except Exception as e:
        status["ok"] = False
        status["components"]["db"] = {"ok": False, "error": str(e)}

    # LLM check
    try:
        client = orch.client
        resp = client.chat.completions.create(model=orch.model, messages=[{"role": "user", "content": "ping"}], max_tokens=6)
        status["components"]["llm"] = {"ok": True}
    except Exception as e:
        status["ok"] = False
        status["components"]["llm"] = {"ok": False, "error": str(e)}

    return jsonify(status)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7878, debug=False)
