# crypto-journal

Short description: importer for Blofin order history CSVs into Postgres, plus some small tools.

Quick start
1. Create and activate venv:
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

2. Install dependencies:
   python -m pip install -r requirements.txt

3. Set DB DSN (PowerShell):
   $env:CRYPTO_JOURNAL_DSN = "dbname=crypto_journal user=postgres password=YOURPASS host=127.0.0.1 port=5432"

4. Put Blofin CSVs into `inbox/` then run:
   python import_blofin_csv.py --input ".\inbox" --tz "America/Los_Angeles" --archive-dir ".\archive"

Notes
- Do not commit your .venv or CSV exports.
- Use the `inbox/` folder for files you want the importer to process.
