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

5) Tuning
- Expand GRADE_MAP patterns for additional variants if encountered
- Tweak y_gap in group_lines if lines appear merged/split incorrectly
- For heavily image-based PDFs, consider higher DPI in OCR or alternative OCR engines
