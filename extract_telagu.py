#!/usr/bin/env python3
"""
Electoral Roll Data Extractor for Telugu Voter Lists
AP SEC / ECI Urban Photo Voter Lists (e.g. Greater Visakhapatnam Municipal Corporation)

Key Highlights:
- NO OCR REQUIRED: The PDF contains native Unicode text encoded with Microsoft Nirmala UI TrueType fonts.
- Technique: Uses `pdftotext -bbox-layout` with XML parsing (same foundational technique as `extract_voters.py`).
- Accurately segments the 3-column card grid per page.
- Extracts:
  1. Ward Voter Serial Number (వార్డు.ఓ.జా.వ.సం.)
  2. Assembly Voter Info / AC-Part-Serial (అ.ఓ.జా.వ.సం.)
  3. Elector Name (ఓటరు పేరు)
  4. Relative Name & Relation Type (తండ్రి/భర్త/తల్లి/సంరక్షకుడు పేరు)
  5. Age (వయస్సు)
  6. Gender (లింగము: పురుషుడు/పు -> M, స్త్రీ -> F)
  7. House Number / Address (ఇంటి సంఖ్య)
  8. EPIC Voter ID Card No (ఓటరు ఐడి. కార్డు నెం.)
  9. Photo Status (Photo Available / Not Available)
  10. Booth / Polling Station & Ward Metadata

Outputs:
1. output1/<name>_telugu_voters.csv: Full structured Telugu voter records
2. output2/<name>_standardized.csv: 32-column standardized database schema
3. output1/<name>_telugu_voters.json: JSON dump of all records
"""

import os
import sys
import csv
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

# Ensure stdout flushes immediately
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)


# ==========================================
# Coordinate Bounds for 3-Column Grid Layout
# ==========================================
# A4 Page Width = ~595 points
GRID_COLUMNS = [
    (25.0, 212.0),   # Column 0: Left card column (~35 to 210)
    (212.0, 389.0),  # Column 1: Middle card column (~212 to 388)
    (389.0, 580.0)   # Column 2: Right card column (~389 to 570)
]


def get_column_index(x_pt: float) -> int:
    """Returns which column (0, 1, or 2) an x-coordinate belongs to."""
    for idx, (left, right) in enumerate(GRID_COLUMNS):
        if left <= x_pt < right:
            return idx
    return -1


def clean_telugu_text(text: str) -> str:
    """
    Cleans and normalizes Telugu text:
    - Removes Unicode replacement character U+FFFD (often produced from zero-width non-joiners/soft hyphens)
    - Strips invisible control characters (ZWNJ, ZWJ, BOM)
    - Cleans leading/trailing colons and whitespace
    """
    if not text:
        return ""
    text = text.replace('\ufffd', '')
    text = re.sub(r'[\u200b-\u200f\ufeff]', '', text)
    text = re.sub(r'^[:\s\-\.]+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# Alias for brevity
clean_telugu = clean_telugu_text


def extract_pdf_metadata(pdf_path: str) -> dict:
    """
    Extracts cover page and header metadata:
    - District (జిల్లా పేరు)
    - ULB / Municipal Corporation (గ్రేటర్ నగర పాలక సంస్థ)
    - Ward Number (వార్డు సంఖ్య)
    - Assembly Constituency (శాసనసభ నియోజకవర్గం)
    - Polling Station / Booth ID & Name (ఎన్నికల కేంద్రము)
    - Total Voters (మొత్తం ఓటర్లు)
    """
    if not os.path.exists(pdf_path):
        return {}

    meta = {
        'district': '',
        'ulb_name': '',
        'ward_no': '',
        'booth_no': '',
        'booth_name': '',
        'ac_no': '',
        'ac_name': '',
        'total_voters': ''
    }

    try:
        stdout = subprocess.check_output(
            ['pdftotext', '-bbox-layout', '-f', '1', '-l', '2', pdf_path, '-'],
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"[!] Warning: Failed to extract metadata via pdftotext: {e}")
        return meta

    try:
        root = ET.fromstring(stdout)
        ns = {'x': 'http://www.w3.org/1999/xhtml'}
        pages = root.findall('.//x:page', ns)
        if not pages:
            return meta

        # Extract Page 1 table lines
        p1 = pages[0]
        p1_lines = []
        for l in p1.findall('.//x:line', ns):
            w_text = ' '.join(w.text for w in l.findall('.//x:word', ns) if w.text)
            if w_text.strip():
                p1_lines.append({
                    'xMin': float(l.attrib['xMin']),
                    'yMin': float(l.attrib['yMin']),
                    'text': w_text.strip()
                })

        # Find key-value pairs by matching Y-coordinates on Page 1
        for kl in [l for l in p1_lines if 130 <= l['xMin'] <= 250]:
            k_text = kl['text']
            # Find corresponding value at xMin >= 340 with close yMin (+- 10 pt)
            v_matches = [
                vl['text'] for vl in p1_lines 
                if vl['xMin'] >= 340 and abs(vl['yMin'] - kl['yMin']) <= 10.0
            ]
            val = ' '.join(v_matches).strip() if v_matches else ''

            if 'జిల్లా' in k_text and not meta['district']:
                meta['district'] = val
            elif 'పాలక సంస్థ' in k_text and not meta['ulb_name']:
                meta['ulb_name'] = val
            elif 'వార్డు సంఖ్య' in k_text and not meta['ward_no']:
                meta['ward_no'] = val
            elif 'శాసనసభ' in k_text and not meta['ac_name']:
                meta['ac_name'] = val
                m_ac = re.search(r'^(\d+)', val)
                if m_ac:
                    meta['ac_no'] = m_ac.group(1)
            elif 'మొత్తం ఓటర్లు' in k_text and not meta['total_voters']:
                meta['total_voters'] = val

        # 2. Extract Polling Station from Page 2 header
        if len(pages) > 1:
            p2 = pages[1]
            for l in p2.findall('.//x:line', ns):
                w_text = ' '.join(w.text for w in l.findall('.//x:word', ns) if w.text)
                if 'ఎన్ని కల కేంద్రము' in w_text or 'ఎన్నికల కేంద్రము' in w_text:
                    m_b = re.search(r'ఎన్ని\s*కల\s*కేంద్రము\s*:\s*([^\n\r]+)', w_text)
                    if m_b:
                        b_str = m_b.group(1).strip()
                        meta['booth_name'] = b_str
                        m_bno = re.search(r'^([0-9\/]+)', b_str)
                        if m_bno:
                            meta['booth_no'] = m_bno.group(1)
                    break
    except Exception:
        pass

    # Fallback booth_no from filename if missing (e.g. 48-10.pdf -> ward 48, booth 10)
    if not meta['booth_no']:
        m_fn = re.search(r'(\d+)[\-_](\d+)', Path(pdf_path).name)
        if m_fn:
            meta['ward_no'] = meta['ward_no'] or m_fn.group(1)
            meta['booth_no'] = f"{m_fn.group(1)}/{m_fn.group(2)}"

    return meta


def parse_voter_card(card_lines: list[dict]) -> dict:
    """
    Parses a single voter card's lines into structured fields:
    - Clusters lines by vertical Y proximity (within 6 points) into logical rows.
    - Extracts ward_sr_no, assembly_voter_info, elector_name, relative_type,
      relative_name, age, gender, house_no, epic_no, photo_status.
    """
    # 1. Cluster lines by vertical proximity (within 6 pt)
    sorted_lines = sorted(card_lines, key=lambda l: l['yMin'])
    y_clusters = []
    for l in sorted_lines:
        placed = False
        for cluster in y_clusters:
            if abs(cluster[0]['yMin'] - l['yMin']) <= 6.0:
                cluster.append(l)
                placed = True
                break
        if not placed:
            y_clusters.append([l])

    # 2. Within each cluster, sort left-to-right (xMin)
    card_rows = []
    for cluster in y_clusters:
        cluster.sort(key=lambda l: l['xMin'])
        row_text = ' '.join(l['text'] for l in cluster)
        card_rows.append({
            'yMin': cluster[0]['yMin'],
            'xMin': cluster[0]['xMin'],
            'text': row_text,
            'items': cluster
        })

    full_text = '\n'.join(r['text'] for r in card_rows)

    # 3. Ward Serial Number (వార్డు.ఓ.జా.వ.సం.)
    ward_sr_no = ''
    m_w = re.search(r'వార్డు\s*[.ఓజావసం\s]*\.\s*(\d+)', full_text)
    if m_w:
        ward_sr_no = m_w.group(1)

    # 4. Assembly Voter Info (అ.ఓ.జా.వ.సం.)
    m_a = re.search(r'అ\.ఓ\.జా\.వ\.సం\s*\.?\s*([0-9\s\-]+)', full_text)
    assembly_voter_info = clean_telugu(m_a.group(1)) if m_a else ''

    # 5. EPIC Voter ID No (ఓటరు ఐడి. కార్డు నెం.)
    epic_no = ''
    m_e = re.search(r'ఓటరు\s*ఐడి[.\s]*కార్డు\s*నెం[.\s]*:\s*([A-Za-z0-9\/]+)', full_text)
    if m_e:
        epic_no = m_e.group(1).replace(' ', '')
    else:
        m_e2 = re.search(r'\b([A-Z]{3}\d{7})\b', full_text)
        if m_e2:
            epic_no = m_e2.group(1)

    # 6. Age (వయస్సు)
    age = ''
    m_age = re.search(r'వయస్సు[^\d]*(\d+)', full_text)
    if m_age:
        age = m_age.group(1)

    # 7. Gender (లింగము: స్త్రీ -> F, పు / పురుష -> M, ఇతరులు -> O)
    gender = ''
    if 'స్త్రీ' in full_text:
        gender = 'F'
    elif 'లింగము' in full_text and 'పు' in full_text:
        gender = 'M'
    elif 'పురుష' in full_text:
        gender = 'M'
    elif 'ఇతరులు' in full_text:
        gender = 'O'

    # 8. Photo Status
    photo = 'Available'
    if 'Not Available' in full_text:
        photo = 'Not Available'

    # 9. Structured Body Row Extraction (Elector Name, Relative, House No)
    # Filter out header (ward serial) and footer (EPIC / date) rows
    body_rows = []
    for r in card_rows:
        if 'వార్డు' in r['text'] and 'సం' in r['text']:
            continue
        if 'ఓటరు ఐడి' in r['text'] or (epic_no and epic_no in r['text']):
            continue
        # Exclude page footer / date lines leaked at page boundary
        if 'ప్రచురణ తేదీ' in r['text'] or 'పుట సంఖ్య' in r['text'] or 'మునిసిపల్ కమీషనరు' in r['text']:
            continue
        body_rows.append(r)

    # Locate row boundaries
    rel_idx = None
    rel_type = ''
    for i, r in enumerate(body_rows):
        m_rt = re.search(r'(తండ్రి|భర్త|తల్లి|ఇతర|సంరక్షకుడు)\s*పేరు', r['text'])
        if m_rt:
            rel_idx = i
            rel_type = m_rt.group(1)
            break

    age_idx = None
    for i, r in enumerate(body_rows):
        if 'వయస్సు' in r['text'] or 'లింగము' in r['text']:
            age_idx = i
            break

    house_idx = None
    for i, r in enumerate(body_rows):
        if 'ఇంటి సంఖ్య' in r['text']:
            house_idx = i
            break

    # If label for relative name was missing in PDF (e.g. Card 9041), detect line between name and age
    if rel_idx is None and age_idx is not None and age_idx > 1:
        rel_idx = age_idx - 1
        rel_type = 'బంధువు'

    # Extract Elector Name: rows from start up to rel_idx (or age_idx)
    name_end = rel_idx if rel_idx is not None else (age_idx if age_idx is not None else len(body_rows))
    name_parts = []
    for r in body_rows[:name_end]:
        t = re.sub(r'ఓటరు\s*పేరు\s*:?', '', r['text'])
        t = re.sub(r'\b(Photo|Available)\b', '', t).strip()
        if t:
            name_parts.append(t)
    elector_name = clean_telugu(' '.join(name_parts))

    # Extract Relative Name: rows from rel_idx up to age_idx (or house_idx)
    rel_parts = []
    if rel_idx is not None:
        rel_end = age_idx if age_idx is not None else (house_idx if house_idx is not None else len(body_rows))
        for r in body_rows[rel_idx:rel_end]:
            t = re.sub(r'(తండ్రి|భర్త|తల్లి|ఇతర|సంరక్షకుడు|బంధువు)\s*పేరు\s*:?', '', r['text'])
            t = re.sub(r'\b(Photo|Available)\b', '', t).strip()
            if t:
                rel_parts.append(t)
    relative_name = clean_telugu(' '.join(rel_parts))

    # Extract House No: rows from house_idx onwards
    house_parts = []
    if house_idx is not None:
        for r in body_rows[house_idx:]:
            t = re.sub(r'ఇంటి\s*సంఖ్య\s*:?', '', r['text'])
            t = re.sub(r'\b(Photo|Available)\b', '', t).strip()
            # Also clean footer leaks if any
            t = re.sub(r'ప్రచురణ\s*తేదీ.*$', '', t).strip()
            t = re.sub(r'ఓటర్ల\s*జాబితా\s*ప్రచురణాధికారి.*$', '', t).strip()
            if t:
                house_parts.append(t)
    house_no = clean_telugu(' '.join(house_parts))

    return {
        'ward_sr_no': int(ward_sr_no) if ward_sr_no.isdigit() else 0,
        'assembly_voter_info': assembly_voter_info,
        'elector_name': elector_name,
        'relative_type': rel_type,
        'relative_name': relative_name,
        'age': age,
        'gender': gender,
        'house_no': house_no,
        'epic_no': epic_no,
        'photo_status': photo
    }


def extract_telugu_pdf_records(pdf_path: str) -> tuple[dict, list[dict]]:
    """
    Extracts all voter cards from the Telugu PDF file using pdftotext bbox-layout.
    Returns:
    - metadata: dictionary containing roll and polling station metadata
    - records: list of structured voter records
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    print(f"[*] Extracting metadata from {pdf_path}...")
    meta = extract_pdf_metadata(pdf_path)
    print(f"[*] District: {meta.get('district')}, Ward: {meta.get('ward_no')}, Booth: {meta.get('booth_no')}")

    print(f"[*] Extracting PDF text bbox layout via pdftotext...")
    try:
        stdout = subprocess.check_output(
            ['pdftotext', '-bbox-layout', pdf_path, '-'],
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        raise RuntimeError(f"pdftotext failed on {pdf_path}: {e}")

    root = ET.fromstring(stdout)
    ns_uri = '{http://www.w3.org/1999/xhtml}'
    pages = list(root.iter(f'{ns_uri}page'))
    print(f"[*] Total PDF pages: {len(pages)}")

    raw_cards = []

    # Process Page 2 onwards (Page 1 is the cover/index page)
    for p_num, page in enumerate(pages[1:], start=2):
        lines = []
        for l in page.iter(f'{ns_uri}line'):
            w_text = ' '.join(w.text for w in l.iter(f'{ns_uri}word') if w.text)
            if not w_text.strip():
                continue
            lines.append({
                'xMin': float(l.attrib['xMin']),
                'yMin': float(l.attrib['yMin']),
                'text': w_text.strip()
            })

        # Process each of the 3 columns independently
        for col_idx in range(3):
            # Keep lines in the voter card content area (y: 70 to 805)
            col_lines = [
                l for l in lines 
                if get_column_index(l['xMin']) == col_idx and 70.0 <= l['yMin'] <= 805.0
            ]
            col_lines.sort(key=lambda item: item['yMin'])

            # Card starts with header containing 'వార్డు' and 'సం'
            header_indices = []
            for i, l in enumerate(col_lines):
                if 'వార్డు' in l['text'] and 'సం' in l['text']:
                    header_indices.append(i)

            for i, s_idx in enumerate(header_indices):
                e_idx = header_indices[i + 1] if i + 1 < len(header_indices) else len(col_lines)
                card_lines = col_lines[s_idx:e_idx]
                if not card_lines:
                    continue
                # Bounding safeguard: card height is ~78 points; do not exceed card_top + 80 pt
                card_top = card_lines[0]['yMin']
                bounded_card_lines = [l for l in card_lines if l['yMin'] <= card_top + 80.0]

                raw_cards.append({
                    'page': p_num,
                    'col': col_idx,
                    'yMin': card_top,
                    'lines': bounded_card_lines
                })

    # Sort cards in standard reading order: page, row (grouped by 30 pt yMin), then column
    raw_cards.sort(key=lambda r: (r['page'], round(r['yMin'] / 30.0), r['col']))

    print(f"[*] Detected {len(raw_cards)} voter cards across all pages. Parsing card fields...")
    records = []
    for idx, card in enumerate(raw_cards, start=1):
        parsed = parse_voter_card(card['lines'])
        parsed['sr_no'] = idx
        records.append(parsed)

    # If ward_sr_no is sequential, ensure records are sorted by ward_sr_no
    if all(r['ward_sr_no'] > 0 for r in records):
        records.sort(key=lambda r: r['ward_sr_no'])
        for idx, r in enumerate(records, start=1):
            r['sr_no'] = idx

    print(f"[✓] Successfully parsed {len(records)} voter records.")
    return meta, records


def build_output_datasets(meta: dict, records: list[dict]):
    """
    Builds both output datasets:
    1. output1_rows: Full direct Telugu schema with rich fields
    2. output2_rows: 32-column standardized database schema matching extract_voters.py
    """
    ward_no = meta.get('ward_no', '')
    booth_no = meta.get('booth_no', '')
    booth_name = meta.get('booth_name', '')
    district = meta.get('district', '')
    ac_no = meta.get('ac_no', '')
    ac_name = meta.get('ac_name', '')

    out1_rows = []
    out2_rows = []

    for r in records:
        sr = r['sr_no']
        ward_sr = r['ward_sr_no'] or sr
        epic = r['epic_no']
        name = r['elector_name']
        rel_type = r['relative_type']
        rel_name = r['relative_name']
        house_no = r['house_no']
        age = r['age']
        gender = r['gender']
        assembly_info = r['assembly_voter_info']

        # Format relative string
        rel_combined = f"{rel_type}: {rel_name}" if rel_type and rel_name else (rel_name or "")

        # 1. Output1 (Direct Telugu Schema)
        out1_rows.append({
            'sr_no': sr,
            'ward_voter_sr_no': ward_sr,
            'assembly_voter_info': assembly_info,
            'elector_name': name,
            'relative_type': rel_type,
            'relative_name': rel_name,
            'age': age,
            'gender': gender,
            'house_no': house_no,
            'epic_no': epic,
            'photo_status': r.get('photo_status', 'Available'),
            'ward_no': ward_no,
            'booth_no': booth_no,
            'booth_name': booth_name,
            'ac_name': ac_name,
            'district': district
        })

        # 2. Output2 (Standardized 32-column Schema)
        out2_rows.append({
            "Sr.No.": sr,
            "org_code": "EITOT",
            "matadar_sangh_code": ac_no,
            "booth_id": booth_no,
            "voter_ser_no": ward_sr,
            "glob_deleted": "0",
            "glob_duplicate": "0",
            "full_name": name,
            "e_full_name": "",
            "age": age,
            "gender": gender,
            "house_no": house_no,
            "voter_id": epic,
            "voter_address1": house_no,
            "evoter_address1": "",
            "booth_address": booth_name,
            "e_booth_address": "",
            "e_booth_name": "",
            "booth_name": booth_name,
            "voter_is_alive": "True",
            "mobile_no": "",
            "optional_contact": "",
            "type": "",
            "imp_voter": "",
            "voter_cast_religion": "",
            "voter_address2": "",
            "influence": "",
            "voter_profession": "",
            "comment": f"{rel_combined} | Assembly: {assembly_info}".strip(" |"),
            "voting_status": "FALSE",
            "part_no": booth_no,
            "vidh_no": ac_no
        })

    return out1_rows, out2_rows


def process_telugu_roll(
    pdf_path: str,
    output1_dir: str = "output1",
    output2_dir: str = "output2"
):
    """
    Processes a Telugu electoral roll PDF and exports results to CSV and JSON.
    """
    base_name = Path(pdf_path).stem
    meta, records = extract_telugu_pdf_records(pdf_path)
    out1_rows, out2_rows = build_output_datasets(meta, records)

    os.makedirs(output1_dir, exist_ok=True)
    os.makedirs(output2_dir, exist_ok=True)

    out1_csv = os.path.join(output1_dir, f"{base_name}_voters.csv")
    out2_csv = os.path.join(output2_dir, f"{base_name}_standardized.csv")
    out1_json = os.path.join(output1_dir, f"{base_name}_voters.json")

    # Output1 fieldnames
    out1_fieldnames = [
        'sr_no',
        'ward_voter_sr_no',
        'assembly_voter_info',
        'elector_name',
        'relative_type',
        'relative_name',
        'age',
        'gender',
        'house_no',
        'epic_no',
        'photo_status',
        'ward_no',
        'booth_no',
        'booth_name',
        'ac_name',
        'district'
    ]

    # Output2 fieldnames (Standardized 32 columns)
    out2_fieldnames = [
        "Sr.No.",
        "org_code",
        "matadar_sangh_code",
        "booth_id",
        "voter_ser_no",
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
        "part_no",
        "vidh_no"
    ]

    # Save Output 1 CSV (utf-8-sig for Excel compatibility with Telugu)
    with open(out1_csv, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=out1_fieldnames)
        writer.writeheader()
        writer.writerows(out1_rows)
    print(f"\n[✓] Exported {len(out1_rows)} records to: {out1_csv}")

    # Save Output 2 CSV (Standardized Schema)
    with open(out2_csv, mode='w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=out2_fieldnames)
        writer.writeheader()
        writer.writerows(out2_rows)
    print(f"[✓] Exported {len(out2_rows)} records to: {out2_csv}")

    # Save Output 1 JSON
    with open(out1_json, mode='w', encoding='utf-8') as f:
        json.dump({
            'metadata': meta,
            'total_records': len(records),
            'records': out1_rows
        }, f, ensure_ascii=False, indent=2)
    print(f"[✓] Exported JSON data to: {out1_json}")

    return out1_rows, out2_rows


if __name__ == '__main__':
    base_dir = Path(__file__).resolve().parent
    default_pdf = base_dir / "48-10.pdf"

    pdf_to_process = sys.argv[1] if len(sys.argv) > 1 else str(default_pdf)

    out1_dir = base_dir / "output1"
    out2_dir = base_dir / "output2"

    print(f"=== Starting Telugu Electoral Roll Extraction: {pdf_to_process} ===")
    out1, out2 = process_telugu_roll(
        pdf_path=pdf_to_process,
        output1_dir=str(out1_dir),
        output2_dir=str(out2_dir)
    )
    print(f"\n[✓] Done! Extracted {len(out1)} total records successfully.")
