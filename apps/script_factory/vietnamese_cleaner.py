"""Vietnamese Language Cleaner and Linter for TTS Audio Narration.

Prevents and cleans garbled text, English numbers preceding Vietnamese units,
stray consonants from OCR/LLM generation, stuttered syllable endings, and common
garbled audio typos before TTS synthesis and QC audits.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# English to Vietnamese number translation map
_UNIT_MAP = {
    "one": "một", "two": "hai", "three": "ba", "four": "bốn", "five": "năm",
    "six": "sáu", "seven": "bảy", "eight": "tám", "nine": "chín", "ten": "mười",
    "eleven": "mười một", "twelve": "mười hai", "thirteen": "mười ba", "fourteen": "mười bốn",
    "fifteen": "mười lăm", "sixteen": "mười sáu", "seventeen": "mười bảy", "eighteen": "mười tám",
    "nineteen": "mười chín", "twenty": "hai mươi", "thirty": "ba mươi", "forty": "bốn mươi",
    "fifty": "năm mươi", "sixty": "sáu mươi", "seventy": "bảy mươi", "eighty": "tám mươi",
    "ninety": "chín mươi",
}

_DIGIT_MAP = {
    "one": "mốt", "two": "hai", "three": "ba", "four": "bốn", "five": "lăm",
    "six": "sáu", "seven": "bảy", "eight": "tám", "nine": "chín",
}

# Recognized valid uppercase acronyms and loan words
VALID_ACRONYMS = {
    "CEO", "Wi-Fi", "Wi-fi", "WiFi", "wifi", "VIP", "QR", "MC", "USB",
    "TV", "SIM", "GPS", "OK", "DNA", "AI", "UBND", "TP", "TP.", "VNĐ", "VND", "USD"
}

_GARBLED_PHRASES = [
    (re.compile(r"\bchợ\s+khựng\b", re.IGNORECASE), "chợt khựng"),
    (re.compile(r"\b(?:điếu\s+thuốc\s+)?tút\s+dở\b", re.IGNORECASE), lambda m: m.group(0).replace("tút dở", "hút dở").replace("Tút dở", "Hút dở")),
    (re.compile(r"\blãng\s+đảng\b", re.IGNORECASE), "lãng đãng"),
]


def _replace_english_number(match: re.Match) -> str:
    tens = match.group(1).lower()
    ones = match.group(2)
    unit = match.group(3)
    
    if ones:
        ones = ones.lower()
        t_viet = _UNIT_MAP.get(tens, tens)
        o_viet = _DIGIT_MAP.get(ones, ones)
        if tens == "twenty":
            viet_num = f"hai mươi {o_viet}"
        else:
            viet_num = f"{t_viet} {o_viet}"
    else:
        viet_num = _UNIT_MAP.get(tens, tens)
        
    return f"{viet_num} {unit}"


def clean_garbled_vietnamese(text: str) -> str:
    """Deterministically clean garbled tokens, English numbers, and typos."""
    if not text:
        return text

    # 1. English numbers before Vietnamese units
    en_num_pattern = re.compile(
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
        r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
        r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](one|two|three|four|five|six|seven|eight|nine))?\s+"
        r"(tuổi|năm|tháng|ngày|giờ|phút|giây|triệu|tỷ|đồng|căn|người|phần)\b",
        re.IGNORECASE,
    )
    cleaned = en_num_pattern.sub(_replace_english_number, text)

    # 2. Syllable stuttering / duplicated phonemes (e.g., xoayay -> xoay, layay -> lay)
    cleaned = re.sub(r"\b([a-zA-Záàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ]+?)(ay)ay\b", r"\1\2", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b([a-zA-Záàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ]+?)(ai)ai\b", r"\1\2", cleaned, flags=re.IGNORECASE)

    # 3. Known typo expressions
    for pattern, replacement in _GARBLED_PHRASES:
        cleaned = pattern.sub(replacement, cleaned)

    # 4. Stray lowercase single consonants (e.g. 'những bí mật r âm ỉ' -> 'những bí mật âm ỉ')
    # Must not match numbers like '10 m', or uppercase letters like 'A', or loanwords.
    cleaned = re.sub(r"(?<![\d\w])([bcdfghjklmnpqrstvwxz])\s+([a-záàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ])", r"\2", cleaned)

    # Clean double spaces
    cleaned = re.sub(r"[ ]{2,}", " ", cleaned)
    return cleaned.strip()


def find_garbled_vietnamese_issues(text: str) -> List[Dict[str, str]]:
    """Scan text and return detected garbled Vietnamese patterns."""
    issues = []
    if not text:
        return issues

    # 1. English numbers before Vietnamese units
    en_num_pattern = re.compile(
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
        r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
        r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](one|two|three|four|five|six|seven|eight|nine))?\s+"
        r"(tuổi|năm|tháng|ngày|giờ|phút|giây|triệu|tỷ|đồng|căn|người|phần)\b",
        re.IGNORECASE,
    )
    for m in en_num_pattern.finditer(text):
        issues.append({
            "type": "GARBLED_VIETNAMESE",
            "matched": m.group(0),
            "reason": f"Sử dụng từ đếm tiếng Anh ('{m.group(0)}') trước danh từ chỉ đơn vị tiếng Việt.",
        })

    # 2. Stray single consonants
    stray_pattern = re.compile(r"(?<![\d\w])([bcdfghjklmnpqrstvwxz])\s+([a-záàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ])")
    for m in stray_pattern.finditer(text):
        issues.append({
            "type": "GARBLED_VIETNAMESE",
            "matched": m.group(0),
            "reason": f"Phụ âm đơn đứng lẻ bất thường ('{m.group(1)}') trong câu tiếng Việt.",
        })

    # 3. Syllable stuttering
    stutter_pattern = re.compile(r"\b([a-zA-Záàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ]+?)(ayay|aiai)\b", re.IGNORECASE)
    for m in stutter_pattern.finditer(text):
        issues.append({
            "type": "GARBLED_VIETNAMESE",
            "matched": m.group(0),
            "reason": f"Từ bị lặp âm tiết/lỗi gõ ('{m.group(0)}').",
        })

    # 4. Known typo expressions
    for pattern, _ in _GARBLED_PHRASES:
        for m in pattern.finditer(text):
            issues.append({
                "type": "GARBLED_VIETNAMESE",
                "matched": m.group(0),
                "reason": f"Từ sai chính tả trong ngữ cảnh audio ('{m.group(0)}').",
            })

    return issues


def num_to_vietnamese_words(n: int) -> List[str]:
    """Converts a number (1-2099) to possible Vietnamese spoken word representations."""
    units = {0: '', 1: 'một', 2: 'hai', 3: 'ba', 4: 'bốn', 5: 'năm', 6: 'sáu', 7: 'bảy', 8: 'tám', 9: 'chín'}
    if n < 0:
        return [str(n)]
    if n < 10:
        return [units[n]] if units[n] else ['không']
    if n < 100:
        ten, unit = divmod(n, 10)
        t_str = 'mười' if ten == 1 else f'{units[ten]} mươi'
        if unit == 0:
            return [t_str]
        elif unit == 1:
            u_str = 'mốt' if ten > 1 else 'một'
        elif unit == 4:
            return [f'{t_str} bốn', f'{t_str} tư']
        elif unit == 5:
            u_str = 'lăm'
        else:
            u_str = units[unit]
        return [f'{t_str} {u_str}']
    if 1000 <= n <= 2099:
        th, rem = divmod(n, 1000)
        h, rem2 = divmod(rem, 100)
        th_word = 'một nghìn' if n < 2000 else 'hai nghìn'
        h_word = f'{units[h]} trăm' if h > 0 else 'không trăm'
        res = []
        if rem == 0:
            res.append(f'{th_word}')
        elif rem2 == 0:
            res.append(f'{th_word} {h_word}')
        elif rem2 < 10:
            res.append(f'{th_word} {h_word} linh {units[rem2]}')
            res.append(f'{th_word} {h_word} lẻ {units[rem2]}')
        else:
            for tw in num_to_vietnamese_words(rem2):
                res.append(f'{th_word} {h_word} {tw}')
                if h == 0 and n >= 2000:
                    res.append(f'{th_word} {tw}')
        return res
    return [str(n)]


def year_to_vietnamese_words(year_str: str) -> List[str]:
    """Returns spoken Vietnamese representations for a 4-digit calendar year."""
    try:
        yr = int(year_str)
        return [year_str, *num_to_vietnamese_words(yr)]
    except (ValueError, TypeError):
        return [year_str]

