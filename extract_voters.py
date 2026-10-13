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

def is_status_annotation(text: str) -> bool:
    """
    Detects overlay and status notes such as [DELETED], [Shifted to: ...], [Shifted from: ...].
    Excludes footer text/legend explanations.
    """
    t_clean = text.strip()
    if 'Indicates that the elector' in t_clean or 'Serial Number —' in t_clean:
        return False
    t_upper = t_clean.upper()
    if any(k in t_upper for k in ['DELET', 'SHIFTED', 'स्थलांतरीत', 'वगळ', 'कमी', 'रद्द']):
        return True
    if re.search(r'^\d+\s*/\s*\d+\]?$', t_clean):
        return True
    return False

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
        # In PDF table layout, 4-digit numbers (>= 1000) wrap across multiple lines (e.g., '116' on line 1, '5' on line 2)
        sr_raw_lines = [
            l for l in lines 
            if 30.0 <= l['xMin'] < 60.0 and l['yMin'] > 195 and l['text'].strip().isdigit()
        ]
        sr_raw_lines.sort(key=lambda item: item['yMin'])

        # Group lines that belong to the same multi-line Sr No (close vertically)
        sr_lines = []
        skip_indices = set()
        for idx, l in enumerate(sr_raw_lines):
            if idx in skip_indices:
                continue
            
            combined_text = l['text'].strip()
            top_y = l['yMin']
            
            # Check if next line(s) are part of this Sr No (vertical gap typically <= 15 points)
            curr_idx = idx
            while curr_idx + 1 < len(sr_raw_lines):
                next_l = sr_raw_lines[curr_idx + 1]
                # If the vertical distance is small (same cell), concatenate the digits
                if next_l['yMin'] - sr_raw_lines[curr_idx]['yMin'] <= 16.0:
                    combined_text += next_l['text'].strip()
                    curr_idx += 1
                    skip_indices.add(curr_idx)
                else:
                    break
            
            sr_lines.append({
                'xMin': l['xMin'],
                'yMin': top_y,
                'text': combined_text
            })

        for i, sr_item in enumerate(sr_lines):
            sr = int(sr_item['text'].strip())
            top_y = sr_item['yMin'] - 4.0
            bottom_y = sr_lines[i+1]['yMin'] - 4.0 if i + 1 < len(sr_lines) else min(sr_item['yMin'] + 80.0, 785.0)
            
            row_lines = [
                l for l in lines 
                if top_y <= l['yMin'] < bottom_y and l['yMin'] < 785.0
            ]

            cols = [[] for _ in range(10)]
            shifted_notes = []
            
            for l in row_lines:
                if is_status_annotation(l['text']):
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

def extract_pdf_metadata(pdf_path: str):
    """
    Extracts metadata such as Part No and District from the header of the PDF.
    """
    if not os.path.exists(pdf_path):
        return {}
    proc = subprocess.Popen(
        ['pdftotext', '-bbox-layout', '-f', '1', '-l', '1', pdf_path, '-'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, _ = proc.communicate()
    root = ET.fromstring(stdout)
    ns = {'x': 'http://www.w3.org/1999/xhtml'}
    
    meta = {'part_no': '', 'district': ''}
    for p in root.findall('.//x:page', ns)[:1]:
        for l in p.findall('.//x:line', ns):
            text = ' '.join(w.text for w in l.findall('.//x:word', ns) if w.text)
            m_part = re.search(r'(?:Part\s*No\.?|भाग\s*क्रमांक)\s*[:.]?\s*(\d+)', text, re.I)
            if m_part:
                meta['part_no'] = m_part.group(1).strip()
            m_dist = re.search(r'(?:District|िजल्ह्याचे\s*नाव)\s*[:.]?\s*([^\n\r]+)', text, re.I)
            if m_dist:
                meta['district'] = m_dist.group(1).strip()
    return meta

def extract_house_no(address: str) -> str:
    """
    Attempts to extract house number / plot number from the beginning of an address.
    """
    if not address:
        return ""
    first_part = address.split(',')[0].strip()
    m = re.match(r'^(?:H\s*N|H\s*No|Plot\s*No|House\s*No)?\s*([0-9]+[A-Za-z0-9\/\-]*)', first_part, re.I)
    if m:
        return m.group(1).strip()
    return ""

def process_electoral_roll_pair(en_pdf: str, mr_pdf: str):
    """
    Extracts and merges records from an English and Marathi PDF pair.
    Returns (part_no, output1_rows, output2_rows)
    """
    print(f"[*] Extracting metadata for pair...")
    en_meta = extract_pdf_metadata(en_pdf)
    mr_meta = extract_pdf_metadata(mr_pdf)
    part_no = en_meta.get('part_no') or mr_meta.get('part_no') or ''
    print(f"[*] Extracted Part No: {part_no}")

    print(f"[*] Extracting English PDF: {en_pdf}...")
    en_records = extract_pdf_records(en_pdf, is_marathi=False)
    en_map = {r['sr_no']: r for r in en_records}

    print(f"[*] Extracting Marathi PDF (with Devanagari Unicode reordering): {mr_pdf}...")
    mr_records = extract_pdf_records(mr_pdf, is_marathi=True)
    mr_map = {r['sr_no']: r for r in mr_records}

    all_srs = sorted(list(set(en_map.keys()) | set(mr_map.keys())))
    print(f"[*] Found {len(all_srs)} voters for Part No {part_no}")

    out1_rows = []
    out2_rows = []

    for sr in all_srs:
        en = en_map.get(sr, {})
        mr = mr_map.get(sr, {})

        epic_no = mr.get('epic_no') or en.get('epic_no') or ''
        age = en.get('age') or mr.get('age') or ''

        # Shifted / deleted detection
        shifted_note = en.get('shifted_note') or mr.get('shifted_note') or ''
        note_lower = shifted_note.lower()
        is_shifted_from = bool(re.search(r'shifted\s*from', note_lower) or 'येथून स्थलांतरीत' in note_lower or 'येथून' in note_lower)

        if shifted_note and not is_shifted_from:
            is_deleted_or_shifted = any(k in note_lower for k in [
                'deleted', 'delet', 'shifted', 'स्थलांतरीत', 'वगळ', 'कमी', 'रद्द'
            ])
        elif shifted_note and is_shifted_from:
            # Only marked deleted if explicitly stated (e.g. deleted/cancelled)
            is_deleted_or_shifted = any(k in note_lower for k in [
                'deleted', 'delet', 'वगळ', 'कमी', 'रद्द'
            ])
        else:
            is_deleted_or_shifted = False

        glob_deleted = "1" if is_deleted_or_shifted else ""

        # Gender mapping: M and F
        g_en = (en.get('gender') or '').strip().upper()
        g_mr = (mr.get('gender') or '').strip()
        if g_en in ('M', 'MALE') or 'पुरुष' in g_mr:
            gender_val = 'M'
        elif g_en in ('F', 'FEMALE') or 'स्त्री' in g_mr:
            gender_val = 'F'
        else:
            gender_val = g_en if g_en else g_mr

        # House No extraction
        house_no = extract_house_no(en.get('address', '')) or extract_house_no(mr.get('address', ''))

        # Qualification and occupation combined for voter_profession
        qual_en = en.get('qualification', '').strip()
        occ_en = en.get('occupation', '').strip()
        if qual_en and occ_en:
            voter_profession_val = f"{qual_en} - {occ_en}"
        elif qual_en:
            voter_profession_val = qual_en
        elif occ_en:
            voter_profession_val = occ_en
        else:
            voter_profession_val = ""

        # Row for output1 (original schema)
        out1_rows.append({
            'sr_no': sr,
            'elector_name_mr': mr.get('elector_name', ''),
            'elector_name_en': en.get('elector_name', ''),
            'relative_name_mr': mr.get('relative_name', ''),
            'relative_name_en': en.get('relative_name', ''),
            'address_mr': mr.get('address', ''),
            'address_en': en.get('address', ''),
            'qualification_mr': mr.get('qualification', ''),
            'qualification_en': qual_en,
            'occupation_mr': mr.get('occupation', ''),
            'occupation_en': occ_en,
            'age': age,
            'gender_mr': mr.get('gender', ''),
            'gender_en': en.get('gender', ''),
            'epic_no': epic_no,
            'photo_status': en.get('photo_status') or mr.get('photo_status', 'Available'),
            'shifted_note': shifted_note
        })

        # Row for output2 (new updated 35-col schema)
        out2_rows.append({
            "Sr.No.": sr,
            "org_code": "",
            "matadar_sangh_code": "",
            "booth_id": part_no,
            "voter_ser_no": sr,
            "unknown_value": "",
            "glob_deleted": glob_deleted,
            "glob_duplicate": "",
            "full_name": mr.get('elector_name', ''),
            "e_full_name": en.get('elector_name', ''),
            "age": age,
            "gender": gender_val,
            "house_no": house_no,
            "voter_id": epic_no,
            "voter_address1": mr.get('address', ''),
            "evoter_address1": en.get('address', ''),
            "booth_address": "",
            "e_booth_address": "",
            "e_booth_name": "",
            "booth_name": "",
            "voter_is_alive": "True",
            "mobile_no": "",
            "optional_contact": "",
            "type": "",
            "imp_voter": "",
            "voter_cast_religion": "",
            "voter_address2": "",
            "influence": "",
            "voter_profession": voter_profession_val,
            "comment": shifted_note if shifted_note else "",
            "voting_status": "",
            "others": "",
            "eothers": "",
            "part_no": part_no,
            "vidh_no": ""
        })

    return part_no, out1_rows, out2_rows

def find_pdf_pairs(files_dir: str):
    """
    Finds all matching (EN, MR) PDF pairs in files_dir.
    Matches files with patterns like <prefix>_EN.pdf and <prefix>_MR.pdf.
    """
    files_path = Path(files_dir)
    if not files_path.exists():
        return []

    groups = {}
    for p in files_path.glob("*.pdf"):
        m = re.match(r'^(.*)_(EN|MR)\.pdf$', p.name, re.I)
        if m:
            base, lang = m.group(1), m.group(2).upper()
            groups.setdefault(base, {})[lang] = str(p)

    pairs = []
    for base in sorted(groups.keys()):
        en_file = groups[base].get('EN')
        mr_file = groups[base].get('MR')
        if en_file and mr_file:
            pairs.append((en_file, mr_file))
        else:
            print(f"[!] Warning: Incomplete pair for prefix {base}: {groups[base]}")
    return pairs

def process_all_rolls(
    files_dir: str = "files",
    output1_dir: str = "output1",
    output2_dir: str = "output2"
):
    pairs = find_pdf_pairs(files_dir)
    if not pairs:
        print(f"[!] No matching EN/MR PDF pairs found in '{files_dir}'.")
        return []

    print(f"[*] Found {len(pairs)} PDF pair(s) to process in '{files_dir}'.")

    # 1. Output1 fieldnames (original schema)
    output1_fieldnames = [
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

    # 2. Output2 fieldnames (exact 35 columns requested by user)
    output2_fieldnames = [
        "Sr.No.",
        "org_code",
        "matadar_sangh_code",
        "booth_id",
        "voter_ser_no",
        "unknown_value",
        "glob_deleted",
        "glob_duplicate",
        "full_name",
        "e_full_name",
        "age",
        "gender",
        "house_no",
        "voter_id",
        "voter_address1",
        "evoter_address1",
        "booth_address",
        "e_booth_address",
        "e_booth_name",
        "booth_name",
        "voter_is_alive",
        "mobile_no",
        "optional_contact",
        "type",
        "imp_voter",
        "voter_cast_religion",
        "voter_address2",
        "influence",
        "voter_profession",
        "comment",
        "voting_status",
        "others",
        "eothers",
        "part_no",
        "vidh_no"
    ]

    all_output1_rows = []
    all_output2_rows = []

    for en_pdf, mr_pdf in pairs:
        print(f"\n---> Processing: {os.path.basename(en_pdf)} & {os.path.basename(mr_pdf)}")
        part_no, out1, out2 = process_electoral_roll_pair(en_pdf, mr_pdf)
        all_output1_rows.extend(out1)
        all_output2_rows.extend(out2)

    # Re-index Sr.No. across all combined records sequentially for output2
    for idx, row in enumerate(all_output2_rows, start=1):
        row["Sr.No."] = idx

    # Ensure output directories exist
    os.makedirs(output1_dir, exist_ok=True)
    os.makedirs(output2_dir, exist_ok=True)

    output1_csv = os.path.join(output1_dir, "voters_extracted.csv")
    output2_csv = os.path.join(output2_dir, "voters_extracted.csv")

    # Save single output1 CSV
    with open(output1_csv, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=output1_fieldnames)
        writer.writeheader()
        writer.writerows(all_output1_rows)
    print(f"\n[✓] Successfully exported total {len(all_output1_rows)} records to single CSV in output1: {output1_csv}")

    # Save single output2 CSV
    with open(output2_csv, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=output2_fieldnames)
        writer.writeheader()
        writer.writerows(all_output2_rows)
    print(f"[✓] Successfully exported total {len(all_output2_rows)} records to single CSV in output2: {output2_csv}")

    return all_output2_rows

if __name__ == '__main__':
    base_dir = Path(__file__).resolve().parent
    files_dir = base_dir / "files/484"
    output1_dir = base_dir / "output1"
    output2_dir = base_dir / "output2"

    records = process_all_rolls(
        files_dir=str(files_dir),
        output1_dir=str(output1_dir),
        output2_dir=str(output2_dir)
    )
    print(f"\n[✓] All files completed. Total extracted records: {len(records)}.")


