<?php

namespace App\Http\Controllers;

use App\Models\Document;
use App\Models\Student;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Storage;

class GithubController extends Controller
{
    public function callback(Request $req)
    {
        $sig = $req->header('X-Extractor-Signature');
        $expected = hash_hmac('sha256', $req->getContent(), config('services.extractor.secret'));
        if (!hash_equals($expected, (string)$sig)) abort(401);

        $payload = $req->json()->all();
        $doc = Document::where('filename', $payload['filename'] ?? '')->latest()->first();
        if (!$doc) return response()->noContent();

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

    public function uploadResults(Request $req)
    {
        $auth = $req->bearerToken();
        if ($auth !== config('services.extractor.token')) abort(401);

        $docId = $req->input('doc_id');
        $doc = Document::find($docId);
        if (!$doc) abort(404);

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
}
