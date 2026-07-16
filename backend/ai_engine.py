"""
AI Engine for Customer 360.

Two layers, by design:
1. Deterministic signal extraction (health score, sentiment, risk/opportunity flags,
   priority, next-best-action) — computed from the merged data with transparent rules.
   This works with zero external dependencies and zero API keys, so the app is fully
   functional out of the box.
2. Optional LLM narrative layer — if OPENAI_API_KEY is set in the environment, the
   deterministic signals are handed to the LLM to produce a natural-language executive
   summary. If no key is set, a template-based summary is generated instead so the
   feature never breaks in a demo/evaluation environment.

This split matters for a real deployment: the numbers driving risk/health scoring
should never depend on a third-party API being available or an LLM "reading the
data correctly" — they should be auditable. The LLM's job is narration, not judgment.
"""
import os
import json
from datetime import datetime

SENTIMENT_SCORE = {"positive": 1, "neutral": 0, "negative": -1}


def compute_health_score(customer, tickets, emails, usage, payments):
    score = 70  # baseline

    open_high = sum(1 for t in tickets if t["priority"] == "High" and t["status"] != "Resolved")
    score -= open_high * 10

    escalated = sum(1 for t in tickets if t["status"] == "Escalated")
    score -= escalated * 8

    neg_emails = sum(1 for e in emails if e["sentiment"] == "negative")
    pos_emails = sum(1 for e in emails if e["sentiment"] == "positive")
    score += (pos_emails - neg_emails) * 4

    if len(usage) >= 2:
        trend = usage[-1]["active_users"] - usage[0]["active_users"]
        if trend > 0:
            score += min(trend, 15)
        else:
            score += max(trend, -15)

    overdue = sum(1 for p in payments if p["status"] == "Overdue")
    score -= overdue * 12

    if customer["account_status"] == "At Risk":
        score -= 10
    elif customer["account_status"] == "Healthy":
        score += 5

    return max(0, min(100, round(score)))


def compute_sentiment(emails, slack_notes):
    if not emails:
        return "Neutral"
    total = sum(SENTIMENT_SCORE.get(e["sentiment"], 0) for e in emails)
    avg = total / len(emails)
    if avg > 0.25:
        return "Positive"
    if avg < -0.25:
        return "Negative"
    return "Mixed"


def detect_risks(customer, tickets, emails, payments, crm_notes):
    risks = []
    open_high = [t for t in tickets if t["priority"] == "High" and t["status"] != "Resolved"]
    if open_high:
        risks.append(f"{len(open_high)} unresolved high-priority support ticket(s), incl. \u201c{open_high[0]['subject']}\u201d")

    overdue = [p for p in payments if p["status"] == "Overdue"]
    if overdue:
        risks.append(f"{len(overdue)} overdue invoice(s) on the account")

    neg_emails = [e for e in emails if e["sentiment"] == "negative"]
    if len(neg_emails) >= 2:
        risks.append("Multiple recent emails carry negative sentiment \u2014 possible dissatisfaction pattern")

    for n in crm_notes:
        if "leaving" in n["note"].lower() or "competitor" in n["note"].lower():
            risks.append(f"CRM/Slack signal: {n['note']}")

    try:
        renewal = datetime.strptime(customer["renewal_date"], "%Y-%m-%d")
        days_to_renewal = (renewal - datetime.now()).days
        if 0 <= days_to_renewal <= 45:
            risks.append(f"Renewal due in {days_to_renewal} day(s) \u2014 no expansion signal logged yet" if customer["crm_stage"] != "Expansion Discussion" else f"Renewal due in {days_to_renewal} day(s)")
        elif days_to_renewal < 0:
            risks.append(f"Renewal date passed {abs(days_to_renewal)} day(s) ago \u2014 verify contract status")
    except Exception:
        pass

    if customer["crm_stage"] == "At Risk":
        risks.append("Account explicitly flagged At Risk in CRM")

    return risks[:5]


def detect_opportunities(customer, crm_notes, slack_notes, usage):
    opps = []
    for n in crm_notes + slack_notes:
        low = n["note"].lower()
        if "expansion" in low or "new office" in low or "referral" in low or "seats" in low:
            opps.append(n["note"])

    if len(usage) >= 2 and usage[-1]["active_users"] > usage[0]["active_users"] * 1.15:
        opps.append("Active user count has grown meaningfully over the past 8 weeks \u2014 candidate for a seat/tier upsell conversation")

    if customer["crm_stage"] == "Expansion Discussion":
        opps.append("Already in active expansion discussion per CRM stage")

    if customer["account_status"] == "Healthy" and customer["segment"] != "Enterprise":
        opps.append("Healthy account on a sub-Enterprise plan \u2014 candidate for a segment upgrade conversation")

    return opps[:5]


def priority_level(health_score, risks):
    if health_score < 45 or len(risks) >= 3:
        return "Critical"
    if health_score < 65 or len(risks) >= 1:
        return "High"
    if health_score < 80:
        return "Medium"
    return "Low"


def next_best_action(customer, risks, opportunities, tickets):
    escalated = [t for t in tickets if t["status"] == "Escalated"]
    if escalated:
        return f"Escalate internally and personally follow up on: \u201c{escalated[0]['subject']}\u201d before any other outreach."
    if any("renewal" in r.lower() for r in risks):
        return "Book a renewal conversation this week; bring a usage summary and address open risks before the renewal date."
    if any("overdue" in r.lower() for r in risks):
        return "Loop in billing/AR to resolve the overdue invoice before the next CSM touchpoint \u2014 unresolved billing issues erode trust fast."
    if opportunities:
        return "Reach out with an expansion/upsell proposal \u2014 usage and CRM signals both support the conversation."
    if risks:
        return "Schedule a proactive check-in call to address the flagged risk signals before they compound."
    return "Account is healthy \u2014 maintain the standard quarterly business review cadence."


def generate_summary(customer, signals, use_llm=False):
    """
    Produces the natural-language executive summary.
    If OPENAI_API_KEY is present in the environment AND use_llm=True, calls the
    OpenAI API. Otherwise falls back to a deterministic template — this keeps the
    app fully demoable without any API key configured.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if use_llm and api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            prompt = f"""You are a Customer Success analyst. Write a concise 3-4 sentence executive
summary of this account for a CSM/Sales rep about to reach out. Be specific, cite the
signals given, and end with a clear recommended tone for the outreach.

Customer: {customer['name']} ({customer['industry']}, {customer['segment']})
Health Score: {signals['health_score']}/100
Sentiment: {signals['sentiment']}
Risks: {signals['risks']}
Opportunities: {signals['opportunities']}
Priority: {signals['priority']}
"""
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=220,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return _template_summary(customer, signals) + f"\n\n(LLM call failed, showing template summary: {e})"
    return _template_summary(customer, signals)


def _template_summary(customer, signals):
    tone = {
        "Critical": "This account needs urgent attention",
        "High": "This account needs proactive attention soon",
        "Medium": "This account is stable but has open items worth monitoring",
        "Low": "This account is in good health",
    }[signals["priority"]]

    risk_txt = f" Key risks: {'; '.join(signals['risks'][:2])}." if signals["risks"] else " No material risks detected in the current data."
    opp_txt = f" Opportunity signal: {signals['opportunities'][0]}." if signals["opportunities"] else ""

    return (
        f"{tone}. {customer['name']} is a {customer['segment']} account in {customer['industry']} "
        f"with a health score of {signals['health_score']}/100 and {signals['sentiment'].lower()} recent sentiment."
        f"{risk_txt}{opp_txt} Recommended next step: {signals['next_best_action']}"
    )


def analyze_customer(customer, crm_notes, tickets, emails, slack_notes, usage, payments, use_llm=False):
    health_score = compute_health_score(customer, tickets, emails, usage, payments)
    sentiment = compute_sentiment(emails, slack_notes)
    risks = detect_risks(customer, tickets, emails, payments, crm_notes)
    opportunities = detect_opportunities(customer, crm_notes, slack_notes, usage)
    priority = priority_level(health_score, risks)
    nba = next_best_action(customer, risks, opportunities, tickets)

    signals = {
        "health_score": health_score,
        "sentiment": sentiment,
        "risks": risks,
        "opportunities": opportunities,
        "priority": priority,
        "next_best_action": nba,
    }
    signals["summary"] = generate_summary(customer, signals, use_llm=use_llm)
    return signals
