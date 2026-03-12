"""Text processing utilities: CID character fixing, Hebrew RTL reversal."""
import re
import logging
from typing import Optional

logger = logging.getLogger("case-ims.text-processors")


# --- CID character fix for broken PDF font encoding ---

_CID_RE = re.compile(r'(?:\(cid:(\d+)\)|\)cid:(\d+)\()')

_SOFIT_LETTERS = ['\u05da', '\u05dd', '\u05df', '\u05e3', '\u05e5']  # ך ם ן ף ץ


def _fix_cid_characters(text: str) -> str:
    if 'cid:' not in text:
        return text

    raw_matches = _CID_RE.findall(text)
    cid_values = set()
    for g1, g2 in raw_matches:
        cid_values.add(g1 or g2)
    cid_values.discard('')

    if not cid_values:
        return text

    cid_map = {}
    for cid_num in cid_values:
        pattern = re.compile(
            r'(.{0,6})(?:\(cid:' + cid_num + r'\)|\)cid:' + cid_num + r'\()(.{0,6})'
        )
        contexts = pattern.findall(text)

        hebrew_contexts = []
        has_hebrew = False
        for before, after in contexts:
            before_stripped = before.rstrip()
            if before_stripped and '\u0590' <= before_stripped[-1] <= '\u05ff':
                hebrew_contexts.append((before, after))
                has_hebrew = True

        if has_hebrew:
            cid_map[cid_num] = _guess_sofit_from_context(cid_num, hebrew_contexts)
        else:
            cid_map[cid_num] = ''

    def _replace_cid(m):
        num = m.group(1) or m.group(2)
        start = m.start()
        end = m.end()
        before_text = text[max(0, start - 3):start].rstrip()
        after_text = text[end:end + 3].lstrip()
        if before_text and before_text[-1].isdigit() and after_text and after_text[0].isdigit():
            return '-'
        if not before_text.strip() and not after_text.strip():
            return cid_map.get(num, '')
        return cid_map.get(num, '')

    return _CID_RE.sub(_replace_cid, text)


def _guess_sofit_from_context(cid_num: str, contexts: list) -> str:
    preceding_letters = {}
    for before, _after in contexts:
        before_stripped = before.rstrip()
        if not before_stripped:
            continue
        last_ch = before_stripped[-1]
        if '\u0590' <= last_ch <= '\u05ff':
            preceding_letters[last_ch] = preceding_letters.get(last_ch, 0) + 1

    if not preceding_letters:
        return '\u05dd'  # default: mem sofit

    scores = {'\u05da': 0, '\u05dd': 0, '\u05df': 0, '\u05e3': 0, '\u05e5': 0}

    # Simple heuristic scoring
    scores['\u05da'] += preceding_letters.get('\u05db', 0) * 8  # כ → ך
    scores['\u05e3'] += preceding_letters.get('\u05e1', 0) * 8  # ס → ף
    scores['\u05e3'] += preceding_letters.get('\u05e8', 0) * 3  # ר → ף
    scores['\u05dd'] += preceding_letters.get('\u05e9', 0) * 4  # ש → ם
    scores['\u05dd'] += preceding_letters.get('\u05d2', 0) * 6  # ג → ם
    scores['\u05df'] += preceding_letters.get('\u05de', 0) * 5  # מ → ן

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return '\u05dd'
    return best


# --- RTL reversal fix ---

_REVERSED_HEBREW_MARKERS = [
    "\u05ea\u05d9\u05d1",
    "\u05d8\u05e4\u05e9\u05de",
    "\u05df\u05d9\u05d3",
    "\u05e7\u05d5\u05d7",
]

_MIN_REVERSED_MARKERS = 2


def _is_reversed_hebrew(text: str) -> bool:
    sample = text[:2000]
    hits = sum(1 for marker in _REVERSED_HEBREW_MARKERS if marker in sample)
    return hits >= _MIN_REVERSED_MARKERS


def _fix_reversed_line(line: str) -> str:
    _HEBREW_RANGE = range(0x0590, 0x0600)

    def _is_hebrew_char(ch):
        return ord(ch) in _HEBREW_RANGE

    def _is_ltr_char(ch):
        return ch.isdigit() or (ch.isascii() and ch.isalpha()) or ch in "/-:.,%"

    segments = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == ' ':
            segments.append((' ', 'SPACE'))
            i += 1
        elif _is_hebrew_char(ch):
            start = i
            while i < len(line) and _is_hebrew_char(line[i]):
                i += 1
            segments.append((line[start:i], 'HEBREW'))
        elif _is_ltr_char(ch):
            start = i
            while i < len(line) and _is_ltr_char(line[i]):
                i += 1
            segments.append((line[start:i], 'LTR'))
        else:
            segments.append((ch, 'HEBREW'))
            i += 1

    segments.reverse()
    parts = []
    for text_seg, seg_type in segments:
        if seg_type == 'HEBREW':
            parts.append(text_seg[::-1])
        else:
            parts.append(text_seg)
    return ''.join(parts)


def _fix_reversed_hebrew(text: str) -> str:
    _HEBREW_RANGE = range(0x0590, 0x0600)

    def _has_hebrew(s):
        return any(ord(ch) in _HEBREW_RANGE for ch in s)

    lines = text.split("\n")
    fixed = []
    for line in lines:
        stripped = line.rstrip()
        if not stripped:
            fixed.append("")
            continue
        if _has_hebrew(stripped):
            fixed.append(_fix_reversed_line(stripped))
        else:
            fixed.append(stripped)
    return "\n".join(fixed)
