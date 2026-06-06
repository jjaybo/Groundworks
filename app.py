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

            create table if not exists jobs (
                id integer primary key autoincrement,
                customer_id integer not null references customers(id),
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
            """
        )

        ensure_column(connection, "jobs", "completed_at", "text")
        ensure_column(connection, "jobs", "completion_notes", "text")
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


def status_badge(status):
    return f"<span class='status status-{esc(status).lower()}'>{esc(status)}</span>"


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def logo():
    return f"""
    <img src="/static/official-logo.svg" alt="{esc(COMPANY_NAME)} - {esc(COMPANY_TAGLINE)}" class="official-logo">
    """


def page(title, body, user=None):
    nav = """
    <a href="/">Home</a>
    <a href="/services">Services & Pricing</a>
    <a href="/request-estimate">Request Estimate</a>
    <a href="/signup">Create Account</a>
    """
    if user:
        nav += """
        <a href="/dashboard">Dashboard</a>
        <a href="/customers">Customers</a>
        <a href="/jobs">Jobs</a>
        <a href="/invoices">Invoices</a>
        <a href="/inquiries">Requests</a>
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
            elif path == "/signup":
                self.signup()
            elif path == "/login":
                self.login()
            elif path == "/logout":
                self.logout()
            elif path == "/dashboard":
                self.require_user()
                self.dashboard()
            elif path == "/customers":
                self.require_user()
                self.customers()
            elif path == "/customers/new":
                self.require_user()
                self.new_customer()
            elif path == "/jobs":
                self.require_user()
                self.jobs()
            elif path == "/jobs/new":
                self.require_user()
                self.new_job()
            elif path == "/jobs/status":
                self.require_user()
                self.update_job_status()
            elif path == "/jobs/complete":
                self.require_user()
                self.complete_job()
            elif path == "/invoices":
                self.require_user()
                self.invoices()
            elif path == "/invoices/view":
                self.require_user()
                self.invoice_detail(parsed)
            elif path == "/invoices/create":
                self.require_user()
                self.create_invoice()
            elif path == "/payments/create":
                self.require_user()
                self.create_payment()
            elif path == "/inquiries":
                self.require_user()
                self.inquiries()
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
        <h1>Staff Login</h1>
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
        with db() as connection:
            sync_invoice_statuses(connection)
            customer_count = connection.execute("select count(*) from customers").fetchone()[0]
            request_count = connection.execute("select count(*) from estimate_requests where status = 'New'").fetchone()[0]
            job_count = connection.execute("select count(*) from jobs where status in ('Scheduled', 'In Progress')").fetchone()[0]
            invoice_total = connection.execute("select coalesce(sum(total_cents - amount_paid_cents), 0) from invoices where status in ('Open', 'Overdue')").fetchone()[0]
            overdue_count = connection.execute("select count(*) from invoices where status = 'Overdue'").fetchone()[0]
            overdue_total = connection.execute("select coalesce(sum(total_cents - amount_paid_cents), 0) from invoices where status = 'Overdue'").fetchone()[0]
        body = f"""
        <h1>Dashboard</h1>
        <div class="grid">
            <article class="metric"><strong>{customer_count}</strong><span>Customers</span></article>
            <article class="metric"><strong>{request_count}</strong><span>New Requests</span></article>
            <article class="metric"><strong>{job_count}</strong><span>Open Jobs</span></article>
            <article class="metric"><strong>{dollars(invoice_total)}</strong><span>Open Invoices</span></article>
            <article class="metric danger-metric"><strong>{overdue_count}</strong><span>Overdue Invoices</span><small>{dollars(overdue_total)} past due</small></article>
        </div>
        """
        self.respond(page("Dashboard", body, user))

    def customers(self):
        user = self.current_user()
        with db() as connection:
            rows = connection.execute("select * from customers order by created_at desc").fetchall()
        table = "".join(
            f"<tr><td>{esc(row['name'])}</td><td>{esc(row['email'])}</td><td>{esc(row['phone'])}</td><td>{esc(row['address'])}</td><td>{dollars(row['balance_cents'])}</td></tr>"
            for row in rows
        )
        body = f"""
        <div class="heading-row"><h1>Customers</h1><a class="button" href="/customers/new">Add Customer</a></div>
        <table><thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Address</th><th>Balance</th></tr></thead><tbody>{table}</tbody></table>
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

    def jobs(self):
        user = self.current_user()
        with db() as connection:
            jobs = connection.execute(
                """
                select jobs.*, customers.name as customer_name, invoices.id as invoice_id, invoices.invoice_number
                from jobs join customers on customers.id = jobs.customer_id
                left join invoices on invoices.job_id = jobs.id
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
            f"<tr><td>{esc(row['created_at'])}</td><td>{esc(row['name'])}</td><td>{esc(row['email'])}</td><td>{esc(row['requested_service'])}</td><td>{esc(row['status'])}</td></tr>"
            for row in requests
        )
        body = f"""
        <h1>Website Requests</h1>
        <table><thead><tr><th>Created</th><th>Name</th><th>Email</th><th>Service</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table>
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
