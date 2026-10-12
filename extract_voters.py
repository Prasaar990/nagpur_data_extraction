#!/usr/bin/env python3
"""
Electoral Roll Data Extractor (English & Marathi)
Maharashtra Legislative Council Electoral Roll - NAGPUR Division Graduates' Constituency

Extracts structured voter data from both English and Marathi PDF files, aligning:
- Sr No
- Elector Name (English & Marathi, with Devanagari Unicode reordering)
- Relative Name (English & Marathi)
- Address (English & Marathi)
- Qualification (English & Marathi)
- Occupation (English & Marathi)
- Age
- Gender (English & Marathi)
- EPIC No
- Photo Availability
- Shifted / Supplementary Note
"""

import os
import sys
import csv
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

# Table layout column horizontal boundaries (in PDF points, A4 width = 595.28)
COL_BOUNDS = [
    (30.0, 60.0),    # 0: Sr No
    (60.0, 142.0),   # 1: Elector Name
    (142.0, 218.0),  # 2: Relative Name
    (218.0, 308.0),  # 3: Address
    (308.0, 354.0),  # 4: Qualification
    (354.0, 396.0),  # 5: Occupation
    (396.0, 424.0),  # 6: Age
    (424.0, 456.0),  # 7: Gender
    (456.0, 515.0),  # 8: Epic No
    (515.0, 580.0)   # 9: Photo
]

def get_col_index(x_start: float) -> int:
    for i, (left, right) in enumerate(COL_BOUNDS):
        if left <= x_start < right:
            return i
    return -1

def clean_marathi_text(text: str) -> str:
    """
    Fixes visual encoding artifacts produced by PDFKit/Cairo for Devanagari:
    1. Hrasva Velanti (ि U+093F): In PDFKit font streams, the short-i matra was 
       encoded before the consonant (visual order: ि + व = िव). Standard Unicode
       requires logical phonetic order: व + ि = वि.
    2. Rafar (र् U+0930 U+094D): Stored after the character instead of before
       (e.g., वाड + र् -> वार्ड).
    3. Normalizes archaic forms (e.g., 'ईतर' -> 'इतर').
    """
    if not text:
        return ""
    
    # 1. Fix Velanti: swap short-i vowel sign with the consonant cluster following it
    text = re.sub(
        r'\u093f((?:[\u0915-\u0939]\u094d)*[\u0915-\u0939])', 
        lambda m: m.group(1) + '\u093f', 
        text
    )
    
    # 2. Fix Rafar: swap consonant/vowel syllable with trailing 'र्'
    text = re.sub(
        r'([\u0915-\u0939\u0905-\u0914][\u093e-\u094c]?)\u0930\u094d', 
        lambda m: '\u0930\u094d' + m.group(1), 
        text
    )
    
    # 3. Standardize archaic spellings
    text = text.replace('ईतर', 'इतर')
    return re.sub(r'\s+', ' ', text).strip()

def extract_pdf_records(pdf_path: str, is_marathi: bool = False):
    """
    Extracts tabular records from a PDF using pdftotext with bbox-layout XML.
    Guarantees accurate text preservation without column leakage or word dropping.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    proc = subprocess.Popen(
        ['pdftotext', '-bbox-layout', pdf_path, '-'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"pdftotext failed on {pdf_path}: {stderr.decode('utf-8', errors='ignore')}")

    root = ET.fromstring(stdout)
    ns = {'x': 'http://www.w3.org/1999/xhtml'}
    
    records = []
    
    for page in root.findall('.//x:page', ns):
        lines = []
        for l in page.findall('.//x:line', ns):
            words = [w.text for w in l.findall('.//x:word', ns) if w.text]
            if not words:
                continue
            line_text = ' '.join(words)
            x_min = float(l.attrib['xMin'])
            y_min = float(l.attrib['yMin'])
            lines.append({'xMin': x_min, 'yMin': y_min, 'text': line_text})

        # Identify rows starting with Sr No in column 0
        sr_lines = [
            l for l in lines 
            if 30.0 <= l['xMin'] < 60.0 and l['yMin'] > 195 and l['text'].strip().isdigit()
        ]
        sr_lines.sort(key=lambda item: item['yMin'])

        for i, sr_item in enumerate(sr_lines):
            sr = int(sr_item['text'].strip())
            top_y = sr_item['yMin'] - 4.0
            bottom_y = sr_lines[i+1]['yMin'] - 4.0 if i + 1 < len(sr_lines) else 785.0
            
            row_lines = [
                l for l in lines 
                if top_y <= l['yMin'] < bottom_y and l['yMin'] < 785.0
            ]

            cols = [[] for _ in range(10)]
            shifted_notes = []
            
            for l in row_lines:
                if 'Shifted to:' in l['text'] or '[Shifted to' in l['text']:
                    shifted_notes.append(l['text'])
                    continue
                c = get_col_index(l['xMin'])
                if c != -1:
                    cols[c].append(l)

            fields = []
            for c in range(10):
                c_lines = sorted(cols[c], key=lambda item: item['yMin'])
                val = ' '.join(item['text'] for item in c_lines).strip()
                if is_marathi and c in (1, 2, 3, 4, 5, 7):
                    val = clean_marathi_text(val)
                fields.append(val)

            photo_status = "Available" if ("Photo" in fields[9] or "Available" in fields[9]) else "Not Available"
            
            records.append({
                'sr_no': sr,
                'elector_name': fields[1],
                'relative_name': fields[2],
                'address': fields[3],
                'qualification': fields[4],
                'occupation': fields[5],
                'age': fields[6],
                'gender': fields[7],
                'epic_no': fields[8].replace(' ', ''),
                'photo_status': photo_status,
                'shifted_note': ' '.join(shifted_notes)
            })
            
    return records

def process_electoral_rolls(
    en_pdf: str, 
    mr_pdf: str, 
    output_csv: str = "output/voters_extracted.csv", 
    output_json: str = "output/voters_extracted.json"
):
    print(f"[*] Extracting English PDF: {en_pdf}...")
    en_records = extract_pdf_records(en_pdf, is_marathi=False)
    en_map = {r['sr_no']: r for r in en_records}

    print(f"[*] Extracting Marathi PDF (with Devanagari Unicode reordering): {mr_pdf}...")
    mr_records = extract_pdf_records(mr_pdf, is_marathi=True)
    mr_map = {r['sr_no']: r for r in mr_records}

    all_srs = sorted(list(set(en_map.keys()) | set(mr_map.keys())))
    print(f"[*] Total unique voters found: {len(all_srs)}")

    combined_rows = []
    for sr in all_srs:
        en = en_map.get(sr, {})
        mr = mr_map.get(sr, {})

        epic_no = mr.get('epic_no') or en.get('epic_no') or ''
        age = en.get('age') or mr.get('age') or ''

        combined_rows.append({
            'sr_no': sr,
            'elector_name_mr': mr.get('elector_name', ''),
            'elector_name_en': en.get('elector_name', ''),
            'relative_name_mr': mr.get('relative_name', ''),
            'relative_name_en': en.get('relative_name', ''),
            'address_mr': mr.get('address', ''),
            'address_en': en.get('address', ''),
            'qualification_mr': mr.get('qualification', ''),
            'qualification_en': en.get('qualification', ''),
            'occupation_mr': mr.get('occupation', ''),
            'occupation_en': en.get('occupation', ''),
            'age': age,
            'gender_mr': mr.get('gender', ''),
            'gender_en': en.get('gender', ''),
            'epic_no': epic_no,
            'photo_status': en.get('photo_status') or mr.get('photo_status', 'Available'),
            'shifted_note': en.get('shifted_note') or mr.get('shifted_note', '')
        })

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output_json)), exist_ok=True)

    # Save to CSV (UTF-8 with BOM for proper display in Excel & Google Sheets)
    fieldnames = [
        'sr_no',
        'elector_name_mr',
        'elector_name_en',
        'relative_name_mr',
        'relative_name_en',
        'address_mr',
        'address_en',
        'qualification_mr',
        'qualification_en',
        'occupation_mr',
        'occupation_en',
        'age',
        'gender_mr',
        'gender_en',
        'epic_no',
        'photo_status',
        'shifted_note'
    ]

    with open(output_csv, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(combined_rows)

    print(f"[✓] Successfully exported {len(combined_rows)} records to CSV: {output_csv}")

    # Save to JSON
    with open(output_json, mode='w', encoding='utf-8') as f:
        json.dump(combined_rows, f, ensure_ascii=False, indent=2)

    print(f"[✓] Successfully exported {len(combined_rows)} records to JSON: {output_json}")

    return combined_rows

if __name__ == '__main__':
    base_dir = Path(__file__).resolve().parent
    
    # Check input PDFs in files/ folder or root directory
    en_file = base_dir / "files" / "GAC7_DIST471_PART247_EN.pdf"
    if not en_file.exists():
        en_file = base_dir / "GAC7_DIST471_PART247_EN.pdf"

    mr_file = base_dir / "files" / "GAC7_DIST471_PART247_MR.pdf"
    if not mr_file.exists():
        mr_file = base_dir / "GAC7_DIST471_PART247_MR.pdf"

    if not en_file.exists() or not mr_file.exists():
        print(f"Error: Could not find input PDFs in {base_dir / 'files'} or {base_dir}")
        sys.exit(1)

    output_dir = base_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_csv = output_dir / "voters_extracted.csv"
    output_json = output_dir / "voters_extracted.json"

    records = process_electoral_rolls(
        str(en_file), 
        str(mr_file), 
        str(output_csv), 
        str(output_json)
    )
    print("\nSample Cleaned Record (Sr No 1):")
    print(json.dumps(records[0], ensure_ascii=False, indent=2))


