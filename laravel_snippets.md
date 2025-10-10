Laravel integration notes

Storage (cPanel):
- Use local disk public/convocation or S3-compatible storage if available. Create a model Document for uploaded PDFs.

Routes (api.php):
- POST /api/upload
- GET  /api/documents
- DELETE /api/documents (delete all)
- POST /api/github/callback (extraction result webhook)

Migrations (example):
- documents: id, filename, path, session, status (processing|complete|failed), xlsx_url, docx_url, csv_url, created_at
- students: id, document_id, surname, first_name, other_name, course_studied, faculty, grade, qualification_obtained, session, created_at

Controller pseudo-code:

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
  $url = Storage::disk('public')->temporaryUrl($path, now()->addMinutes(30));

  // Trigger GH Action
  Http::withToken(config('services.github.pat'))
    ->post('https://api.github.com/repos/{owner}/{repo}/dispatches', [
      'event_type' => 'process_pdf',
      'client_payload' => [
        'source_url' => $url,
        'original_filename' => $file->getClientOriginalName(),
        'session' => $doc->session,
        'callback_url' => route('github.callback'),
      ]
    ]);

  return response()->json(['id' => $doc->id, 'status' => 'processing']);
}

public function callback(Request $req) {
  // verify signature
  $sig = $req->header('X-Extractor-Signature');
  $expected = hash_hmac('sha256', $req->getContent(), config('services.extractor.secret'));
  abort_unless(hash_equals($expected, $sig), 401);

  $payload = $req->json()->all();
  $doc = Document::where('filename', $payload['filename'])->latest()->first();
  if (!$doc) { return response()->noContent(); }

  // Save artifact URLs if you publish them, or download from GH artifacts
  // Option A: the extractor can POST presigned upload URLs. For simplicity here we assume we can pull artifacts via a signed URL you manage.

  $doc->update([
    'status' => 'complete',
    'csv_url' => $payload['files']['csv'] ?? null,
    'xlsx_url' => $payload['files']['xlsx'] ?? null,
    'docx_url' => $payload['files']['docx'] ?? null,
  ]);

  // Parse CSV rows to DB
  // If URLs are local paths from the runner, prefer passing a downloadable URL instead. Alternatively, have extractor also POST rows[] inline.
  if (isset($payload['rows'])) {
    foreach ($payload['rows'] as $r) {
      Student::create(array_merge($r, ['document_id' => $doc->id]));
    }
  }

  return response()->json(['ok' => true]);
}

public function deleteAllDocs() {
  foreach (Document::all() as $doc) {
    Storage::disk('public')->delete($doc->path);
    $doc->delete();
  }
  Student::truncate();
  return response()->json(['deleted' => true]);
}

Search endpoint:
public function search(Request $req) {
  $q = $req->input('q');
  $query = Student::query();
  if ($q) {
    $query->where(function($w) use ($q) {
      $w->where('surname', 'like', "%$q%")
        ->orWhere('first_name', 'like', "%$q%")
        ->orWhere('other_name', 'like', "%$q%")
        ->orWhere('course_studied', 'like', "%$q%")
        ->orWhere('faculty', 'like', "%$q%")
        ->orWhere('grade', 'like', "%$q%")
        ->orWhere('qualification_obtained', 'like', "%$q%")
        ->orWhere('session', 'like', "%$q%");
    });
  }
  // optional filters: faculty, grade, session
  foreach (['faculty','grade','session'] as $f) {
    if ($v = $req->input($f)) $query->where($f, $v);
  }
  return $query->paginate(50);
}

UI notes:
- Provide a Delete All button that hits DELETE /api/documents
- Show processing status per upload, and links to download XLSX/DOCX when ready
- Power search box with filters
