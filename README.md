# RCS Convocation Extractor — Laravel + GitHub Actions

This repository hosts a full flow for extracting structured data from Convocation PDFs using a Laravel API and a GitHub Actions extractor.

## Prerequisites
- PHP 8.1+ and Composer
- Node 18+ (optional for frontend tweaks)
- XAMPP MySQL running locally
- Git and GitHub access

## Setup
1. Create Laravel app (already scaffolded here under `rcs-app`).
2. Copy frontend into `rcs-app/public/convocation/` (already done).
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
- Open http://127.0.0.1:8000/convocation/index.html

## Endpoints
- POST /api/upload
- GET  /api/documents
- DELETE /api/documents
- GET  /api/search
- POST /api/github/callback
- POST /api/github/upload-results

## GitHub Actions
Ensure the following repo secrets are added in GitHub:
- CALLBACK_HMAC_SECRET (same as EXTRACTOR_CALLBACK_SECRET)
- RESULT_UPLOAD_TOKEN (same as EXTRACTOR_BEARER_TOKEN)

The workflow is at `.github/workflows/process_pdf.yml`.

## Notes
- The upload endpoint only dispatches to GitHub when `GITHUB_PAT` is set.
- The extractor script is in `scripts/extract.py` and expects environment vars from the workflow.