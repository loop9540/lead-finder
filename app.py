#!/usr/bin/env python3
"""Flask web interface for Lead Finder."""

import os
import threading
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect, url_for,
    jsonify, send_file,
)

import db
from config import OUTPUT_DIR, UPLOAD_DIR
from run import run_discovery, SOURCE_MAP
from export import export_to_excel

app = Flask(__name__)
app.secret_key = "leadfinder-2026"

# Background run state
_run_lock = threading.Lock()
_active_run = {"run_id": None, "progress": []}


def _execute_run(run_id: int, sources: list[str], existing_file: str):
    """Background thread target for running discovery."""
    try:
        db.update_run(run_id, status="running")
        _active_run["progress"] = ["Starting discovery..."]

        def on_progress(msg):
            _active_run["progress"].append(msg)

        leads, meta = run_discovery(sources, existing_file, progress_callback=on_progress)
        db.insert_leads(leads, run_id)
        db.update_run(
            run_id,
            status="completed",
            total_raw=meta["total_raw"],
            total_deduped=meta["total_deduped"],
            output_file=meta["output_file"],
            finished_at=datetime.now().isoformat(),
        )
    except Exception as e:
        db.update_run(
            run_id,
            status="failed",
            error_message=str(e),
            finished_at=datetime.now().isoformat(),
        )
    finally:
        with _run_lock:
            _active_run["run_id"] = None


# --- Routes ---

@app.route("/")
def dashboard():
    stats = db.get_stats()
    runs = db.get_runs(limit=5)
    # Contact stats
    conn = db._conn()
    contact_total = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    contact_with_email = conn.execute(
        "SELECT COUNT(*) FROM contacts WHERE email != ''"
    ).fetchone()[0]
    leads_with_contacts = conn.execute(
        "SELECT COUNT(DISTINCT lead_id) FROM contacts"
    ).fetchone()[0]
    conn.close()
    contact_stats = {
        "total": contact_total,
        "with_email": contact_with_email,
        "leads_matched": leads_with_contacts,
    }
    return render_template("dashboard.html", stats=stats, runs=runs,
                           contact_stats=contact_stats)


@app.route("/leads")
def leads():
    platform = request.args.get("platform", "")
    admin = request.args.get("admin", "")
    source = request.args.get("source", "")
    search = request.args.get("q", "")
    page = int(request.args.get("page", 1))
    per_page = 50

    rows, total = db.get_leads(platform, source, search, admin=admin, page=page, per_page=per_page)
    total_pages = max(1, (total + per_page - 1) // per_page)

    # Get contact counts for each lead
    if rows:
        conn = db._conn()
        lead_ids = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(lead_ids))
        counts = conn.execute(
            f"SELECT lead_id, COUNT(*) as cnt FROM contacts WHERE lead_id IN ({placeholders}) GROUP BY lead_id",
            lead_ids,
        ).fetchall()
        conn.close()
        count_map = {r[0]: r[1] for r in counts}
        for row in rows:
            row["contact_count"] = count_map.get(row["id"], 0)

    return render_template(
        "leads.html",
        leads=rows, total=total, page=page, total_pages=total_pages,
        platform=platform, admin=admin, source=source, search=search,
        platforms=db.get_platforms(), sources=db.get_sources(),
        admins=db.get_admins(),
    )


@app.route("/leads/<int:lead_id>")
def lead_detail(lead_id):
    conn = db._conn()
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if not lead:
        conn.close()
        return "Lead not found", 404
    lead = dict(lead)
    contacts = db.get_contacts_for_lead(lead_id)
    conn.close()
    return render_template("lead_detail.html", lead=lead, contacts=contacts)


@app.route("/contacts")
def contacts():
    search = request.args.get("q", "")
    page = int(request.args.get("page", 1))
    per_page = 50
    rows, total = db.get_contacts(page, per_page, search)
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template(
        "contacts.html",
        contacts=rows, total=total, page=page, total_pages=total_pages,
        search=search,
    )


@app.route("/run", methods=["GET", "POST"])
def run():
    if request.method == "POST":
        with _run_lock:
            if _active_run["run_id"] is not None:
                return redirect(url_for("run_status", run_id=_active_run["run_id"]))

            sources = request.form.getlist("sources")
            if not sources:
                sources = list(SOURCE_MAP.keys())

            existing_file = ""
            if "existing" in request.files:
                f = request.files["existing"]
                if f.filename:
                    os.makedirs(UPLOAD_DIR, exist_ok=True)
                    path = os.path.join(UPLOAD_DIR, f.filename)
                    f.save(path)
                    existing_file = path

            run_id = db.create_run(sources, existing_file)
            _active_run["run_id"] = run_id
            _active_run["progress"] = []

            t = threading.Thread(
                target=_execute_run,
                args=(run_id, sources, existing_file),
                daemon=True,
            )
            t.start()

            return redirect(url_for("run_status", run_id=run_id))

    # GET — add tech_detect to available sources
    all_sources = list(SOURCE_MAP.keys()) + ["tech_detect"]
    active_id = _active_run["run_id"]
    return render_template(
        "run.html", sources=all_sources, active_run_id=active_id,
    )


@app.route("/run/<int:run_id>")
def run_status(run_id):
    r = db.get_run(run_id)
    if not r:
        return "Run not found", 404
    return render_template("run_status.html", run=r)


@app.route("/api/run/<int:run_id>")
def api_run(run_id):
    r = db.get_run(run_id)
    if not r:
        return jsonify({"error": "not found"}), 404
    r["progress"] = _active_run["progress"] if _active_run["run_id"] == run_id else []
    return jsonify(r)


@app.route("/api/stats")
def api_stats():
    return jsonify(db.get_stats())


@app.route("/history")
def history():
    runs = db.get_runs(limit=50)
    return render_template("history.html", runs=runs)


@app.route("/download/<int:run_id>")
def download_run(run_id):
    r = db.get_run(run_id)
    if not r or not r["output_file"]:
        return "No file available", 404
    return send_file(r["output_file"], as_attachment=True)


@app.route("/download/all")
def download_all():
    rows, total = db.get_leads(per_page=100000)
    if not rows:
        return "No leads to download", 404
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{OUTPUT_DIR}/leads_all_{timestamp}.xlsx"
    export_to_excel(rows, path)
    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    db.init_db()
    print("Lead Finder — http://localhost:5001")
    app.run(debug=True, port=5001)
