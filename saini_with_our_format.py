#!/usr/bin/env python3
"""
Saini Shiksha Samiti Alwar - Electoral Roll Data Extractor
Extracts structured member data from the Saini Shiksha Samiti Alwar PDF
(Old and New Members list) encoded in DevLys-010 / Kruti Dev.

Outputs:
1. output3/saini_members.csv: Clean structured CSV (sr_no, member_name, relative_name, address, mobile_no, member_type)
2. output3/voters_extracted.csv: 32-column standardized schema matching extract_voters.py
3. output3/saini_members.json: JSON dump of all records
"""

import os
import sys
import csv
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


# ==========================================
# DevLys-010 / Kruti Dev to Unicode Mapping
# ==========================================

ARRAY_ONE = [
    'ñ', 'Q+Z', 'sas', 'aa', ')Z', 'ZZ', '‘', '’', '“', '”',
    'å', 'ƒ', '„', '…', '†', '‡', 'ˆ', '‰', 'Š', '‹',
    '¶+', 'd+', '[+k', '[+', 'x+', 'T+', 't+', 'M+', '<+', 'Q+', ';+', 'j+', 'u+',
    'Ùk', 'Ù', 'Dr', '–', 'é', '™', '=kk', 'f=k',
    'à', 'á', 'â', 'ã', 'ºz', 'º', 'í', '{k', '{', '=', '«',
    'Nî', 'Vî', 'Bî', 'Mî', '<î', '|', 'K', '}',
    'J', 'Vª', 'Mª', '<ªª', 'Nª', 'Ø', 'Ý', 'nzZ', 'æ', 'ç', 'Á', 'xz', '#', ':',
    'v‚', 'vks', 'vkS', 'vk', 'v', 'b±', 'Ã', 'bZ', 'b', 'm', 'Å', ',s', ',', '_',
    'ô', 'd', 'Dk', 'D', '[k', '[', 'x', 'Xk', 'X', 'Ä', '?k', '?', '³',
    'pkS', 'p', 'Pk', 'P', 'N', 't', 'Tk', 'T', '>', '÷', '¥',
    'ê', 'ë', 'V', 'B', 'ì', 'ï', 'M+', '<+', 'M', '<', '.k', '.',
    'r', 'Rk', 'R', 'Fk', 'F', ')', 'n', '/k', 'èk', '/', 'Ë', 'è', 'u', 'Uk', 'U',
    'i', 'Ik', 'I', 'Q', '¶', 'c', 'Ck', 'C', 'Hk', 'H', 'e', 'Ek', 'E',
    ';', '¸', 'j', 'y', 'Yk', 'Y', 'G', 'o', 'Ok', 'O',
    '\'k', '\'', '\"k', '\"', 'l', 'Lk', 'L', 'g',
    'È', 'z',
    'Ì', 'Í', 'Î', 'Ï', 'Ñ', 'Ò', 'Ó', 'Ô', 'Ö',
    '‚', 'ks', 'kS', 'k', 'h', 'q', 'w', '`', 's', 'S',
    'a', '¡', '%', 'W', '•', '·', '∙', '~j', '~', '\\', '+',
    '^', '*', 'Þ', 'ß', '¼', '½', '¿', 'À', '¾', 'A', '-', '&', 'Œ', ']', '@'
]

ARRAY_TWO = [
    '॰', 'QZ+', 'sa', 'a', 'र्द्ध', 'Z', '"', '"', '\'', '\'',
    '०', '१', '२', '३', '४', '५', '६', '७', '८', '९',
    'फ़्', 'क़', 'ख़', 'ख़्', 'ग़', 'ज़्', 'ज़', 'ड़', 'ढ़', 'फ़', 'य़', 'ऱ', 'ऩ',
    'त्त', 'त्त्', 'क्त', 'दृ', 'न्न', 'न्न्', '=k', 'f=',
    'ह्न', 'ह्य', 'हृ', 'ह्म', 'ह्र', 'ह्', 'द्द', 'क्ष', 'क्ष्', 'त्र', 'त्र्',
    'छ्य', 'ट्य', 'ठ्य', 'ड्य', 'ढ्य', 'द्य', 'ज्ञ', 'द्व',
    'श्र', 'ट्र', 'ड्र', 'ढ्र', 'छ्र', 'क्र', 'फ्र', 'र्द्र', 'द्र', 'प्र', 'प्र', 'ग्र', 'रु', 'रू',
    'ऑ', 'ओ', 'औ', 'आ', 'अ', 'ईं', 'ई', 'ई', 'इ', 'उ', 'ऊ', 'ऐ', 'ए', 'ऋ',
    'क्क', 'क', 'क', 'क्', 'ख', 'ख्', 'ग', 'ग', 'ग्', 'घ', 'घ', 'घ्', 'ङ',
    'चै', 'च', 'च', 'च्', 'छ', 'ज', 'ज', 'ज्', 'झ', 'झ्', 'ञ',
    'ट्ट', 'ट्ठ', 'ट', 'ठ', 'ड्ड', 'ड्ढ', 'ड़', 'ढ़', 'ड', 'ढ', 'ण', 'ण्',
    'त', 'त', 'त्', 'थ', 'थ्', 'द्ध', 'द', 'ध', 'ध', 'ध्', 'ध्', 'ध', 'न', 'न', 'न्',
    'प', 'प', 'प्', 'फ', 'फ्', 'ब', 'ब', 'ब्', 'भ', 'भ्', 'म', 'म', 'म्',
    'य', 'य्', 'र', 'ल', 'ल', 'ल्', 'ळ', 'व', 'व', 'व्',
    'श', 'श्', 'ष', 'ष्', 'स', 'स', 'स्', 'ह',
    'ीं', '्र',
    'द्द', 'ट्ट', 'ट्ठ', 'ड्ड', 'भ', '्य', 'ड्ढ', 'झ्', 'क्र',
    'ॉ', 'ो', 'ौ', 'ा', 'ी', 'ु', 'ू', 'ृ', 'े', 'ै',
    'ं', 'ँ', 'ः', 'ॅ', 'ऽ', 'ऽ', 'ऽ', '्र', '्', '?', '़',
    '‘', '’', '“', '”', '(', ')', '{', '}', '=', '।', '-', '-', '॰', ',', '/'
]

HALF_CHARS = set(['D', '[', 'X', '?', 'P', 'T', 'R', 'F', 'U', 'I', 'C', 'H', 'E', 'Y', 'O', 'L'])
TWO_CHAR_CONSONANTS = set(['[k', '?k', '.k', 'Fk', '/k', 'Hk', '\'k', '\"k', '{k'])


def fix_chhoti_i(text: str) -> str:
    """
    In Kruti Dev / DevLys-010, the short-i matra ('f') is typed before the consonant cluster.
    This repositions 'f' after the full base consonant syllable so it maps to logically ordered 'ि'.
    """
    res = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == 'f':
            j = i + 1
            # Skip any half consonants
            while j < n and text[j] in HALF_CHARS and (j + 1 < n and text[j:j+2] not in TWO_CHAR_CONSONANTS):
                j += 1
            if j < n:
                if j + 1 < n and text[j:j+2] in TWO_CHAR_CONSONANTS:
                    j += 2
                else:
                    j += 1
            res.append(text[i+1:j] + 'ि')
            i = j
        else:
            res.append(text[i])
            i += 1
    return ''.join(res)


def kruti_to_unicode(text: str) -> str:
    """
    Converts DevLys-010 / Kruti Dev encoded string to standard Unicode Devanagari.
    """
    if not text:
        return ""

    modified = text

    # Pre-substitutions for common compound symbols
    modified = modified.replace('Ê', 'hZ')        # e.g., QuÊpj -> फर्नीचर
    modified = modified.replace('—', 'd`')        # e.g., —".k -> कृष्ण
    modified = modified.replace('czãpk', 'czãpk')
    modified = modified.replace('vfiZr', 'vfZir')  # अर्पित
    modified = modified.replace('±', 'Zk')
    modified = modified.replace('Ø-l-', 'क्र.स.')

    # Reorder 'f' (chhoti-i)
    modified = fix_chhoti_i(modified)

    # Reorder 'Z' (reph / rafar): moves 'j~' before the base syllable
    modified = "  " + modified + "  "
    set_of_matras = ["‚", "ks", "kS", "k", "h", "q", "w", "`", "s", "S", "a", "¡", "%", "W", "•", "·", "∙", "~j", "~", "ि"]
    position_of_r = modified.find("Z")
    while position_of_r != -1:
        modified = modified[:position_of_r] + modified[position_of_r+1:]
        # Find preceding character to place 'j~' (र्) before it
        pos = position_of_r - 1
        while pos > 0 and modified[pos] in set_of_matras:
            pos -= 1
        # If preceding char is part of two_char_consonant like 'k in 'k
        if pos > 0 and modified[pos] == 'k' and modified[pos-1] in ("'", '"', '[', '?', '.', 'F', '/', 'H', '{'):
            pos -= 1
        # If preceding is a half character, keep moving back
        while pos > 0 and modified[pos-1] in HALF_CHARS:
            pos -= 1

        modified = modified[:pos] + "j~" + modified[pos:]
        position_of_r = modified.find("Z", position_of_r + 2)

    modified = modified.strip()

    # Glyph mapping replacement
    for src, dst in zip(ARRAY_ONE, ARRAY_TWO):
        modified = modified.replace(src, dst)

    # Clean up any leftover artifacts
    modified = modified.replace('  ', ' ')
    modified = re.sub(r'\s+,', ',', modified)
    modified = re.sub(r',\s*', ', ', modified)
    return modified.strip()


# ==========================================
# Extraction & Table Parser
# ==========================================

def extract_house_no(address: str) -> str:
    """Extracts house/plot number from address if present."""
    if not address:
        return ""
    first_part = address.split(',')[0].strip()
    m = re.match(r'^(?:म\.\s*नं\.?|म\s*नं\.?|प्लॉट\s*नं\.?|हाउस\s*नं\.?|एच\.\s*नं\.?|बी\.\s*नं\.?|H\s*N|Plot\s*No)?\s*([0-9]+[A-Za-z0-9\/\-]*)', first_part, re.I)
    if m:
        return m.group(1).strip()
    return ""


def detect_gender(name: str, relative_name: str) -> str:
    """Infers gender from member name and relative indicators."""
    female_indicators = [
        'देवी', 'कुमारी', 'रानी', 'कांता', 'रेखा', 'अनिता', 'कविता', 'सुनीता',
        'मंजू', 'पूजा', 'शकुन्तला', 'शीला', 'कमला', 'विमला', 'उर्मिला', 'आशा',
        'पिंकी', 'सरोज', 'आरती', 'संगीता', 'मोनिका', 'सुमन', 'हेमलता', 'प्रियंका',
        'प्रतिभा', 'किरण', 'मीना', 'रीता', 'नीतू', 'ललिता', 'ममता', 'गायत्री',
        'स्वाती', 'भारती', 'अल्पना', 'अंजू', 'रूकमणी', 'लक्ष्मी', 'पार्वती'
    ]
    for ind in female_indicators:
        if ind in name:
            return 'F'
    male_indicators = [
        'कुमार', 'लाल', 'सिंह', 'राम', 'प्रसाद', 'चन्द', 'पाल', 'नाथ', 'प्रकाश',
        'मोहन', 'किशोर', 'दत्त', 'देव', 'नारायण', 'शंकर', 'स्वरूप', 'भूपेन्द्र',
        'जितेन्द्र', 'सुरेन्द्र', 'योगेश', 'नरेश', 'दिनेश', 'राजेश', 'महेश', 'अशोक',
        'अमित', 'सुनील', 'अनिल', 'संजय', 'दीपक', 'पवन', 'प्रवीण', 'संदीप', 'राकेश'
    ]
    for ind in male_indicators:
        if ind in name:
            return 'M'
    return ""


def extract_saini_records(pdf_path: str):
    """
    Extracts all voter/member rows from the Saini Shiksha Samiti PDF.
    Returns list of parsed records.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found at: {pdf_path}")

    proc = subprocess.Popen(
        ['pdftotext', '-bbox-layout', pdf_path, '-'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {stderr.decode('utf-8', errors='ignore')}")

    root = ET.fromstring(stdout)
    ns = {'x': 'http://www.w3.org/1999/xhtml'}

    all_records = []

    for page_idx, page in enumerate(root.findall('.//x:page', ns), 1):
        words = []
        for w in page.findall('.//x:word', ns):
            text = (w.text or '').strip()
            if not text:
                continue
            xmin = float(w.attrib['xMin'])
            ymin = float(w.attrib['yMin'])
            words.append((xmin, ymin, text))

        # Check if page is in New Members section (page 102 to 125)
        has_mobile_col = (page_idx >= 102)

        # Header boundary: pages 1 & 102 have header blocks above y=128
        y_min_content = 128.0 if page_idx in (1, 102) else 40.0
        y_max_content = 745.0  # footer page number is at y > 750

        # Anchor words: Serial numbers in Column 0 (x between 25 and 58)
        sr_words = [
            w for w in words
            if 25.0 <= w[0] <= 58.0 and y_min_content <= w[1] <= y_max_content and w[2].isdigit()
        ]
        sr_words.sort(key=lambda item: item[1])

        if not sr_words:
            continue

        for idx, (sx, sy, sr_str) in enumerate(sr_words):
            sr_no = int(sr_str)

            # Midpoint row segmentation
            top_y = (sr_words[idx - 1][1] + sy) / 2.0 if idx > 0 else max(sy - 20.0, y_min_content)
            bot_y = (sy + sr_words[idx + 1][1]) / 2.0 if idx < len(sr_words) - 1 else min(sy + 25.0, y_max_content)

            # Collect words belonging to this row
            row_words = [w for w in words if top_y <= w[1] < bot_y and w[0] >= 58.0]

            # Columns separation:
            # Col 1: Member Name (58 to 185)
            # Col 2: Relative Name (185 to 288)
            # Col 3: Address (288 to 480 if mobile, else 288 to 585)
            # Col 4: Mobile Number (>= 480 if mobile)
            col1_words = [w for w in row_words if 58.0 <= w[0] < 185.0]
            col2_words = [w for w in row_words if 185.0 <= w[0] < 288.0]

            if has_mobile_col:
                col3_words = [w for w in row_words if 288.0 <= w[0] < 480.0]
                col4_words = [w for w in row_words if w[0] >= 480.0]
            else:
                col3_words = [w for w in row_words if w[0] >= 288.0]
                col4_words = []

            def join_words(w_list):
                # Sort primarily by vertical line (5pt grid) then horizontal x
                s = sorted(w_list, key=lambda it: (round(it[1] / 5.0), it[0]))
                return ' '.join(it[2] for it in s).strip()

            raw_name = join_words(col1_words)
            raw_rel = join_words(col2_words)
            raw_addr = join_words(col3_words)
            raw_mob = join_words(col4_words)

            # Decode Kruti Dev to Unicode
            name_hi = kruti_to_unicode(raw_name)
            rel_hi = kruti_to_unicode(raw_rel)
            addr_hi = kruti_to_unicode(raw_addr)

            # Clean mobile: extract 10-digit number
            mob_clean = re.sub(r'[^0-9]', '', raw_mob)
            if len(mob_clean) > 10:
                mob_clean = mob_clean[:10]

            member_type = "नवीन मतदाता" if has_mobile_col else "सामान्य मतदाता"

            all_records.append({
                'sr_no': sr_no,
                'member_name': name_hi,
                'relative_name': rel_hi,
                'address': addr_hi,
                'mobile_no': mob_clean,
                'member_type': member_type,
                'page_no': page_idx
            })

    return all_records


def build_output_rows(records):
    """
    Constructs both clean schema rows and 32-column standardized schema rows.
    """
    clean_rows = []
    std_rows = []

    for r in records:
        sr = r['sr_no']
        name_hi = r['member_name']
        rel_hi = r['relative_name']
        addr_hi = r['address']
        mob = r['mobile_no']
        m_type = r['member_type']

        gender = detect_gender(name_hi, rel_hi)
        house_no = extract_house_no(addr_hi)

        clean_rows.append({
            'sr_no': sr,
            'member_name': name_hi,
            'relative_name': rel_hi,
            'address': addr_hi,
            'mobile_no': mob,
            'member_type': m_type,
            'gender': gender,
            'district': 'अलवर',
            'society': 'सैनी शिक्षा समिति, अलवर'
        })

        # Standard 32-column schema identical to extract_voters.py
        comment_val = f"पिता/पति: {rel_hi}" if rel_hi else ""
        std_rows.append({
            "Sr.No.": sr,
            "org_code": "EITOT",
            "matadar_sangh_code": "",
            "booth_id": "ALWAR",
            "voter_ser_no": sr,
            "glob_deleted": "0",
            "glob_duplicate": "0",
            "full_name": name_hi,
            "e_full_name": "",
            "age": "",
            "gender": gender,
            "house_no": house_no,
            "voter_id": "",
            "voter_address1": addr_hi,
            "evoter_address1": "",
            "booth_address": "सैनी शिक्षा समिति, अलवर",
            "e_booth_address": "",
            "e_booth_name": "",
            "booth_name": "सैनी शिक्षा समिति",
            "voter_is_alive": "True",
            "mobile_no": mob,
            "optional_contact": "",
            "type": m_type,
            "imp_voter": "",
            "voter_cast_religion": "सैनी",
            "voter_address2": "",
            "influence": "",
            "voter_profession": "",
            "comment": comment_val,
            "voting_status": "FALSE",
            "part_no": "ALWAR_SAINI_2026",
            "vidh_no": ""
        })

    return clean_rows, std_rows


def process_saini_electoral_roll(
    pdf_path: str,
    output_dir: str = "output3"
):
    """
    Main extraction pipeline for Saini Shiksha Samiti PDF.
    Exports clean CSV, standardized 32-column CSV, and JSON to output_dir.
    """
    print(f"[*] Processing Saini Electoral Roll: {pdf_path}")
    os.makedirs(output_dir, exist_ok=True)

    records = extract_saini_records(pdf_path)
    print(f"[✓] Extracted total {len(records)} voter records.")

    clean_rows, std_rows = build_output_rows(records)

    # 1. Clean schema CSV
    clean_csv = os.path.join(output_dir, "saini_members.csv")
    clean_fieldnames = [
        'sr_no', 'member_name', 'relative_name', 'address',
        'mobile_no', 'member_type', 'gender', 'district', 'society'
    ]
    with open(clean_csv, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=clean_fieldnames)
        writer.writeheader()
        writer.writerows(clean_rows)
    print(f"[✓] Saved clean members CSV: {clean_csv}")

    # 2. Standard 32-column CSV matching extract_voters.py
    std_csv = os.path.join(output_dir, "voters_extracted.csv")
    std_fieldnames = [
        "Sr.No.", "org_code", "matadar_sangh_code", "booth_id", "voter_ser_no",
        "glob_deleted", "glob_duplicate", "full_name", "e_full_name", "age",
        "gender", "house_no", "voter_id", "voter_address1", "evoter_address1",
        "booth_address", "e_booth_address", "e_booth_name", "booth_name",
        "voter_is_alive", "mobile_no", "optional_contact", "type", "imp_voter",
        "voter_cast_religion", "voter_address2", "influence", "voter_profession",
        "comment", "voting_status", "part_no", "vidh_no"
    ]
    with open(std_csv, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=std_fieldnames)
        writer.writeheader()
        writer.writerows(std_rows)
    print(f"[✓] Saved standardized 32-column CSV: {std_csv}")

    # 3. JSON Export
    json_path = os.path.join(output_dir, "saini_members.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(clean_rows, f, ensure_ascii=False, indent=2)
    print(f"[✓] Saved JSON records: {json_path}")

    # Summary
    mob_count = sum(1 for r in clean_rows if r['mobile_no'])
    print(f"\n[Summary]")
    print(f"- Total Members: {len(clean_rows)}")
    print(f"- Regular Members (1-1896): {sum(1 for r in clean_rows if r['sr_no'] < 1897)}")
    print(f"- New Members (1897-2347): {sum(1 for r in clean_rows if r['sr_no'] >= 1897)}")
    print(f"- Members with Mobile: {mob_count}")

    return clean_rows


if __name__ == '__main__':
    base_dir = Path(__file__).resolve().parent
    default_pdf = base_dir / "Saini Shiksha Samiti Alwar  List 07-10-2026 A to Z (OLD & New  MEMBER).pdf"
    default_out = base_dir / "output3"

    pdf_file = sys.argv[1] if len(sys.argv) > 1 else str(default_pdf)
    out_dir = sys.argv[2] if len(sys.argv) > 2 else str(default_out)

    process_saini_electoral_roll(pdf_path=pdf_file, output_dir=out_dir)
