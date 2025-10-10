<?php

namespace App\Http\Controllers;

use App\Models\Student;
use Illuminate\Http\Request;

class SearchController extends Controller
{
    public function search(Request $req)
    {
        $q = trim((string)$req->input('q'));
        $query = Student::query();

        if ($q !== '') {
            try {
                $query->whereRaw("MATCH(surname, first_name, other_name, course_studied, faculty) AGAINST (? IN BOOLEAN MODE)", [$q]);
            } catch (\Throwable $e) {
                $query->where(function ($w) use ($q) {
                    $w->where('surname', 'like', "%$q%")
                        ->orWhere('first_name', 'like', "%$q%")
                        ->orWhere('other_name', 'like', "%$q%")
                        ->orWhere('course_studied', 'like', "%$q%")
                        ->orWhere('faculty', 'like', "%$q%");
                });
            }
        }
        foreach (['faculty', 'grade', 'session'] as $f) {
            if ($v = $req->input($f)) $query->where($f, $v);
        }
        return $query->orderBy('surname')->paginate(50);
    }
}
