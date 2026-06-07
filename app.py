from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import csv
import html
import os
import secrets
import sqlite3
import hashlib
import datetime as dt


ROOT = Path(__file__).parent
DB_PATH = Path(os.environ.get("DB_PATH", ROOT / "groundworks.db"))
PRICE_LIST_PATH = ROOT / "data" / "service-price-list.csv"
HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8000"))
SESSIONS = {}
COMPANY_NAME = "J & E Professional Services, LLC"
COMPANY_TAGLINE = "Your property, our priority!"
COMPANY_ADDRESS = "466 Garvin Lake Rd, Gaffney, SC 29340"
COMPANY_PHONE = "+1 (864) 425-5883"
COMPANY_EMAIL = "justin@jandeprofessionalservices.com"
COMPANY_WEBSITE = "www.jandepro.com"
APP_NAME = "Groundworks"
JOB_STATUSES = ["Scheduled", "In Progress", "Completed", "Invoiced", "Cancelled"]
DEMO_SERVICE_NAMES = ["Lawn Mowing", "Mulch Installation", "Leaf Cleanup", "Recurring Lawn Plan"]
PAYMENT_METHODS = ["Cash", "Check", "Card", "Other"]
INVOICE_STATUSES = ["Open", "Overdue", "Paid"]
STAFF_ROLES = ["admin", "employee"]
ESTIMATE_STATUSES = ["Draft", "Sent", "Approved", "Needs Changes", "Declined", "Converted"]
ESTIMATE_DISCLAIMER = (
    "This estimate is subject to change upon in-person inspection of the property. "
    "No work will be performed without prior customer approval."
)
SERVICE_AGREEMENT_TITLE = "Lawn Care Service Agreement"


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return salt, digest.hex()


def verify_password(password, salt, expected_hash):
    _, actual_hash = hash_password(password, salt)
    return secrets.compare_digest(actual_hash, expected_hash)


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_database():
    with db() as connection:
        connection.executescript(
            """
            create table if not exists users (
                id integer primary key autoincrement,
                name text not null,
                email text not null unique,
                role text not null check(role in ('admin', 'employee', 'customer')),
                password_salt text not null,
                password_hash text not null,
                created_at text not null
            );

            create table if not exists customers (
                id integer primary key autoincrement,
                name text not null,
                email text not null,
                phone text,
                address text,
                balance_cents integer not null default 0,
                referral_credit_cents integer not null default 0,
                created_at text not null
            );

            create table if not exists services (
                id integer primary key autoincrement,
                name text not null,
                description text not null,
                starting_price_cents integer not null,
                self_schedulable integer not null default 0
            );

            create table if not exists estimate_requests (
                id integer primary key autoincrement,
                name text not null,
                email text not null,
                phone text,
                address text,
                requested_service text not null,
                message text,
                status text not null default 'New',
                created_at text not null
            );

            create table if not exists estimates (
                id integer primary key autoincrement,
                customer_id integer not null references customers(id),
                source_request_id integer references estimate_requests(id),
                estimate_number text not null unique,
                status text not null default 'Draft',
                notes text,
                terms text,
                expires_at text,
                approved_at text,
                approval_name text,
                approval_signature text,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists estimate_line_items (
                id integer primary key autoincrement,
                estimate_id integer not null references estimates(id),
                description text not null,
                quantity integer not null default 1,
                unit_price_cents integer not null,
                total_cents integer not null
            );

            create table if not exists jobs (
                id integer primary key autoincrement,
                customer_id integer not null references customers(id),
                estimate_id integer references estimates(id),
                service_name text not null,
                scheduled_for text not null,
                status text not null default 'Scheduled',
                notes text,
                completed_at text,
                completion_notes text,
                created_at text not null
            );

            create table if not exists invoices (
                id integer primary key autoincrement,
                customer_id integer not null references customers(id),
                job_id integer not null unique references jobs(id),
                invoice_number text not null unique,
                status text not null default 'Open',
                subtotal_cents integer not null,
                credit_applied_cents integer not null default 0,
                total_cents integer not null,
                amount_paid_cents integer not null default 0,
                due_date text not null,
                created_at text not null
            );

            create table if not exists invoice_line_items (
                id integer primary key autoincrement,
                invoice_id integer not null references invoices(id),
                description text not null,
                quantity integer not null default 1,
                unit_price_cents integer not null,
                total_cents integer not null
            );

            create table if not exists payments (
                id integer primary key autoincrement,
                customer_id integer not null references customers(id),
                invoice_id integer not null references invoices(id),
                recorded_by_user_id integer references users(id),
                recorded_by_name text,
                amount_cents integer not null,
                method text not null,
                reference text,
                note text,
                paid_at text not null,
                created_at text not null
            );

            create table if not exists service_agreements (
                id integer primary key autoincrement,
                customer_id integer not null references customers(id),
                job_id integer references jobs(id),
                status text not null default 'Pending Customer Signature',
                customer_name text,
                customer_signature text,
                customer_signed_at text,
                technician_name text,
                technician_signature text,
                technician_signed_at text,
                created_at text not null,
                updated_at text not null
            );
            """
        )

        ensure_column(connection, "jobs", "completed_at", "text")
        ensure_column(connection, "jobs", "completion_notes", "text")
        ensure_column(connection, "jobs", "estimate_id", "integer references estimates(id)")
        ensure_column(connection, "estimates", "approved_at", "text")
        ensure_column(connection, "estimates", "approval_name", "text")
        ensure_column(connection, "estimates", "approval_signature", "text")
        ensure_column(connection, "payments", "recorded_by_user_id", "integer references users(id)")
        ensure_column(connection, "payments", "recorded_by_name", "text")

        admin_count = connection.execute("select count(*) from users where role = 'admin'").fetchone()[0]
        if admin_count == 0:
            salt, password_hash = hash_password("admin123")
            connection.execute(
                """
                insert into users (name, email, role, password_salt, password_hash, created_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                ("Groundworks Admin", "admin@groundworks.local", "admin", salt, password_hash, now()),
            )

        service_count = connection.execute("select count(*) from services").fetchone()[0]
        if service_count == 0 and not PRICE_LIST_PATH.exists():
            connection.executemany(
                """
                insert into services (name, description, starting_price_cents, self_schedulable)
                values (?, ?, ?, ?)
                """,
                [
                    ("Lawn Mowing", "Routine mowing, trimming, edging, and cleanup.", 4500, 1),
                    ("Mulch Installation", "Fresh mulch installation priced by bed size and material.", 12500, 0),
                    ("Leaf Cleanup", "Seasonal cleanup for lawns, beds, driveways, and walkways.", 9500, 0),
                    ("Recurring Lawn Plan", "Discounted weekly or bi-weekly recurring lawn care.", 4000, 1),
                ],
            )
        if PRICE_LIST_PATH.exists():
            connection.executemany("delete from services where name = ?", [(name,) for name in DEMO_SERVICE_NAMES])
        sync_price_list(connection)
        recalculate_invoice_due_dates(connection)
        sync_invoice_statuses(connection)


def ensure_column(connection, table, column, definition):
    columns = connection.execute(f"pragma table_info({table})").fetchall()
    if column not in {row["name"] for row in columns}:
        connection.execute(f"alter table {table} add column {column} {definition}")


def sync_price_list(connection):
    if not PRICE_LIST_PATH.exists():
        return
    with PRICE_LIST_PATH.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            description = (row.get("description") or "").strip()
            cost_cents = parse_money_to_cents(row.get("cost"))
            existing = connection.execute("select id from services where name = ? limit 1", (name,)).fetchone()
            if existing:
                connection.execute(
                    "update services set description = ?, starting_price_cents = ? where id = ?",
                    (description, cost_cents, existing["id"]),
                )
            else:
                connection.execute(
                    """
                    insert into services (name, description, starting_price_cents, self_schedulable)
                    values (?, ?, ?, 0)
                    """,
                    (name, description, cost_cents),
                )


def recalculate_invoice_due_dates(connection):
    invoices = connection.execute(
        """
        select invoices.id, jobs.scheduled_for
        from invoices
        join jobs on jobs.id = invoices.job_id
        """
    ).fetchall()
    for invoice in invoices:
        connection.execute(
            "update invoices set due_date = ? where id = ?",
            (add_days_to_date(invoice["scheduled_for"], 15), invoice["id"]),
        )


def invoice_status(invoice, today=None):
    if invoice_balance(invoice) <= 0:
        return "Paid"
    today = today or dt.date.today().isoformat()
    if invoice["due_date"] < today:
        return "Overdue"
    return "Open"


def sync_invoice_statuses(connection):
    today = dt.date.today().isoformat()
    connection.execute(
        """
        update invoices
        set status = case
            when amount_paid_cents >= total_cents then 'Paid'
            when due_date < ? then 'Overdue'
            else 'Open'
        end
        where status not in ('Open', 'Overdue', 'Paid')
           or status != case
                when amount_paid_cents >= total_cents then 'Paid'
                when due_date < ? then 'Overdue'
                else 'Open'
           end
        """,
        (today, today),
    )


def dollars(cents):
    return f"${cents / 100:,.2f}"


def parse_money_to_cents(value):
    cleaned = (value or "0").replace("$", "").replace(",", "").strip()
    if not cleaned:
        return 0
    return int(round(float(cleaned) * 100))


def add_days(days):
    return (dt.date.today() + dt.timedelta(days=days)).isoformat()


def date_part(value):
    return (value or "").split("T")[0].split(" ")[0]


def add_days_to_date(value, days):
    base = dt.date.fromisoformat(date_part(value))
    return (base + dt.timedelta(days=days)).isoformat()


def invoice_balance(invoice):
    return invoice["total_cents"] - invoice["amount_paid_cents"]


def estimate_total(estimate):
    return estimate["total_cents"] or 0


def agreement_status(agreement):
    if not agreement:
        return "Not Started"
    if agreement["customer_signed_at"] and agreement["technician_signed_at"]:
        return "Fully Signed"
    if agreement["customer_signed_at"]:
        return "Pending Technician Signature"
    return "Pending Customer Signature"


def status_badge(status):
    class_name = esc(status).lower().replace(" ", "-")
    return f"<span class='status status-{class_name}'>{esc(status)}</span>"


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def logo():
    return f"""
    <img src="/static/official-logo.svg" alt="{esc(COMPANY_NAME)} - {esc(COMPANY_TAGLINE)}" class="official-logo">
    """


def service_agreement_body(customer, agreement=None, job=None):
    effective_date = (agreement["created_at"].split(" ")[0] if agreement else dt.date.today().isoformat())
    customer_signature = agreement["customer_signature"] if agreement and agreement["customer_signature"] else "_______________________________"
    customer_name = agreement["customer_name"] if agreement and agreement["customer_name"] else customer["name"]
    customer_date = agreement["customer_signed_at"].split(" ")[0] if agreement and agreement["customer_signed_at"] else "________________"
    technician_signature = agreement["technician_signature"] if agreement and agreement["technician_signature"] else "_______________________________"
    technician_name = agreement["technician_name"] if agreement and agreement["technician_name"] else "_______________________________"
    technician_date = agreement["technician_signed_at"].split(" ")[0] if agreement and agreement["technician_signed_at"] else "________________"
    job_note = ""
    if job:
        job_note = f"""
        <p><strong>Related Job:</strong> {esc(job['service_name'])} scheduled for {esc(job['scheduled_for'])}</p>
        """
    return f"""
    <article class="legal-page agreement-page">
        <h1>J &amp; E Professional Services</h1>
        <h2>{esc(SERVICE_AGREEMENT_TITLE)}</h2>
        <p class="muted">Effective Date: {esc(effective_date)}</p>
        <p>This Lawn Care Service Agreement ("Agreement") is entered into between J and E Professional Services ("Company") and the undersigned customer ("Customer").</p>

        <section><h2>1. Scope of Services</h2><p>The services to be performed under this Agreement shall be those specifically listed in the service descriptions, estimates, work orders, invoices, scheduling software, customer portal, or other written documentation approved by the Customer. The Company shall perform only those services specifically authorized by the Customer. Company technicians are not authorized to perform additional services or incur additional charges without prior notification to and approval from the Customer.</p></section>
        <section><h2>2. Payment Terms</h2><p>Payment is due immediately upon completion of services unless otherwise agreed in writing. Any deposits paid prior to completion of services, as well as any credits currently on the Customer's account, shall be applied toward the balance due. Any overpayments shall be credited to the Customer's account unless the Customer expressly requests a refund. Account credits do not expire and shall remain on the Customer's account indefinitely until applied to future services or refunded upon request. Returned payments, declined transactions, chargebacks, or non-sufficient funds (NSF) payments may be subject to a fee of up to $35.00 or the maximum amount permitted by applicable law. Any balance remaining unpaid more than fifteen (15) days after the service date may be subject to a late fee of the lesser of one and one-half percent (1.5%) per month, eighteen percent (18%) per year, or the maximum rate permitted by law. The Customer agrees to pay all reasonable costs incurred in collecting past-due amounts, including collection agency fees, court costs, filing fees, and reasonable attorney's fees where permitted by law. The Company reserves the right to suspend or discontinue future services until all outstanding balances have been paid in full.</p></section>
        <section><h2>3. Service Concerns and Property Damage</h2><p>Customer satisfaction is important to us. Any concerns regarding services performed should be reported at the time of service whenever possible, or within twenty-four (24) hours of service completion so that corrective action may be taken promptly. The Company understands that extenuating circumstances may occur and will consider such circumstances on a case-by-case basis. Concerns or complaints first reported more than forty-eight (48) hours after service completion may result in additional charges if corrective work is requested. If any damage to the Customer's property is believed to have been caused by a representative of the Company, the Customer must notify the Company as soon as reasonably feasible, preferably immediately upon discovery, so that the Company may investigate and take appropriate corrective action. Failure to promptly report alleged damage may limit the Company's ability to verify the cause and extent of the issue.</p></section>
        <section><h2>4. Animals, Access, and Property Conditions</h2><p>The Customer agrees to notify the Company of any animals located on the property prior to the scheduled service. All animals must be properly secured during service. The Customer shall notify the Company of any gates, fences, locks, access restrictions, or other barriers that may affect service and shall ensure access is available at the scheduled service time. The Customer is responsible for maintaining a reasonably safe and accessible property and for notifying the Company of any known hazards, concealed obstacles, unstable ground conditions, underground structures, irrigation components, utility lines, septic systems, wells, sinkholes, aggressive animals, hazardous materials, or other conditions that may affect personnel, equipment, or service quality. If services cannot be completed due to unsecured animals, denied access, inaccessible work areas, unsafe conditions, or other circumstances within the Customer's control, the Company may reschedule the service and assess a $35.00 rescheduling fee.</p></section>
        <section><h2>5. Scheduling, Weather, and Delays</h2><p>The Company understands that the Customer's time is valuable and will make every reasonable effort to arrive as scheduled. However, weather conditions, equipment issues, traffic conditions, emergencies, prior job delays, and other unforeseen circumstances may occasionally require service delays or rescheduling. The Company reserves the right to postpone, delay, or reschedule services due to rain, lightning, severe weather, saturated ground conditions, unsafe working conditions, equipment failures, or other circumstances that may adversely affect safety or service quality. Weather-related rescheduling initiated by the Company shall not result in additional charges to the Customer. The Company will make reasonable efforts to notify the Customer as early as possible of any delays or scheduling changes.</p></section>
        <section><h2>6. Property Markings and Customer Responsibilities</h2><p>The Customer is responsible for identifying and marking the location of sprinkler heads, irrigation systems, invisible pet fences, underground utilities, low-voltage wiring, septic systems, drainage systems, landscape lighting, survey markers, hidden structures, and other items that may be concealed by vegetation, mulch, soil, debris, or ground cover. The Customer is also responsible for removing or identifying toys, hoses, pet items, decorations, tools, lawn furniture, and other movable property from service areas prior to service. The Company shall not be responsible for damage to hidden, unmarked, improperly installed, buried, obscured, or undisclosed items, nor for damage caused by objects left within service areas that could reasonably interfere with mowing, trimming, edging, blowing, or related services.</p></section>
        <section><h2>7. Lawn and Landscape Results</h2><p>The Customer acknowledges that lawn, landscape, and property conditions are influenced by factors beyond the Company's control, including weather, soil conditions, pests, disease, irrigation practices, foot traffic, pet activity, prior maintenance practices, and environmental conditions. Unless expressly stated in writing, the Company does not guarantee specific growth rates, turf density, color, weed elimination, pest elimination, plant survival, or other aesthetic results.</p></section>
        <section><h2>8. Limitation of Liability</h2><p>The Company will exercise reasonable care in performing services but shall not be responsible for conditions that are hidden, inaccessible, undisclosed, improperly installed, deteriorated, defective, or otherwise unknown at the time services are performed. The Company shall not be liable for damages resulting from pre-existing property conditions, acts of nature, weather events, concealed debris, underground structures, defective irrigation systems, or circumstances beyond its reasonable control. While reasonable precautions are taken during mowing, trimming, and related operations, hidden rocks, sticks, debris, and other foreign objects may occasionally become airborne. The Company shall not be responsible for damage caused by concealed or undisclosed debris that could not reasonably have been identified before service. To the fullest extent permitted by applicable law, the Company's liability for any claim arising from services performed shall be limited to the amount paid by the Customer for the specific service giving rise to the claim.</p></section>
        <section><h2>9. Right to Refuse or Stop Work</h2><p>The Company reserves the right to refuse, postpone, or discontinue services when conditions are determined to be unsafe, hazardous, unlawful, inaccessible, or likely to result in injury, property damage, equipment damage, or environmental harm. Such conditions may include, but are not limited to, severe weather, lightning, flooding, unsecured animals, aggressive behavior, unsafe terrain, hazardous materials, lack of required access, or threats to employee safety.</p></section>
        <section><h2>10. Photographs and Documentation</h2><p>The Customer authorizes the Company to take photographs of the property before, during, and after services for documentation, quality control, training, dispute resolution, and marketing purposes. The Company will make reasonable efforts to avoid photographing individuals, personal identifying information, or areas unrelated to the services being performed.</p></section>
        <section><h2>11. Recurring Services</h2><p>For customers enrolled in recurring maintenance services, services shall continue according to the agreed service schedule until canceled by either party. Either party may terminate recurring services upon reasonable notice. Pricing for recurring services may be adjusted periodically to reflect changes in labor, fuel, materials, equipment costs, market conditions, or service requirements. Customers will be notified before any pricing changes take effect.</p></section>
        <section><h2>12. Force Majeure</h2><p>The Company shall not be liable for delays, interruptions, or failure to perform services resulting from circumstances beyond its reasonable control, including severe weather, natural disasters, labor shortages, fuel shortages, equipment failures, governmental actions, utility outages, public emergencies, or other unforeseen events.</p></section>
        <section><h2>13. Indemnification</h2><p>To the fullest extent permitted by law, the Customer agrees to indemnify and hold harmless the Company, its owners, employees, contractors, and representatives from claims, damages, losses, liabilities, and expenses arising from undisclosed property conditions, inaccurate information provided by the Customer, unsafe property conditions, violations of applicable laws, or circumstances beyond the Company's control.</p></section>
        <section><h2>14. Electronic Communications and Signatures</h2><p>The Customer agrees that estimates, invoices, photographs, notices, approvals, authorizations, signatures, and other communications may be transmitted and received electronically, including by email, text message, electronic signature platform, customer portal, or other electronic means. Electronic signatures and electronic approvals shall have the same force and effect as original handwritten signatures to the fullest extent permitted by law.</p></section>
        <section><h2>15. Term and Continuing Effect</h2><p>This Agreement shall become effective upon the Customer's acceptance of services, approval of an estimate, execution of this Agreement, authorization of work, or scheduling of services through any written or electronic means. Unless terminated by either party, this Agreement shall remain in full force and effect and shall govern all services performed by the Company for the Customer, including future estimates, invoices, work orders, recurring maintenance schedules, and additional services authorized by the Customer. Each estimate, work order, invoice, service request, recurring service schedule, or other authorization for services shall be incorporated into and governed by this Agreement. Either party may terminate this Agreement at any time upon notice to the other party. Termination shall not affect obligations arising from services previously performed or balances previously incurred. The Company reserves the right to modify this Agreement from time to time. Any revised version shall become effective upon notice to the Customer and shall apply to future services performed thereafter.</p></section>
        <section><h2>16. Governing Law and General Provisions</h2><p>This Agreement shall be governed by the laws of the State of South Carolina. If any provision of this Agreement is found to be invalid or unenforceable, the remaining provisions shall remain in full force and effect. This Agreement, together with all approved estimates, invoices, work orders, service schedules, and written amendments, constitutes the entire agreement between the parties and supersedes all prior discussions, understandings, and agreements regarding the services provided.</p></section>
        <section><h2>17. Acceptance</h2><p>By signing this Agreement, approving an estimate, scheduling services, requesting services, accepting services, authorizing work through any written or electronic means, or making payment for services, the Customer acknowledges that they have read, understood, and agree to be bound by the terms and conditions of this Agreement.</p></section>

        <section>
            <h2>Customer Information</h2>
            <p>
                Customer Name: {esc(customer['name'])}<br>
                Property Address: {esc(customer['address'])}<br>
                Phone Number: {esc(customer['phone'])}<br>
                Email Address: {esc(customer['email'])}
            </p>
            {job_note}
        </section>
        <section>
            <h2>Description of Services</h2>
            <p>Services to be performed are described in the approved estimate, work order, invoice, service schedule, or line-item descriptions generated through the Company's scheduling and invoicing systems, all of which are incorporated into this Agreement by reference.</p>
        </section>
        <section>
            <h2>Signatures</h2>
            <p><strong>IMPORTANT:</strong> By signing below, requesting services, approving an estimate, scheduling services, or accepting services from J and E Professional Services, Customer agrees to all terms and conditions contained in this Agreement, including future services performed unless this Agreement is terminated in accordance with its terms.</p>
            <div class="agreement-signatures">
                <div>
                    <span>Customer Signature</span>
                    <strong>{esc(customer_signature)}</strong>
                    <small>Printed Name: {esc(customer_name)}</small>
                    <small>Date: {esc(customer_date)}</small>
                </div>
                <div>
                    <span>Company Representative</span>
                    <strong>{esc(technician_signature)}</strong>
                    <small>Printed Name: {esc(technician_name)}</small>
                    <small>Date: {esc(technician_date)}</small>
                </div>
            </div>
        </section>
    </article>
    """


def page(title, body, user=None):
    nav = """
    <a href="/">Home</a>
    <a href="/services">Services & Pricing</a>
    <a href="/request-estimate">Request Estimate</a>
    <a href="/signup">Create Account</a>
    <a href="/portal">Customer Portal</a>
    """
    if user and user["role"] == "customer":
        nav += """
        <a href="/portal">My Portal</a>
        <a href="/logout">Log Out</a>
        """
    elif user:
        nav += """
        <a href="/dashboard">Dashboard</a>
        <a href="/customers">Customers</a>
        <a href="/estimates">Estimates</a>
        <a href="/jobs">Jobs</a>
        <a href="/invoices">Invoices</a>
        <a href="/inquiries">Requests</a>
        """
        if user["role"] == "admin":
            nav += '<a href="/employees">Employees</a>'
        nav += """
        <a href="/logout">Log Out</a>
        """
    else:
        nav += '<a href="/login">Staff Login</a>'

    return f"""<!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{esc(title)} | {esc(APP_NAME)}</title>
        <link rel="stylesheet" href="/static/styles.css">
    </head>
    <body>
        <header class="site-header">
            <a class="brand" href="/">{logo()}</a>
            <nav>{nav}</nav>
        </header>
        <main>{body}</main>
        <footer class="site-footer">
            <p>{esc(COMPANY_NAME)} &nbsp; | &nbsp; <a href="/privacy-policy">Privacy Policy</a></p>
        </footer>
    </body>
    </html>"""


class App(BaseHTTPRequestHandler):
    def do_GET(self):
        self.route()

    def do_POST(self):
        self.route()

    def route(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/":
                self.home()
            elif path == "/services":
                self.services()
            elif path == "/request-estimate":
                self.request_estimate()
            elif path == "/privacy-policy":
                self.privacy_policy()
            elif path == "/signup":
                self.signup()
            elif path == "/login":
                self.login()
            elif path == "/logout":
                self.logout()
            elif path == "/dashboard":
                self.require_user()
                self.dashboard()
            elif path == "/portal":
                self.require_user()
                self.customer_portal()
            elif path == "/portal/agreement":
                self.require_user()
                self.customer_service_agreement()
            elif path == "/portal/agreement/sign":
                self.require_user()
                self.sign_customer_service_agreement()
            elif path == "/portal/estimates/view":
                self.require_user()
                self.customer_estimate_detail(parsed)
            elif path == "/portal/estimates/approve":
                self.require_user()
                self.approve_estimate()
            elif path == "/portal/invoices/view":
                self.require_user()
                self.customer_invoice_detail(parsed)
            elif path == "/customers":
                if self.require_staff():
                    self.customers()
            elif path == "/customers/new":
                if self.require_staff():
                    self.new_customer()
            elif path == "/service-agreements/view":
                if self.require_staff():
                    self.staff_service_agreement(parsed)
            elif path == "/service-agreements/technician-sign":
                if self.require_staff():
                    self.sign_technician_service_agreement()
            elif path == "/estimates":
                if self.require_staff():
                    self.estimates()
            elif path == "/estimates/new":
                if self.require_staff():
                    self.new_estimate(parsed)
            elif path == "/estimates/view":
                if self.require_staff():
                    self.estimate_detail(parsed)
            elif path == "/estimates/status":
                if self.require_staff():
                    self.update_estimate_status()
            elif path == "/estimates/convert":
                if self.require_staff():
                    self.convert_estimate()
            elif path == "/jobs":
                if self.require_staff():
                    self.jobs()
            elif path == "/jobs/new":
                if self.require_staff():
                    self.new_job()
            elif path == "/jobs/status":
                if self.require_staff():
                    self.update_job_status()
            elif path == "/jobs/complete":
                if self.require_staff():
                    self.complete_job()
            elif path == "/invoices":
                if self.require_staff():
                    self.invoices()
            elif path == "/invoices/view":
                if self.require_staff():
                    self.invoice_detail(parsed)
            elif path == "/invoices/create":
                if self.require_staff():
                    self.create_invoice()
            elif path == "/payments/create":
                if self.require_staff():
                    self.create_payment()
            elif path == "/inquiries":
                if self.require_staff():
                    self.inquiries()
            elif path == "/employees":
                if self.require_admin():
                    self.employees()
            elif path == "/employees/new":
                if self.require_admin():
                    self.new_employee()
            elif path == "/static/styles.css":
                self.static_css()
            elif path == "/static/logo-mark.svg":
                self.static_logo()
            elif path == "/static/official-logo.svg":
                self.static_official_logo()
            else:
                self.respond("Not found", HTTPStatus.NOT_FOUND)
        except PermissionError:
            self.redirect("/login")

    def form_data(self):
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length).decode()
        return {key: values[0].strip() for key, values in parse_qs(raw).items()}

    def current_user(self):
        cookie = self.headers.get("cookie", "")
        cookies = dict(part.strip().split("=", 1) for part in cookie.split(";") if "=" in part)
        session_id = cookies.get("groundworks_session")
        user_id = SESSIONS.get(session_id)
        if not user_id:
            return None
        with db() as connection:
            return connection.execute("select * from users where id = ?", (user_id,)).fetchone()

    def require_user(self):
        if not self.current_user():
            raise PermissionError()

    def require_staff(self):
        user = self.current_user()
        if not user:
            raise PermissionError()
        if user["role"] not in STAFF_ROLES:
            self.respond("Forbidden", HTTPStatus.FORBIDDEN)
            return False
        return True

    def require_admin(self):
        user = self.current_user()
        if not user:
            raise PermissionError()
        if user["role"] != "admin":
            self.respond("Forbidden", HTTPStatus.FORBIDDEN)
            return False
        return True

    def customer_for_user(self, user=None):
        user = user or self.current_user()
        if not user or user["role"] != "customer":
            return None
        with db() as connection:
            return connection.execute(
                "select * from customers where lower(email) = lower(?) order by id limit 1",
                (user["email"],),
            ).fetchone()

    def ensure_service_agreement(self, connection, customer_id, job_id=None):
        if job_id:
            agreement = connection.execute(
                "select * from service_agreements where customer_id = ? and job_id = ? order by id desc limit 1",
                (customer_id, job_id),
            ).fetchone()
        else:
            agreement = connection.execute(
                "select * from service_agreements where customer_id = ? and job_id is null order by id desc limit 1",
                (customer_id,),
            ).fetchone()
        if agreement:
            return agreement
        created_at = now()
        cursor = connection.execute(
            """
            insert into service_agreements (customer_id, job_id, status, created_at, updated_at)
            values (?, ?, 'Pending Customer Signature', ?, ?)
            """,
            (customer_id, job_id, created_at, created_at),
        )
        return connection.execute("select * from service_agreements where id = ?", (cursor.lastrowid,)).fetchone()

    def respond(self, content, status=HTTPStatus.OK, content_type="text/html"):
        encoded = content.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def redirect(self, path):
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", path)
        self.end_headers()

    def home(self):
        user = self.current_user()
        body = """
        <section class="hero">
            <div>
                <p class="eyebrow">Your property, our priority!</p>
                <h1>J & E Professional Services, LLC</h1>
                <p>Reliable property services with clear pricing, easy scheduling, and service records customers can trust.</p>
                <div class="actions">
                    <a class="button" href="/request-estimate">Request an Estimate</a>
                    <a class="button secondary" href="/services">View Pricing</a>
                </div>
            </div>
        </section>
        <section class="band">
            <h2>Our Mission</h2>
            <p>J & E Professional Services helps property owners maintain healthy, clean, and welcoming spaces through dependable service, transparent communication, and accountable field work.</p>
        </section>
        """
        self.respond(page("Home", body, user))

    def services(self):
        user = self.current_user()
        with db() as connection:
            services = connection.execute("select * from services order by starting_price_cents").fetchall()
        cards = "".join(
            f"""
            <article class="card">
                <h3>{esc(service['name'])}</h3>
                <p>{esc(service['description'])}</p>
                <strong>Starting at {dollars(service['starting_price_cents'])}</strong>
                <span>{'Online scheduling available' if service['self_schedulable'] else 'Estimate required'}</span>
            </article>
            """
            for service in services
        )
        self.respond(page("Services", f"<h1>Services & Pricing</h1><div class='grid'>{cards}</div>", user))

    def privacy_policy(self):
        user = self.current_user()
        body = f"""
        <article class="legal-page">
            <h1>Privacy Policy</h1>
            <p class="muted">Last updated: {dt.date.today().isoformat()}</p>
            <section>
                <h2>1. Information We Collect</h2>
                <p>When you book a service or contact us, we may collect the following information:</p>
                <ul>
                    <li><strong>Name</strong> - your full name or business name.</li>
                    <li><strong>Address</strong> - service address including city, state, and ZIP code.</li>
                    <li><strong>Phone number</strong> - so we can reach you about your job.</li>
                    <li><strong>Email address</strong> - for booking confirmations and service communications.</li>
                    <li><strong>Service history</strong> - a record of services provided at your property.</li>
                    <li><strong>Payment information</strong> - handled entirely by our third-party payment processor.</li>
                </ul>
                <p>We do not collect sensitive personal data such as Social Security numbers, driver's license numbers, or health information.</p>
            </section>

            <section>
                <h2>2. How We Use Your Information</h2>
                <p>Your information is used only to run our business and serve you well:</p>
                <ul>
                    <li><strong>Job scheduling</strong> - assigning a technician and time window for your service.</li>
                    <li><strong>Customer communication</strong> - sending booking confirmations, day-of reminders, and follow-up messages.</li>
                    <li><strong>Service delivery</strong> - our field technicians use your address and contact info to complete work at your property.</li>
                    <li><strong>Payment processing</strong> - collecting payment for services rendered via our third-party processor.</li>
                    <li><strong>Internal records</strong> - maintaining service history for warranty and quality purposes.</li>
                </ul>
                <p>We do not sell, rent, or share your personal information with third parties for their own marketing purposes.</p>
            </section>

            <section>
                <h2>3. Payment Information</h2>
                <p>J &amp; E Professional Services does not store, access, or transmit raw credit card data. All payment processing is handled by Stripe, a PCI-compliant third-party payment processor. When you pay, your card information goes directly to Stripe. It never passes through our servers in a readable form.</p>
                <p>Stripe's privacy policy and security practices govern how your payment information is stored. You can review Stripe's privacy policy at <a href="https://stripe.com/privacy">stripe.com/privacy</a>.</p>
                <p>If you choose to pay a deposit to confirm your booking, we store a reference to that payment, such as the payment intent ID, in our system for record-keeping purposes only.</p>
            </section>

            <section>
                <h2>4. Data Storage and Security</h2>
                <p>Customer data, including name, address, phone, email, and service records, is stored in a secure PostgreSQL database hosted by Neon, a cloud database provider, with TLS encryption in transit and at rest.</p>
                <p>Access to the database is restricted to J &amp; E employees with administrative credentials. All administrative access is logged.</p>
                <p>Payment card data is stored exclusively by Stripe. We never hold card numbers, expiration dates, or CVV codes.</p>
                <p>If you have questions about our data security practices, contact us using the information at the bottom of this page.</p>
            </section>

            <section>
                <h2>5. Employee and Technician Access</h2>
                <p>Our field technicians, the people who work on your property, can:</p>
                <ul>
                    <li>Add customer information and create or book jobs for new and existing customers.</li>
                    <li>View customer name, address, and contact information relevant to their current jobs.</li>
                    <li>Upload before and after photos of completed work.</li>
                </ul>
                <p>Field technicians do not have administrative-level access to the database. They cannot view financial records, aggregate customer data, or access system administration tools.</p>
            </section>

            <section>
                <h2>6. Your Rights</h2>
                <p>You have the following rights regarding your personal information:</p>
                <ul>
                    <li><strong>Request your data</strong> - contact us to receive a copy of the personal information we have on file for you.</li>
                    <li><strong>Request correction</strong> - if your information is inaccurate, let us know and we'll update it promptly.</li>
                    <li><strong>Request deletion</strong> - you can ask us to delete your personal information, subject to any legal or financial record-keeping requirements.</li>
                    <li><strong>Opt out of marketing</strong> - email us at the address below and we'll remove you from our promotional list. You may still receive transactional messages related to your service, including confirmations, reminders, and invoices.</li>
                </ul>
                <p>We will respond to any data request within 30 days. There is no fee for exercising any of these rights.</p>
            </section>

            <section>
                <h2>7. Contact Us</h2>
                <p>
                    J &amp; E Professional Services, LLC<br>
                    Gaffney, South Carolina 29340<br>
                    {esc(COMPANY_PHONE)}<br>
                    <a href="mailto:{esc(COMPANY_EMAIL)}">{esc(COMPANY_EMAIL)}</a>
                </p>
            </section>

            <div class="notice">
                This policy is a working draft for business planning and should be reviewed by a qualified attorney before publication.
            </div>
        </article>
        """
        self.respond(page("Privacy Policy", body, user))

    def request_estimate(self):
        user = self.current_user()
        if self.command == "POST":
            data = self.form_data()
            with db() as connection:
                connection.execute(
                    """
                    insert into estimate_requests
                    (name, email, phone, address, requested_service, message, created_at)
                    values (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        data.get("name"),
                        data.get("email"),
                        data.get("phone"),
                        data.get("address"),
                        data.get("requested_service"),
                        data.get("message"),
                        now(),
                    ),
                )
            self.respond(page("Estimate Requested", "<div class='notice'>Thanks. Your request has been received.</div>", user))
            return

        body = """
        <h1>Request an Estimate</h1>
        <form method="post" class="form">
            <label>Name <input name="name" required></label>
            <label>Email <input name="email" type="email" required></label>
            <label>Phone <input name="phone"></label>
            <label>Service Address <input name="address"></label>
            <label>Requested Service <input name="requested_service" required></label>
            <label>Message <textarea name="message" rows="5"></textarea></label>
            <button>Send Request</button>
        </form>
        """
        self.respond(page("Request Estimate", body, user))

    def signup(self):
        user = self.current_user()
        if self.command == "POST":
            data = self.form_data()
            salt, password_hash = hash_password(data.get("password", ""))
            with db() as connection:
                connection.execute(
                    """
                    insert into users (name, email, role, password_salt, password_hash, created_at)
                    values (?, ?, 'customer', ?, ?, ?)
                    """,
                    (data.get("name"), data.get("email"), salt, password_hash, now()),
                )
                connection.execute(
                    """
                    insert into customers (name, email, phone, address, created_at)
                    values (?, ?, ?, ?, ?)
                    """,
                    (data.get("name"), data.get("email"), data.get("phone"), data.get("address"), now()),
                )
            self.redirect("/login")
            return

        body = """
        <h1>Create Customer Account</h1>
        <form method="post" class="form">
            <label>Name <input name="name" required></label>
            <label>Email <input name="email" type="email" required></label>
            <label>Phone <input name="phone"></label>
            <label>Service Address <input name="address"></label>
            <label>Password <input name="password" type="password" required></label>
            <button>Create Account</button>
        </form>
        """
        self.respond(page("Create Account", body, user))

    def login(self):
        if self.command == "POST":
            data = self.form_data()
            with db() as connection:
                user = connection.execute("select * from users where email = ?", (data.get("email"),)).fetchone()
            if user and verify_password(data.get("password", ""), user["password_salt"], user["password_hash"]):
                session_id = secrets.token_hex(32)
                SESSIONS[session_id] = user["id"]
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "/dashboard")
                self.send_header("Set-Cookie", f"groundworks_session={session_id}; HttpOnly; SameSite=Lax; Path=/")
                self.end_headers()
                return
            self.respond(page("Login", "<div class='notice danger'>Invalid email or password.</div>" + self.login_form()))
            return
        self.respond(page("Login", self.login_form()))

    def login_form(self):
        return """
        <h1>Account Login</h1>
        <p class="muted">Customers and staff can log in here. Customer accounts open the customer portal.</p>
        <form method="post" class="form">
            <label>Email <input name="email" type="email" required></label>
            <label>Password <input name="password" type="password" required></label>
            <button>Log In</button>
        </form>
        """

    def logout(self):
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.send_header("Set-Cookie", "groundworks_session=; Max-Age=0; Path=/")
        self.end_headers()

    def dashboard(self):
        user = self.current_user()
        if user["role"] == "customer":
            self.customer_portal()
            return
        with db() as connection:
            sync_invoice_statuses(connection)
            customer_count = connection.execute("select count(*) from customers").fetchone()[0]
            request_count = connection.execute("select count(*) from estimate_requests where status = 'New'").fetchone()[0]
            estimate_count = connection.execute("select count(*) from estimates where status in ('Draft', 'Sent', 'Approved', 'Needs Changes')").fetchone()[0]
            job_count = connection.execute("select count(*) from jobs where status in ('Scheduled', 'In Progress')").fetchone()[0]
            invoice_total = connection.execute("select coalesce(sum(total_cents - amount_paid_cents), 0) from invoices where status in ('Open', 'Overdue')").fetchone()[0]
            overdue_count = connection.execute("select count(*) from invoices where status = 'Overdue'").fetchone()[0]
            overdue_total = connection.execute("select coalesce(sum(total_cents - amount_paid_cents), 0) from invoices where status = 'Overdue'").fetchone()[0]
        body = f"""
        <h1>Dashboard</h1>
        <div class="grid">
            <article class="metric"><strong>{customer_count}</strong><span>Customers</span></article>
            <article class="metric"><strong>{request_count}</strong><span>New Requests</span></article>
            <article class="metric"><strong>{estimate_count}</strong><span>Active Estimates</span></article>
            <article class="metric"><strong>{job_count}</strong><span>Open Jobs</span></article>
            <article class="metric"><strong>{dollars(invoice_total)}</strong><span>Open Invoices</span></article>
            <article class="metric danger-metric"><strong>{overdue_count}</strong><span>Overdue Invoices</span><small>{dollars(overdue_total)} past due</small></article>
        </div>
        """
        self.respond(page("Dashboard", body, user))

    def customer_portal(self):
        user = self.current_user()
        customer = self.customer_for_user(user)
        if not customer:
            self.respond(page("Customer Portal", "<div class='notice danger'>No customer record is linked to this account yet.</div>", user))
            return
        with db() as connection:
            sync_invoice_statuses(connection)
            estimates = connection.execute(
                """
                select estimates.*, coalesce(sum(estimate_line_items.total_cents), 0) as total_cents
                from estimates
                left join estimate_line_items on estimate_line_items.estimate_id = estimates.id
                where estimates.customer_id = ?
                group by estimates.id
                order by estimates.updated_at desc
                """,
                (customer["id"],),
            ).fetchall()
            jobs = connection.execute(
                """
                select *
                from jobs
                where customer_id = ?
                order by scheduled_for desc
                """,
                (customer["id"],),
            ).fetchall()
            invoices = connection.execute(
                """
                select invoices.*, jobs.service_name, jobs.scheduled_for
                from invoices
                join jobs on jobs.id = invoices.job_id
                where invoices.customer_id = ?
                order by invoices.created_at desc
                """,
                (customer["id"],),
            ).fetchall()
            agreement = self.ensure_service_agreement(connection, customer["id"])

        estimate_rows = "".join(
            f"""
            <tr>
                <td><a href="/portal/estimates/view?id={estimate['id']}">{esc(estimate['estimate_number'])}</a></td>
                <td>{status_badge(estimate['status'])}</td>
                <td>{esc(estimate['expires_at'])}</td>
                <td>{dollars(estimate_total(estimate))}</td>
            </tr>
            """
            for estimate in estimates
        ) or "<tr><td colspan='4'>No estimates yet.</td></tr>"
        job_rows = "".join(
            f"""
            <tr>
                <td>{esc(job['scheduled_for'])}</td>
                <td>{esc(job['service_name'])}</td>
                <td>{status_badge(job['status'])}</td>
                <td>{esc(job['completion_notes'] or job['notes'])}</td>
            </tr>
            """
            for job in jobs
        ) or "<tr><td colspan='4'>No jobs yet.</td></tr>"
        invoice_rows = "".join(
            f"""
            <tr>
                <td><a href="/portal/invoices/view?id={invoice['id']}">{esc(invoice['invoice_number'])}</a></td>
                <td>{esc(invoice['due_date'])}</td>
                <td>{dollars(invoice['total_cents'])}</td>
                <td>{dollars(invoice_balance(invoice))}</td>
                <td>{status_badge(invoice_status(invoice))}</td>
            </tr>
            """
            for invoice in invoices
        ) or "<tr><td colspan='5'>No invoices yet.</td></tr>"
        body = f"""
        <h1>My Portal</h1>
        <section class="band">
            <h2>Account</h2>
            <p><strong>{esc(customer['name'])}</strong><br>{esc(customer['address'])}<br>{esc(customer['phone'])}<br>{esc(customer['email'])}</p>
            <div class="grid">
                <article class="metric"><strong>{dollars(customer['balance_cents'])}</strong><span>Account Balance</span></article>
                <article class="metric"><strong>{len(estimates)}</strong><span>Estimates</span></article>
                <article class="metric"><strong>{len(jobs)}</strong><span>Jobs</span></article>
                <article class="metric"><strong>{len(invoices)}</strong><span>Invoices</span></article>
            </div>
            <p><a class="button compact" href="/portal/agreement">View and Sign Service Agreement</a> {status_badge(agreement_status(agreement))}</p>
        </section>
        <section class="band">
            <h2>Estimates</h2>
            <table><thead><tr><th>Estimate</th><th>Status</th><th>Expires</th><th>Total</th></tr></thead><tbody>{estimate_rows}</tbody></table>
        </section>
        <section class="band">
            <h2>Jobs</h2>
            <table><thead><tr><th>Scheduled</th><th>Service</th><th>Status</th><th>Notes</th></tr></thead><tbody>{job_rows}</tbody></table>
        </section>
        <section class="band">
            <h2>Invoices</h2>
            <table><thead><tr><th>Invoice</th><th>Due</th><th>Total</th><th>Balance</th><th>Status</th></tr></thead><tbody>{invoice_rows}</tbody></table>
        </section>
        """
        self.respond(page("My Portal", body, user))

    def customer_service_agreement(self):
        user = self.current_user()
        customer = self.customer_for_user(user)
        if not customer:
            self.respond("Customer record not found.", HTTPStatus.NOT_FOUND)
            return
        with db() as connection:
            agreement = self.ensure_service_agreement(connection, customer["id"])
        signature_panel = ""
        if not agreement["customer_signed_at"]:
            signature_panel = f"""
            <section class="payment-panel no-print">
                <h2>Customer Signature Required</h2>
                <form method="post" action="/portal/agreement/sign" class="form compact-form">
                    <input type="hidden" name="agreement_id" value="{agreement['id']}">
                    <label>Printed Name <input name="customer_name" value="{esc(customer['name'])}" required></label>
                    <label>Digital Signature <input name="customer_signature" placeholder="Type your full legal name" required></label>
                    <label class="checkbox-label"><input type="checkbox" name="accepted_terms" value="yes" required> I have read and agree to the Lawn Care Service Agreement.</label>
                    <button>Sign Agreement</button>
                </form>
            </section>
            """
        else:
            signature_panel = f"<section class='notice no-print'>Customer signature recorded on {esc(agreement['customer_signed_at'])}.</section>"
        body = f"""
        <div class="invoice-actions no-print">
            <a class="button secondary compact" href="/portal">Back to Portal</a>
            <button onclick="window.print()">Print Agreement</button>
        </div>
        {signature_panel}
        {service_agreement_body(customer, agreement)}
        """
        self.respond(page("Service Agreement", body, user))

    def sign_customer_service_agreement(self):
        if self.command != "POST":
            self.redirect("/portal")
            return
        user = self.current_user()
        customer = self.customer_for_user(user)
        if not customer:
            self.respond("Customer record not found.", HTTPStatus.NOT_FOUND)
            return
        data = self.form_data()
        if data.get("accepted_terms") != "yes":
            self.respond("Agreement signature requires accepting the service agreement.", HTTPStatus.BAD_REQUEST)
            return
        customer_name = data.get("customer_name")
        customer_signature = data.get("customer_signature")
        if not customer_name or not customer_signature:
            self.respond("Printed name and digital signature are required.", HTTPStatus.BAD_REQUEST)
            return
        with db() as connection:
            agreement = connection.execute(
                "select * from service_agreements where id = ? and customer_id = ?",
                (data.get("agreement_id"), customer["id"]),
            ).fetchone()
            if not agreement:
                self.respond("Agreement not found.", HTTPStatus.NOT_FOUND)
                return
            if agreement["customer_signed_at"]:
                self.redirect("/portal/agreement")
                return
            signed_at = now()
            new_status = "Fully Signed" if agreement["technician_signed_at"] else "Pending Technician Signature"
            connection.execute(
                """
                update service_agreements
                set customer_name = ?, customer_signature = ?, customer_signed_at = ?, status = ?, updated_at = ?
                where id = ? and customer_id = ?
                """,
                (customer_name, customer_signature, signed_at, new_status, signed_at, agreement["id"], customer["id"]),
            )
        self.redirect("/portal/agreement")

    def customer_estimate_detail(self, parsed):
        user = self.current_user()
        customer = self.customer_for_user(user)
        if not customer:
            self.respond("Customer record not found.", HTTPStatus.NOT_FOUND)
            return
        estimate_id = (parse_qs(parsed.query).get("id") or [""])[0]
        with db() as connection:
            estimate = connection.execute(
                """
                select estimates.*, customers.name as customer_name, customers.email, customers.phone, customers.address,
                       coalesce(sum(estimate_line_items.total_cents), 0) as total_cents
                from estimates
                join customers on customers.id = estimates.customer_id
                left join estimate_line_items on estimate_line_items.estimate_id = estimates.id
                where estimates.id = ? and estimates.customer_id = ?
                group by estimates.id
                """,
                (estimate_id, customer["id"]),
            ).fetchone()
            if not estimate:
                self.respond("Estimate not found.", HTTPStatus.NOT_FOUND)
                return
            line_items = connection.execute(
                "select * from estimate_line_items where estimate_id = ? order by id",
                (estimate_id,),
            ).fetchall()

        line_rows = "".join(
            f"""
            <tr>
                <td>{esc(item['description'])}</td>
                <td>{item['quantity']}</td>
                <td>{dollars(item['unit_price_cents'])}</td>
                <td>{dollars(item['total_cents'])}</td>
            </tr>
            """
            for item in line_items
        )
        approval_panel = ""
        if estimate["status"] in ("Draft", "Sent", "Needs Changes"):
            approval_panel = f"""
            <section class="payment-panel no-print">
                <h2>Approve Estimate</h2>
                <form method="post" action="/portal/estimates/approve" class="form compact-form">
                    <input type="hidden" name="estimate_id" value="{estimate['id']}">
                    <label>Your Name <input name="approval_name" value="{esc(customer['name'])}" required></label>
                    <label>Signature <input name="approval_signature" placeholder="Type your full legal name" required></label>
                    <label class="checkbox-label"><input type="checkbox" name="accepted_terms" value="yes" required> I approve this estimate and understand the inspection disclaimer.</label>
                    <button>Approve Estimate</button>
                </form>
            </section>
            """
        elif estimate["approved_at"]:
            approval_panel = f"""
            <section class="notice">
                Approved by {esc(estimate['approval_name'])} on {esc(estimate['approved_at'])}.
            </section>
            """
        approval_block = ""
        if estimate["approved_at"]:
            approval_block = f"""
            <section class="signature-record">
                <h2>Customer Approval</h2>
                <p><strong>{esc(estimate['approval_signature'])}</strong></p>
                <p>Approved by {esc(estimate['approval_name'])} on {esc(estimate['approved_at'])}</p>
            </section>
            """

        body = f"""
        <div class="invoice-actions no-print">
            <a class="button secondary compact" href="/portal">Back to Portal</a>
            <button onclick="window.print()">Print Estimate</button>
        </div>
        {approval_panel}
        <article class="invoice-sheet">
            <header class="invoice-header">
                <div class="invoice-company">
                    {logo()}
                    <p>{esc(COMPANY_ADDRESS)}<br>{esc(COMPANY_PHONE)}<br>{esc(COMPANY_EMAIL)}</p>
                </div>
                <div class="invoice-title">
                    <h1>Estimate</h1>
                    <dl>
                        <div><dt>Estimate #</dt><dd>{esc(estimate['estimate_number'])}</dd></div>
                        <div><dt>Status</dt><dd>{status_badge(estimate['status'])}</dd></div>
                        <div><dt>Expires</dt><dd>{esc(estimate['expires_at'])}</dd></div>
                    </dl>
                </div>
            </header>
            <section class="invoice-parties two-column">
                <div>
                    <h2>Customer</h2>
                    <p><strong>{esc(estimate['customer_name'])}</strong><br>{esc(estimate['address'])}</p>
                </div>
                <div>
                    <h2>Contact</h2>
                    <p>{esc(estimate['phone'])}<br>{esc(estimate['email'])}</p>
                </div>
            </section>
            <table class="invoice-lines">
                <thead><tr><th>Description</th><th>Qty</th><th>Price</th><th>Total</th></tr></thead>
                <tbody>{line_rows}</tbody>
            </table>
            <section class="invoice-summary">
                <div class="invoice-notes">
                    <h2>Notes and Terms</h2>
                    <p>{esc(estimate['notes'])}</p>
                    <p>{esc(estimate['terms'])}</p>
                    <p><strong>Disclaimer:</strong> {esc(ESTIMATE_DISCLAIMER)}</p>
                </div>
                <div class="invoice-totals">
                    <div class="total-row total"><span>Estimate Total</span><strong>{dollars(estimate_total(estimate))}</strong></div>
                </div>
            </section>
            {approval_block}
        </article>
        """
        self.respond(page(f"Estimate {estimate['estimate_number']}", body, user))

    def approve_estimate(self):
        if self.command != "POST":
            self.redirect("/portal")
            return
        user = self.current_user()
        customer = self.customer_for_user(user)
        if not customer:
            self.respond("Customer record not found.", HTTPStatus.NOT_FOUND)
            return
        data = self.form_data()
        if data.get("accepted_terms") != "yes":
            self.respond("Estimate approval requires accepting the estimate terms.", HTTPStatus.BAD_REQUEST)
            return
        approval_name = data.get("approval_name")
        approval_signature = data.get("approval_signature")
        if not approval_name or not approval_signature:
            self.respond("Name and signature are required.", HTTPStatus.BAD_REQUEST)
            return
        with db() as connection:
            estimate = connection.execute(
                "select * from estimates where id = ? and customer_id = ?",
                (data.get("estimate_id"), customer["id"]),
            ).fetchone()
            if not estimate:
                self.respond("Estimate not found.", HTTPStatus.NOT_FOUND)
                return
            if estimate["status"] not in ("Draft", "Sent", "Needs Changes"):
                self.respond("This estimate can no longer be approved online.", HTTPStatus.BAD_REQUEST)
                return
            connection.execute(
                """
                update estimates
                set status = 'Approved', approved_at = ?, approval_name = ?, approval_signature = ?, updated_at = ?
                where id = ? and customer_id = ?
                """,
                (now(), approval_name, approval_signature, now(), estimate["id"], customer["id"]),
            )
        self.redirect(f"/portal/estimates/view?id={data.get('estimate_id')}")

    def customer_invoice_detail(self, parsed):
        user = self.current_user()
        customer = self.customer_for_user(user)
        if not customer:
            self.respond("Customer record not found.", HTTPStatus.NOT_FOUND)
            return
        invoice_id = (parse_qs(parsed.query).get("id") or [""])[0]
        with db() as connection:
            sync_invoice_statuses(connection)
            invoice = connection.execute(
                """
                select invoices.*, customers.name as customer_name, customers.email, customers.phone,
                       customers.address, customers.balance_cents,
                       jobs.service_name, jobs.scheduled_for, jobs.notes, jobs.completed_at,
                       jobs.completion_notes, services.description as service_description
                from invoices
                join customers on customers.id = invoices.customer_id
                join jobs on jobs.id = invoices.job_id
                left join services on services.name = jobs.service_name
                where invoices.id = ? and invoices.customer_id = ?
                """,
                (invoice_id, customer["id"]),
            ).fetchone()
            if not invoice:
                self.respond("Invoice not found.", HTTPStatus.NOT_FOUND)
                return
            line_items = connection.execute(
                "select * from invoice_line_items where invoice_id = ? order by id",
                (invoice_id,),
            ).fetchall()
            payments = connection.execute(
                "select * from payments where invoice_id = ? order by paid_at desc, id desc",
                (invoice_id,),
            ).fetchall()

        line_rows = "".join(
            f"""
            <tr>
                <td><strong>{esc(item['description'])}</strong><small>{esc(invoice['service_description'])}</small></td>
                <td>{dollars(item['unit_price_cents'])}</td>
                <td>{item['quantity']}</td>
                <td>{dollars(item['total_cents'])}</td>
            </tr>
            """
            for item in line_items
        )
        amount_due = invoice_balance(invoice)
        paid_note = ""
        if invoice["amount_paid_cents"]:
            paid_note = f"<div class='total-row'><span>Amount Paid</span><strong>{dollars(invoice['amount_paid_cents'])}</strong></div>"
        payment_rows = "".join(
            f"""
            <tr>
                <td>{esc(payment['paid_at'])}</td>
                <td>{esc(payment['method'])}</td>
                <td>{esc(payment['reference'])}</td>
                <td>{dollars(payment['amount_cents'])}</td>
            </tr>
            """
            for payment in payments
        )
        payment_history = ""
        if payments:
            payment_history = f"""
            <section class="payment-history">
                <h2>Payment History</h2>
                <table>
                    <thead><tr><th>Date</th><th>Method</th><th>Reference</th><th>Amount</th></tr></thead>
                    <tbody>{payment_rows}</tbody>
                </table>
            </section>
            """
        work_notes = invoice["completion_notes"] or invoice["notes"] or "Thank you for your business."
        body = f"""
        <div class="invoice-actions no-print">
            <a class="button secondary compact" href="/portal">Back to Portal</a>
            <button onclick="window.print()">Print Invoice</button>
        </div>
        <article class="invoice-sheet">
            <header class="invoice-header">
                <div class="invoice-company">
                    {logo()}
                    <p>{esc(COMPANY_ADDRESS)}<br>{esc(COMPANY_PHONE)}</p>
                </div>
                <div class="invoice-title">
                    <h1>Invoice</h1>
                    <dl>
                        <div><dt>Account #</dt><dd>{invoice['customer_id']:04d}</dd></div>
                        <div><dt>Invoice #</dt><dd>{esc(invoice['invoice_number'])}</dd></div>
                        <div><dt>Invoice Date</dt><dd>{esc(invoice['created_at'].split(' ')[0])}</dd></div>
                        <div><dt>Due Date</dt><dd>{esc(invoice['due_date'])}</dd></div>
                        <div><dt>Status</dt><dd>{status_badge(invoice_status(invoice))}</dd></div>
                    </dl>
                </div>
            </header>
            <section class="invoice-parties">
                <div><h2>Bill To</h2><p><strong>{esc(invoice['customer_name'])}</strong><br>{esc(invoice['address'])}</p></div>
                <div><h2>Service Address</h2><p><strong>{esc(invoice['customer_name'])}</strong><br>{esc(invoice['address'])}</p></div>
                <div><h2>Primary Contact</h2><p><strong>{esc(invoice['customer_name'])}</strong><br>{esc(invoice['phone'])}<br>{esc(invoice['email'])}</p></div>
            </section>
            <table class="invoice-lines">
                <thead><tr><th>Item</th><th>Cost</th><th>Qty</th><th>Price</th></tr></thead>
                <tbody>{line_rows}</tbody>
            </table>
            <section class="invoice-summary">
                <div class="invoice-notes">
                    <h2>Terms</h2>
                    <p>Payment is due 15 days from the date of service.</p>
                    <h2>Notes</h2>
                    <p>{esc(work_notes)}</p>
                    <p>Service Date: {esc(date_part(invoice['scheduled_for']))}</p>
                    <p>Due Date: {esc(invoice['due_date'])}</p>
                </div>
                <div class="invoice-totals">
                    <div class="total-row"><span>Subtotal</span><strong>{dollars(invoice['subtotal_cents'])}</strong></div>
                    <div class="total-row total"><span>Total</span><strong>{dollars(invoice['total_cents'])}</strong></div>
                    {paid_note}
                    <div class="total-row"><span>Amount Due</span><strong>{dollars(amount_due)}</strong></div>
                    <div class="total-row total"><span>Balance Due</span><strong>{dollars(amount_due)}</strong></div>
                </div>
            </section>
            {payment_history}
        </article>
        """
        self.respond(page(f"Invoice {invoice['invoice_number']}", body, user))

    def employees(self):
        user = self.current_user()
        with db() as connection:
            employees = connection.execute(
                """
                select id, name, email, role, created_at
                from users
                where role in ('admin', 'employee')
                order by role, name
                """
            ).fetchall()
        rows = "".join(
            f"""
            <tr>
                <td>{esc(employee['name'])}</td>
                <td>{esc(employee['email'])}</td>
                <td>{status_badge(employee['role'].title())}</td>
                <td>{esc(employee['created_at'])}</td>
            </tr>
            """
            for employee in employees
        )
        body = f"""
        <div class="heading-row"><h1>Employees</h1><a class="button" href="/employees/new">Add Employee</a></div>
        <table>
            <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Created</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
        """
        self.respond(page("Employees", body, user))

    def new_employee(self):
        user = self.current_user()
        role_options = "".join(f"<option value='{role}'>{esc(role.title())}</option>" for role in STAFF_ROLES)
        if self.command == "POST":
            data = self.form_data()
            role = data.get("role")
            if role not in STAFF_ROLES:
                self.respond("Invalid employee role.", HTTPStatus.BAD_REQUEST)
                return
            password = data.get("password", "")
            if len(password) < 8:
                body = "<div class='notice danger'>Temporary password must be at least 8 characters.</div>" + self.employee_form(role_options)
                self.respond(page("Add Employee", body, user))
                return
            salt, password_hash = hash_password(password)
            try:
                with db() as connection:
                    connection.execute(
                        """
                        insert into users (name, email, role, password_salt, password_hash, created_at)
                        values (?, ?, ?, ?, ?, ?)
                        """,
                        (data.get("name"), data.get("email"), role, salt, password_hash, now()),
                    )
            except sqlite3.IntegrityError:
                body = "<div class='notice danger'>An account already exists for that email.</div>" + self.employee_form(role_options)
                self.respond(page("Add Employee", body, user))
                return
            self.redirect("/employees")
            return
        self.respond(page("Add Employee", self.employee_form(role_options), user))

    def employee_form(self, role_options):
        return f"""
        <h1>Add Employee</h1>
        <form method="post" class="form">
            <label>Name <input name="name" required></label>
            <label>Email <input name="email" type="email" required></label>
            <label>Role <select name="role" required>{role_options}</select></label>
            <label>Temporary Password <input name="password" type="password" minlength="8" required></label>
            <button>Save Employee</button>
        </form>
        """

    def customers(self):
        user = self.current_user()
        with db() as connection:
            rows = connection.execute(
                """
                select customers.*, service_agreements.id as agreement_id,
                       service_agreements.status as agreement_status
                from customers
                left join service_agreements
                  on service_agreements.customer_id = customers.id
                 and service_agreements.job_id is null
                 and service_agreements.id = (
                    select max(id) from service_agreements
                    where customer_id = customers.id and job_id is null
                 )
                order by customers.created_at desc
                """
            ).fetchall()
        table = "".join(
            f"""
            <tr>
                <td>{esc(row['name'])}</td>
                <td>{esc(row['email'])}</td>
                <td>{esc(row['phone'])}</td>
                <td>{esc(row['address'])}</td>
                <td>{dollars(row['balance_cents'])}</td>
                <td>{status_badge(row['agreement_status'] or 'Not Started')}</td>
                <td><a class="button secondary compact" href="/service-agreements/view?customer_id={row['id']}">Agreement</a></td>
            </tr>
            """
            for row in rows
        )
        body = f"""
        <div class="heading-row"><h1>Customers</h1><a class="button" href="/customers/new">Add Customer</a></div>
        <table><thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Address</th><th>Balance</th><th>Agreement</th><th>Action</th></tr></thead><tbody>{table}</tbody></table>
        """
        self.respond(page("Customers", body, user))

    def new_customer(self):
        user = self.current_user()
        if self.command == "POST":
            data = self.form_data()
            with db() as connection:
                connection.execute(
                    "insert into customers (name, email, phone, address, created_at) values (?, ?, ?, ?, ?)",
                    (data.get("name"), data.get("email"), data.get("phone"), data.get("address"), now()),
                )
            self.redirect("/customers")
            return
        body = """
        <h1>Add Customer</h1>
        <form method="post" class="form">
            <label>Name <input name="name" required></label>
            <label>Email <input name="email" type="email" required></label>
            <label>Phone <input name="phone"></label>
            <label>Service Address <input name="address"></label>
            <button>Save Customer</button>
        </form>
        """
        self.respond(page("Add Customer", body, user))

    def staff_service_agreement(self, parsed):
        user = self.current_user()
        params = parse_qs(parsed.query)
        customer_id = (params.get("customer_id") or [""])[0]
        job_id = (params.get("job_id") or [""])[0] or None
        with db() as connection:
            if job_id and not customer_id:
                job = connection.execute("select * from jobs where id = ?", (job_id,)).fetchone()
                if not job:
                    self.respond("Job not found.", HTTPStatus.NOT_FOUND)
                    return
                customer_id = job["customer_id"]
            customer = connection.execute("select * from customers where id = ?", (customer_id,)).fetchone()
            if not customer:
                self.respond("Customer not found.", HTTPStatus.NOT_FOUND)
                return
            agreement = self.ensure_service_agreement(connection, customer["id"], job_id)
            job = None
            if agreement["job_id"]:
                job = connection.execute("select * from jobs where id = ?", (agreement["job_id"],)).fetchone()

        technician_panel = ""
        if not agreement["technician_signed_at"]:
            technician_panel = f"""
            <section class="payment-panel no-print">
                <h2>Technician Signature</h2>
                <form method="post" action="/service-agreements/technician-sign" class="form compact-form">
                    <input type="hidden" name="agreement_id" value="{agreement['id']}">
                    <label>Technician Name <input name="technician_name" value="{esc(user['name'])}" required></label>
                    <label>Technician Signature <input name="technician_signature" placeholder="Type your full legal name" required></label>
                    <button>Sign as Technician</button>
                </form>
            </section>
            """
        else:
            technician_panel = f"<section class='notice no-print'>Technician signature recorded on {esc(agreement['technician_signed_at'])}.</section>"
        body = f"""
        <div class="invoice-actions no-print">
            <a class="button secondary compact" href="/customers">Back to Customers</a>
            <button onclick="window.print()">Print Agreement</button>
        </div>
        {technician_panel}
        {service_agreement_body(customer, agreement, job)}
        """
        self.respond(page("Service Agreement", body, user))

    def sign_technician_service_agreement(self):
        if self.command != "POST":
            self.redirect("/customers")
            return
        data = self.form_data()
        technician_name = data.get("technician_name")
        technician_signature = data.get("technician_signature")
        if not technician_name or not technician_signature:
            self.respond("Technician name and signature are required.", HTTPStatus.BAD_REQUEST)
            return
        with db() as connection:
            agreement = connection.execute("select * from service_agreements where id = ?", (data.get("agreement_id"),)).fetchone()
            if not agreement:
                self.respond("Agreement not found.", HTTPStatus.NOT_FOUND)
                return
            signed_at = now()
            new_status = "Fully Signed" if agreement["customer_signed_at"] else "Pending Customer Signature"
            connection.execute(
                """
                update service_agreements
                set technician_name = ?, technician_signature = ?, technician_signed_at = ?, status = ?, updated_at = ?
                where id = ?
                """,
                (technician_name, technician_signature, signed_at, new_status, signed_at, agreement["id"]),
            )
        self.redirect(f"/service-agreements/view?customer_id={agreement['customer_id']}")

    def estimates(self):
        user = self.current_user()
        with db() as connection:
            estimates = connection.execute(
                """
                select estimates.*, customers.name as customer_name,
                       coalesce(sum(estimate_line_items.total_cents), 0) as total_cents,
                       jobs.id as job_id
                from estimates
                join customers on customers.id = estimates.customer_id
                left join estimate_line_items on estimate_line_items.estimate_id = estimates.id
                left join jobs on jobs.estimate_id = estimates.id
                group by estimates.id
                order by estimates.updated_at desc
                """
            ).fetchall()
        rows = "".join(
            f"""
            <tr>
                <td><a href="/estimates/view?id={estimate['id']}">{esc(estimate['estimate_number'])}</a></td>
                <td>{esc(estimate['customer_name'])}</td>
                <td>{status_badge(estimate['status'])}</td>
                <td>{esc(estimate['expires_at'])}</td>
                <td>{dollars(estimate_total(estimate))}</td>
                <td>{'<a class="button secondary compact" href="/jobs">View Job</a>' if estimate['job_id'] else ''}</td>
            </tr>
            """
            for estimate in estimates
        )
        body = f"""
        <div class="heading-row"><h1>Estimates</h1><a class="button" href="/estimates/new">Create Estimate</a></div>
        <table>
            <thead><tr><th>Estimate</th><th>Customer</th><th>Status</th><th>Expires</th><th>Total</th><th>Job</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
        """
        self.respond(page("Estimates", body, user))

    def new_estimate(self, parsed):
        user = self.current_user()
        request_id = (parse_qs(parsed.query).get("request_id") or [""])[0]
        source = None
        if request_id:
            with db() as connection:
                source = connection.execute("select * from estimate_requests where id = ?", (request_id,)).fetchone()

        if self.command == "POST":
            data = self.form_data()
            try:
                unit_price_cents = parse_money_to_cents(data.get("amount"))
            except ValueError:
                self.respond("Estimate amount must be a number.", HTTPStatus.BAD_REQUEST)
                return
            if unit_price_cents <= 0:
                self.respond("Estimate amount must be greater than zero.", HTTPStatus.BAD_REQUEST)
                return

            with db() as connection:
                customer = connection.execute(
                    "select * from customers where lower(email) = lower(?) limit 1",
                    (data.get("email"),),
                ).fetchone()
                if customer:
                    customer_id = customer["id"]
                    connection.execute(
                        "update customers set name = ?, phone = ?, address = ? where id = ?",
                        (data.get("name"), data.get("phone"), data.get("address"), customer_id),
                    )
                else:
                    cursor = connection.execute(
                        "insert into customers (name, email, phone, address, created_at) values (?, ?, ?, ?, ?)",
                        (data.get("name"), data.get("email"), data.get("phone"), data.get("address"), now()),
                    )
                    customer_id = cursor.lastrowid

                next_id = connection.execute("select coalesce(max(id), 0) + 1 from estimates").fetchone()[0]
                estimate_number = f"EST-{next_id:05d}"
                created_at = now()
                cursor = connection.execute(
                    """
                    insert into estimates
                    (customer_id, source_request_id, estimate_number, status, notes, terms, expires_at, created_at, updated_at)
                    values (?, ?, ?, 'Draft', ?, ?, ?, ?, ?)
                    """,
                    (
                        customer_id,
                        data.get("source_request_id") or None,
                        estimate_number,
                        data.get("notes"),
                        data.get("terms"),
                        data.get("expires_at"),
                        created_at,
                        created_at,
                    ),
                )
                estimate_id = cursor.lastrowid
                connection.execute(
                    """
                    insert into estimate_line_items
                    (estimate_id, description, quantity, unit_price_cents, total_cents)
                    values (?, ?, 1, ?, ?)
                    """,
                    (estimate_id, data.get("service_name"), unit_price_cents, unit_price_cents),
                )
                if data.get("source_request_id"):
                    connection.execute(
                        "update estimate_requests set status = 'Estimate Created' where id = ?",
                        (data.get("source_request_id"),),
                    )
            self.redirect(f"/estimates/view?id={estimate_id}")
            return

        with db() as connection:
            services = connection.execute("select * from services order by name").fetchall()

        selected_service = source["requested_service"] if source else ""
        service_options = "".join(
            f"<option {'selected' if service['name'] == selected_service else ''}>{esc(service['name'])}</option>"
            for service in services
        )
        if selected_service and selected_service not in {service["name"] for service in services}:
            service_options = f"<option selected>{esc(selected_service)}</option>" + service_options
        expires_at = add_days(30)
        body = f"""
        <h1>Create Estimate</h1>
        <form method="post" class="form">
            <input type="hidden" name="source_request_id" value="{esc(request_id)}">
            <label>Customer Name <input name="name" value="{esc(source['name'] if source else '')}" required></label>
            <label>Email <input name="email" type="email" value="{esc(source['email'] if source else '')}" required></label>
            <label>Phone <input name="phone" value="{esc(source['phone'] if source else '')}"></label>
            <label>Service Address <input name="address" value="{esc(source['address'] if source else '')}"></label>
            <label>Service <select name="service_name" required>{service_options}</select></label>
            <label>Estimate Amount <input name="amount" inputmode="decimal" placeholder="0.00" required></label>
            <label>Expires <input name="expires_at" type="date" value="{esc(expires_at)}"></label>
            <label>Internal Notes <textarea name="notes" rows="4">{esc(source['message'] if source else '')}</textarea></label>
            <label>Customer Terms <textarea name="terms" rows="3">Estimate valid for 30 days. Approved work will be scheduled after customer confirmation.</textarea></label>
            <button>Save Estimate</button>
        </form>
        """
        self.respond(page("Create Estimate", body, user))

    def estimate_detail(self, parsed):
        user = self.current_user()
        estimate_id = (parse_qs(parsed.query).get("id") or [""])[0]
        with db() as connection:
            estimate = connection.execute(
                """
                select estimates.*, customers.name as customer_name, customers.email, customers.phone, customers.address,
                       coalesce(sum(estimate_line_items.total_cents), 0) as total_cents,
                       jobs.id as job_id
                from estimates
                join customers on customers.id = estimates.customer_id
                left join estimate_line_items on estimate_line_items.estimate_id = estimates.id
                left join jobs on jobs.estimate_id = estimates.id
                where estimates.id = ?
                group by estimates.id
                """,
                (estimate_id,),
            ).fetchone()
            if not estimate:
                self.respond("Estimate not found.", HTTPStatus.NOT_FOUND)
                return
            line_items = connection.execute(
                "select * from estimate_line_items where estimate_id = ? order by id",
                (estimate_id,),
            ).fetchall()

        status_options = "".join(
            f"<option {'selected' if status == estimate['status'] else ''}>{esc(status)}</option>"
            for status in ESTIMATE_STATUSES
        )
        rows = "".join(
            f"""
            <tr>
                <td>{esc(item['description'])}</td>
                <td>{item['quantity']}</td>
                <td>{dollars(item['unit_price_cents'])}</td>
                <td>{dollars(item['total_cents'])}</td>
            </tr>
            """
            for item in line_items
        )
        approval_block = ""
        if estimate["approved_at"]:
            approval_block = f"""
            <section class="signature-record">
                <h2>Customer Approval</h2>
                <p><strong>{esc(estimate['approval_signature'])}</strong></p>
                <p>Approved by {esc(estimate['approval_name'])} on {esc(estimate['approved_at'])}</p>
            </section>
            """
        convert_panel = ""
        if estimate["job_id"]:
            convert_panel = "<div class='notice no-print'>This estimate has already been converted into a scheduled job.</div>"
        elif estimate["status"] == "Approved":
            convert_panel = f"""
            <section class="band no-print">
                <h2>Schedule Approved Work</h2>
                <form method="post" action="/estimates/convert" class="form compact-form">
                    <input type="hidden" name="estimate_id" value="{estimate['id']}">
                    <label>Date and Time <input name="scheduled_for" type="datetime-local" required></label>
                    <label>Job Notes <textarea name="notes" rows="3">{esc(estimate['notes'])}</textarea></label>
                    <button>Convert to Job</button>
                </form>
            </section>
            """
        else:
            convert_panel = "<div class='notice no-print'>Approve this estimate before scheduling the work.</div>"

        body = f"""
        <div class="invoice-actions no-print">
            <a class="button secondary compact" href="/estimates">Back to Estimates</a>
            <button onclick="window.print()">Print Estimate</button>
        </div>
        <article class="invoice-sheet">
            <header class="invoice-header">
                <div class="invoice-company">
                    {logo()}
                    <p>{esc(COMPANY_ADDRESS)}<br>{esc(COMPANY_PHONE)}<br>{esc(COMPANY_EMAIL)}</p>
                </div>
                <div class="invoice-title">
                    <h1>Estimate</h1>
                    <dl>
                        <div><dt>Estimate #</dt><dd>{esc(estimate['estimate_number'])}</dd></div>
                        <div><dt>Status</dt><dd>{status_badge(estimate['status'])}</dd></div>
                        <div><dt>Expires</dt><dd>{esc(estimate['expires_at'])}</dd></div>
                    </dl>
                </div>
            </header>
            <section class="invoice-parties two-column">
                <div>
                    <h2>Customer</h2>
                    <p><strong>{esc(estimate['customer_name'])}</strong><br>{esc(estimate['address'])}</p>
                </div>
                <div>
                    <h2>Contact</h2>
                    <p>{esc(estimate['phone'])}<br>{esc(estimate['email'])}</p>
                </div>
            </section>
            <table class="invoice-lines">
                <thead><tr><th>Description</th><th>Qty</th><th>Price</th><th>Total</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
            <section class="invoice-summary">
                <div class="invoice-notes">
                    <h2>Notes and Terms</h2>
                    <p>{esc(estimate['notes'])}</p>
                    <p>{esc(estimate['terms'])}</p>
                    <p><strong>Disclaimer:</strong> {esc(ESTIMATE_DISCLAIMER)}</p>
                </div>
                <div class="invoice-totals">
                    <div class="total-row total"><span>Estimate Total</span><strong>{dollars(estimate_total(estimate))}</strong></div>
                </div>
            </section>
            {approval_block}
        </article>
        <section class="payment-panel no-print">
            <h2>Estimate Status</h2>
            <form method="post" action="/estimates/status" class="inline-form">
                <input type="hidden" name="estimate_id" value="{estimate['id']}">
                <select name="status">{status_options}</select>
                <button>Update Status</button>
            </form>
        </section>
        {convert_panel}
        """
        self.respond(page(f"Estimate {estimate['estimate_number']}", body, user))

    def update_estimate_status(self):
        if self.command != "POST":
            self.redirect("/estimates")
            return
        data = self.form_data()
        status = data.get("status")
        if status not in ESTIMATE_STATUSES:
            self.respond("Invalid estimate status.", HTTPStatus.BAD_REQUEST)
            return
        with db() as connection:
            connection.execute(
                "update estimates set status = ?, updated_at = ? where id = ?",
                (status, now(), data.get("estimate_id")),
            )
        self.redirect(f"/estimates/view?id={data.get('estimate_id')}")

    def convert_estimate(self):
        if self.command != "POST":
            self.redirect("/estimates")
            return
        data = self.form_data()
        estimate_id = data.get("estimate_id")
        with db() as connection:
            estimate = connection.execute(
                """
                select estimates.*, customers.name as customer_name
                from estimates
                join customers on customers.id = estimates.customer_id
                where estimates.id = ?
                """,
                (estimate_id,),
            ).fetchone()
            if not estimate:
                self.respond("Estimate not found.", HTTPStatus.NOT_FOUND)
                return
            if estimate["status"] != "Approved":
                self.respond("Only approved estimates can be converted to jobs.", HTTPStatus.BAD_REQUEST)
                return
            existing_job = connection.execute("select id from jobs where estimate_id = ?", (estimate_id,)).fetchone()
            if existing_job:
                self.redirect("/jobs")
                return
            line_item = connection.execute(
                "select * from estimate_line_items where estimate_id = ? order by id limit 1",
                (estimate_id,),
            ).fetchone()
            if not line_item:
                self.respond("Estimate needs at least one line item before it can be scheduled.", HTTPStatus.BAD_REQUEST)
                return
            notes = f"Created from {estimate['estimate_number']}."
            if data.get("notes"):
                notes += f" {data.get('notes')}"
            connection.execute(
                """
                insert into jobs (customer_id, estimate_id, service_name, scheduled_for, notes, created_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    estimate["customer_id"],
                    estimate["id"],
                    line_item["description"],
                    data.get("scheduled_for"),
                    notes,
                    now(),
                ),
            )
            connection.execute(
                "update estimates set status = 'Converted', updated_at = ? where id = ?",
                (now(), estimate["id"]),
            )
        self.redirect("/jobs")

    def jobs(self):
        user = self.current_user()
        with db() as connection:
            jobs = connection.execute(
                """
                select jobs.*, customers.name as customer_name, invoices.id as invoice_id, invoices.invoice_number,
                       service_agreements.id as agreement_id,
                       service_agreements.status as agreement_status
                from jobs join customers on customers.id = jobs.customer_id
                left join invoices on invoices.job_id = jobs.id
                left join service_agreements on service_agreements.job_id = jobs.id
                order by scheduled_for
                """
            ).fetchall()
        rows = "".join(self.job_row(job) for job in jobs)
        body = f"""
        <div class="heading-row"><h1>Jobs</h1><a class="button" href="/jobs/new">Schedule Job</a></div>
        <table><thead><tr><th>Scheduled</th><th>Customer</th><th>Service</th><th>Status</th><th>Notes</th><th>Actions</th></tr></thead><tbody>{rows}</tbody></table>
        """
        self.respond(page("Jobs", body, user))

    def job_row(self, job):
        status_options = "".join(
            f"<option {'selected' if status == job['status'] else ''}>{esc(status)}</option>"
            for status in JOB_STATUSES
        )
        complete_form = ""
        if job["status"] not in ("Completed", "Invoiced", "Cancelled"):
            complete_form = f"""
            <form method="post" action="/jobs/complete" class="inline-form stacked">
                <input type="hidden" name="job_id" value="{job['id']}">
                <textarea name="completion_notes" rows="2" placeholder="Completion notes"></textarea>
                <button>Complete Job</button>
            </form>
            """

        if job["invoice_id"]:
            invoice_control = f"<a class='button secondary compact' href='/invoices/view?id={job['invoice_id']}'>View {esc(job['invoice_number'])}</a>"
        elif job["status"] == "Completed":
            invoice_control = f"""
            <form method="post" action="/invoices/create" class="inline-form">
                <input type="hidden" name="job_id" value="{job['id']}">
                <input name="amount" inputmode="decimal" placeholder="Amount" required>
                <button>Create Invoice</button>
            </form>
            """
        else:
            invoice_control = "<span class='muted'>Complete job before invoicing</span>"
        agreement_control = f"""
        <a class="button secondary compact" href="/service-agreements/view?job_id={job['id']}">Service Agreement</a>
        <small>{esc(job['agreement_status'] or 'Not Started')}</small>
        """

        return f"""
        <tr>
            <td>{esc(job['scheduled_for'])}</td>
            <td>{esc(job['customer_name'])}</td>
            <td>{esc(job['service_name'])}</td>
            <td><span class="status">{esc(job['status'])}</span></td>
            <td>{esc(job['notes'])}<br><small>{esc(job['completion_notes'])}</small></td>
            <td>
                <form method="post" action="/jobs/status" class="inline-form">
                    <input type="hidden" name="job_id" value="{job['id']}">
                    <select name="status">{status_options}</select>
                    <button>Update</button>
                </form>
                {complete_form}
                {invoice_control}
                {agreement_control}
            </td>
        </tr>
        """

    def update_job_status(self):
        if self.command != "POST":
            self.redirect("/jobs")
            return
        data = self.form_data()
        status = data.get("status")
        if status not in JOB_STATUSES:
            self.respond("Invalid job status", HTTPStatus.BAD_REQUEST)
            return
        completed_at = now() if status == "Completed" else None
        with db() as connection:
            if status == "Completed":
                connection.execute(
                    "update jobs set status = ?, completed_at = coalesce(completed_at, ?) where id = ?",
                    (status, completed_at, data.get("job_id")),
                )
            else:
                connection.execute("update jobs set status = ? where id = ?", (status, data.get("job_id")))
        self.redirect("/jobs")

    def complete_job(self):
        if self.command != "POST":
            self.redirect("/jobs")
            return
        data = self.form_data()
        with db() as connection:
            connection.execute(
                """
                update jobs
                set status = 'Completed', completed_at = coalesce(completed_at, ?), completion_notes = ?
                where id = ?
                """,
                (now(), data.get("completion_notes"), data.get("job_id")),
            )
        self.redirect("/jobs")

    def create_invoice(self):
        if self.command != "POST":
            self.redirect("/jobs")
            return
        data = self.form_data()
        job_id = data.get("job_id")
        try:
            amount_cents = parse_money_to_cents(data.get("amount"))
        except ValueError:
            self.respond("Invoice amount must be a number.", HTTPStatus.BAD_REQUEST)
            return
        if amount_cents <= 0:
            self.respond("Invoice amount must be greater than zero.", HTTPStatus.BAD_REQUEST)
            return

        with db() as connection:
            job = connection.execute(
                """
                select jobs.*, customers.name as customer_name
                from jobs join customers on customers.id = jobs.customer_id
                where jobs.id = ?
                """,
                (job_id,),
            ).fetchone()
            if not job:
                self.respond("Job not found.", HTTPStatus.NOT_FOUND)
                return
            if job["status"] != "Completed":
                self.respond("Only completed jobs can be invoiced.", HTTPStatus.BAD_REQUEST)
                return

            existing = connection.execute("select id from invoices where job_id = ?", (job_id,)).fetchone()
            if existing:
                self.redirect("/invoices")
                return

            next_id = connection.execute("select coalesce(max(id), 0) + 1 from invoices").fetchone()[0]
            invoice_number = f"INV-{next_id:05d}"
            created_at = now()
            due_date = add_days_to_date(job["scheduled_for"], 15)
            cursor = connection.execute(
                """
                insert into invoices
                (customer_id, job_id, invoice_number, subtotal_cents, total_cents, due_date, created_at)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (job["customer_id"], job["id"], invoice_number, amount_cents, amount_cents, due_date, created_at),
            )
            invoice_id = cursor.lastrowid
            connection.execute(
                """
                insert into invoice_line_items
                (invoice_id, description, quantity, unit_price_cents, total_cents)
                values (?, ?, 1, ?, ?)
                """,
                (invoice_id, job["service_name"], amount_cents, amount_cents),
            )
            connection.execute(
                "update customers set balance_cents = balance_cents + ? where id = ?",
                (amount_cents, job["customer_id"]),
            )
            connection.execute("update jobs set status = 'Invoiced' where id = ?", (job["id"],))
        self.redirect(f"/invoices/view?id={invoice_id}")

    def create_payment(self):
        if self.command != "POST":
            self.redirect("/invoices")
            return
        user = self.current_user()
        data = self.form_data()
        invoice_id = data.get("invoice_id")
        method = data.get("method")
        if method not in PAYMENT_METHODS:
            self.respond("Invalid payment method.", HTTPStatus.BAD_REQUEST)
            return
        try:
            amount_cents = parse_money_to_cents(data.get("amount"))
        except ValueError:
            self.respond("Payment amount must be a number.", HTTPStatus.BAD_REQUEST)
            return
        if amount_cents <= 0:
            self.respond("Payment amount must be greater than zero.", HTTPStatus.BAD_REQUEST)
            return

        with db() as connection:
            invoice = connection.execute("select * from invoices where id = ?", (invoice_id,)).fetchone()
            if not invoice:
                self.respond("Invoice not found.", HTTPStatus.NOT_FOUND)
                return
            current_balance = invoice_balance(invoice)
            if amount_cents > current_balance:
                self.respond("Payment cannot be greater than the invoice balance.", HTTPStatus.BAD_REQUEST)
                return

            paid_at = data.get("paid_at") or dt.date.today().isoformat()
            connection.execute(
                """
                insert into payments
                (customer_id, invoice_id, recorded_by_user_id, recorded_by_name, amount_cents, method, reference, note, paid_at, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice["customer_id"],
                    invoice["id"],
                    user["id"],
                    user["name"],
                    amount_cents,
                    method,
                    data.get("reference"),
                    data.get("note"),
                    paid_at,
                    now(),
                ),
            )
            new_paid_total = invoice["amount_paid_cents"] + amount_cents
            preview = dict(invoice)
            preview["amount_paid_cents"] = new_paid_total
            new_status = invoice_status(preview)
            connection.execute(
                "update invoices set amount_paid_cents = ?, status = ? where id = ?",
                (new_paid_total, new_status, invoice["id"]),
            )
            connection.execute(
                """
                update customers
                set balance_cents = max(balance_cents - ?, 0)
                where id = ?
                """,
                (amount_cents, invoice["customer_id"]),
            )
        self.redirect(f"/invoices/view?id={invoice_id}")

    def invoices(self):
        user = self.current_user()
        with db() as connection:
            sync_invoice_statuses(connection)
            invoices = connection.execute(
                """
                select invoices.*, customers.name as customer_name, jobs.service_name, jobs.scheduled_for
                from invoices
                join customers on customers.id = invoices.customer_id
                join jobs on jobs.id = invoices.job_id
                order by invoices.created_at desc
                """
            ).fetchall()
        rows = "".join(
            f"""
            <tr>
                <td><a href="/invoices/view?id={invoice['id']}">{esc(invoice['invoice_number'])}</a></td>
                <td>{esc(invoice['customer_name'])}</td>
                <td>{esc(invoice['service_name'])}</td>
                <td>{esc(invoice['created_at'])}</td>
                <td>{esc(invoice['due_date'])}</td>
                <td>{dollars(invoice['total_cents'])}</td>
                <td>{dollars(invoice_balance(invoice))}</td>
                <td>{status_badge(invoice_status(invoice))}</td>
            </tr>
            """
            for invoice in invoices
        )
        body = f"""
        <h1>Invoices</h1>
        <table>
            <thead>
                <tr><th>Invoice</th><th>Customer</th><th>Service</th><th>Created</th><th>Due</th><th>Total</th><th>Balance</th><th>Status</th></tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
        """
        self.respond(page("Invoices", body, user))

    def invoice_detail(self, parsed):
        user = self.current_user()
        invoice_id = (parse_qs(parsed.query).get("id") or [""])[0]
        with db() as connection:
            sync_invoice_statuses(connection)
            invoice = connection.execute(
                """
                select invoices.*, customers.name as customer_name, customers.email, customers.phone,
                       customers.address, customers.balance_cents,
                       jobs.service_name, jobs.scheduled_for, jobs.notes, jobs.completed_at,
                       jobs.completion_notes, services.description as service_description
                from invoices
                join customers on customers.id = invoices.customer_id
                join jobs on jobs.id = invoices.job_id
                left join services on services.name = jobs.service_name
                where invoices.id = ?
                """,
                (invoice_id,),
            ).fetchone()
            if not invoice:
                self.respond("Invoice not found.", HTTPStatus.NOT_FOUND)
                return
            line_items = connection.execute(
                "select * from invoice_line_items where invoice_id = ? order by id",
                (invoice_id,),
            ).fetchall()
            payments = connection.execute(
                "select * from payments where invoice_id = ? order by paid_at desc, id desc",
                (invoice_id,),
            ).fetchall()

        line_rows = "".join(
            f"""
            <tr>
                <td>
                    <strong>{esc(item['description'])}</strong>
                    <small>{esc(invoice['service_description'])}</small>
                </td>
                <td>{dollars(item['unit_price_cents'])}</td>
                <td>{item['quantity']}</td>
                <td>{dollars(item['total_cents'])}</td>
            </tr>
            """
            for item in line_items
        )
        amount_due = invoice_balance(invoice)
        current_status = invoice_status(invoice)
        overdue_notice = ""
        if current_status == "Overdue":
            overdue_notice = f"<div class='notice danger no-print'>This invoice is overdue. {dollars(amount_due)} is past due as of {esc(invoice['due_date'])}.</div>"
        paid_note = ""
        if invoice["amount_paid_cents"]:
            paid_note = f"<div class='total-row'><span>Amount Paid</span><strong>{dollars(invoice['amount_paid_cents'])}</strong></div>"

        payment_method_options = "".join(f"<option>{esc(method)}</option>" for method in PAYMENT_METHODS)
        payment_form = ""
        if amount_due > 0:
            payment_form = f"""
            <section class="payment-panel no-print">
                <h2>Record Payment</h2>
                <form method="post" action="/payments/create" class="payment-form">
                    <input type="hidden" name="invoice_id" value="{invoice['id']}">
                    <label>Amount <input name="amount" inputmode="decimal" value="{amount_due / 100:.2f}" required></label>
                    <label>Method <select name="method" required>{payment_method_options}</select></label>
                    <label>Date <input name="paid_at" type="date" value="{dt.date.today().isoformat()}" required></label>
                    <label>Reference <input name="reference" placeholder="Check # or card reference"></label>
                    <label>Note <textarea name="note" rows="2"></textarea></label>
                    <button>Record Payment</button>
                </form>
            </section>
            """
        else:
            payment_form = "<section class='payment-panel no-print'><h2>Record Payment</h2><p class='notice'>This invoice is paid in full.</p></section>"

        payment_rows = "".join(
            f"""
            <tr>
                <td>{esc(payment['paid_at'])}</td>
                <td>{esc(payment['recorded_by_name'] or 'Unknown')}</td>
                <td>{esc(payment['method'])}</td>
                <td>{esc(payment['reference'])}</td>
                <td>{esc(payment['note'])}</td>
                <td>{dollars(payment['amount_cents'])}</td>
            </tr>
            """
            for payment in payments
        )
        payment_history = ""
        if payments:
            payment_history = f"""
            <section class="payment-history">
                <h2>Payment History</h2>
                <table>
                    <thead><tr><th>Date</th><th>Recorded By</th><th>Method</th><th>Reference</th><th>Note</th><th>Amount</th></tr></thead>
                    <tbody>{payment_rows}</tbody>
                </table>
            </section>
            """

        work_notes = invoice["completion_notes"] or invoice["notes"] or "Thank you for your business."
        body = f"""
        <div class="invoice-actions no-print">
            <a class="button secondary compact" href="/invoices">Back to Invoices</a>
            <button onclick="window.print()">Print Invoice</button>
        </div>
        {overdue_notice}
        {payment_form}
        <article class="invoice-sheet">
            <header class="invoice-header">
                <div class="invoice-company">
                    {logo()}
                    <p>{esc(COMPANY_ADDRESS)}<br>{esc(COMPANY_PHONE)}</p>
                </div>
                <div class="invoice-title">
                    <h1>Invoice</h1>
                    <dl>
                        <div><dt>Account #</dt><dd>{invoice['customer_id']:04d}</dd></div>
                        <div><dt>Invoice #</dt><dd>{esc(invoice['invoice_number'])}</dd></div>
                <div><dt>Invoice Date</dt><dd>{esc(invoice['created_at'].split(' ')[0])}</dd></div>
                        <div><dt>Due Date</dt><dd>{esc(invoice['due_date'])}</dd></div>
                        <div><dt>Status</dt><dd>{status_badge(current_status)}</dd></div>
                    </dl>
                </div>
            </header>

            <section class="invoice-parties">
                <div>
                    <h2>Bill To</h2>
                    <p><strong>{esc(invoice['customer_name'])}</strong><br>{esc(invoice['address'])}</p>
                </div>
                <div>
                    <h2>Service Address</h2>
                    <p><strong>{esc(invoice['customer_name'])}</strong><br>{esc(invoice['address'])}</p>
                </div>
                <div>
                    <h2>Primary Contact</h2>
                    <p><strong>{esc(invoice['customer_name'])}</strong><br>{esc(invoice['phone'])}<br>{esc(invoice['email'])}</p>
                </div>
            </section>

            <table class="invoice-lines">
                <thead><tr><th>Item</th><th>Cost</th><th>Qty</th><th>Price</th></tr></thead>
                <tbody>{line_rows}</tbody>
            </table>

            <section class="invoice-summary">
                <div class="invoice-notes">
                    <h2>Terms</h2>
                    <p>Payment is due 15 days from the date of service.</p>
                    <h2>Notes</h2>
                    <p>Thank you for your business.</p>
                    <p>{esc(work_notes)}</p>
                    <p>Service Date: {esc(date_part(invoice['scheduled_for']))}</p>
                    <p>Due Date: {esc(invoice['due_date'])}</p>
                    <p>There will be a $5.00 late fee for invoices not paid by the due date.</p>
                </div>
                <div class="invoice-totals">
                    <div class="total-row"><span>Subtotal</span><strong>{dollars(invoice['subtotal_cents'])}</strong></div>
                    <div class="total-row"><span>Discount</span><strong>{dollars(invoice['credit_applied_cents'])}</strong></div>
                    <div class="total-row total"><span>Total</span><strong>{dollars(invoice['total_cents'])}</strong></div>
                    {paid_note}
                    <div class="total-row"><span>Amount Due</span><strong>{dollars(amount_due)}</strong></div>
                    <div class="total-row"><span>Account Balance</span><strong>{dollars(invoice['balance_cents'])}</strong></div>
                    <div class="total-row total"><span>Balance Due</span><strong>{dollars(amount_due)}</strong></div>
                </div>
            </section>

            <section class="signature-grid">
                <div><span>Client Signature</span></div>
                <div><span>Tech Signature</span></div>
            </section>

            {payment_history}

            <footer class="invoice-footer">
                <p>PHONE: {esc(COMPANY_PHONE)} &nbsp; EMAIL: {esc(COMPANY_EMAIL)} &nbsp; {esc(COMPANY_WEBSITE)}</p>
            </footer>

            <section class="payment-stub">
                <h2>Payment Stub</h2>
                <dl>
                    <div><dt>Customer</dt><dd>{esc(invoice['customer_name'])}</dd></div>
                    <div><dt>Account #</dt><dd>{invoice['customer_id']:04d}</dd></div>
                    <div><dt>Invoice #</dt><dd>{esc(invoice['invoice_number'])}</dd></div>
                    <div><dt>Invoice Date</dt><dd>{esc(invoice['created_at'].split(' ')[0])}</dd></div>
                    <div><dt>Balance Due</dt><dd>{dollars(amount_due)}</dd></div>
                    <div><dt>Amount Enclosed</dt><dd>&nbsp;</dd></div>
                </dl>
            </section>
        </article>
        """
        self.respond(page(f"Invoice {invoice['invoice_number']}", body, user))

    def new_job(self):
        user = self.current_user()
        if self.command == "POST":
            data = self.form_data()
            with db() as connection:
                connection.execute(
                    """
                    insert into jobs (customer_id, service_name, scheduled_for, notes, created_at)
                    values (?, ?, ?, ?, ?)
                    """,
                    (data.get("customer_id"), data.get("service_name"), data.get("scheduled_for"), data.get("notes"), now()),
                )
            self.redirect("/jobs")
            return
        with db() as connection:
            customers = connection.execute("select * from customers order by name").fetchall()
            services = connection.execute("select * from services order by name").fetchall()
        customer_options = "".join(f"<option value='{row['id']}'>{esc(row['name'])}</option>" for row in customers)
        service_options = "".join(f"<option>{esc(row['name'])}</option>" for row in services)
        body = f"""
        <h1>Schedule Job</h1>
        <form method="post" class="form">
            <label>Customer <select name="customer_id" required>{customer_options}</select></label>
            <label>Service <select name="service_name" required>{service_options}</select></label>
            <label>Date and Time <input name="scheduled_for" type="datetime-local" required></label>
            <label>Notes <textarea name="notes" rows="4"></textarea></label>
            <button>Schedule Job</button>
        </form>
        """
        self.respond(page("Schedule Job", body, user))

    def inquiries(self):
        user = self.current_user()
        with db() as connection:
            requests = connection.execute("select * from estimate_requests order by created_at desc").fetchall()
        rows = "".join(
            f"""
            <tr>
                <td>{esc(row['created_at'])}</td>
                <td>{esc(row['name'])}</td>
                <td>{esc(row['email'])}</td>
                <td>{esc(row['requested_service'])}</td>
                <td>{status_badge(row['status'])}</td>
                <td><a class="button secondary compact" href="/estimates/new?request_id={row['id']}">Create Estimate</a></td>
            </tr>
            """
            for row in requests
        )
        body = f"""
        <h1>Website Requests</h1>
        <table><thead><tr><th>Created</th><th>Name</th><th>Email</th><th>Service</th><th>Status</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table>
        """
        self.respond(page("Requests", body, user))

    def static_css(self):
        self.respond((ROOT / "static" / "styles.css").read_text(), content_type="text/css")

    def static_logo(self):
        self.respond((ROOT / "static" / "logo-mark.svg").read_text(), content_type="image/svg+xml")

    def static_official_logo(self):
        self.respond((ROOT / "static" / "official-logo.svg").read_text(), content_type="image/svg+xml")


if __name__ == "__main__":
    init_database()
    print(f"Groundworks is running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), App).serve_forever()
