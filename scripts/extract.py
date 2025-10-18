#!/usr/bin/env python3
import os
import re
import io
import json
import hmac
import hashlib
import tempfile
import shutil
from dataclasses import dataclass, asdict
from typing import List, Tuple, Dict, Optional

# ------------ Config ------------
GRADE_MAP = {
    # Honours
    r"FIRST\s+CLASS(\s+HONOURS)?": "FIRST CLASS",
    r"SECOND\s+CLASS\s+(HONOURS\s+)?(UPPER|UPPER\s+DIVISION)": "SECOND CLASS UPPER",
    r"SECOND\s+CLASS\s+(HONOURS\s+)?(LOWER|LOWER\s+DIVISION)": "SECOND CLASS LOWER",
    r"THIRD\s+CLASS(\s+HONOURS)?": "THIRD CLASS",
    # Polytechnics
    r"DISTINCTION": "DISTINCTION",
    r"MERIT": "MERIT",
    r"UPPER\s+CREDIT": "UPPER CREDIT",
    r"LOWER\s+CREDIT": "LOWER CREDIT",
    r"PASS": "PASS",
}

QUALI_PAT = re.compile(r"^(B\.?\s?[A-Z][A-Za-z\.]*|BSc|B\.Eng\.|BEng|HND|ND|PGD|MSc|MBA|PhD)[^\n]*?(?:\(([^)]+)\))?", re.I)
FACULTY_PAT = re.compile(r"^FACULTY\s+OF\s+.+", re.I)
SESSION_PAT = re.compile(r"(\d{4}/\d{4}).{0,20}?ACADEMIC\s+SESSION", re.I)

NAME_SPLIT_COMMA = re.compile(r"^\s*([A-Z\-']+),\s*(.+)$")
UPPER_TOKEN = re.compile(r"^[A-Z][A-Z\-']+$")

# Common non-name words and phrases that appear as page decorations/headers
NOISE_STOPWORDS = {
    'AN', 'A', 'ON', 'OF', 'IN', 'THE', 'AND', 'WITH', 'FOR', 'TO',
    'UNIVERSITY', 'UYO', 'UNIVERSITY OF UYO',
    'CONVOCATION', 'CEREMONY', 'PROGRAMME', 'PROGRAM', 'VOLUME', 'VOL', 'NO',
    'INSTITUTION', 'MISSION', 'AN INSTITUTION ON A MISSION',
}

@dataclass
class Row:
    surname: str
    first_name: str
    other_name: str
    course_studied: str
    faculty: str
    grade: str
    qualification_obtained: str
    session: str

# ------------ Utils ------------

def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def titlecase_name(s: str) -> str:
    # Preserve hyphens and apostrophes in names
    parts = [p.capitalize() for p in re.split(r"([\-'])", s.lower())]
    return "".join(parts)


def detect_columns(words: List[dict], page_width: float, expected_cols: Optional[int] = None) -> List[List[dict]]:
    # words: list of dict with keys x0,y0,x1,y1,text
    if not words:
        return [[], [], []]
    import numpy as np
    centers = np.array([(((w['x0']+w['x1'])/2.0)) for w in words]).reshape(-1,1)

    # Try cluster 3, then 2, then 1
    for k in ([expected_cols] if expected_cols else []) + [3,2,1]:
        try:
            km = kmeans_1d(centers, k)
            labels = km['labels']
            cols = [[] for _ in range(k)]
            for w, lab in zip(words, labels):
                cols[lab].append(w)
            # sort each column by y, then x
            for c in cols:
                c.sort(key=lambda w: (w['y0'], w['x0']))
            # order columns left to right by mean x
            order = sorted(range(k), key=lambda i: np.mean([(w['x0']+w['x1'])/2 for w in cols[i]]) if cols[i] else 1e9)
            cols = [cols[i] for i in order]
            return cols
        except Exception:
            continue
    # fallback equal thirds (3 cols)
    thirds = [[],[],[]]
    w1 = page_width/3
    for w in words:
        cx = (w['x0']+w['x1'])/2
        idx = min(2, int(cx//w1))
        thirds[idx].append(w)
    for c in thirds:
        c.sort(key=lambda w: (w['y0'], w['x0']))
    return thirds


def kmeans_1d(X, k: int, iters: int = 50) -> Dict:
    # simple 1D k-means
    import numpy as np
    rng = np.random.default_rng(0)
    centers = np.quantile(X, np.linspace(0,1,k+2)[1:-1]).reshape(-1,1)
    for _ in range(iters):
        d = np.abs(X - centers.T)
        labels = d.argmin(axis=1)
        new_centers = np.array([X[labels==i].mean() if np.any(labels==i) else centers[i] for i in range(k)]).reshape(-1,1)
        if np.allclose(new_centers, centers):
            break
        centers = new_centers
    return { 'centers': centers, 'labels': labels }


def group_lines(col_words: List[dict], y_gap: float = 6.0) -> List[str]:
    # Build lines by proximity in y
    lines = []
    current = []
    last_y = None
    for w in col_words:
        y = w['y0']
        if last_y is None or abs(y - last_y) <= y_gap:
            current.append(w)
        else:
            lines.append(" ".join([ww['text'] for ww in current]))
            current = [w]
        last_y = y
    if current:
        lines.append(" ".join([ww['text'] for ww in current]))
    return [norm_space(l) for l in lines if norm_space(l)]


def parse_headings(line: str) -> Dict[str,str]:
    out = {}
    if FACULTY_PAT.match(line):
        out['faculty'] = norm_space(line.upper())
    m = QUALI_PAT.match(line)
    if m:
        out['qualification'] = norm_space(m.group(1))
        if m.group(2):
            out['course'] = norm_space(m.group(2).upper())
    ms = SESSION_PAT.search(line)
    if ms:
        out['session'] = ms.group(1)
    return out


def is_grade(line: str) -> Optional[str]:
    u = line.upper()
    for pat, lab in GRADE_MAP.items():
        if re.fullmatch(pat, u):
            return lab
    return None


def parse_name(line: str) -> Optional[Tuple[str,str,str]]:
    # remove trailing dots/commas for robustness where not separating surname
    line = norm_space(line)
    # ignore obvious non-name keywords
    if FACULTY_PAT.match(line) or QUALI_PAT.match(line) or is_grade(line):
        return None
    # reject common decorative lines and mottos
    u = line.upper()
    if ('UNIVERSITY' in u or 'CONVOCATION' in u or 'CEREMONY' in u or 'INSTITUTION' in u or 'MISSION' in u) and ',' not in line:
        return None
    # comma pattern
    m = NAME_SPLIT_COMMA.match(line)
    if m:
        surname = m.group(1).strip()
        rest = m.group(2).split()
        if not rest:
            return None
        first_name = rest[0]
        other = " ".join(rest[1:])
        return surname, first_name, other
    # uppercase first token(s) as surname
    tokens = line.split()
    if not tokens:
        return None
    # if majority of tokens are known stopwords and there's no comma, likely not a name
    if ',' not in line:
        toks_u = [t.upper() for t in tokens]
        sw_hits = sum(1 for t in toks_u if t in NOISE_STOPWORDS)
        if toks_u and sw_hits/len(toks_u) >= 0.6:
            return None
    # find leading uppercase tokens
    idx = 0
    while idx < len(tokens) and UPPER_TOKEN.match(tokens[idx]):
        idx += 1
    if idx == 0:
        # No all-caps prefix; require a comma to be safe for Surname First Middle
        # If no comma, bail out to avoid parsing mottos and headings
        return None
    # If the entire line is uppercase tokens and we consumed all tokens as surname,
    # reinterpret as Surname First Other using the first token as surname
    if idx == len(tokens) and len(tokens) >= 2:
        surname = tokens[0].upper()
        first_name = tokens[1]
        other = " ".join(tokens[2:])
        return surname, first_name, other
    surname = " ".join(tokens[:idx]).upper()
    rest = tokens[idx:]
    if not rest:
        return None
    first_name = rest[0]
    other = " ".join(rest[1:])
    # avoid interpreting one-letter "A" or "AN" as first name unless there's a comma
    if ',' not in line and len(first_name) <= 1 and not other:
        return None
    return surname, first_name, other


def extract_words_from_pdf(path: str, pages: Optional[List[int]] = None, keepalive: bool = True) -> List[Dict]:
    """Extract words via text from specific 1-based pages (or all if None)."""
    words_all = []
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        total = len(pdf.pages)
        indices = list(range(1, total + 1)) if not pages else pages
        for idx in indices:
            try:
                page = pdf.pages[idx - 1]
            except Exception:
                continue
            pw = page.width
            ph = page.height
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            words = [{
                'text': w['text'],
                'x0': float(w['x0']), 'y0': float(w['top']),
                'x1': float(w['x1']), 'y1': float(w['bottom']),
                'page_width': pw,
                'page_height': ph,
            } for w in words]
            words_all.append({ 'page_num': idx, 'page_width': pw, 'page_height': ph, 'words': words })
            if keepalive:
                print(f"[extract-text] page {idx}/{total} -> {len(words)} words", flush=True)
    return words_all


def _group_ranges(pages: List[int]) -> List[Tuple[int, int]]:
    if not pages:
        return []
    pages = sorted(set(pages))
    ranges: List[Tuple[int,int]] = []
    start = prev = pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
        else:
            ranges.append((start, prev))
            start = prev = p
    ranges.append((start, prev))
    return ranges


def extract_words_via_ocr(path: str, pages: Optional[List[int]] = None, dpi: int = 250, tess_psm: Optional[str] = None, tess_lang: Optional[str] = None, keepalive: bool = True) -> List[Dict]:
    """OCR specific pages (1-based). Uses grouped ranges for efficiency."""
    tmpdir = tempfile.mkdtemp()
    try:
        from pdf2image import convert_from_path
        import pytesseract
        pages_out = []
        ranges = _group_ranges(pages) if pages else [(None, None)]
        total_pages = 0
        for first, last in ranges:
            kwargs = { 'dpi': dpi }
            if first is not None and last is not None:
                kwargs.update({'first_page': first, 'last_page': last})
            images = convert_from_path(path, **kwargs)
            # Map image index back to page numbers
            start_page_num = first if first is not None else 1
            for idx, img in enumerate(images):
                page_num = (start_page_num + idx) if first is not None else (total_pages + idx + 1)
                config = ''
                if tess_psm:
                    config += f" --psm {tess_psm}"
                if tess_lang:
                    config += f" -l {tess_lang}"
                data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config=config or None)
                pw, ph = img.size
                words = []
                n = len(data['text'])
                for i in range(n):
                    t = data['text'][i]
                    if not t or t.strip() == "":
                        continue
                    x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                    words.append({
                        'text': t,
                        'x0': float(x), 'y0': float(y),
                        'x1': float(x+w), 'y1': float(y+h),
                        'page_width': pw,
                        'page_height': ph,
                    })
                pages_out.append({ 'page_num': page_num, 'page_width': pw, 'page_height': ph, 'words': words })
                if keepalive:
                    print(f"[ocr] page {page_num} -> {len(words)} words", flush=True)
            total_pages += len(images)
        return pages_out
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def is_text_extractable(path: str) -> bool:
    try:
        import fitz  # PyMuPDF
        with fitz.open(path) as doc:
            for p in doc:
                if p.get_text().strip():
                    return True
        return False
    except Exception:
        return False


def get_page_count(path: str) -> int:
    try:
        import fitz  # PyMuPDF
        with fitz.open(path) as doc:
            return len(doc)
    except Exception:
        return 0


def hybrid_extract_words(path: str, pages: Optional[List[int]], ocr_dpi: int = 250, tess_psm: Optional[str] = None, tess_lang: Optional[str] = None, keepalive: bool = True, min_text_words: int = 25) -> List[Dict]:
    """Try text extraction first, then OCR per page if too few words were found."""
    # First pass: text extraction for selected pages
    text_pages = extract_words_from_pdf(path, pages=pages, keepalive=keepalive)
    # Build a quick lookup of page_num -> index
    by_num: Dict[int, Dict] = {p.get('page_num', i+1): p for i, p in enumerate(text_pages)}
    results: List[Dict] = []
    indices = [p.get('page_num', i+1) for i, p in enumerate(text_pages)]
    # For each, decide whether to OCR fallback
    to_ocr: List[int] = []
    for pnum in indices:
        words = by_num[pnum]['words']
        if len(words) < min_text_words:
            to_ocr.append(pnum)
        else:
            results.append(by_num[pnum])
    if to_ocr:
        ocr_pages = extract_words_via_ocr(path, pages=to_ocr, dpi=ocr_dpi, tess_psm=tess_psm, tess_lang=tess_lang, keepalive=keepalive)
        # decide which to keep per page: pick whichever has more words
        ocr_by_num = {p['page_num']: p for p in ocr_pages}
        for pnum in to_ocr:
            txt = by_num.get(pnum)
            ocr = ocr_by_num.get(pnum)
            chosen = None
            if ocr and (not txt or len(ocr['words']) >= len(txt['words'])):
                chosen = ocr
                if keepalive:
                    print(f"[hybrid] page {pnum}: text={len(txt['words']) if txt else 0} ocr={len(ocr['words'])} -> using OCR", flush=True)
            else:
                chosen = txt
                if keepalive:
                    print(f"[hybrid] page {pnum}: text={len(txt['words']) if txt else 0} ocr={len(ocr['words']) if ocr else 0} -> using text", flush=True)
            results.append(chosen)
    # Sort by page order
    results.sort(key=lambda p: p.get('page_num', 0))
    return results


def parse_page_env(total_pages: int) -> Optional[List[int]]:
    """Parse PAGE_START/PAGE_END or PAGES env. Returns list of 1-based pages or None for all."""
    pages_env = os.getenv('PAGES', '').strip()
    start_env = os.getenv('PAGE_START', '').strip()
    end_env = os.getenv('PAGE_END', '').strip()
    pages: List[int] = []
    if pages_env:
        # format like "1-10,12,15-20"
        for part in pages_env.split(','):
            part = part.strip()
            if not part:
                continue
            if '-' in part:
                a,b = part.split('-',1)
                try:
                    a_i = max(1, int(a))
                    b_i = min(total_pages, int(b))
                    if a_i <= b_i:
                        pages.extend(list(range(a_i, b_i+1)))
                except Exception:
                    continue
            else:
                try:
                    p = int(part)
                    if 1 <= p <= total_pages:
                        pages.append(p)
                except Exception:
                    continue
    elif start_env or end_env:
        try:
            a_i = int(start_env) if start_env else 1
            b_i = int(end_env) if end_env else total_pages
            a_i = max(1, a_i); b_i = min(total_pages, b_i)
            if a_i <= b_i:
                pages = list(range(a_i, b_i+1))
        except Exception:
            pages = []
    return pages or None


def parse_document(pages_words: List[Dict], default_session: str = "") -> Tuple[List[Row], Dict]:
    rows: List[Row] = []
    audit = { 'unparsed': [], 'pages': len(pages_words) }
    current = {
        'faculty': '',
        'qualification': '',
        'course': '',
        'grade': '',
        'session': default_session,
    }

    for pi, page in enumerate(pages_words):
        words = page['words']
        pw = page['page_width']
        # Detect probable column count by clustering and measuring cluster count
        cols = detect_columns(words, pw)
        # Build lines in reading order across columns
        lines = []
        for c in cols:
            lines.extend(group_lines(c))
        # Scan lines
        seen_heading = False
        for li, line in enumerate(lines):
            # detect headings
            h = parse_headings(line)
            if h:
                seen_heading = True
                current['faculty'] = h.get('faculty', current['faculty'])
                current['qualification'] = h.get('qualification', current['qualification'])
                current['course'] = h.get('course', current['course'])
                current['session'] = h.get('session', current['session'])
                continue
            g = is_grade(line)
            if g:
                current['grade'] = g
                continue
            # try name
            nm = parse_name(line)
            if nm:
                surname, first_name, other = nm
                rows.append(Row(
                    surname=surname,
                    first_name=titlecase_name(first_name),
                    other_name=titlecase_name(other),
                    course_studied=current['course'],
                    faculty=current['faculty'],
                    grade=current['grade'],
                    qualification_obtained=current['qualification'],
                    session=current['session']
                ))
            else:
                # ignore page numbers and decorative texts
                if re.fullmatch(r"\d+|Vol\.?\s*\d+|Convocation|Ceremony|UNIVERSITY OF UYO|An?\s+Institution\s+on\s+a\s+Mission", line, re.I):
                    continue
                audit['unparsed'].append({ 'page': pi+1, 'line': line })
        # If no heading seen on this page, assume continuation of previous headings
        # current state already carries over
    return rows, audit


def save_outputs(rows: List[Row], base: str, out_dir: str) -> Dict[str,str]:
    os.makedirs(out_dir, exist_ok=True)
    data = [asdict(r) for r in rows]
    import pandas as pd
    from docx import Document
    df = pd.DataFrame(data, columns=[
        'surname','first_name','other_name','course_studied','faculty','grade','qualification_obtained','session'
    ])
    csv_path = os.path.join(out_dir, base + '.csv')
    xlsx_path = os.path.join(out_dir, base + '.xlsx')
    docx_path = os.path.join(out_dir, base + '.docx')
    df.to_csv(csv_path, index=False)
    df.to_excel(xlsx_path, index=False)
    # DOCX
    doc = Document()
    table = doc.add_table(rows=len(df)+1, cols=len(df.columns))
    for j, col in enumerate(df.columns):
        table.cell(0,j).text = col
    for i, row in enumerate(df.itertuples(index=False), start=1):
        for j, val in enumerate(row):
            table.cell(i,j).text = '' if pd.isna(val) else str(val)
    doc.save(docx_path)
    return { 'csv': csv_path, 'xlsx': xlsx_path, 'docx': docx_path }


def compute_signature(secret: str, payload: bytes) -> str:
    mac = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
    return mac


def upload_results(upload_url: str, token: str, doc_id: Optional[str], paths: Dict[str,str], summary: Dict) -> None:
    if not upload_url:
        return
    try:
        import requests
        files = {}
        for key in ['csv','xlsx','docx']:
            p = paths.get(key)
            if p and os.path.exists(p):
                files[key] = (os.path.basename(p), open(p, 'rb'), 'application/octet-stream')
        data = { 'doc_id': doc_id or '', 'summary': json.dumps(summary) }
        headers = {}
        if token:
            headers['Authorization'] = f"Bearer {token}"
        resp = requests.post(upload_url, files=files, data=data, headers=headers, timeout=120)
        print('Upload results status:', resp.status_code)
    except Exception as e:
        print('Upload results error:', repr(e))


def main():
    import requests
    source_url = os.getenv('SOURCE_URL')
    source_file = os.getenv('SOURCE_FILE')
    original_filename = os.getenv('ORIGINAL_FILENAME', 'document.pdf')
    default_session = os.getenv('SESSION', '')
    callback_url = os.getenv('CALLBACK_URL')
    callback_secret = os.getenv('CALLBACK_HMAC_SECRET', '')
    result_upload_url = os.getenv('RESULT_UPLOAD_URL')
    result_upload_token = os.getenv('RESULT_UPLOAD_TOKEN', '')
    doc_id = os.getenv('DOC_ID')
    out_suffix = os.getenv('OUT_SUFFIX', '').strip()
    # OCR tuning
    ocr_dpi = int(os.getenv('OCR_DPI', '250') or '250')
    tess_psm = os.getenv('TESSERACT_PSM', '').strip() or None
    tess_lang = os.getenv('TESSERACT_LANG', '').strip() or None

    if not source_url and not source_file:
        print('SOURCE_URL or SOURCE_FILE env required', flush=True)
        return 2

    tmp_pdf = tempfile.mktemp(suffix='.pdf')
    if source_file and os.path.exists(source_file):
        shutil.copy2(source_file, tmp_pdf)
    else:
        r = requests.get(source_url, timeout=120)
        r.raise_for_status()
        with open(tmp_pdf, 'wb') as f:
            f.write(r.content)

    total_pages = get_page_count(tmp_pdf)
    sel_pages = parse_page_env(total_pages)
    print(f"[init] total_pages={total_pages} selected={('all' if not sel_pages else len(sel_pages))}", flush=True)

    min_words = int(os.getenv('MIN_TEXT_WORDS', '25') or '25')
    # Use hybrid extraction to avoid pages where text layer is sparse or out of order
    pages_words = hybrid_extract_words(tmp_pdf, pages=sel_pages, ocr_dpi=ocr_dpi, tess_psm=tess_psm, tess_lang=tess_lang, keepalive=True, min_text_words=min_words)

    rows, audit = parse_document(pages_words, default_session)

    base = os.path.splitext(os.path.basename(original_filename))[0]
    if sel_pages:
        # if continuous range, append suffix, else allow provided OUT_SUFFIX
        rng = _group_ranges(sel_pages)
        if len(rng) == 1 and not out_suffix:
            a,b = rng[0]
            out_suffix = f"-p{a}-{b}"
    if out_suffix:
        base = base + out_suffix
    out_dir = os.path.join('outputs')
    paths = save_outputs(rows, base, out_dir)

    summary = {
        'status': 'success',
        'counts': { 'rows': len(rows) },
        'audit': audit,
        'files': paths,
        'filename': original_filename
    }

    # write local summary
    with open(os.path.join(out_dir, base + '.summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)

    # upload results files back to app if configured
    if result_upload_url:
        if not result_upload_token:
            print('[warn] RESULT_UPLOAD_TOKEN is empty; skipping upload to app.', flush=True)
        upload_results(result_upload_url, result_upload_token, doc_id, paths, summary)

    # callback with JSON summary
    if callback_url:
        payload = json.dumps(summary).encode('utf-8')
        headers = { 'Content-Type': 'application/json' }
        if callback_secret:
            headers['X-Extractor-Signature'] = compute_signature(callback_secret, payload)
        try:
            cr = requests.post(callback_url, data=payload, headers=headers, timeout=60)
            print('Callback status:', cr.status_code)
        except Exception as e:
            print('Callback error:', repr(e))
    else:
        print('[info] CALLBACK_URL not set; skipping callback to app.', flush=True)

    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
