"""Allocate words to narrative work, rather than equally to call-sized chunks."""
from __future__ import annotations

import math
import re

ROLES = {'HOOK', 'SETUP', 'DEVELOPMENT', 'ESCALATION', 'DECISION', 'PAYOFF', 'REFLECTION', 'SIGNOFF'}
WEIGHTS = {'HOOK': .5, 'SETUP': 1, 'DEVELOPMENT': 1.5, 'ESCALATION': 1.8,
           'DECISION': 1.5, 'PAYOFF': 1.5, 'REFLECTION': .3, 'SIGNOFF': .15}
DECISION_OWNERSHIP_INSTRUCTION = (
    'NHÂN QUẢ VÀ QUYỀN QUYẾT ĐỊNH: ghi rõ ai đề xuất, ai xác nhận, ai chịu rủi ro ở việc then chốt. '
    'Đơn đã được khách chốt số lượng khác với ký gửi/thử bán do người làm tự chọn số lượng. '
    'Không vừa khẳng định khách đặt lượng đó vừa quy lỗi người giao vì tự chọn lượng đó; '
    'nếu rủi ro thuộc người giao thì phải có thỏa thuận/chủ động làm dư/sai quy cách được kể rõ. '
    'Tương tự, tách lời đề nghị khỏi đồng ý và cam kết bồi hoàn khỏi bồi hoàn đã thực hiện. '
    'Không tự suy ra trách nhiệm pháp lý từ lời kể. Factual giữ điều nguồn xác nhận và điều chưa rõ; '
    'own không đổi trách nhiệm/canon. Fiction giải quyết sự mơ hồ trong thiết kế trước khi viết. '
    'Sau khi một người đã đồng ý hợp tác, cảnh sau không xin lại cùng sự đồng ý như lần đầu; '
    'lần gặp mới phải có điều kiện, thử nghiệm, trở ngại hoặc kết quả mới được nói rõ. '
)
DESIGN_INSTRUCTION = (
    'THIẾT KẾ NHỊP KỂ: mỗi cảnh có role=HOOK|SETUP|DEVELOPMENT|ESCALATION|DECISION|PAYOFF|REFLECTION|SIGNOFF, '
    'state_before, state_after và listener_question. Trong cảnh diễn biến, hai trạng thái phải mô tả điều kiện/kiến thức thực tế, không chỉ đổi cảm xúc. '
    'REFLECTION/SIGNOFF có thể giữ nguyên tình thế sau payoff; không bịa thêm một sự kiện để đổi trạng thái ở lời chào. '
    'Mở bằng trở ngại/chi tiết cụ thể khiến người nghe muốn biết chuyện tiếp theo. '
    'Các cảnh giữa tập nối bằng nguyên nhân → lựa chọn → hệ quả; không chia một thao tác thành nhiều cảnh nhận xét. '
    'PAYOFF là sự kiện thực hiện đáp án, được dành đủ cảnh và thời lượng; REFLECTION chỉ chiêm nghiệm sau sự kiện. '
    'Tối đa một REFLECTION và một SIGNOFF ở cuối; tổng hai cảnh này tối đa 8% số từ, không bù thời lượng bằng bài học lặp. '
    'Kế hoạch/dành tiền/chuẩn bị KHÔNG thay được hành động đã hoàn thành trong Bible. '
    'Đúng chủ thể, đối tượng, lần thực hiện và nguồn tiền/nguồn bằng chứng; sự kiện đầu tập không trả lời một kết quả mới cuối tập. '
    'Factual giữ giới hạn chưa biết đúng nguồn; không bịa kết quả để làm tròn lời hứa. '
) + DECISION_OWNERSHIP_INSTRUCTION


def scene_word_budgets(scenes, total):
    """Integer allocation with an explicit cap on reflection, never on payoff."""
    if not scenes:
        return []
    if not any(s.get('role') for s in scenes):  # Imported legacy outlines.
        return [total // len(scenes) + (i < total % len(scenes)) for i in range(len(scenes))]
    closing = [i for i, s in enumerate(scenes) if s.get('role') in {'REFLECTION', 'SIGNOFF'}]
    main = [i for i in range(len(scenes)) if i not in closing]
    if not main:
        raise ValueError('Dàn cảnh không có diễn biến; không thể chỉ viết phần kết.')
    weights = [WEIGHTS.get(s.get('role'), 1.5) for s in scenes]
    # A lone REFLECTION also contains the required programme sign-off. Pure
    # proportional weighting left an 810-word episode only 25 words for both,
    # rejecting a concise 62-word ending that fits the overall closing cap.
    # Reserve enough for one brief reflection and sign-off, taking those words
    # from the body rather than increasing the episode's budget or QC limit.
    closing_minimum = 60 if len(closing) == 1 or any(scenes[i].get('role') == 'REFLECTION' for i in closing) else 20
    closing_total = min(math.floor(total * .08), max(closing_minimum,
        round(total * sum(weights[i] for i in closing) / sum(weights)))) if closing else 0
    allocations = [0] * len(scenes)
    for indices, budget in ((closing, closing_total), (main, total - closing_total)):
        if not indices:
            continue
        raw = {i: budget * weights[i] / sum(weights[j] for j in indices) for i in indices}
        for i in indices:
            allocations[i] = math.floor(raw[i])
        for i in sorted(indices, key=lambda i: raw[i] - allocations[i], reverse=True)[:budget - sum(allocations[i] for i in indices)]:
            allocations[i] += 1
    return allocations


def scene_batches(scenes, total, max_words=1000):
    """Contiguous groups: do not give the last few closing scenes 1/N of a show."""
    if not any(s.get('role') for s in scenes):
        count = min(len(scenes), math.ceil(total / max_words))
        return [(scenes[i*len(scenes)//count:(i+1)*len(scenes)//count],
                 total//count + (i < total%count)) for i in range(count)]
    budgets = scene_word_budgets(scenes, total)
    groups, current, words = [], [], 0
    for scene, budget in zip(scenes, budgets):
        starts_closing = scene.get('role') in {'REFLECTION', 'SIGNOFF'} and current and current[-1].get('role') not in {'REFLECTION', 'SIGNOFF'}
        if current and (words + budget > max_words or starts_closing):
            groups.append((current, words))
            current, words = [], 0
        current.append({**scene, 'word_budget': budget})
        words += budget
    if current:
        groups.append((current, words))
    # Keep closing separate: asking a final payoff call to also close encouraged
    # the model to spend the payoff's word budget on a second summary of the show.
    if (len(groups) > 1 and not any(s.get('role') in {'REFLECTION','SIGNOFF'} for s in groups[-1][0])
            and groups[-1][1] < max_words * .2 and groups[-2][1] + groups[-1][1] <= max_words * 1.2):
        group, size = groups.pop()
        groups[-1] = (groups[-1][0] + group, groups[-1][1] + size)
    return groups


def outline_design_errors(scenes):
    errors = []
    if any(s.get('role') not in ROLES or not s.get('state_before') or not s.get('state_after') or not s.get('listener_question') for s in scenes):
        errors.append('Mỗi cảnh cần role, state_before, state_after, listener_question.')
    actions = set()
    closing_started = False
    for s in scenes:
        action = ' '.join(s.get('action', '').lower().split())
        if action in actions:
            errors.append('Hai cảnh lặp cùng hành động: ' + action)
        actions.add(action)
        if s.get('role') in {'REFLECTION', 'SIGNOFF'}:
            closing_started = True
        elif closing_started:
            errors.append('Không đặt cảnh diễn biến sau chiêm nghiệm/lời chào kết.')
        if s.get('role') not in {'REFLECTION', 'SIGNOFF'} and s.get('state_before') == s.get('state_after'):
            errors.append('Cảnh không đổi tình thế: ' + str(s.get('no')))
    for role in ('REFLECTION', 'SIGNOFF'):
        if sum(s.get('role') == role for s in scenes) > 1:
            errors.append('Tối đa một cảnh ' + role)
    if scenes and scenes[0].get('role') != 'HOOK':
        errors.append('Cảnh đầu cần HOOK cụ thể.')
    return errors


def validate_scene_assignment(segments, scenes):
    """Validate batch scope; grounded QC still checks the prose under each label."""
    allowed = [s['no'] for s in scenes]
    # JSON providers sometimes serialize a numeric scene ID as a string. Only
    # canonicalize exact numeric IDs; missing, booleans and future scenes fail.
    for segment in segments:
        value = segment.get('scene_no')
        if isinstance(value, str) and re.fullmatch(r'[0-9]+', value):
            segment['scene_no'] = int(value)
    assigned = [s.get('scene_no') for s in segments]
    if any(type(n) is not int or n not in allowed for n in assigned):
        invalid = [{'segment_index':i+1,'returned_scene_no':n} for i,n in enumerate(assigned)
                   if type(n) is not int or n not in allowed]
        raise ValueError(f'Mỗi đoạn cần scene_no thuộc đúng cảnh được giao {allowed}; không viết cảnh trước/sau. '
                         f'Giá trị sai/thiếu: {invalid[:5]}. Giữ nội dung hợp lệ, thêm scene_no vào TỪNG item segments; '
                         f'ví dụ {{"scene_no": {allowed[0]}, "text": "...", "delivery_profile": "NORMAL"}}.')
    positions = [allowed.index(n) for n in assigned]
    if positions != sorted(positions) or set(assigned) != set(allowed):
        raise ValueError('Viết đủ từng cảnh được giao, theo đúng thứ tự, không quay lại cảnh đã kết thúc.')
    closing = [s for s in scenes if s.get('role') in {'REFLECTION', 'SIGNOFF'}]
    for scene in closing:
        if scene.get('role') in {'REFLECTION', 'SIGNOFF'}:
            if sum(s['scene_no'] == scene['no'] for s in segments) != 1:
                raise ValueError(f"Cảnh {scene['no']} là {scene['role']}: chỉ một đoạn; không chia bài học thành nhiều đoạn.")
    # REFLECTION and SIGNOFF share a closing ceiling. Their weighted split is
    # guidance, not a semantic boundary: a 52-word goodbye may legitimately
    # use words unused by the reflection, without lengthening the total tail.
    closing_ids = {s['no'] for s in closing}
    words = sum(len(s['text'].split()) for s in segments if s['scene_no'] in closing_ids)
    budget = sum(s['word_budget'] for s in closing)
    if closing and words > max(25, budget * 1.15):
        raise ValueError(f"Phần khép lại {sorted(closing_ids)}: {words} từ vượt ngân sách chung {budget}; rút nhận xét, giữ sự kiện kết quả.")


def payment_payoff_missing(promise, events):
    """Reject a cited intention as proof of a promised payment, not generic style."""
    payment = r'(?:đóng|trả|thanh toán)\s+(?:phần\s+|khoản\s+|tiền\s+)?(?:học phí|viện phí|khoản nợ|nợ|tiền thuê)'
    if not re.search(payment, promise.lower()):
        return None
    # A canonical plan/unknown outcome must stay a plan/unknown outcome.
    if re.search(r'\b(?:dự định|dự kiến|chuẩn bị|sẽ|chưa)\b[^.!?]{0,60}' + payment, promise.lower()):
        return None
    quotes = [str(ref.get('quote', '')).lower() for event in events for ref in event.get('evidence', [])]
    for quote in quotes:
        for sentence in re.split(r'[.!?;]', quote):
            if (re.search(payment, sentence)
                    and not re.search(r'\b(?:sẽ|để|dành|dự định|dự kiến|chuẩn bị|chưa|không)\b[^.!?]{0,60}' + payment, sentence)):
                if 'tiếp theo' in promise.lower() and ('lần đầu' in sentence or 'đầu tiên' in sentence):
                    continue
                return None
    return 'Bible yêu cầu một khoản thanh toán đã thực hiện; quote chỉ chứng minh chuẩn bị/dành tiền hoặc lần thanh toán trước.'


def event_state_matches(required_action, actual_state):
    """Plans/unknown outcomes stay honest; completed events cannot be mere plans."""
    action = required_action.lower()
    if re.search(r'\b(?:chưa rõ|chưa biết|chưa cho biết|không rõ|không cho biết)\b', action):
        return actual_state == 'UNKNOWN'
    if re.search(r'\b(?:dự định|dự kiến|chuẩn bị|sẽ|kế hoạch)\b', action):
        return actual_state == 'PLANNED'
    return actual_state == 'COMPLETED'


def ending_event_catalog(promise):
    """Bind review IDs to exact Bible clauses, without asking an LLM to recopy them."""
    clauses = [part.strip() for part in re.split(r'[,;\n]+', promise) if part.strip()]
    if any(len(part.split()) < 4 for part in clauses):
        # Keep short adjuncts attached without reconstructing punctuation or
        # inventing an independent action from a time/place fragment.
        clauses = [promise.strip()]
    return {f'ENDING_ACTION_{i}': text for i, text in enumerate(clauses, 1)}
