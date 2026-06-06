# Getting Started With Groundworks

This project starts with a beginner-friendly Python web app. It uses only Python's built-in tools so you can learn the moving parts before adding larger frameworks.

## What We Built First

- `app.py`: the Python web server, routing, database setup, forms, login, and page rendering.
- `static/styles.css`: the visual design for the public website and internal screens.
- `groundworks.db`: the SQLite database file. Python creates it automatically the first time the app runs.

## How To Run It

Open PowerShell in the Groundworks folder and run:

```powershell
python app.py
```

If PowerShell says `python` is not recognized, use the bundled Python path available in this Codex workspace:

```powershell
& 'C:\Users\jjayb\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' app.py
```

Then open:

```text
http://127.0.0.1:8000
```

The starter admin login is:

```text
Email: admin@groundworks.local
Password: admin123
```

## What Each Part Does

### Python

Python is the programming language running the server. The server receives browser requests and sends back HTML pages.

### HTML

HTML is the structure of the web pages. It defines headings, links, forms, tables, and buttons.

### CSS

CSS controls the appearance of the pages: colors, spacing, typography, layout, and mobile behavior.

### SQLite

SQLite is a small database stored in one local file. It is good for learning and prototyping because it does not require a separate database server.

### Routes

A route is a URL the app knows how to answer.

Examples:

- `/` shows the public homepage.
- `/services` shows transparent service pricing.
- `/request-estimate` lets a visitor request an estimate.
- `/login` logs staff into the internal system.
- `/customers` shows customer records.
- `/jobs` shows scheduled jobs.

## How The App Works

1. You run `python app.py`.
2. Python creates the database tables if they do not exist.
3. Python starts a local web server at `http://127.0.0.1:8000`.
4. Your browser requests a page.
5. The server looks at the URL and runs the matching route.
6. The route reads or writes data in SQLite.
7. The server returns an HTML page to the browser.

## Why Start This Way

This starter keeps the first version understandable. Later, we can move the same concepts into a professional framework such as Django or FastAPI when you are ready.

Recommended next learning path:

1. Run the app.
2. Add a customer.
3. Submit an estimate request from the public site.
4. Log in and view the request.
5. Schedule a job.
6. Change the job status.
7. Complete the job with completion notes.
8. Create an invoice from the completed job.
9. Open the invoice detail page and use the print button.
10. Record a payment against the invoice.
11. Review `app.py` route by route.

## New Concepts: Job Status And Invoices

A job status update is a small HTML form that sends a `POST` request to the server. The server reads the job ID and the new status, then updates the matching row in the `jobs` table.

Invoice generation writes multiple records together:

- one row in `invoices`
- one row in `invoice_line_items`
- an updated customer balance
- an updated job status of `Invoiced`
- a due date calculated 15 days after the service date

Those related writes happen inside one database connection so the records stay linked.

The invoice detail page is a normal web page with print-specific CSS. That means the same HTML can be viewed in the browser today and can later become the basis for a real PDF export feature.

## New Concept: Payments

A payment is stored separately from the invoice. This gives the business a history of what was paid, when it was paid, and how it was paid.

When a payment is recorded:

- one row is added to the `payments` table
- the invoice's `amount_paid_cents` increases
- the invoice status changes to `Paid` if the full balance has been paid
- the customer's account balance is reduced

## Installing Python Normally

For day-to-day development, install Python from:

```text
https://www.python.org/downloads/windows/
```

During installation, check the box that says `Add python.exe to PATH`. That lets PowerShell understand:

```powershell
python app.py
```

without needing the long bundled path.
