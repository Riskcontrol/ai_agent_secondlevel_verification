Extractor overview

1) Trigger
- repository_dispatch event type: process_pdf
- client_payload must include: source_url, original_filename (optional), session (optional), callback_url (optional)

2) Outputs
- outputs/<name>.csv, .xlsx, .docx
- outputs/<name>.summary.json

3) Environment and secrets
- CALLBACK_HMAC_SECRET (repo/org secret) used to sign callback payload header X-Extractor-Signature

4) Parsing rules
- Detect FACULTY, QUALIFICATION (with optional course in parentheses), SESSION lines
- Detect grade headings (First Class Honours, Second Class Upper/Lower, Third Class, Distinction, Merit, Upper/Lower Credit, Pass)
- Names parsed as "SURNAME, First Middle" or "SURNAME First Middle". Leading uppercase token(s) treated as surname when comma absent.
- Multi-column handling: automatic clustering to 3/2/1 columns; reading order left-to-right, top-to-bottom.
- Continuations: If a page starts without headings, previous faculty/qualification/course/session persist.

Hybrid extraction

- The extractor now uses a hybrid strategy: try text-layer extraction first and, for any page with too few words (controlled by MIN_TEXT_WORDS, default 25), automatically fall back to OCR for that page. This avoids misreads when the PDF has a sparse or corrupted text layer.

Environment tuning

- OCR_DPI: DPI used by OCR fallback (default 250)
- TESSERACT_PSM: Optional psm mode for tesseract (e.g., 6 or 4)
- TESSERACT_LANG: Optional language codes (e.g., eng)
- MIN_TEXT_WORDS: Minimum words required from text-layer extraction before using OCR fallback (default 25)

5) Tuning
- Expand GRADE_MAP patterns for additional variants if encountered
- Tweak y_gap in group_lines if lines appear merged/split incorrectly
- For heavily image-based PDFs, consider higher DPI in OCR or alternative OCR engines
