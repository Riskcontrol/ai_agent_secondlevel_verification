<?php

namespace App\Http\Controllers;

use App\Models\Document;
use App\Models\Student;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Facades\URL;

class DocumentController extends Controller
{
    public function upload(Request $req)
    {
        $req->validate(['file' => 'required|mimes:pdf|max:30000', 'session' => 'nullable|string']);
        $file = $req->file('file');
        $path = $file->store('convocation', 'public');

        $doc = Document::create([
            'filename' => $file->getClientOriginalName(),
            'path' => $path,
            'session' => $req->input('session'),
            'status' => 'processing'
        ]);

    // Extend expiry to 24h to accommodate long/parallel processing in CI
    $sourceUrl = URL::temporarySignedRoute('documents.download', now()->addHours(24), ['doc' => $doc->id]);

        $pat = config('services.github.pat');
        if (!empty($pat)) {
            Http::withToken($pat)
                ->post('https://api.github.com/repos/Riskcontrol/ai_agent_secondlevel_verification/dispatches', [
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
        }

        return response()->json(['id' => $doc->id, 'status' => 'processing']);
    }

    public function download(Request $req, Document $doc)
    {
        if (!$req->hasValidSignature()) abort(401);
        $full = Storage::disk('public')->path($doc->path);
        if (!file_exists($full)) abort(404);
        return response()->file($full, ['Content-Type' => 'application/pdf']);
    }

    public function index()
    {
        return Document::latest()->get();
    }

    public function deleteAll()
    {
        foreach (Document::cursor() as $doc) {
            Storage::disk('public')->delete($doc->path);
            $doc->delete();
        }
        Student::truncate();
        return response()->json(['deleted' => true]);
    }
}
