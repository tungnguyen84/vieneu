"""Read-only writing obligations and conservative calendar arithmetic.

No invented dates, no use of the machine's current year, and no rewriting of
creative artifacts. Unknown birthdays yield an interval, not a false exact age.
"""
import json
import re

from apps.script_factory.event_facts import normalized, year_mentions
from apps.script_factory.vietnamese_cleaner import num_to_vietnamese_words


def age_facts(bible):
    period = normalized(bible.time_period or '')
    present = re.search(r'(?:hiện tại|bối cảnh hiện tại|thời điểm hiện tại)(?:\s+là)?\s+(?:năm\s+)?((?:19|20)\d{2})', period)
    if not present:
        return []
    current = int(present.group(1))
    facts = []
    for ch in [bible.protagonist, *(bible.supporting_characters or [])]:
        if not isinstance(ch, dict) or not ch.get('name'):
            continue
        birth = ch.get('birth_year')
        if str(birth).isdigit() and 1900 <= int(birth) <= current:
            facts.append({'subject': ch['name'], 'birth_year': int(birth), 'present_year': current,
                          'min_age': current-int(birth)-1, 'max_age': current-int(birth)})
    # Only bind an unnamed child when both the relationship and singular birth
    # are explicit. Multiple children or ambiguous histories stay with review.
    sources = [*(bible.timeline or []), *[r.get('relationship', '') for r in bible.relationships or [] if isinstance(r, dict)], period]
    for role in ('con gái', 'con trai'):
        birth_years = set()
        ambiguous = False
        for source in sources:
            text = normalized(source)
            if re.search(r'(?:hai|ba|\d+)\s+' + role, text):
                ambiguous = True
            if role not in text or not re.search(r'\b(?:sinh|chào đời)\b', text):
                continue
            # Only one dated event in this sentence, or a directly stated birth.
            direct = re.search(role + r'[^.;]{0,45}?sinh năm ((?:19|20)\d{2})', text)
            years = year_mentions(text)
            if direct:
                birth_years.add(int(direct.group(1)))
            elif len(years) == 1:
                birth_years.add(years[0][2])
        if not ambiguous and len(birth_years) == 1:
            birth = next(iter(birth_years))
            if birth <= current:
                facts.append({'subject': role, 'birth_year': birth, 'present_year': current,
                              'min_age': current-birth-1, 'max_age': current-birth})
    return facts


def age_claims(text, fact):
    numbers = {str(n): n for n in range(0, 101)}
    for n in range(0, 101):
        numbers.update({w: n for w in num_to_vietnamese_words(n)})
    num = '(?:' + '|'.join(re.escape(w) for w in sorted(numbers, key=len, reverse=True)) + ')'
    # Do not project a present-day age onto an explicitly dated flashback,
    # future intention or someone's deliberately false quoted claim.
    for clause in re.split(r'[.!?;]', normalized(text)):
        if '“' in clause or '"' in clause or re.search(r'\b(?:khi|lúc|hồi|đến năm|sẽ|từng|không phải)\b', clause):
            continue
        if any(y[2] != fact['present_year'] for y in year_mentions(clause)):
            continue
        pattern = r'(?<!\w)' + re.escape(normalized(fact['subject'])) + r'(?!\w)[^,.;:]{0,32}?\b(' + num + r')\s+tuổi\b'
        for match in re.finditer(pattern, clause):
            # Never borrow an age belonging to a second person in the clause.
            middle = clause[match.start():match.start(1)]
            if re.search(r'\b(?:vợ|chồng|mẹ|bố|cha|anh trai|em gái)\b', middle):
                continue
            yield numbers[match.group(1)], clause


def bible_age_conflicts(bible):
    issues = []
    sources = [('protagonist', str(bible.protagonist)), ('supporting_characters', str(bible.supporting_characters))]
    for fact in age_facts(bible):
        for ch in [bible.protagonist, *(bible.supporting_characters or [])]:
            if isinstance(ch, dict) and ch.get('name') == fact['subject'] and str(ch.get('age')).isdigit():
                if not fact['min_age'] <= int(ch['age']) <= fact['max_age']:
                    issues.append(('protagonist' if ch is bible.protagonist else 'supporting_characters',
                        f"{fact['subject']} sinh {fact['birth_year']}, hiện tại {fact['present_year']}: age phải trong {fact['min_age']}–{fact['max_age']}, không phải {ch['age']}."))
        for field, text in sources:
            for age, quote in age_claims(text, fact):
                if not fact['min_age'] <= age <= fact['max_age']:
                    issues.append((field, f"{fact['subject']} sinh {fact['birth_year']}, hiện tại {fact['present_year']}: tuổi có thể {fact['min_age']}–{fact['max_age']} (chưa biết sinh nhật), không phải {age}. Đồng bộ tuổi trong nhân vật, giữ mốc sinh và bối cảnh đã nêu."))
    return issues


def script_age_conflicts(script, bible):
    for fact in age_facts(bible):
        for segment in script.segments:
            for age, quote in age_claims(segment.text, fact):
                if not fact['min_age'] <= age <= fact['max_age']:
                    yield segment.id, quote, f"{fact['subject']}: {fact['present_year']} - {fact['birth_year']} = {fact['max_age']}; tuổi hợp lệ {fact['min_age']}–{fact['max_age']}, không phải {age}."


def payoff_obligations(bible):
    obligations = []
    skeleton = bible.narrative_skeleton or {}
    for key, text in [('title_trigger', str(skeleton.get('trigger', '') or (bible.title if bible.clues else '')))]:
        if text:
            obligations.append({'id': key, 'promise': text, 'question': 'Giải thích cụ thể dấu hiệu mở đầu/chi tiết tiêu đề từ đâu và mang ý nghĩa gì, qua nguồn nào; không chỉ cất hoặc nhắc lại vật.'})
    clues = bible.structured_clues or []
    if clues:
        for i, clue in enumerate(clues, 1):
            if isinstance(clue, dict) and clue.get('clue'):
                obligations.append({'id': f'clue_{i}', 'promise': clue['clue'], 'question': clue.get('next_question') or 'Manh mối được giải thích/kiểm chứng thế nào?', 'scope': clue.get('what_it_does_NOT_prove', '')})
    else:
        obligations.extend({'id': f'clue_{i}', 'promise': text, 'question': 'Nội dung cụ thể, nguồn và giới hạn kết luận của manh mối này là gì?'} for i, text in enumerate(bible.clues or [], 1))
    for key in ('reveal_1', 'reveal_2', 'ending'):
        text = getattr(bible, key, '')
        if text:
            obligations.append({'id': key, 'promise': text, 'question': 'Phải có cảnh hành động/đối thoại hiện thực hóa đúng sự kiện này, không chỉ tóm tắt hoặc hứa sẽ làm.'})
    return obligations


def contract_block(bible):
    return '\nHỢP ĐỒNG VIẾT & KIỂM TRA (hậu trường, KHÔNG đọc ra):\n' + json.dumps({
        'calendar_arithmetic': age_facts(bible), 'payoff_obligations': payoff_obligations(bible)
    }, ensure_ascii=False) + '\nTuổi là số học theo NĂM TRONG TRUYỆN, không dùng năm máy tính. Chưa biết ngày sinh thì chấp nhận khoảng tuổi đã tính; không tự bịa sinh nhật. Mỗi lời hứa có cảnh trả lời cụ thể, không thay bằng việc cất vật/đối chiếu chung chung.\n'
