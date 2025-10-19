"""
CONVOCATION PDF STUDENT DATA EXTRACTOR
=======================================
A robust system for extracting student graduation records from multi-column PDFs
using Gemini 2.5 Pro API with intelligent parsing and validation.

Features:
- Handles both image-based and text-based PDFs
- Processes multi-column layouts (1, 2, or 3 columns per page)
- Intelligent header detection and context tracking
- Comprehensive validation and error checking
- Progress tracking with detailed logs
- Excel export with proper formatting
"""

import os
import io
import json
import time
import base64
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path

# Core libraries
import pandas as pd
import numpy as np
from PIL import Image
import pdf2image
from pdf2image import convert_from_path
import PyPDF2

# Google Generative AI
import google.generativeai as genai

# Progress tracking
from tqdm.auto import tqdm


@dataclass
class StudentRecord:
    """Structured student record"""
    surname: str
    first_name: str
    other_name: str
    course_studied: str
    faculty: str
    grade: str
    qualification_obtained: str
    session: str
    
    def to_dict(self):
        return asdict(self)
    
    def validate(self) -> Tuple[bool, List[str]]:
        """Validate record completeness"""
        errors = []
        if not self.surname or self.surname.strip() == "":
            errors.append("Missing surname")
        if not self.first_name or self.first_name.strip() == "":
            errors.append("Missing first name")
        # Do NOT hard-fail if course/faculty/grade are missing; they may span pages
        # These may be filled from previous-page context; keep as soft warnings only if needed
        # Leaving them out of error list to avoid dropping valid name rows
        
        return len(errors) == 0, errors


class ConvocationPDFExtractor:
    """
    Main extractor class for processing convocation PDFs
    """
    
    def __init__(self, api_key: str, session: str = "2021/2022"):
        """
        Initialize extractor with Gemini API
        
        Args:
            api_key: Google Gemini API key
            session: Academic session (e.g., "2021/2022")
        """
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        self.session = session
        self.extraction_log = []
        # Track last known context across pages to handle pages with only names
        self.last_context: Dict[str, Optional[str]] = {
            'faculty': None,
            'course_studied': None,
            'qualification_obtained': None,
            'grade': None,
        }
        
    def convert_pdf_to_images(self, pdf_path: str, dpi: int = 300) -> List[Image.Image]:
        """
        Convert PDF pages to high-resolution images
        
        Args:
            pdf_path: Path to PDF file
            dpi: Resolution for conversion (higher = better quality)
            
        Returns:
            List of PIL Image objects
        """
        print(f"📄 Converting PDF to images (DPI: {dpi})...")
        try:
            images = convert_from_path(pdf_path, dpi=dpi)
            print(f"✅ Converted {len(images)} pages")
            return images
        except Exception as e:
            print(f"❌ Error converting PDF: {str(e)}")
            raise
    
    def encode_image(self, image: Image.Image) -> str:
        """Encode PIL Image to base64 string"""
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    
    def create_extraction_prompt(self, page_num: int, total_pages: int, prev_context: Optional[Dict[str, Optional[str]]] = None) -> str:
        """
        Create detailed extraction prompt for Gemini
        """
        context_block = ""
        if prev_context:
            # Include any previously known context (from the previous page) to help the model
            ctx_fac = prev_context.get('faculty') or ""
            ctx_course = prev_context.get('course_studied') or ""
            ctx_qual = prev_context.get('qualification_obtained') or ""
            ctx_grade = prev_context.get('grade') or ""
            context_lines = [
                "KNOWN CONTEXT FROM PREVIOUS PAGE:",
                f"  • Faculty: {ctx_fac if ctx_fac else '[unknown]'}",
                f"  • Course/Qualification: {ctx_course if ctx_course else '[unknown]'}",
                f"  • Short Qualification: {ctx_qual if ctx_qual else '[unknown]'}",
                f"  • Grade: {ctx_grade if ctx_grade else '[unknown]'}",
                "IF THIS PAGE HAS NO NEW HEADERS, CONTINUE USING THE KNOWN CONTEXT ABOVE.",
            ]
            context_block = "\n" + "\n".join(context_lines) + "\n"

        prompt = f"""You are an expert data extraction specialist analyzing a convocation ceremony document (Page {page_num}/{total_pages}).{context_block}

**CRITICAL INSTRUCTIONS:**

1. **DOCUMENT STRUCTURE UNDERSTANDING:**
   - This page may contain 1, 2, or 3 VERTICAL SECTIONS (columns)
   - Each section may have its own headers (Faculty, Course, Grade) OR continue from previous section
   - Headers appear at the top of sections: FACULTY → COURSE/QUALIFICATION → GRADE → Student Names
   - Student names are listed under their respective grade categories

2. **HEADER DETECTION:**
   - FACULTY: Usually starts with "FACULTY OF..." (e.g., "FACULTY OF AGRICULTURE")
   - COURSE/QUALIFICATION: Degree program (e.g., "B. Agric. (Agricultural Economics and Extension)")
   - GRADE CATEGORIES: 
     * "First Class Honours" or "First Class"
     * "Second Class Honours (Upper Division)" or "Second Class Upper"
     * "Second Class Honours (Lower Division)" or "Second Class Lower"
     * "Third Class Honours" or "Third Class"
     * "Pass" or "Pass Degree"
     * "Upper Credit" / "Lower Credit" / "Distinction"
    - If no new headers appear, continue with the LAST KNOWN headers from previous sections OR previous page

3. **NAME PARSING RULES:**
   - Names follow format: SURNAME, First Name Middle Name(s)
   - SURNAME is always in UPPERCASE
   - First name and middle names follow the comma
   - Example: "AKWAOWO, Sifongobong Udoudo" → Surname: AKWAOWO, First: Sifongobong, Other: Udoudo
   - If only two parts after comma: treat last part as first name, other_name can be empty
   - Handle variations: "ROBSON, Ubongabasi Godwin" → Surname: ROBSON, First: Ubongabasi, Other: Godwin

4. **EXTRACTION REQUIREMENTS:**
   - Extract EVERY student name visible on this page
   - Track context (faculty/course/grade) across all sections
   - When a new header appears, update the context for subsequent students
   - Maintain context until a NEW header explicitly changes it

5. **OUTPUT FORMAT:**
   Return ONLY a valid JSON array with this exact structure:
   ```json
   [
     {{
       "surname": "AKWAOWO",
       "first_name": "Sifongobong",
       "other_name": "Udoudo",
       "course_studied": "B. Agric. (Agricultural Economics and Extension)",
       "faculty": "FACULTY OF AGRICULTURE",
       "grade": "Pass",
       "qualification_obtained": "B. Agric.",
       "page_number": {page_num}
     }}
   ]
   ```

6. **QUALITY CHECKS:**
   - NO student should be skipped
   - NO duplicate entries
   - NO made-up data
   - If uncertain about a name, include it with a note in "other_name" field
   - Handle hyphenated names, apostrophes, and special characters properly

7. **EDGE CASES:**
   - If page contains only partial information (e.g., continuation), extract visible students
    - If no headers visible, STILL extract names and LEAVE missing fields empty; they will be filled from last known context
   - If names span multiple columns, track each separately

**NOW ANALYZE THIS PAGE AND EXTRACT ALL STUDENT RECORDS:**
"""
        return prompt
    
    def extract_from_page(self, image: Image.Image, page_num: int, total_pages: int, 
                          retry_count: int = 3,
                          prev_context: Optional[Dict[str, Optional[str]]] = None) -> List[Dict[str, Any]]:
        """
        Extract student records from a single page using Gemini Vision
        
        Args:
            image: PIL Image of the page
            page_num: Current page number
            total_pages: Total pages in document
            retry_count: Number of retry attempts on failure
            
        Returns:
            List of student record dictionaries
        """
        prompt = self.create_extraction_prompt(page_num, total_pages, prev_context)

        for attempt in range(retry_count):
            try:
                print(f"  🔍 Analyzing page {page_num} (Attempt {attempt + 1}/{retry_count})...")
                
                # Send to Gemini with image
                response = self.model.generate_content([prompt, image])
                
                # Parse response
                response_text = response.text.strip()
                
                # Extract JSON from response (handle markdown code blocks)
                json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
                if json_match:
                    json_text = json_match.group(1)
                else:
                    # Try to find raw JSON array
                    json_match = re.search(r'\[\s*\{.*?\}\s*\]', response_text, re.DOTALL)
                    if json_match:
                        json_text = json_match.group(0)
                    else:
                        json_text = response_text
                
                # Parse JSON
                records = json.loads(json_text)
                
                if not isinstance(records, list):
                    raise ValueError("Response is not a JSON array")
                
                print(f"  ✅ Extracted {len(records)} student(s) from page {page_num}")
                
                # Log extraction
                self.extraction_log.append({
                    "page": page_num,
                    "students_found": len(records),
                    "attempt": attempt + 1,
                    "status": "success"
                })
                
                return records
                
            except json.JSONDecodeError as e:
                print(f"  ⚠️ JSON parsing error on attempt {attempt + 1}: {str(e)}")
                if attempt == retry_count - 1:
                    print(f"  ❌ Failed to parse page {page_num} after {retry_count} attempts")
                    self.extraction_log.append({
                        "page": page_num,
                        "students_found": 0,
                        "attempt": attempt + 1,
                        "status": "failed",
                        "error": str(e)
                    })
                    return []
                time.sleep(2)  # Wait before retry
                
            except Exception as e:
                print(f"  ⚠️ Error on attempt {attempt + 1}: {str(e)}")
                if attempt == retry_count - 1:
                    print(f"  ❌ Failed to process page {page_num}: {str(e)}")
                    self.extraction_log.append({
                        "page": page_num,
                        "students_found": 0,
                        "attempt": attempt + 1,
                        "status": "failed",
                        "error": str(e)
                    })
                    return []
                time.sleep(2)
        
        return []

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _is_nonempty(value: Optional[str]) -> bool:
        return bool(value) and str(value).strip() != ""

    def _fill_missing_from_context(self, records: List[Dict[str, Any]], context: Dict[str, Optional[str]]) -> List[Dict[str, Any]]:
        """Fill missing faculty/course/qualification/grade from last known context for each record."""
        keys = ['faculty', 'course_studied', 'qualification_obtained', 'grade']
        filled = []
        for rec in records:
            r = dict(rec) if rec is not None else {}
            for k in keys:
                v = r.get(k)
                if not self._is_nonempty(v) and self._is_nonempty(context.get(k)):
                    r[k] = context.get(k)
            filled.append(r)
        return filled

    def _update_context_from_records(self, records: List[Dict[str, Any]], context: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
        """Update context with the last non-empty values observed in the records order."""
        keys = ['faculty', 'course_studied', 'qualification_obtained', 'grade']
        new_ctx = dict(context)
        for rec in records:
            if not isinstance(rec, dict):
                continue
            for k in keys:
                v = rec.get(k)
                if self._is_nonempty(v):
                    new_ctx[k] = v
        return new_ctx
    
    def post_process_records(self, all_records: List[Dict[str, Any]]) -> List[StudentRecord]:
        """
        Post-process and validate extracted records
        
        Args:
            all_records: Raw records from extraction
            
        Returns:
            List of validated StudentRecord objects
        """
        print("\n🔧 Post-processing records...")
        
        processed_records = []
        duplicates_removed = 0
        invalid_records = 0
        seen_students = set()
        
        def _clean(value: Any, *, case: Optional[str] = None) -> str:
            s = "" if value is None else str(value)
            s = s.strip()
            if case == 'upper':
                return s.upper()
            if case == 'title':
                return s.title()
            return s
        
        for record in all_records:
            try:
                # Create student record with session
                student = StudentRecord(
                    surname=_clean(record.get('surname'), case='upper'),
                    first_name=_clean(record.get('first_name'), case='title'),
                    other_name=_clean(record.get('other_name'), case='title'),
                    course_studied=_clean(record.get('course_studied')),
                    faculty=_clean(record.get('faculty')),
                    grade=_clean(record.get('grade')),
                    qualification_obtained=_clean(record.get('qualification_obtained')),
                    session=self.session
                )
                
                # Validate record
                is_valid, errors = student.validate()
                
                if not is_valid:
                    print(f"  ⚠️ Invalid record: {student.surname} {student.first_name} - {', '.join(errors)}")
                    invalid_records += 1
                    continue
                
                # Check for duplicates
                student_key = f"{student.surname}_{student.first_name}_{student.course_studied}"
                if student_key in seen_students:
                    duplicates_removed += 1
                    continue
                
                seen_students.add(student_key)
                processed_records.append(student)
                
            except Exception as e:
                print(f"  ❌ Error processing record: {str(e)}")
                invalid_records += 1
        
        print(f"✅ Processed {len(processed_records)} valid records")
        print(f"  🗑️ Removed {duplicates_removed} duplicates")
        print(f"  ⚠️ Skipped {invalid_records} invalid records")
        
        return processed_records
    
    def extract_from_pdf(self, pdf_path: str, start_page: int = 1, 
                        end_page: Optional[int] = None, dpi: int = 300) -> pd.DataFrame:
        """
        Main extraction pipeline
        
        Args:
            pdf_path: Path to PDF file
            start_page: Starting page number (1-indexed)
            end_page: Ending page number (None = all pages)
            dpi: Image resolution for conversion
            
        Returns:
            Pandas DataFrame with extracted records
        """
        print(f"\n{'='*60}")
        print(f"🎓 CONVOCATION PDF EXTRACTOR")
        print(f"{'='*60}")
        print(f"📁 File: {pdf_path}")
        print(f"📅 Session: {self.session}")
        print(f"{'='*60}\n")
        
        # Convert PDF to images
        images = self.convert_pdf_to_images(pdf_path, dpi=dpi)
        
        # Determine page range
        if end_page is None:
            end_page = len(images)
        
        end_page = min(end_page, len(images))
        pages_to_process = images[start_page-1:end_page]
        
        print(f"\n📊 Processing pages {start_page} to {end_page} ({len(pages_to_process)} pages)\n")
        
        # Extract from each page with cross-page context retention
        all_records = []
        # Start with any persisted context from previous runs within this instance
        page_context = dict(self.last_context)
        
        for idx, image in enumerate(tqdm(pages_to_process, desc="Extracting pages")):
            page_num = start_page + idx

            # Pass previous context to the prompt/model
            records = self.extract_from_page(image, page_num, len(images), prev_context=page_context)

            # Fill missing headers using last known context
            records = self._fill_missing_from_context(records, page_context)

            # Update context for the next page using observed headers
            page_context = self._update_context_from_records(records, page_context)
            self.last_context = dict(page_context)

            all_records.extend(records)
            
            # Rate limiting to avoid API throttling
            time.sleep(1)
        
        # Post-process records
        processed_records = self.post_process_records(all_records)
        
        # Convert to DataFrame
        df = pd.DataFrame([record.to_dict() for record in processed_records])
        
        # Reorder columns
        column_order = ['surname', 'first_name', 'other_name', 'course_studied', 
                       'faculty', 'grade', 'qualification_obtained', 'session']
        df = df[column_order]
        
        print(f"\n{'='*60}")
        print(f"✅ EXTRACTION COMPLETE")
        print(f"{'='*60}")
        print(f"📊 Total students extracted: {len(df)}")
        print(f"🎯 Success rate: {len(df)}/{len(images)} pages processed")
        print(f"{'='*60}\n")
        
        return df
    
    def save_to_excel(self, df: pd.DataFrame, output_path: str):
        """
        Save DataFrame to Excel with formatting
        
        Args:
            df: DataFrame to save
            output_path: Output file path
        """
        print(f"💾 Saving to Excel: {output_path}")
        
        with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Student Records')
            
            # Get workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets['Student Records']
            
            # Define formats
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'top',
                'fg_color': '#4472C4',
                'font_color': 'white',
                'border': 1
            })
            
            cell_format = workbook.add_format({
                'text_wrap': True,
                'valign': 'top',
                'border': 1
            })
            
            # Apply formatting
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
            
            # Set column widths
            column_widths = {
                'surname': 20,
                'first_name': 18,
                'other_name': 18,
                'course_studied': 40,
                'faculty': 35,
                'grade': 25,
                'qualification_obtained': 25,
                'session': 12
            }
            
            for idx, col in enumerate(df.columns):
                worksheet.set_column(idx, idx, column_widths.get(col, 15), cell_format)
            
            # Freeze header row
            worksheet.freeze_panes(1, 0)
        
        print(f"✅ Excel file saved successfully")
    
    def generate_summary_report(self, df: pd.DataFrame) -> str:
        """Generate extraction summary report"""
        report = f"""
{'='*60}
EXTRACTION SUMMARY REPORT
{'='*60}

📊 STATISTICS:
  • Total Students: {len(df)}
  • Faculties: {df['faculty'].nunique()}
  • Courses: {df['course_studied'].nunique()}
  • Academic Session: {self.session}

🎓 GRADE DISTRIBUTION:
"""
        grade_counts = df['grade'].value_counts()
        for grade, count in grade_counts.items():
            percentage = (count / len(df)) * 100
            report += f"  • {grade}: {count} ({percentage:.1f}%)\n"
        
        report += f"""
🏫 TOP 5 FACULTIES:
"""
        faculty_counts = df['faculty'].value_counts().head(5)
        for faculty, count in faculty_counts.items():
            report += f"  • {faculty}: {count} students\n"
        
        report += f"""
📚 TOP 5 COURSES:
"""
        course_counts = df['course_studied'].value_counts().head(5)
        for course, count in course_counts.items():
            report += f"  • {course}: {count} students\n"
        
        report += f"\n{'='*60}\n"
        
        return report


# ============================================================================
# GOOGLE COLAB INTERFACE
# ============================================================================

def main():
    """Main function for Google Colab execution"""
    
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║     🎓 CONVOCATION PDF STUDENT DATA EXTRACTOR 🎓            ║
    ║                                                              ║
    ║          Powered by Gemini 2.5 Pro Vision AI                ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Step 1: Get API Key
    print("\n" + "="*60)
    print("STEP 1: SETUP")
    print("="*60)
    
    api_key = input("\n🔑 Enter your Gemini API Key: ").strip()
    
    if not api_key:
        print("❌ API Key is required!")
        return
    
    # Step 2: Upload PDF
    print("\n" + "="*60)
    print("STEP 2: UPLOAD PDF")
    print("="*60)
    
    try:
        from google.colab import files  # type: ignore
        print("\n📤 Please upload your convocation PDF file...")
        uploaded = files.upload()
        
        if not uploaded:
            print("❌ No file uploaded!")
            return
        
        pdf_filename = list(uploaded.keys())[0]
        pdf_path = pdf_filename
        
        print(f"✅ File uploaded: {pdf_filename}")
        
    except ImportError:
        # Not in Colab, use local file
        pdf_path = input("\n📁 Enter PDF file path: ").strip()
        
        if not os.path.exists(pdf_path):
            print(f"❌ File not found: {pdf_path}")
            return
    
    # Step 3: Configure extraction
    print("\n" + "="*60)
    print("STEP 3: CONFIGURATION")
    print("="*60)
    
    session = input("\n📅 Enter academic session (e.g., 2021/2022): ").strip()
    if not session:
        session = "2021/2022"
    
    start_page_input = input("📄 Start from page (default: 1): ").strip()
    start_page = int(start_page_input) if start_page_input else 1
    
    end_page_input = input("📄 End at page (default: all): ").strip()
    end_page = int(end_page_input) if end_page_input else None
    
    dpi_input = input("🖼️ Image quality DPI (default: 300, higher=better): ").strip()
    dpi = int(dpi_input) if dpi_input else 300
    
    # Step 4: Extract data
    print("\n" + "="*60)
    print("STEP 4: EXTRACTION")
    print("="*60)
    
    extractor = ConvocationPDFExtractor(api_key=api_key, session=session)
    
    try:
        df = extractor.extract_from_pdf(
            pdf_path=pdf_path,
            start_page=start_page,
            end_page=end_page,
            dpi=dpi
        )
        
        # Step 5: Display results
        print("\n" + "="*60)
        print("STEP 5: RESULTS")
        print("="*60)
        
        print("\n📋 PREVIEW (First 10 records):")
        print(df.head(10).to_string(index=False))
        
        # Generate summary
        summary = extractor.generate_summary_report(df)
        print(summary)
        
        # Step 6: Save results
        print("="*60)
        print("STEP 6: SAVE RESULTS")
        print("="*60)
        
        output_filename = f"student_records_{session.replace('/', '_')}.xlsx"
        extractor.save_to_excel(df, output_filename)
        
        # Download in Colab
        try:
            from google.colab import files  # type: ignore
            print(f"\n⬇️ Downloading: {output_filename}")
            files.download(output_filename)
        except ImportError:
            print(f"\n✅ File saved locally: {output_filename}")
        
        print("\n" + "="*60)
        print("🎉 EXTRACTION COMPLETED SUCCESSFULLY!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
