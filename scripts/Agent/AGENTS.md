# AGENTS.md — Implementation Guide for Copilot GPT-5 (VS Code) — Laravel + GitHub Actions Convocation Extractor

This document provides everything needed for an AI agent (Copilot GPT-5 in VS Code) to implement and ship a complete Laravel-based system that:
- Accepts convocation PDFs (text or image-based)
- Sends them to a GitHub Actions worker for robust extraction (1/2/3 columns)
- Receives structured outputs (CSV, XLSX, DOCX) + JSON audit
- Persists all student rows to MySQL (XAMPP)
- Exposes powerful search + file downloads
- Supports a Delete All PDFs & Data operation

Company: Risk Control Services Nigeria
Local DB (XAMPP MySQL): ai_agent_secondlevel_verification

Repo: https://github.com/Riskcontrol/ai_agent_secondlevel_verification
Frontend scaffold already included (frontend/). Extractor and scripting scaffold already included (scripts/).

-------------------------------------------------------------------------------
1) PREREQUISITES (LOCAL DEV WITH XAMPP)
-------------------------------------------------------------------------------
- OS: Windows/macOS/Linux with XAMPP running MySQL
- PHP 8.1+ and Composer installed
- Node 18+ and npm
- VS Code with GitHub Copilot and GitHub extension
- Git configured and access to the above GitHub repo (main branch)
- XAMPP MySQL:
  - Database: ai_agent_secondlevel_verification (already created)
  - Default MySQL credentials on XAMPP: user=root, password="" (empty), host=127.0.0.1, port=3306

-------------------------------------------------------------------------------
2) CLONE REPO AND CREATE LARAVEL APP
-------------------------------------------------------------------------------
- In VS Code terminal:
  git clone https://github.com/Riskcontrol/ai_agent_secondlevel_verification.git
  cd ai_agent_secondlevel_verification

- If Laravel app does not exist yet in this repo, create it in a subfolder `rcs-app`:
  composer create-project laravel/laravel rcs-app

- Move existing frontend/ into Laravel public directory:
  - Copy repo folder frontend/* to rcs-app/public/convocation/

- Commit these repo changes once arranged.

-------------------------------------------------------------------------------
3) LARAVEL ENV CONFIG (.env)
-------------------------------------------------------------------------------
Inside rcs-app/.env update/add:

APP_NAME="RCS Convocation Extractor"
APP_ENV=local
APP_KEY=base64:GENERATE_THIS
APP_DEBUG=true
APP_URL=http://127.0.0.1:8000

# XAMPP MySQL
DB_CONNECTION=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=ai_agent_secondlevel_verification
DB_USERNAME=root
DB_PASSWORD=

# GitHub + Extractor secrets
GITHUB_PAT=REPLACE_WITH_GITHUB_PAT_WITH_repo:write
EXTRACTOR_CALLBACK_SECRET=REPLACE_WITH_RANDOM_LONG_SECRET
EXTRACTOR_BEARER_TOKEN=REPLACE_WITH_ANOTHER_RANDOM_LONG_SECRET

Run:
- php artisan key:generate
- php artisan storage:link

-------------------------------------------------------------------------------
4) COMPOSER PACKAGES (IF NEEDED)
-------------------------------------------------------------------------------
- Laravel default is fine. Optionally add Laravel Scout + Meilisearch if you want indexed search. The base LIKE/FULLTEXT implementation below is sufficient.

-------------------------------------------------------------------------------
5) DATABASE MIGRATIONS & MODELS
-------------------------------------------------------------------------------
Create migrations for documents and students:

php artisan make:model Document -m
php artisan make:model Student -m

In database/migrations/xxxx_create_documents_table.php:

Schema::create('documents', function (Blueprint $table) {
    $table->id();
    $table->string('filename');
    $table->string('path'); // storage path on 'public' disk
    $table->string('session')->nullable();
    $table->enum('status', ['processing','complete','failed'])->default('processing');
    $table->string('csv_url')->nullable();
    $table->string('xlsx_url')->nullable();
    $table->string('docx_url')->nullable();
    $table->timestamps();
});

In database/migrations/xxxx_create_students_table.php:

Schema::create('students', function (Blueprint $table) {
    $table->id();
    $table->foreignId('document_id')->constrained('documents')->onDelete('cascade');
    $table->string('surname');
    $table->string('first_name');
    $table->string('other_name')->nullable();
    $table->string('course_studied')->nullable();
    $table->string('faculty')->nullable();
    $table->string('grade')->nullable();
    $table->string('qualification_obtained')->nullable();
    $table->string('session')->nullable();
    $table->timestamps();
});

Optional FULLTEXT index (MySQL 5.7+ InnoDB):
Add a migration or raw statement:
DB::statement('ALTER TABLE students ADD FULLTEXT fulltext_students (surname, first_name, other_name, course_studied, faculty)');

Models (app/Models/Document.php):
protected $fillable = ['filename','path','session','status','csv_url','xlsx_url','docx_url'];

Models (app/Models/Student.php):
protected $fillable = ['document_id','surname','first_name','other_name','course_studied','faculty','grade','qualification_obtained','session'];

Run:
php artisan migrate

-------------------------------------------------------------------------------
6) ROUTES (routes/api.php)
-------------------------------------------------------------------------------
use App\Http\Controllers\DocumentController;
use App\Http\Controllers\GithubController;
use App\Http\Controllers\SearchController;

Route::post('/upload', [DocumentController::class, 'upload']);
Route::get('/documents', [DocumentController::class, 'index']);
Route::delete('/documents', [DocumentController::class, 'deleteAll']);
Route::get('/download/{doc}', [DocumentController::class, 'download'])->name('documents.download')->middleware('signed');

Route::post('/github/callback', [GithubController::class, 'callback'])->name('github.callback');
Route::post('/github/upload-results', [GithubController::class, 'uploadResults'])->name('github.uploadResults');

Route::get('/search', [SearchController::class, 'search']);

-------------------------------------------------------------------------------
7) CONTROLLERS
-------------------------------------------------------------------------------
php artisan make:controller DocumentController
php artisan make:controller GithubController
php artisan make:controller SearchController

app/Http/Controllers/DocumentController.php

public function upload(Request $req) {
  $req->validate(['file' => 'required|mimes:pdf|max:30000', 'session' => 'nullable|string']);
  $file = $req->file('file');
  $path = $file->store('convocation', 'public');

  $doc = Document::create([
    'filename' => $file->getClientOriginalName(),
    'path' => $path,
    'session' => $req->input('session'),
    'status' => 'processing'
  ]);

  $sourceUrl = URL::temporarySignedRoute('documents.download', now()->addMinutes(30), ['doc' => $doc->id]);

  Http::withToken(config('services.github.pat'))
    ->post('https://api.github.com/repos/OWNER/REPO/dispatches', [
      'event_type' => 'process_pdf',
      'client_payload' => [
        'source_url' => $sourceUrl,
        'original_filename' => $file->getClientOriginalName(),
        'session' => $doc->session,
        'callback_url' => route('github.callback'),
        'result_upload_url' => route('github.uploadResults'),
        'doc_id' => (string)$doc->id,
      ]
    ]);

  return response()->json(['id' => $doc->id, 'status' => 'processing']);
}

public function download(Request $req, Document $doc) {
  if (! $req->hasValidSignature()) abort(401);
  $full = Storage::disk('public')->path($doc->path);
  if (! file_exists($full)) abort(404);
  return response()->file($full, ['Content-Type' => 'application/pdf']);
}

public function index() { return Document::latest()->get(); }

public function deleteAll() {
  foreach (Document::cursor() as $doc) {
    Storage::disk('public')->delete($doc->path);
    $doc->delete();
  }
  Student::truncate();
  return response()->json(['deleted' => true]);
}

app/Http/Controllers/GithubController.php

public function callback(Request $req) {
  $sig = $req->header('X-Extractor-Signature');
  $expected = hash_hmac('sha256', $req->getContent(), config('services.extractor.secret'));
  if (! hash_equals($expected, (string)$sig)) abort(401);

  $payload = $req->json()->all();
  $doc = Document::where('filename', $payload['filename'] ?? '')->latest()->first();
  if (! $doc) return response()->noContent();

  $doc->update([
    'status' => 'complete',
    'csv_url' => $payload['files']['csv'] ?? $doc->csv_url,
    'xlsx_url' => $payload['files']['xlsx'] ?? $doc->xlsx_url,
    'docx_url' => $payload['files']['docx'] ?? $doc->docx_url,
  ]);

  if (!empty($payload['rows']) && is_array($payload['rows'])) {
    foreach ($payload['rows'] as $r) {
      Student::create([
        'document_id' => $doc->id,
        'surname' => $r['surname'] ?? '',
        'first_name' => $r['first_name'] ?? '',
        'other_name' => $r['other_name'] ?? '',
        'course_studied' => $r['course_studied'] ?? null,
        'faculty' => $r['faculty'] ?? null,
        'grade' => $r['grade'] ?? null,
        'qualification_obtained' => $r['qualification_obtained'] ?? null,
        'session' => $r['session'] ?? null,
      ]);
    }
  }
  return response()->json(['ok' => true]);
}

public function uploadResults(Request $req) {
  $auth = $req->bearerToken();
  if ($auth !== config('services.extractor.token')) abort(401);

  $docId = $req->input('doc_id');
  $doc = Document::find($docId);
  if (! $doc) abort(404);

  $csvFile = $req->file('csv');
  $xlsxFile = $req->file('xlsx');
  $docxFile = $req->file('docx');

  if ($csvFile) {
    $csvPath = $csvFile->store('processed', 'public');
    $doc->csv_url = Storage::disk('public')->url($csvPath);

    if (($h = fopen(Storage::disk('public')->path($csvPath), 'r')) !== false) {
      $header = fgetcsv($h);
      while (($row = fgetcsv($h)) !== false) {
        $data = array_combine($header, $row);
        Student::create([
          'document_id' => $doc->id,
          'surname' => $data['surname'] ?? '',
          'first_name' => $data['first_name'] ?? '',
          'other_name' => $data['other_name'] ?? '',
          'course_studied' => $data['course_studied'] ?? null,
          'faculty' => $data['faculty'] ?? null,
          'grade' => $data['grade'] ?? null,
          'qualification_obtained' => $data['qualification_obtained'] ?? null,
          'session' => $data['session'] ?? $doc->session,
        ]);
      }
      fclose($h);
    }
  }
  if ($xlsxFile) { $xlsxPath = $xlsxFile->store('processed', 'public'); $doc->xlsx_url = Storage::disk('public')->url($xlsxPath); }
  if ($docxFile) { $docxPath = $docxFile->store('processed', 'public'); $doc->docx_url = Storage::disk('public')->url($docxPath); }

  $doc->status = 'complete';
  $doc->save();
  return response()->json(['ok' => true, 'doc' => $doc]);
}

app/Http/Controllers/SearchController.php

public function search(Request $req) {
  $q = trim((string)$req->input('q'));
  $query = Student::query();

  if ($q !== '') {
    try {
      $query->whereRaw("MATCH(surname, first_name, other_name, course_studied, faculty) AGAINST (? IN BOOLEAN MODE)", [$q]);
    } catch (\Throwable $e) {
      $query->where(function($w) use ($q) {
        $w->where('surname', 'like', "%$q%")
          ->orWhere('first_name', 'like', "%$q%")
          ->orWhere('other_name', 'like', "%$q%")
          ->orWhere('course_studied', 'like', "%$q%")
          ->orWhere('faculty', 'like', "%$q%");
      });
    }
  }
  foreach (['faculty','grade','session'] as $f) { if ($v = $req->input($f)) $query->where($f, $v); }
  return $query->orderBy('surname')->paginate(50);
}

-------------------------------------------------------------------------------
8) CONFIG/SERVICES.PHP
-------------------------------------------------------------------------------
Add to config/services.php:

return [
  // ...
  'github' => ['pat' => env('GITHUB_PAT')],
  'extractor' => [
    'secret' => env('EXTRACTOR_CALLBACK_SECRET'),
    'token'  => env('EXTRACTOR_BEARER_TOKEN'),
  ],
];

-------------------------------------------------------------------------------
9) FRONTEND (RCS BRAND)
-------------------------------------------------------------------------------
- Already included in repo at frontend/.
- Copy to rcs-app/public/convocation/ (index.html, styles.css, app.js)
- Access at http://127.0.0.1:8000/convocation/index.html
- Brand colors used: #32CD32 (primary) and #90EE90 (light). Update public/convocation/styles.css if different brand palette provided.

-------------------------------------------------------------------------------
10) GITHUB ACTIONS WORKFLOW (MANUAL ADD VIA UI)
-------------------------------------------------------------------------------
- The repo push from the sandbox could not include workflow due to permission; add this file via GitHub UI:

Path: .github/workflows/process_pdf.yml

name: Process Convocation PDF
on:
  repository_dispatch:
    types: [process_pdf]
jobs:
  extract:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install system deps
        run: |
          sudo apt-get update
          sudo apt-get install -y tesseract-ocr poppler-utils libpoppler-cpp-dev

      - name: Install Python deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run extractor
        env:
          SOURCE_URL: ${{ github.event.client_payload.source_url }}
          ORIGINAL_FILENAME: ${{ github.event.client_payload.original_filename }}
          SESSION: ${{ github.event.client_payload.session }}
          CALLBACK_URL: ${{ github.event.client_payload.callback_url }}
          CALLBACK_HMAC_SECRET: ${{ secrets.CALLBACK_HMAC_SECRET }}
          RESULT_UPLOAD_URL: ${{ github.event.client_payload.result_upload_url }}
          RESULT_UPLOAD_TOKEN: ${{ secrets.RESULT_UPLOAD_TOKEN }}
          DOC_ID: ${{ github.event.client_payload.doc_id }}
        run: |
          python scripts/extract.py

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: outputs
          path: outputs/*

- Add repo secrets:
  - CALLBACK_HMAC_SECRET = (must match EXTRACTOR_CALLBACK_SECRET in Laravel)
  - RESULT_UPLOAD_TOKEN  = (must match EXTRACTOR_BEARER_TOKEN in Laravel)

-------------------------------------------------------------------------------
11) END-TO-END FLOW
-------------------------------------------------------------------------------
1. User uploads PDF at /convocation/index.html → POST /api/upload
2. Laravel stores PDF to public disk and creates Document
3. Laravel generates signed download URL (30 mins) and triggers GitHub repository_dispatch
4. GitHub Action downloads the PDF; extractor parses using pdfplumber (text) or Tesseract (image), supporting 1/2/3 columns
5. Extractor saves CSV/XLSX/DOCX, uploads them back to Laravel at /api/github/upload-results (Bearer token), and sends JSON callback (HMAC-signed)
6. Laravel updates Document with URLs, imports CSV rows into students table
7. Frontend shows files and supports search + Delete All

-------------------------------------------------------------------------------
12) RUN & TEST (LOCAL)
-------------------------------------------------------------------------------
- Start XAMPP MySQL
- cd rcs-app
- php artisan serve
- Visit http://127.0.0.1:8000/convocation/index.html
- Upload a sample PDF (max 30MB default). Processing requires that GitHub runner can access the signed URL:
  - For local dev, the signed URL is not public. Use a public environment (staging on cPanel) OR expose local with ngrok and set APP_URL accordingly for signed routes.
  - In production (cPanel), APP_URL is public; GitHub runner can fetch it.

Manual trigger example (scripts/dispatch_example.http):
- Replace OWNER/REPO and $GITHUB_TOKEN, then run the cURL to dispatch.

-------------------------------------------------------------------------------
13) SECURITY CHECKLIST
-------------------------------------------------------------------------------
- Validate uploads: mimes:pdf, max size
- Never expose tokens in frontend
- HMAC verify callback signature on /api/github/callback
- Protect /api/github/upload-results with Bearer token
- Signed download route with short TTL
- Set PHP upload_max_filesize and post_max_size large enough (cPanel php.ini if needed)

-------------------------------------------------------------------------------
14) EXTRACTOR BEHAVIOR SUMMARY
-------------------------------------------------------------------------------
- Detects 1/2/3 columns by k-means clustering x-center of word boxes
- Reads columns left-to-right, then top-to-bottom
- Headings detected:
  - FACULTY OF ... → faculty
  - Qualification (B., BSc, B.Eng., HND, ND, PGD, MSc, MBA, PhD) with optional (Course) → qualification_obtained + course_studied
  - Session: (\d{4}/\d{4}) ACADEMIC SESSION → session
- Grades normalized: FIRST CLASS, SECOND CLASS UPPER, SECOND CLASS LOWER, THIRD CLASS, DISTINCTION, MERIT, UPPER CREDIT, LOWER CREDIT, PASS
- Names parsed as "SURNAME, First Other" or "SURNAME First Other"; surname kept UPPERCASE; first/other title-cased; hyphen/apostrophe preserved
- Outputs: CSV, XLSX, DOCX, plus summary (audit.unparsed lines)

-------------------------------------------------------------------------------
15) TROUBLESHOOTING
-------------------------------------------------------------------------------
- GitHub Action won’t run: add the workflow file via UI and set secrets
- GitHub Action can’t download PDF: ensure the signed URL is public (use staging/cPanel or ngrok with correct APP_URL)
- PHP upload too small: increase upload_max_filesize and post_max_size
- Search returns nothing: check DB rows imported, verify LIKE vs FULLTEXT branch
- OCR low accuracy: increase OCR DPI in scripts/extract.py (extract_words_via_ocr) or consider paid OCR later

-------------------------------------------------------------------------------
16) DONE CRITERIA
-------------------------------------------------------------------------------
- Upload → GitHub Action → XLSX/DOCX/CSV back → DB filled → Search works → Delete All works
- Brand-styled frontend at /convocation
- Secrets set and protected

-------------------------------------------------------------------------------
17) COPILOT GPT-5 TASK PLAN (ACTIONS IN VS CODE)
-------------------------------------------------------------------------------
1) Create Laravel app under rcs-app/ if missing in repo
2) Apply .env settings and generate APP_KEY; storage:link
3) Add migrations and models; migrate
4) Implement controllers and routes as above
5) Copy frontend to public/convocation
6) Add config/services.php keys
7) Add workflow via GitHub UI; add secrets
8) Test upload on public (staging) environment; verify outputs saved and rows imported
9) Implement any brand color adjustments in styles.css (using provided hex values)
10) QA: multi-column sample, 1-2 column edge cases, long names, grade transitions

-------------------------------------------------------------------------------
APPENDIX: FILE MAP IN REPO
-------------------------------------------------------------------------------
- scripts/extract.py            # Python extractor
- scripts/README_EXTRACTOR.md   # Extractor notes
- scripts/dispatch_example.http # Example repository_dispatch cURL
- requirements.txt              # Python deps for workflow
- frontend/                     # RCS-branded dashboard (static)
- AGENTS.md                     # This file
# Laravel app expected at rcs-app/ (to be created by agent if absent)