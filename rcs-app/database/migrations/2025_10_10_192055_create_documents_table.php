<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
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
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('documents');
    }
};
