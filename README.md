# RCS Convocation Extractor — Laravel + GitHub Actions

End‑to‑end pipeline: upload a Convocation PDF in the Laravel app, process it in GitHub Actions, and push structured results (CSV/XLSX/DOCX) back to the app. Now resilient for long PDFs via chunked extraction.

## Prerequisites
- PHP 8.1+ and Composer
- Node 18+ (optional for frontend tweaks)
- XAMPP MySQL running locally
- Git and GitHub access

## Setup
1. Laravel app lives in `rcs-app` (already scaffolded).
2. Frontend runs as a Blade view with Vite/Tailwind. Entry: `resources/views/convocation.blade.php` and `resources/js/convocation.js`.
3. Configure environment in `rcs-app/.env`:
   - APP_URL=http://127.0.0.1:8000
   - DB_CONNECTION=mysql
   - DB_HOST=127.0.0.1
   - DB_PORT=3306
   - DB_DATABASE=ai_agent_secondlevel_verification
   - DB_USERNAME=root
   - DB_PASSWORD=
   - GITHUB_PAT=your_pat_with_repo_write
   - EXTRACTOR_CALLBACK_SECRET=your_random_long_secret
   - EXTRACTOR_BEARER_TOKEN=your_random_long_secret
4. Link storage and generate app key:
   - php artisan key:generate
   - php artisan storage:link
5. Migrate DB:
   - php artisan migrate

## Run (Local)
- cd rcs-app
- php artisan serve --host=127.0.0.1 --port=8000
- Open http://127.0.0.1:8000/ (convocation UI is served by Blade)

## Endpoints
- POST /api/upload
- GET  /api/documents
- DELETE /api/documents
- GET  /api/search
- POST /api/github/callback
- POST /api/github/upload-results

## GitHub Actions (Extractor)
Workflow: `.github/workflows/process_pdf.yml`.

What it does now:
- Probes the uploaded PDF and determines total pages.
- Splits work into page ranges (default 10 pages per chunk) and runs them in parallel.
- Downloads the source PDF once and reuses it across chunks (prevents signed URL expiration issues).
- Aggregates CSV results from all chunks into a single CSV/XLSX/DOCX.
- Uploads results back to the app and posts a JSON callback on success.

Required repo secrets:
- `CALLBACK_HMAC_SECRET` -> must equal `EXTRACTOR_CALLBACK_SECRET` in Laravel `.env`.
- `RESULT_UPLOAD_TOKEN` -> must equal `EXTRACTOR_BEARER_TOKEN` in Laravel `.env`.

Important app settings:
- Set `APP_URL` to your live domain (e.g., `https://search.riskcontrolnigeria.com`).
- We force HTTPS and use `URL::temporarySignedRoute` for downloads. Expiry is set to 24h for reliability..

Optional knob in client payload:
- `chunk_size` (int): pages per chunk. If omitted, defaults to 10.

## Notes
- The upload endpoint only dispatches to GitHub when `GITHUB_PAT` is set.
- Extractor script: `scripts/extract.py`
  - Supports page ranges via env: `PAGE_START`, `PAGE_END`, or `PAGES` (e.g., `1-10,12,15-18`).
  - OCR tuning: `OCR_DPI` (default 250), `TESSERACT_PSM`, `TESSERACT_LANG`.
  - Keep‑alive logs per page to avoid idle timeouts.
- Aggregation script: `scripts/aggregate_results.py` merges chunk CSVs and performs a single upload+callback.

## Troubleshooting & Recovery Runbook

If a long PDF run was cancelled or took too long:
1. Ensure GitHub repo secrets are set:
   - `CALLBACK_HMAC_SECRET` and `RESULT_UPLOAD_TOKEN` must not be empty.
2. Ensure Laravel `.env` matches:
   - `EXTRACTOR_CALLBACK_SECRET` and `EXTRACTOR_BEARER_TOKEN` match the GitHub secrets.
   - `APP_URL` uses your HTTPS live domain; run `php artisan config:clear` then `config:cache`.
3. Re‑upload the PDF via the UI. The workflow now:
   - Splits into 10‑page chunks (configurable `chunk_size`).
   - Uses the single downloaded source artifact across chunks (no signed URL churn).
   - Aggregates and uploads results to the app.
4. If OCR is slow or unnecessary:
   - Many Convocation PDFs are text‑based; extraction will auto‑detect and skip OCR.
   - For image‑only PDFs, you can lower `OCR_DPI` (e.g., 220) or set `TESSERACT_PSM` depending on layout.
5. For very large documents:
   - Increase concurrency by lowering `chunk_size`.
   - Consider a self‑hosted runner with more CPU/RAM; the workflow works on both hosted and self‑hosted.

## Self‑Hosted Runner (Optional)
If you prefer not to use GitHub’s hosted runners for long extractions:
- Register a self‑hosted runner on a machine with Tesseract and Poppler.
- Ensure Python 3.11 and the packages in `requirements.txt` are installed.
- The same workflow will run on your runner (change `runs-on` to your label if needed).