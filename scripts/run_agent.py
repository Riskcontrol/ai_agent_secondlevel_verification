#!/usr/bin/env python3
import os
import json
import hashlib
import hmac
import tempfile
import shutil
from typing import Dict

import requests
import pandas as pd
import sys
from pathlib import Path
import importlib.util

# Robustly load agent.py from the same directory regardless of sys.path
_scripts_dir = Path(__file__).resolve().parent
_agent_path = _scripts_dir / 'agent.py'
if not _agent_path.exists():
    raise FileNotFoundError(f"agent.py not found at {_agent_path}")
_spec = importlib.util.spec_from_file_location('agent_local', str(_agent_path))
if _spec is None or _spec.loader is None:
    raise ImportError('Could not load agent.py module spec')
_agent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_agent)
ConvocationPDFExtractor = getattr(_agent, 'ConvocationPDFExtractor')


def norm_space(s: str) -> str:
    return " ".join((s or "").split()).strip()


def compute_signature(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()


def upload_results(upload_url: str, token: str, doc_id: str, paths: Dict[str, str], summary: Dict) -> None:
    if not upload_url:
        print('[agent] RESULT_UPLOAD_URL empty; skipping upload to app')
        return
    try:
        files = {}
        for key in ['csv', 'xlsx']:
            p = paths.get(key)
            if p and os.path.exists(p):
                files[key] = (os.path.basename(p), open(p, 'rb'), 'application/octet-stream')
        data = {'doc_id': doc_id or '', 'summary': json.dumps(summary)}
        headers = {}
        if token:
            headers['Authorization'] = f"Bearer {token}"
        resp = requests.post(upload_url, files=files, data=data, headers=headers, timeout=120)
        print('[agent] Upload results status:', resp.status_code)
    except Exception as e:
        print('[agent] Upload results error:', repr(e))


def main() -> int:
    # Inputs
    api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GEMINI-API-KEY')
    if not api_key:
        print('[agent] GEMINI_API_KEY missing')
        return 2

    source_url = os.getenv('SOURCE_URL', '').strip()
    source_file = os.getenv('SOURCE_FILE', '').strip()
    original_filename = os.getenv('ORIGINAL_FILENAME', 'document.pdf')
    session = os.getenv('SESSION', '2021/2022')
    page_start = int(os.getenv('PAGE_START', '1') or '1')
    page_end_env = os.getenv('PAGE_END', '').strip()
    page_end = int(page_end_env) if page_end_env else None
    dpi = int(os.getenv('DPI', os.getenv('OCR_DPI', '300')) or '300')

    # App integration
    callback_url = os.getenv('CALLBACK_URL', '').strip()
    callback_secret = os.getenv('CALLBACK_HMAC_SECRET', '').strip()
    result_upload_url = os.getenv('RESULT_UPLOAD_URL', '').strip()
    result_upload_token = os.getenv('RESULT_UPLOAD_TOKEN', '').strip()
    doc_id = os.getenv('DOC_ID', '')

    # Resolve PDF path
    tmp_pdf = tempfile.mktemp(suffix='.pdf')
    if source_file and os.path.exists(source_file):
        shutil.copy2(source_file, tmp_pdf)
    elif source_url:
        r = requests.get(source_url, timeout=300)
        r.raise_for_status()
        with open(tmp_pdf, 'wb') as f:
            f.write(r.content)
    else:
        print('[agent] SOURCE_URL or SOURCE_FILE is required')
        return 2

    # Run extractor
    extractor = ConvocationPDFExtractor(api_key=api_key, session=session)
    df = extractor.extract_from_pdf(pdf_path=tmp_pdf, start_page=page_start, end_page=page_end, dpi=dpi)

    # Normalize and order columns
    cols = ['surname', 'first_name', 'other_name', 'course_studied', 'faculty', 'grade', 'qualification_obtained', 'session']
    for c in cols:
        if c not in df.columns:
            df[c] = ''
    df = df[cols]

    # Save outputs (CSV and XLSX only)
    base = os.path.splitext(os.path.basename(original_filename))[0]
    out_dir = os.path.join('outputs')
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, base + '.csv')
    xlsx_path = os.path.join(out_dir, base + '.xlsx')
    df.to_csv(csv_path, index=False)
    print('[agent] Wrote CSV:', csv_path)
    # use openpyxl by default to avoid xlsxwriter dependency
    try:
        with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        print('[agent] Wrote XLSX:', xlsx_path)
    except Exception as e:
        print('[agent] XLSX write failed with openpyxl:', e, '-> trying default engine')
        df.to_excel(xlsx_path, index=False)
        print('[agent] Wrote XLSX:', xlsx_path)

    summary = {
        'status': 'success',
        'counts': {'rows': int(len(df))},
        'files': {'csv': csv_path, 'xlsx': xlsx_path},
        'filename': original_filename,
    }

    # Upload to app
    if not result_upload_token:
        print('[agent] RESULT_UPLOAD_TOKEN is empty; upload may be rejected by app')
    upload_results(result_upload_url, result_upload_token, doc_id, {'csv': csv_path, 'xlsx': xlsx_path}, summary)

    # Callback
    if callback_url:
        payload = json.dumps(summary).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        if callback_secret:
            headers['X-Extractor-Signature'] = compute_signature(callback_secret, payload)
        try:
            cr = requests.post(callback_url, data=payload, headers=headers, timeout=60)
            print('[agent] Callback status:', cr.status_code)
        except Exception as e:
            print('[agent] Callback error:', repr(e))
    else:
        print('[agent] CALLBACK_URL not set; skipping callback')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
