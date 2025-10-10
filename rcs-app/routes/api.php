<?php

use Illuminate\Support\Facades\Route;
use App\Http\Controllers\DocumentController;
use App\Http\Controllers\GithubController;
use App\Http\Controllers\SearchController;

Route::post('/upload', [DocumentController::class, 'upload']);
Route::get('/documents', [DocumentController::class, 'index']);
Route::delete('/documents', [DocumentController::class, 'deleteAll']);
Route::get('/download/{doc}', [DocumentController::class, 'download'])
    ->name('documents.download')
    ->middleware('signed');

Route::post('/github/callback', [GithubController::class, 'callback'])->name('github.callback');
Route::post('/github/upload-results', [GithubController::class, 'uploadResults'])->name('github.uploadResults');

Route::get('/search', [SearchController::class, 'search']);
