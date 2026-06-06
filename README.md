# Groundworks

Groundworks is a web-based operating system for a lawn care business. The current version is a beginner-friendly Python starter app that demonstrates the public website, estimate requests, account creation, staff login, customer management, and job scheduling.

The starter also includes job status updates and basic invoice generation from completed jobs.

## Run The Starter App

If Python is installed on your computer and available in PowerShell:

```powershell
python app.py
```

In this Codex workspace, Python is available at:

```powershell
& 'C:\Users\jjayb\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' app.py
```

Then open:

```text
http://127.0.0.1:8000
```

If port `8000` is already busy, run the app on another port:

```powershell
$env:PORT='8010'
python app.py
```

For testing without touching your normal local database, you can point the app at a different SQLite file:

```powershell
$env:DB_PATH='groundworks-test.db'
python app.py
```

Starter admin login:

```text
Email: admin@groundworks.local
Password: admin123
```

## Project Files

- `app.py`: Python server, routes, forms, database setup, login, customers, jobs, and website pages.
- `static/styles.css`: page styling.
- `static/official-logo.svg`: official J&E logo used by the app.
- `static/logo-mark.svg`: earlier starter logo mark kept as a fallback/reference.
- `docs/groundworks-product-blueprint.md`: product requirements and phased feature plan.
- `docs/getting-started.md`: beginner walkthrough.
- `docs/brand-notes.md`: brand colors, typefaces, tagline, and logo usage notes from the provided PDF.
- `docs/invoice-template-notes.md`: invoice layout requirements learned from the paid and unpaid invoice samples.
- `data/service-price-list.csv`: service catalog imported from the provided J&E price list workbook.
