#!/usr/bin/env python3
import os
import re
import io
import json
import hmac
import hashlib
import tempfile
import shutil
import requests
from dataclasses import dataclass, asdict
from typing import List, Tuple, Dict, Optional

import fitz  # PyMuPDF
import pdfplumber
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
import numpy as np
import pandas as pd
from docx import Document

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
    centers = np.array([( (w['x0']+w['x1'])/2.0 ) for w in words]).reshape(-1,1)

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


def kmeans_1d(X: np.ndarray, k: int, iters: int = 50) -> Dict:
    # simple 1D k-means
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
    # find leading uppercase tokens
    idx = 0
    while idx < len(tokens) and UPPER_TOKEN.match(tokens[idx]):
        idx += 1
    if idx == 0:
        # might still be Surname First Middle with Surname capitalized only first letter
        idx = 1
    surname = " ".join(tokens[:idx]).upper()
    rest = tokens[idx:]
    if not rest:
        return None
    first_name = rest[0]
    other = " ".join(rest[1:])
    return surname, first_name, other


def extract_words_from_pdf(path: str) -> List[Dict]:
    words_all = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
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
            words_all.append({ 'page_width': pw, 'page_height': ph, 'words': words })
    return words_all


def extract_words_via_ocr(path: str, dpi: int = 300) -> List[Dict]:
    tmpdir = tempfile.mkdtemp()
    try:
        images = convert_from_path(path, dpi=dpi)
        pages_out = []
        for img in images:
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
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
            pages_out.append({ 'page_width': pw, 'page_height': ph, 'words': words })
        return pages_out
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def is_text_extractable(path: str) -> bool:
    try:
        with fitz.open(path) as doc:
            for p in doc:
                if p.get_text().strip():
                    return True
        return False
    except Exception:
        return False


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
                if re.fullmatch(r"\d+|Vol\.?\s*\d+|Convocation|Ceremony|UNIVERSITY OF UYO|An institution on a Mission", line, re.I):
                    continue
                audit['unparsed'].append({ 'page': pi+1, 'line': line })
        # If no heading seen on this page, assume continuation of previous headings
        # current state already carries over
    return rows, audit


def save_outputs(rows: List[Row], base: str, out_dir: str) -> Dict[str,str]:
    os.makedirs(out_dir, exist_ok=True)
    data = [asdict(r) for r in rows]
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
    source_url = os.getenv('SOURCE_URL')
    original_filename = os.getenv('ORIGINAL_FILENAME', 'document.pdf')
    default_session = os.getenv('SESSION', '')
    callback_url = os.getenv('CALLBACK_URL')
    callback_secret = os.getenv('CALLBACK_HMAC_SECRET', '')
    result_upload_url = os.getenv('RESULT_UPLOAD_URL')
    result_upload_token = os.getenv('RESULT_UPLOAD_TOKEN', '')
    doc_id = os.getenv('DOC_ID')

    if not source_url:
        print('SOURCE_URL env required', flush=True)
        return 2

    tmp_pdf = tempfile.mktemp(suffix='.pdf')
    r = requests.get(source_url, timeout=120)
    r.raise_for_status()
    with open(tmp_pdf, 'wb') as f:
        f.write(r.content)

    text_ok = is_text_extractable(tmp_pdf)
    if text_ok:
        pages_words = extract_words_from_pdf(tmp_pdf)
    else:
        pages_words = extract_words_via_ocr(tmp_pdf)

    rows, audit = parse_document(pages_words, default_session)

    base = os.path.splitext(os.path.basename(original_filename))[0]
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

    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
