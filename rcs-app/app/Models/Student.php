<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class Student extends Model
{
    protected $fillable = [
        'document_id','surname','first_name','other_name','course_studied','faculty','grade','qualification_obtained','session'
    ];
}
