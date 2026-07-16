import os
import sqlite3
from flask import Flask, jsonify, request, render_template, Response
from ai_engine import analyze_customer

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "customer360.db")

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "..", "frontend", "templates"),
    static_folder=os.path.join(BASE_DIR, "..", "frontend", "static"),
)


def get_db():
    if not os.path.exists(DB_PATH):
        from seed_data import build
        build()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


def fetch_customer_bundle(conn, customer_id):
    customer = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not customer:
        return None
    customer = dict(customer)
    crm_notes = rows_to_dicts(conn.execute("SELECT * FROM crm_notes WHERE customer_id=? ORDER BY created_at DESC", (customer_id,)).fetchall())
    tickets = rows_to_dicts(conn.execute("SELECT * FROM support_tickets WHERE customer_id=? ORDER BY created_at DESC", (customer_id,)).fetchall())
    emails = rows_to_dicts(conn.execute("SELECT * FROM emails WHERE customer_id=? ORDER BY created_at DESC", (customer_id,)).fetchall())
    slack_notes = rows_to_dicts(conn.execute("SELECT * FROM slack_notes WHERE customer_id=? ORDER BY created_at DESC", (customer_id,)).fetchall())
    usage = rows_to_dicts(conn.execute("SELECT * FROM product_usage WHERE customer_id=? ORDER BY week ASC", (customer_id,)).fetchall())
    payments = rows_to_dicts(conn.execute("SELECT * FROM payment_history WHERE customer_id=? ORDER BY invoice_date DESC", (customer_id,)).fetchall())
    return {
        "customer": customer, "crm_notes": crm_notes, "tickets": tickets,
        "emails": emails, "slack_notes": slack_notes, "usage": usage, "payments": payments,
    }


def build_timeline(bundle):
    events = []
    for n in bundle["crm_notes"]:
        events.append({"date": n["created_at"], "source": "CRM", "text": n["note"]})
    for t in bundle["tickets"]:
        events.append({"date": t["created_at"], "source": "Support Ticket", "text": f"[{t['priority']}] {t['subject']} ({t['status']})"})
    for e in bundle["emails"]:
        events.append({"date": e["created_at"], "source": "Email", "text": f"{e['subject']} ({e['sentiment']})"})
    for s in bundle["slack_notes"]:
        events.append({"date": s["created_at"], "source": "Slack", "text": s["note"]})
    for p in bundle["payments"]:
        events.append({"date": p["invoice_date"], "source": "Payment", "text": f"Invoice \u2014 ${p['amount']:,} ({p['status']})"})
    events.sort(key=lambda x: x["date"], reverse=True)
    return events


# ---------------- Pages ----------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/customer/<int:customer_id>")
def customer_page(customer_id):
    return render_template("customer.html", customer_id=customer_id)


# ---------------- API ----------------

@app.route("/api/customers")
def api_customers():
    conn = get_db()
    q = request.args.get("q", "").strip().lower()
    status_filter = request.args.get("status", "")
    segment_filter = request.args.get("segment", "")

    customers = rows_to_dicts(conn.execute("SELECT * FROM customers ORDER BY name ASC").fetchall())
    results = []
    for c in customers:
        bundle = fetch_customer_bundle(conn, c["id"])
        signals = analyze_customer(
            bundle["customer"], bundle["crm_notes"], bundle["tickets"],
            bundle["emails"], bundle["slack_notes"], bundle["usage"], bundle["payments"],
        )
        c["health_score"] = signals["health_score"]
        c["priority"] = signals["priority"]
        c["sentiment"] = signals["sentiment"]
        results.append(c)

    if q:
        results = [c for c in results if q in c["name"].lower() or q in c["industry"].lower() or q in c["country"].lower()]
    if status_filter:
        results = [c for c in results if c["account_status"] == status_filter]
    if segment_filter:
        results = [c for c in results if c["segment"] == segment_filter]

    conn.close()
    return jsonify(results)


@app.route("/api/customer/<int:customer_id>")
def api_customer_detail(customer_id):
    conn = get_db()
    bundle = fetch_customer_bundle(conn, customer_id)
    if not bundle:
        conn.close()
        return jsonify({"error": "Customer not found"}), 404

    use_llm = request.args.get("llm", "0") == "1"
    signals = analyze_customer(
        bundle["customer"], bundle["crm_notes"], bundle["tickets"],
        bundle["emails"], bundle["slack_notes"], bundle["usage"], bundle["payments"],
        use_llm=use_llm,
    )
    timeline = build_timeline(bundle)
    conn.close()
    return jsonify({
        "customer": bundle["customer"],
        "signals": signals,
        "timeline": timeline[:20],
        "usage": bundle["usage"],
        "sources": {
            "crm_notes": len(bundle["crm_notes"]),
            "tickets": len(bundle["tickets"]),
            "emails": len(bundle["emails"]),
            "slack_notes": len(bundle["slack_notes"]),
            "payments": len(bundle["payments"]),
        },
    })


@app.route("/api/customer/<int:customer_id>/export")
def api_export_summary(customer_id):
    conn = get_db()
    bundle = fetch_customer_bundle(conn, customer_id)
    if not bundle:
        conn.close()
        return jsonify({"error": "Customer not found"}), 404
    signals = analyze_customer(
        bundle["customer"], bundle["crm_notes"], bundle["tickets"],
        bundle["emails"], bundle["slack_notes"], bundle["usage"], bundle["payments"],
    )
    conn.close()
    c = bundle["customer"]
    text = f"""CUSTOMER 360 SUMMARY
=====================
Account: {c['name']}
Industry: {c['industry']} | Segment: {c['segment']} | Country: {c['country']}
Owner (CSM): {c['owner']}
MRR: ${c['mrr']:,} | Renewal: {c['renewal_date']} | CRM Stage: {c['crm_stage']}

HEALTH SCORE: {signals['health_score']}/100
SENTIMENT: {signals['sentiment']}
PRIORITY: {signals['priority']}

SUMMARY
-------
{signals['summary']}

RISKS
-----
{chr(10).join('- ' + r for r in signals['risks']) if signals['risks'] else 'None detected'}

OPPORTUNITIES
-------------
{chr(10).join('- ' + o for o in signals['opportunities']) if signals['opportunities'] else 'None detected'}

RECOMMENDED NEXT BEST ACTION
-----------------------------
{signals['next_best_action']}
"""
    return Response(text, mimetype="text/plain", headers={
        "Content-Disposition": f"attachment; filename={c['name'].replace(' ', '_')}_summary.txt"
    })


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        from seed_data import build
        build()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
