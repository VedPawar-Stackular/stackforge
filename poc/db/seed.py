"""
Seed script: creates schema, inserts a demo client/project, writes sample docs.

Usage:
    cd poc
    python db/seed.py              # set up DB + write sample docs (no pipeline run)
    python db/seed.py --run-pipeline  # also run the full ingestion pipeline
"""

import argparse
import asyncio
import hashlib
import os
import sys
import uuid

import pg8000.dbapi
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.environ["DATABASE_URL"]

# ─── Sample documents ────────────────────────────────────────────────────────

SAMPLE_SOW = """\
STATEMENT OF WORK
Client: TechCorp Inc.
Project: Customer Portal Redesign
Version: 1.2 | Date: 2026-05-15

1. PROJECT OVERVIEW
TechCorp Inc. requires a redesign of its existing customer portal to improve
usability, modernise the technology stack, and support a growing user base. The
current portal is a legacy PHP application last updated in 2019 and struggles
with performance issues under peak load. The new portal must be scalable,
secure, and maintainable by the internal engineering team.

2. SCOPE OF WORK
The vendor shall deliver a fully functional web-based customer portal covering
the following capabilities:

2.1 User Authentication and Account Management
Users must be able to register, log in, reset passwords, and manage their
profile information. Multi-factor authentication (MFA) is required for
enterprise accounts. Single sign-on (SSO) via the client's existing Azure AD
tenant must be supported.

2.2 Dashboard and Reporting
Each user should see a personalised dashboard upon login. The dashboard must
display recent activity, open support tickets, invoice summaries, and key
account metrics. Managers should be able to export reports in PDF and CSV
formats.

2.3 Support Ticket Management
Users must be able to raise, view, and comment on support tickets. Tickets must
support file attachments (max 25 MB per file). The system must send email
notifications on ticket status changes. SLA tracking should be visible to
end-users.

2.4 Billing and Invoice Management
The portal must integrate with the client's existing Stripe account for payment
processing. Users should be able to view invoice history, download PDFs, and
update payment methods. Automatic payment retries on failed charges must be
configurable by administrators.

2.5 Notifications and Alerts
A configurable notification centre should allow users to opt in or out of
specific alert categories. Notifications must be delivered via email and
in-portal bell icon. Future support for SMS and Slack integrations is
desirable but out of scope for this engagement.

3. NON-FUNCTIONAL REQUIREMENTS
- The portal must support up to 5,000 concurrent users without degradation.
- Page load time for the dashboard must not exceed 2 seconds on a standard
  broadband connection.
- The system must achieve 99.9% uptime SLA.
- All data at rest and in transit must be encrypted using AES-256 and TLS 1.3
  respectively.
- The application must comply with GDPR and CCPA data privacy regulations.
- The codebase must include unit and integration test coverage of at least 80%.

4. ASSUMPTIONS
- TechCorp will provide sandbox access to their Azure AD tenant within two
  weeks of project kick-off.
- The client's Stripe account is already configured; vendor is not responsible
  for Stripe onboarding.
- Content migration from the legacy portal is out of scope unless separately
  agreed in writing.
- The client's infrastructure team will provision the cloud hosting environment.

5. TIMELINE
- Phase 1 (Authentication + Dashboard): 6 weeks
- Phase 2 (Support Tickets + Billing): 8 weeks
- Phase 3 (QA, UAT, Go-Live): 4 weeks
- Total estimated duration: 18 weeks

6. DELIVERABLES
- Source code repository (private GitHub)
- Deployment runbook
- API documentation (OpenAPI spec)
- Test coverage report
- Post-launch support for 30 days
"""

SAMPLE_TRANSCRIPT = """\
MEETING TRANSCRIPT
Project: Customer Portal Redesign — Kick-off Call
Attendees: Sarah (TechCorp PM), James (TechCorp CTO), Priya (Vendor Lead),
           Marcus (Vendor Architect)
Date: 2026-05-22

Sarah: Thanks everyone for joining. I want to make sure we're aligned on
priorities before the team starts. The biggest pain point for our users right
now is the login experience — it takes forever and MFA is confusing.

Priya: Understood. We've planned authentication as Phase 1. One question — the
SOW mentions Azure AD SSO. Do all users need SSO or just enterprise accounts?

James: Good question. Only our enterprise tier customers need SSO. Standard and
free tier users will use email and password with optional MFA.

Marcus: Got it. We'll gate the SSO flow behind the account plan type. That
affects the registration flow too — should free users ever be able to upgrade
to enterprise within the portal itself?

Sarah: Yes, that's actually really important. We lose people because they have
to email sales to upgrade. We want a self-serve upgrade path in Phase 2.

Priya: That wasn't in the original SOW. We'd need to scope that as an
additional requirement — it touches billing, permissions, and the SSO
provisioning flow.

James: Fair, but it's a must-have for us before go-live. Can we fold it into
Phase 2?

Priya: We can try but no promises on timeline — Marcus, thoughts?

Marcus: It's doable but we need to pin down the Stripe integration details
first. Is the client on Stripe Billing or just Stripe Payments?

James: We use Stripe Billing with annual and monthly plans. Customers have
proration enabled.

Marcus: Good, that simplifies things. One concern — the SOW says 5,000
concurrent users. Is that based on actual load data or an estimate?

Sarah: Honest answer — it's a guess. We peak at about 800 concurrent right now
but we're projecting 3x growth next year.

Marcus: OK so realistic peak is probably 2,500–3,000. We'll design for 5,000
as headroom but I want to flag that the infrastructure spec needs to match
that. Who's provisioning the cloud environment?

James: Our ops team will handle AWS provisioning. I'll connect you with Raj,
our DevOps lead.

Priya: Perfect. One more item — the SOW mentions GDPR and CCPA compliance. Do
you have a DPA template, or should we use ours?

Sarah: Legal is handling that. They'll send something over this week. Also —
we need a cookie consent banner on the login page before go-live.

Priya: Noted. That's a small addition but we'll capture it. Any questions on
the dashboard scope?

Sarah: The report export — can we add Excel as a format? PDF and CSV are in
the SOW but our finance team lives in Excel.

Priya: We can add XLSX export. It's straightforward with the libraries we're
using. Consider it included.

Marcus: I want to flag one risk: the 2-second page load requirement for the
dashboard. If the dashboard is pulling live data from multiple sources, we'll
need caching. Can we agree upfront that some metrics can be up to 15 minutes
stale?

Sarah: 15 minutes is fine for aggregate metrics. Real-time status on open
tickets is important though.

Marcus: Understood — ticket status will be live, aggregate metrics will be
cached. We'll document that clearly in the API spec.

James: Last thing from me — the 30-day post-launch support. Does that include
bug fixes for issues we discover in production?

Priya: Yes, critical and high severity bugs are covered. We define critical as
data loss or security issues, high as features broken for more than 10% of
users. Medium and low severity go into a separate maintenance retainer if
you want it.

James: We'll need to talk about that retainer. Can you send a proposal?

Priya: Will do. OK, I think that covers the main items. We'll send meeting
notes with the additional requirements captured: self-serve plan upgrade, XLSX
export, cookie consent banner, and the caching agreement on dashboard metrics.

Sarah: Perfect. Talk next week.
"""

SAMPLE_DOCS = {
    "sample_sow.txt": SAMPLE_SOW,
    "sample_transcript.txt": SAMPLE_TRANSCRIPT,
}

# ─── DB setup ────────────────────────────────────────────────────────────────

def get_conn():
    from urllib.parse import urlparse
    import ssl
    p = urlparse(DB_URL)
    kwargs = {
        "host": p.hostname or "localhost",
        "port": p.port or 5432,
        "user": p.username or "postgres",
        "password": p.password or "",
        "database": p.path.lstrip("/"),
    }
    if "sslmode=require" in DB_URL:
        ctx = ssl.create_default_context()
        kwargs["ssl_context"] = ctx
        kwargs["server_hostname"] = kwargs["host"]
    conn = pg8000.dbapi.connect(**kwargs)
    conn.autocommit = False
    return conn


def run_schema(conn):
    import re
    schema_path = os.path.join(os.path.dirname(__file__), "init.sql")
    with open(schema_path) as f:
        sql = f.read()
    # Strip single-line comments first — pg8000 can choke on non-ASCII chars
    # in decorative comment lines (e.g. -- ─── section headers ───)
    sql = re.sub(r"--[^\n]*", "", sql)
    # Split on semicolons; skip blank fragments
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    cur = conn.cursor()
    for stmt in statements:
        cur.execute(stmt)
    cur.close()
    conn.commit()
    print("Schema applied.")


def seed_db(conn):
    cur = conn.cursor()

    # Check if demo client already exists
    cur.execute("SELECT id FROM clients WHERE name = 'TechCorp Inc.'")
    row = cur.fetchone()
    if row:
        client_id = row[0]
        print(f"Client already exists: {client_id}")
    else:
        client_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO clients (id, name) VALUES (%s, %s)",
            (client_id, "TechCorp Inc."),
        )
        print(f"Created client: {client_id}")

    # Check if demo project already exists
    cur.execute(
        "SELECT id FROM projects WHERE client_id = %s AND name = %s",
        (client_id, "Customer Portal Redesign"),
    )
    row = cur.fetchone()
    if row:
        project_id = row[0]
        print(f"Project already exists: {project_id}")
    else:
        project_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO projects (id, client_id, name, status) VALUES (%s, %s, %s, 'pending')",
            (project_id, client_id, "Customer Portal Redesign"),
        )
        print(f"Created project: {project_id}")

    cur.close()
    conn.commit()
    return client_id, project_id


def write_sample_docs(project_id: str):
    """Write sample text files to sample_docs/ and return their paths."""
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_docs")
    os.makedirs(docs_dir, exist_ok=True)
    paths = []
    for filename, content in SAMPLE_DOCS.items():
        path = os.path.join(docs_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        paths.append(path)
        print(f"Wrote: {path}")
    return paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-pipeline",
        action="store_true",
        help="After seeding, run the full ingestion pipeline on sample docs",
    )
    args = parser.parse_args()

    conn = get_conn()
    try:
        run_schema(conn)
        client_id, project_id = seed_db(conn)
        doc_paths = write_sample_docs(project_id)

        print(f"\nDemo data ready:")
        print(f"  Client ID  : {client_id}")
        print(f"  Project ID : {project_id}")
        print(f"  Docs       : {', '.join(os.path.basename(p) for p in doc_paths)}")

        if args.run_pipeline:
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from pipeline.runner import run_pipeline_for_project
            print("\nRunning pipeline...")
            asyncio.run(run_pipeline_for_project(project_id, doc_paths))
            print("Pipeline complete.")
        else:
            print("\nTo run the pipeline, start the FastAPI server and upload docs via the UI,")
            print("or re-run with: python db/seed.py --run-pipeline")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
