"""Conservative, clause-scoped extraction for dates and named event participants.

Ambiguous prose is left to semantic review; a keyword in an unrelated clause
must never become an instruction to change a locked date.
"""
from functools import lru_cache
import re
import unicodedata

from apps.script_factory.vietnamese_cleaner import year_to_vietnamese_words, num_to_vietnamese_words


EVENTS = {
    'hiến thận': ('hiến thận', 'hiến tạng', 'hiến một phần cơ thể'),
    'ghép thận': ('ghép thận',),
    'chia tay': ('chia tay', 'chấm dứt quan hệ', 'ly hôn'),
    'kết hôn': ('kết hôn', 'đám cưới', 'lễ cưới'),
    'tuyển dụng': ('tuyển dụng', 'nhận vào làm', 'vào làm việc'),
    'mở di chúc': ('mở di chúc', 'mở bức di chúc', 'mở bản di chúc'),
    'tiêu hủy di chúc': ('tiêu hủy di chúc', 'hủy bản di chúc', 'đốt di chúc'),
    'lâm bệnh': ('lâm bệnh', 'mắc bệnh nặng', 'suy thận'),
}


def normalized(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', str(text)).casefold()).strip()


@lru_cache(maxsize=1)
def _spoken_years():
    variants = {}
    for year in range(1900, 2100):
        for phrase in year_to_vietnamese_words(str(year))[1:]:
            variants[phrase] = year
            variants[phrase.replace('nghìn', 'ngàn')] = year
    pattern = re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(p) for p in sorted(variants, key=len, reverse=True)) + r')(?!\w)')
    return pattern, variants


def year_mentions(text):
    text = normalized(text)
    pattern, variants = _spoken_years()
    mentions = [(m.start(), m.end(), int(m.group())) for m in re.finditer(r'\b(?:19|20)\d{2}\b', text)]
    mentions.extend((m.start(), m.end(), variants[m.group()]) for m in pattern.finditer(text))
    return sorted(mentions)


def clauses(text):
    # Keep commas: dates and an event's subject often straddle a comma.
    return [c.strip() for c in re.split(r'[.!?;]\s*', normalized(text)) if c.strip()]


def character_aliases(bible):
    names = []
    for ch in [bible.protagonist, *(bible.supporting_characters or [])]:
        if isinstance(ch, dict) and ch.get('name'):
            names.append(normalized(ch['name']))
    # Timeline fixtures and imported stories need not have a complete cast yet.
    for entry in bible.timeline or []:
        body = str(entry).split(':', 1)[-1].strip()
        match = re.match(r'([A-ZĐ][\w]*(?:\s+[A-ZĐ][\w]*)*)', body)
        if match:
            names.append(normalized(match.group()))
    aliases = {}
    for name in set(names):
        aliases.setdefault(name, set()).add(name)
        aliases.setdefault(name.split()[-1], set()).add(name)
    return {alias: next(iter(owners)) for alias, owners in aliases.items() if len(owners) == 1}


def actor_before(clause, position, aliases):
    matches = []
    for alias, owner in aliases.items():
        for match in re.finditer(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', clause[:position]):
            matches.append((match.end(), len(alias), owner))
    return max(matches)[2] if matches else None


def negated_event(clause, position):
    prefix = clause[max(0, position - 40):position]
    if re.search(r'không chỉ\s*$', prefix):
        return False
    return bool(re.search(r'\b(?:không|chưa|chẳng)(?:\s+\w+){0,3}\s*$', prefix))


def extract_events(text, aliases):
    events = []
    for clause in clauses(text):
        years = year_mentions(clause)
        occurrences = []
        for label, keywords in EVENTS.items():
            for keyword in keywords:
                occurrences.extend((m.start(), m.end(), label) for m in re.finditer(r'(?<!\w)' + re.escape(keyword) + r'(?!\w)', clause))
        occurrences.sort()
        for idx, (start, end, label) in enumerate(occurrences):
            if negated_event(clause, start):
                continue
            if label == 'ghép thận' and re.search(r'\b(?:cần|chờ|phải)(?:\s+\w+){0,2}\s*$', clause[max(0,start-30):start]):
                continue
            # Associate the closest date within this event's clause, not all dates.
            lower = occurrences[idx-1][1] if idx else 0
            upper = occurrences[idx+1][0] if idx+1 < len(occurrences) else len(clause)
            candidates = [y for y in years if y[0] >= lower and y[1] <= upper]
            nearest = min(candidates, key=lambda y: min(abs(y[0]-end), abs(start-y[1]))) if candidates else None
            events.append({'label': label, 'year': nearest[2] if nearest else None,
                'actor': actor_before(clause, start, aliases), 'clause': clause, 'start':start})
    return events


def transplant_duration_constraint(bible):
    """Only bind a duration when a locked fact explicitly describes the transplant.

    Illness onset and a later operation are different events. Do not infer an
    operation from a sentence saying the patient needed or awaited one.
    """
    for fact in bible.critical_facts or []:
        if fact.status != 'LOCKED' or 'ghép' not in normalized(fact.description):
            continue
        duration = re.match(r'(\d+)\s+năm\b', normalized(fact.value))
        if duration:
            years = year_mentions(fact.value)
            return int(duration.group(1)), (years[0][2] if len(years) >= 2 else None)
    return None


def bible_timeline_conflicts(bible):
    constraint = transplant_duration_constraint(bible)
    if not constraint or constraint[1] is None:
        return []
    events = [e for t in bible.timeline or [] for e in extract_events(t, character_aliases(bible))]
    operation_years = {e['year'] for e in events if e['label'] in {'hiến thận', 'ghép thận'} and e['year']}
    if len(operation_years) == 1 and constraint[1] not in operation_years:
        return [f'Dữ kiện khóa ghi ghép năm {constraint[1]}, nhưng timeline ghi hiến/ghép năm {next(iter(operation_years))}.']
    return []


def script_duration_conflicts(script, bible):
    constraint = transplant_duration_constraint(bible)
    if not constraint:
        return []
    numbers = {str(n): n for n in range(1,100)}
    for n in range(1,100):
        numbers.update({word:n for word in num_to_vietnamese_words(n)})
    pattern = re.compile(r'cách đây\s+(' + '|'.join(re.escape(w) for w in sorted(numbers,key=len,reverse=True)) + r')\s+năm\b')
    issues = []
    for segment in script.segments:
        for clause in clauses(segment.text):
            if 'ghép thận' not in clause:
                continue
            for match in pattern.finditer(clause):
                if numbers[match.group(1)] != constraint[0]:
                    issues.append((segment.id, clause, f'Ghép thận được khóa cách đây {constraint[0]} năm, đoạn này kể {numbers[match.group(1)]} năm.'))
    return issues
