<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        try {
            DB::statement('ALTER TABLE students ADD FULLTEXT fulltext_students (surname, first_name, other_name, course_studied, faculty)');
        } catch (\Throwable $e) {
            // Ignore if not supported
        }
    }

    public function down(): void
    {
        try {
            DB::statement('ALTER TABLE students DROP INDEX fulltext_students');
        } catch (\Throwable $e) {
            // Ignore if not supported
        }
    }
};
