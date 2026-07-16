"""
Seed script for the Customer 360 AI App.
Generates realistic dummy data across 6 source systems and merges them
into a single SQLite database (customer360.db) that the Flask app reads from.

Run: python seed_data.py
"""
import sqlite3
import random
from datetime import datetime, timedelta
import os

random.seed(7)
DB_PATH = os.path.join(os.path.dirname(__file__), "customer360.db")

COMPANIES = [
    ("Brightline Logistics", "Logistics", "Singapore", "Growth"),
    ("Novara Retail Group", "E-commerce", "Indonesia", "Enterprise"),
    ("Summit Manufacturing Co", "Manufacturing", "Vietnam", "Growth"),
    ("Vertex Health Systems", "Healthcare", "Philippines", "Enterprise"),
    ("Primewave Fintech", "Fintech", "India", "Growth"),
    ("Northstar EdTech", "EdTech", "Malaysia", "SMB"),
    ("Clearpath Hospitality", "Hospitality", "Thailand", "SMB"),
    ("Orbit Media Studio", "Media", "UAE", "Growth"),
    ("Anchor Real Estate Partners", "Real Estate", "Australia", "Enterprise"),
    ("Pulse Analytics Labs", "SaaS", "Hong Kong", "Growth"),
    ("Swift Freight Solutions", "Logistics", "Singapore", "SMB"),
    ("Crestline Foods", "E-commerce", "India", "SMB"),
]

OWNERS = ["Ananya Rao", "Marcus Tan", "Priya Sharma", "Daniel Wong", "Fatima Al-Sayed"]

CRM_STAGES = ["Onboarding", "Active", "Expansion Discussion", "Renewal Due", "At Risk"]

TICKET_SUBJECTS = [
    ("Card declined at vendor payment", "High"),
    ("Unable to add new approver to workflow", "Medium"),
    ("Question about multi-currency FX rates", "Low"),
    ("Bulk invoice upload failing", "High"),
    ("Request to increase card limit", "Medium"),
    ("Integration with accounting software broke after update", "High"),
    ("How to export monthly spend report", "Low"),
    ("Duplicate transaction appearing in ledger", "Medium"),
]

EMAIL_SNIPPETS = [
    ("Following up on our renewal conversation", "positive"),
    ("Frustrated with the recurring card decline issue", "negative"),
    ("Asking about adding 15 more seats for our new regional office", "positive"),
    ("Requesting a call to discuss pricing before renewal", "neutral"),
    ("Escalating unresolved support ticket from last week", "negative"),
    ("Thanking the team for quick support turnaround", "positive"),
    ("Asking whether the platform supports a new subsidiary entity", "neutral"),
]

SLACK_NOTES = [
    "CSM sync: customer mentioned evaluating a competitor for the renewal.",
    "Sales flagged expansion interest — new APAC office opening Q3.",
    "Support escalation shared in #customer-escalations, still unresolved.",
    "CSM sync: champion (finance lead) is leaving the company end of month.",
    "Onboarding specialist noted slow adoption of the approvals module.",
    "Partnerships team introduced a referral lead from this account.",
    "CSM sync: customer very happy with recent card issuing rollout.",
]

def rand_date(days_back_min, days_back_max):
    today = datetime.now()
    d = today - timedelta(days=random.randint(days_back_min, days_back_max))
    return d.strftime("%Y-%m-%d")

def build():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE customers (
        id INTEGER PRIMARY KEY,
        name TEXT, industry TEXT, country TEXT, segment TEXT,
        owner TEXT, mrr INTEGER, contract_start TEXT, renewal_date TEXT,
        crm_stage TEXT, account_status TEXT
    );
    CREATE TABLE crm_notes (
        id INTEGER PRIMARY KEY, customer_id INTEGER, note TEXT, created_at TEXT
    );
    CREATE TABLE support_tickets (
        id INTEGER PRIMARY KEY, customer_id INTEGER, subject TEXT, priority TEXT,
        status TEXT, created_at TEXT
    );
    CREATE TABLE emails (
        id INTEGER PRIMARY KEY, customer_id INTEGER, subject TEXT, sentiment TEXT, created_at TEXT
    );
    CREATE TABLE slack_notes (
        id INTEGER PRIMARY KEY, customer_id INTEGER, note TEXT, created_at TEXT
    );
    CREATE TABLE product_usage (
        id INTEGER PRIMARY KEY, customer_id INTEGER, week TEXT, active_users INTEGER,
        cards_issued INTEGER, transactions INTEGER
    );
    CREATE TABLE payment_history (
        id INTEGER PRIMARY KEY, customer_id INTEGER, invoice_date TEXT, amount INTEGER,
        status TEXT
    );
    """)

    for i, (name, industry, country, segment) in enumerate(COMPANIES, 1):
        owner = random.choice(OWNERS)
        mrr = random.choice([2500, 4200, 6800, 9500, 12000, 18000, 25000, 32000])
        contract_start = rand_date(200, 700)
        renewal_date = rand_date(-90, 60)  # some overdue-looking, some upcoming
        crm_stage = random.choice(CRM_STAGES)
        account_status = random.choices(["Healthy", "Needs Attention", "At Risk"], weights=[0.5, 0.3, 0.2])[0]
        c.execute("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (i, name, industry, country, segment, owner, mrr, contract_start, renewal_date, crm_stage, account_status))

        for _ in range(random.randint(2, 4)):
            note = f"{random.choice(['QBR', 'Check-in call', 'Kickoff', 'Expansion discussion'])}: {random.choice(['positive engagement', 'requested pricing review', 'flagged adoption concerns', 'discussed new use case'])}."
            c.execute("INSERT INTO crm_notes (customer_id, note, created_at) VALUES (?,?,?)",
                       (i, note, rand_date(5, 180)))

        for _ in range(random.randint(1, 4)):
            subj, prio = random.choice(TICKET_SUBJECTS)
            status = random.choices(["Open", "Resolved", "Escalated"], weights=[0.3, 0.55, 0.15])[0]
            c.execute("INSERT INTO support_tickets (customer_id, subject, priority, status, created_at) VALUES (?,?,?,?,?)",
                       (i, subj, prio, status, rand_date(1, 90)))

        for _ in range(random.randint(2, 4)):
            subj, sentiment = random.choice(EMAIL_SNIPPETS)
            c.execute("INSERT INTO emails (customer_id, subject, sentiment, created_at) VALUES (?,?,?,?)",
                       (i, subj, sentiment, rand_date(1, 60)))

        for _ in range(random.randint(1, 3)):
            note = random.choice(SLACK_NOTES)
            c.execute("INSERT INTO slack_notes (customer_id, note, created_at) VALUES (?,?,?)",
                       (i, note, rand_date(1, 45)))

        base_users = random.randint(5, 80)
        for w in range(8):
            week = (datetime.now() - timedelta(weeks=(7 - w))).strftime("%Y-%m-%d")
            drift = random.randint(-5, 5)
            active_users = max(1, base_users + drift + w)
            c.execute("INSERT INTO product_usage (customer_id, week, active_users, cards_issued, transactions) VALUES (?,?,?,?,?)",
                       (i, week, active_users, random.randint(1, 20), random.randint(50, 900)))

        for _ in range(random.randint(3, 6)):
            status = random.choices(["Paid", "Paid", "Paid", "Overdue"], weights=[0.6, 0.15, 0.15, 0.10])[0]
            c.execute("INSERT INTO payment_history (customer_id, invoice_date, amount, status) VALUES (?,?,?,?)",
                       (i, rand_date(10, 240), mrr, status))

    conn.commit()
    conn.close()
    print(f"Seeded {len(COMPANIES)} customers into {DB_PATH}")

if __name__ == "__main__":
    build()
