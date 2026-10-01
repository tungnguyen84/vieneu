"""Storytelling craft for the script writer, learned from an aired episode.

The QC rules say what a script must not do; they cannot make it gripping. A
model given only prohibitions writes defensively ("chưa đủ để kết luận" in every
other segment). This module gives the writer a positive target: concrete craft
principles plus a short voice reference from Sau Cánh Cửa EP01, an episode that
was written in chat, voiced and published.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, List

logger = logging.getLogger("VieNeu.ScriptCraft")

VOICE_REFERENCE_PATH = Path(__file__).resolve().parents[2] / "script_factory" / "style_references" / "ep01_voice_reference.json"

CRAFT_PRINCIPLES = """NGHỀ KỂ CHUYỆN (bắt buộc, quan trọng ngang các quy tắc cứng):
- HOOK: mở bằng một câu TRÍCH NGUYÊN VĂN từ lá thư (trong ngoặc kép) hoặc một hành động cụ thể; MC được phép nói phản ứng thật của mình ("Thú thật, khi đọc đến đây tôi cũng đã nghĩ…") và dẫn người nghe đoán theo hướng dễ đoán nhất. Không mở bằng câu triết lý.
- Câu ngắn, có nhịp; dùng câu cụt để nhấn ("Năm triệu mỗi tháng. Suốt bảy năm."). Mỗi phân đoạn 1-3 câu.
- Chi tiết đời thường RIÊNG TƯ và cụ thể (vết sẹo, tên con vật nuôi, món đồ cũ, câu nói quen miệng) làm nhân vật tin và làm người nghe tin.
- Nhân vật CHỦ ĐỘNG kiểm chứng bằng hành động (cố tình hỏi sai, đòi gọi video, hẹn gặp, đối chiếu ngày tháng). Giới hạn của bằng chứng thể hiện qua kết quả của hành động đó, KHÔNG bằng câu rào đón của người kể như "chưa đủ để kết luận", "mới chỉ là dấu hiệu", "cần tìm hiểu thêm".
- Lời thoại trực tiếp ngắn trong ngoặc kép ở các cảnh then chốt (đối chất, thú nhận, câu hỏi của người thân).
- Nội tâm của NGƯỜI GỬI THƯ được dẫn bằng lá thư: "<tên người gửi thư> viết…", "<tên người gửi thư> kể rằng…". CHỈ người gửi thư mới "viết" hoặc "kể trong thư"; nhân vật khác chỉ nói qua lời thoại họ nói với người gửi thư. (Trong MẪU GIỌNG KỂ, người gửi thư tên Lan; tập này người gửi thư là nhân vật chính của Story Bible.)
- Mỗi cuộc gặp/cuộc gọi then chốt phải có ít nhất một câu thoại trực tiếp của người được gặp. Không tóm tắt kiểu "câu trả lời của anh ta khiến tôi phải suy nghĩ lại".
- REVEAL tách thành nhiều nhịp ngắn, mỗi nhịp một chi tiết, để khoảng lặng làm việc.
- Gieo manh mối công bằng từ sớm để cú lật bất ngờ mà người nghe nhìn lại vẫn thấy hợp lý.
- Không lặp một nhịp/ý quá 2 lần (ví dụ "anh vẫn chưa hỏi vợ"). Theo dõi ai đang giữ đồ vật nào; mỗi thay đổi trạng thái chỉ xảy ra một lần. Người thân đã xuất hiện (con cái) phải có mặt khi gia đình thay đổi.
- KẾT bằng một hành động cụ thể của nhân vật (pha cốc nước, ngồi nghe kể lại), sau đó tối đa 1 câu chiêm nghiệm và 1 câu hỏi người nghe, rồi chào. Không giảng đạo nhiều đoạn, không cảm ơn nhiều lần."""


# The script can only be as surprising as the Story Bible behind it. A bible
# that confirms exactly what the listener guessed in minute one produces a flat
# episode no matter how well it is voiced.
STORY_DESIGN_PRINCIPLES = """THIẾT KẾ KỊCH TÍNH (bắt buộc):
- Người nghe phải ĐOÁN SAI một cách hợp lý ở nửa đầu: giả thuyết ban đầu (false_lead) là điều ai cũng nghĩ tới.
- Cú lật (reveal_2) phải làm người nghe HIỂU LẠI câu chuyện bằng một SỰ KIỆN, DANH TÍNH hoặc QUAN HỆ cụ thể mà người nghe không ngờ (người thứ ba là ai, tiền/đồ vật thật ra đi đâu, ai đã biết từ trước, việc xảy ra bằng cách nào), nhưng vẫn giữ đúng sự thật trung tâm của chủ đề người dùng. Một lời giải thích về động cơ nội tâm ("cô cần được lắng nghe") KHÔNG tính là cú lật. Không được chỉ "xác nhận đúng điều đã nghi từ đầu".
- Người đang che giấu chỉ thú nhận khi bị đặt trước bằng chứng không thể chối hoặc có lý do rõ ràng.
- Bằng chứng phải là thứ NGƯỜI THƯỜNG có được: đồ vật trong nhà, máy/tài khoản dùng chung của gia đình, điều tận mắt thấy hoặc nghe được, lời người quen kể, ảnh trên mạng xã hội, vật để quên. KHÔNG dùng camera của khách sạn/quán/tòa nhà/công ty, lịch sử thanh toán hay sao kê của người khác, hợp đồng thuê nhà, dữ liệu do công ty/khách sạn/ngân hàng cung cấp cho người hỏi; ngoài đời họ không cung cấp, và viết 'theo quy trình' không làm nó thật hơn.
- Gieo ít nhất 3 manh mối công bằng từ sớm; nhìn lại thấy cú lật hợp lý.
- Ít nhất 3 chi tiết đời thường RIÊNG TƯ và cụ thể (đồ vật, thói quen, câu nói, nơi chốn) gắn với nhân vật.
- Có một cảnh nhân vật chính CHỦ ĐỘNG kiểm chứng (thử hỏi sai, hẹn gặp, đối chiếu) và kết quả của nó làm câu chuyện rẽ hướng.
- Kết thúc bằng một HÀNH ĐỘNG cụ thể của nhân vật thể hiện lựa chọn của họ, không bằng lời giảng."""

@lru_cache(maxsize=1)
def _load_reference() -> dict:
    try:
        return json.loads(VOICE_REFERENCE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # The writer still works without the sample.
        logger.warning(f"[ScriptCraft] Voice reference unavailable: {exc}")
        return {}


def voice_reference_block() -> str:
    """Craft principles plus excerpts of an aired episode, for the writer prompt."""
    ref = _load_reference()
    parts = [CRAFT_PRINCIPLES]
    if ref.get("sections"):
        parts.append(
            "\nMẪU GIỌNG KỂ (trích tập đã phát sóng). CHỈ học giọng kể, nhịp câu, cách dựng cảnh. "
            "TUYỆT ĐỐI KHÔNG dùng lại nhân vật, tình tiết, đồ vật, con số hay câu chữ của mẫu."
        )
        for section in ref["sections"]:
            parts.append(f"\n# {section['lesson']}")
            parts.extend(f"[{seg['profile']}] {seg['text']}" for seg in section["segments"])
    return "\n".join(parts)


# Any thank-you before the final sign-off repeats the closing (the sign-off thanks listeners).
_CLOSING_THANKS_RE = re.compile(r"\bcảm\s+ơn\b", re.IGNORECASE)


_NARRATIVE_SUBJECTS = {"anh", "cô", "chị", "ông", "bà", "họ", "con bé", "cậu bé", "hai người", "hai vợ chồng", "hai bố con", "hai mẹ con"}
_WORD_RE = re.compile(r"[^\W\d_]+")
# "câu chuyện của Hoàng" / "lá thư của Hoàng" is the host reflecting, not narration.
_HOST_FRAME_RE = re.compile(r"(?:chuyện|thư|lời)\s+của\s+[^\W\d_]+", re.IGNORECASE)


def character_names(texts: List[str], min_count: int = 3) -> set:
    """Capitalised words that recur mid-sentence: the episode's character names."""
    counts: dict = {}
    for text in texts:
        for sentence in re.split(r"(?<=[.!?…])\s+", str(text or "")):
            for word in _WORD_RE.findall(sentence)[1:]:
                if word[0].isupper():
                    counts[word] = counts.get(word, 0) + 1
    return {w for w, n in counts.items() if n >= min_count}


def _is_narration(text: str, names: set) -> bool:
    """True for story narration rather than a host reflection.

    Reflections speak in general terms ("Sự phản bội đôi khi..."); narration
    follows a character ("Ngày dọn đi, Hoàng cất...", "Anh không mở nó ra nữa").
    """
    text = _HOST_FRAME_RE.sub("", str(text or ""))
    for sentence in re.split(r"(?<=[.!?…])\s+", text.strip()):
        words = _WORD_RE.findall(sentence)
        if not words:
            continue
        lead = " ".join(words[:3]).lower()
        if any(lead == s or lead.startswith(s + " ") for s in _NARRATIVE_SUBJECTS):
            return True
        if names & set(words):
            return True
    return False


def trim_overlong_closing(segments: List[Any]) -> List[Any]:
    """Drops surplus reflection segments after the last reveal.

    Writers pile up moral summaries, thank-yous and audience questions at the end
    (15 closing segments in one run). Keeps the narrative resolution untouched and
    retains one reflection, one audience question and the final sign-off. Works on
    ScriptSegment objects or dicts.
    """
    def get(seg, key, default=None):
        return seg.get(key, default) if isinstance(seg, dict) else getattr(seg, key, default)

    if len(segments) < 20:
        return segments
    last_reveal = max(
        (i for i, s in enumerate(segments) if str(get(s, "delivery_profile", "")).upper() == "REVEAL"),
        default=None,
    )
    if last_reveal is None:
        return segments
    final_index = len(segments) - 1
    tail = range(last_reveal + 1, final_index)
    # Extra thank-you lines before the canonical sign-off repeat the closing.
    thanks = {i for i in tail if _CLOSING_THANKS_RE.search(str(get(segments[i], "text", "")))}
    comments = [
        i for i in tail
        if str(get(segments[i], "delivery_profile", "")).upper() == "COMMENT" and i not in thanks
    ]
    questions = [i for i in comments if get(segments[i], "audience_address", False)]
    # Writers label resolution lines ("Ngày dọn đi, Hoàng cất chiếc áo...") as
    # COMMENT too; dropping them cut the Story Bible ending out of the episode.
    names = character_names([str(get(s, "text", "")) for s in segments])
    narrative = [i for i in comments if i not in questions and _is_narration(str(get(segments[i], "text", "")), names)]
    for i in narrative:
        if isinstance(segments[i], dict):
            segments[i]["delivery_profile"] = "NORMAL"
        else:
            segments[i].delivery_profile = "NORMAL"
    comments = [i for i in comments if i not in narrative]
    reflections = [i for i in comments if i not in questions]
    keep = set(questions[-1:] + reflections[-1:])
    drop = {i for i in comments if i not in keep} | thanks
    if drop:
        logger.info(f"[ScriptCraft] Trimmed {len(drop)} surplus closing segments")
    return [s for i, s in enumerate(segments) if i not in drop]


HEDGE_PATTERNS = [
    r"chưa\s+đủ\s+(?:để\s+)?(?:kết\s+luận|khẳng\s+định|chứng\s+minh)",
    r"mới\s+chỉ\s+là\s+(?:dấu\s+hiệu|nghi\s+ngờ|giả\s+thuyết)",
    r"chưa\s+thể\s+(?:kết\s+luận|khẳng\s+định)",
    r"cần\s+(?:tìm\s+hiểu|xác\s+minh|biết)\s+thêm",
    r"chưa\s+phải\s+(?:là\s+)?câu\s+trả\s+lời",
]
_HEDGE_RE = re.compile("|".join(HEDGE_PATTERNS), re.IGNORECASE)


def hedge_segment_ids(segments: List[Any]) -> List[str]:
    """Segments where the narrator hedges instead of dramatizing verification."""
    ids = []
    for seg in segments:
        text = seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", "")
        if _HEDGE_RE.search(str(text)):
            ids.append(seg.get("id") if isinstance(seg, dict) else getattr(seg, "id", ""))
    return ids


# Evidence obtained through institutional procedure ("khách sạn cung cấp camera
# theo quy trình") is not something a spouse can get in real life; models used it
# to satisfy "access must be plausible" instead of choosing everyday evidence.
_PROCEDURAL_EVIDENCE_RE = re.compile(
    r"(?:camera[^.!?]{0,60}(?:do|được)[^.!?]{0,30}(?:ban\s+quản\s+lý|quản\s+lý|chủ\s+quán|khách\s+sạn|tòa\s+nhà|công\s+ty|cửa\s+hàng)[^.!?]{0,20}(?:cung\s+cấp|cho\s+xem|trích\s+xuất))"
    r"|(?:(?:ban\s+quản\s+lý|khách\s+sạn|chủ\s+quán|ngân\s+hàng|bộ\s+phận\s+nhân\s+sự)[^.!?]{0,40}(?:cung\s+cấp|gửi|cho\s+xem|xác\s+nhận)[^.!?]{0,40}(?:camera|sao\s+kê|lịch\s+sử\s+(?:thanh\s+toán|đặt\s+phòng)|hợp\s+đồng|dữ\s+liệu|thông\s+tin\s+(?:khách|lưu\s+trú)))"
    r"|(?:theo\s+(?:đúng\s+)?(?:quy\s+trình|quy\s+định)[^.!?]{0,40}(?:camera|thông\s+tin|dữ\s+liệu|khách))",
    re.IGNORECASE,
)


def procedural_evidence_hits(texts: List[str]) -> List[int]:
    """Indexes of texts that obtain evidence through an institution handing over private data."""
    return [i for i, text in enumerate(texts) if _PROCEDURAL_EVIDENCE_RE.search(str(text or ""))]


# A writer sometimes jumps from the confession straight to the closing
# reflection, so the Story Bible ending (moving out, custody, the final gesture)
# never airs. Measured on syllable pairs of the ending that the first 70% of the
# script does not already contain: a delivered resolution reuses ~0.14-0.32 of
# them, a skipped one ~0.08 (only incidental pairs).
ENDING_COVERAGE_MIN = 0.11
_MIN_FRESH_PAIRS = 12


def _syllable_pairs(text: str) -> set:
    words = re.findall(r"[^\W\d_]+", str(text or "").lower())
    return {f"{a} {b}" for a, b in zip(words, words[1:])}


def ending_coverage(texts: List[str], ending: str) -> float | None:
    """Share of the ending's new syllable pairs present in the last 30% (None = cannot judge)."""
    if len(texts) < 20 or not str(ending or "").strip():
        return None
    cut = int(len(texts) * 0.7)
    fresh = _syllable_pairs(ending) - _syllable_pairs(" ".join(texts[:cut]))
    if len(fresh) < _MIN_FRESH_PAIRS:
        return None
    return len(fresh & _syllable_pairs(" ".join(texts[cut:-1]))) / len(fresh)


def closing_block_start(segments: List[Any]) -> int:
    """Index where the trailing reflection/question/sign-off block begins."""
    def profile(seg):
        return str(seg.get("delivery_profile", "") if isinstance(seg, dict) else getattr(seg, "delivery_profile", "")).upper()

    index = len(segments)
    while index > 0 and profile(segments[index - 1]) in ("COMMENT", "ENDING"):
        index -= 1
    return index
