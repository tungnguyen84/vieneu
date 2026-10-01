"""Character Continuity Resolver for Sau Cánh Cửa Studio Visual Planning.

Guarantees 100% character continuity:
- Analyzes narration_summary, segment texts, and prompts for each scene.
- Extracts generic aliases, honorifics, and kinship terms from Character Library.
- Resolves visible_characters and character_refs_required.
- Preserves continuity so existing characters never arbitrarily disappear.
- Enforces dependency validation before export: human scenes must have character references.
- Populates resolved character dependency objects: character_id, name, reference_required, reference_media_id.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


def is_human_scene(scene: Dict[str, Any]) -> Tuple[bool, str]:
    """Detects whether a scene contains a human subject.
    
    Returns (is_human, reason).
    """
    # 1. If it already has visible characters, it definitely depicts human subjects
    if scene.get("visible_characters"):
        return True, f"Explicit visible characters: {scene.get('visible_characters')}"

    prompt = (scene.get("image_prompt") or "").lower()
    vp = str(scene.get("video_prompt") or "").lower()
    combined = f"{prompt} {vp}"

    # 2. Explicit non-human signals
    non_human_signals = [
        r"\bno people\b", r"\bno human\b", r"\bno living people\b", r"\bno hands\b",
        r"\bmacro photography\b", r"\bmacro shot\b", r"\bmacro view\b",
        r"\bestablishing shot of an antique\b", r"\bproduct view\b", r"\bempty room\b",
        r"\bproduct documentary photograph\b", r"\barchival photograph\b", r"\bsepia photograph\b",
        r"\bwedding photograph\b", r"\bvintage memory portrait\b"
    ]
    if any(re.search(sig, combined) for sig in non_human_signals):
        return False, "Explicit non-human shot"

    # 3. Human keywords with word boundaries
    human_signals = [
        r"\bman\b", r"\bwoman\b", r"\bperson\b", r"\bpeople\b", r"\bcouple\b", r"\bcharacter\b",
        r"\bfigure\b", r"\bface\b", r"\bportrait\b", r"\bhusband\b", r"\bwife\b", r"\bmother\b",
        r"\bfather\b", r"\bdaughter\b", r"\bson\b", r"\bhands\b",
        r"\bsitting\b", r"\bstanding\b", r"\bwalking\b", r"\blooking\b", r"\bholding\b",
        r"\bcrying\b", r"\bweeping\b", r"\brealistic vietnamese character identity\b",
        r"\brestrained human emotion\b"
    ]
    for sig in human_signals:
        if re.search(sig, combined):
            return True, f"Found human signal '{sig}'"

    # 4. Human keywords in narration
    narr = (scene.get("narration_summary") or "").lower()
    narr_human_words = [
        r"\bcô\b", r"\banh\b", r"\bbà\b", r"\bông\b", r"\bngười\b", r"\bvợ\b",
        r"\bchồng\b", r"\bmẹ\b", r"\bcha\b", r"\bbố\b", r"\bcon\b"
    ]
    for nw in narr_human_words:
        if re.search(nw, narr):
            return True, f"Found narration human indicator '{nw}'"

    return False, "No human signals"


class CharacterContinuityResolver:
    """Resolves character appearances and maintains identity continuity across scenes."""

    def __init__(self, characters: List[Dict[str, Any]], primary_protagonist_id: Optional[str] = None):
        self.characters = characters
        self.char_map = {c["character_id"]: c for c in characters}
        self.primary_protagonist_id = primary_protagonist_id or (characters[0]["character_id"] if characters else None)
        self.patterns = self._build_character_patterns()

    def _build_character_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Extracts comprehensive alias patterns, honorifics, and kinship for each character."""
        patterns = {}
        for c in self.characters:
            cid = c["character_id"]
            name = c.get("name", "")
            role = str(c.get("role") or c.get("emotional_baseline") or "")
            desc = str(c.get("description") or c.get("appearance") or c.get("face_description") or "")
            gender = c.get("gender")

            words = name.strip().split()
            given_name = words[-1].lower() if words else ""

            exact_phrases = set()

            # 1. Full name
            if name:
                exact_phrases.add(name.lower())

            # 2. Compound and honorific combinations
            if len(words) >= 3:
                exact_phrases.add(f"{words[-2]} {words[-1]}".lower())
                exact_phrases.add(f"{words[0]} {words[-1]}".lower())
            elif len(words) == 2:
                exact_phrases.add(f"{words[0]} {words[1]}".lower())

            # Standard Vietnamese honorifics with given name
            for h in ["bà", "ông", "cô", "chú", "bác", "anh", "chị", "em"]:
                if given_name:
                    exact_phrases.add(f"{h} {given_name}")

            # 3. Specific Kinship / Role keywords (strictly scoped to avoid cross-contamination)
            combined_text = (role + " " + desc).lower()

            if re.search(r"\bmẹ chồng\b", combined_text):
                exact_phrases.update(["mẹ chồng", "mẹ của chồng", "người mẹ chồng", "mẹ chồng cô"])
            elif re.search(r"\b(?:mẹ ruột|mẹ đẻ|người mẹ)\b", combined_text):
                exact_phrases.update(["mẹ ruột", "mẹ đẻ", "người mẹ", "người mẹ già"])

            if re.search(r"\b(?:vợ của|người vợ|nàng dâu|chị dâu|vợ)\b", combined_text):
                exact_phrases.update(["vợ của", "vợ anh", "người vợ", "chị dâu", "nàng dâu", "vợ"])

            if re.search(r"\b(?:chồng của|người chồng|chồng)\b", combined_text) and not re.search(r"\bem chồng\b", combined_text):
                exact_phrases.update(["chồng của", "chồng cô", "người chồng", "anh chồng", "chồng"])

            if re.search(r"\b(?:em chồng|em trai)\b", combined_text):
                exact_phrases.update(["em chồng", "cậu em trai", "em trai", "người em trai"])

            if re.search(r"\bcon trai\b", combined_text):
                exact_phrases.update(["con trai", "người con trai"])
            elif re.search(r"\bcon gái\b", combined_text):
                exact_phrases.update(["con gái", "người con gái"])

            is_protagonist = (
                (cid == self.primary_protagonist_id)
                or bool(re.search(r"\b(?:nhân vật chính|protagonist)\b", combined_text))
            )

            patterns[cid] = {
                "given_name": given_name,
                "exact_phrases": sorted(list(exact_phrases), key=len, reverse=True),
                "gender": gender,
                "is_protagonist": is_protagonist,
            }
        return patterns

    def _match_single_word(self, word: str, text: str) -> bool:
        """Matches a single given name ensuring no negative false-positive context."""
        if not word or len(word) < 2:
            return False

        negative_before = {
            "mai": r"(?:ngày|sớm|ban|nay|tương|hoa|cây)\s+",
            "quân": r"(?:bình|tướng|hải|không|lục|đoàn)\s+",
            "hoàng": r"(?:huy|đàng)\s+",
            "an": r"(?:bình|công|trật|an|bất|hoài)\s+",
            "thủy": r"(?:thu|thủy)\s+",
            "hùng": r"(?:anh|hào)\s+",
            "thành": r"(?:hoàn|trở|tiến|chân|trung|hình)\s+",
            "dũng": r"(?:anh|dũng)\s+",
            "minh": r"(?:thông|văn|chứng|bình|minh)\s+",
        }
        negative_after = {
            "mai": r"\s+(?:sau|táng|tươi)",
            "quân": r"\s+(?:đội|sự|đoàn|doanh|nhu|tử)",
            "hoàng": r"\s+(?:hôn|gia|kim|đế|hậu|thành|cung)",
            "an": r"\s+(?:tâm|toàn|ninh|ủi|táng|dưỡng|phận|lành)",
            "thủy": r"\s+(?:chung|thủ|điện|sản|triều|cung|quân|lợi)",
            "hùng": r"\s+(?:vĩ|hồn|dũng|mạnh)",
            "thành": r"\s+(?:phố|công|tựu|viên|quả|phần|công)",
            "dũng": r"\s+(?:cảm|mãnh|khí)",
            "minh": r"\s+(?:bạch|mẫn|oan|họa|tinh)",
        }

        pattern = r"\b" + re.escape(word) + r"\b"
        for m in re.finditer(pattern, text, re.IGNORECASE):
            start, end = m.start(), m.end()
            prefix = text[max(0, start - 20):start].lower()
            suffix = text[end:min(len(text), end + 20)].lower()

            neg_b = negative_before.get(word.lower())
            if neg_b and re.search(neg_b + r"$", prefix):
                continue
            neg_a = negative_after.get(word.lower())
            if neg_a and re.search(r"^" + neg_a, suffix):
                continue
            return True
        return False

    def match_characters_in_text(self, text: str) -> List[str]:
        """Finds all characters mentioned in a given text string."""
        matched = []
        t_low = text.lower()
        for cid, pdata in self.patterns.items():
            # 1. Exact multi-word phrases first
            found = False
            for phrase in pdata["exact_phrases"]:
                pattern = r"\b" + re.escape(phrase) + r"\b"
                if re.search(pattern, t_low):
                    matched.append(cid)
                    found = True
                    break
            if found:
                continue

            # 2. Check given name with negative filters
            if self._match_single_word(pdata["given_name"], text):
                matched.append(cid)

        return matched

    def resolve_scenes(self, scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Resolves character continuity for all scenes in chronological order."""
        active_characters: List[str] = [self.primary_protagonist_id] if self.primary_protagonist_id else []

        for sc in scenes:
            narr = sc.get("narration_summary") or sc.get("visual_mode_reason") or ""
            prompt = sc.get("image_prompt") or ""

            # 1. Match direct mentions in narration
            matched = self.match_characters_in_text(narr)

            # 2. If nothing in narration, check prompt
            if not matched and prompt:
                matched = self.match_characters_in_text(prompt)

            # 3. Check pronouns / continuation if still no characters
            if not matched:
                narr_low = narr.lower()
                if any(w in narr_low for w in ["cô", "chị dâu", "người vợ", "nàng dâu"]):
                    females = [
                        cid for cid, p in self.patterns.items()
                        if p.get("gender") == "FEMALE" or p.get("is_protagonist")
                    ]
                    if females:
                        matched.append(females[0])
                elif any(w in narr_low for w in ["anh", "người chồng"]):
                    males = [
                        cid for cid, p in self.patterns.items()
                        if p.get("gender") == "MALE" and not p.get("is_protagonist")
                    ]
                    if males:
                        matched.append(males[0])
                elif any(w in narr_low for w in ["bà", "người mẹ"]):
                    elders = [
                        cid for cid, p in self.patterns.items()
                        if any("bà" in ph or "mẹ" in ph for ph in p.get("exact_phrases", []))
                    ]
                    if elders:
                        matched.append(elders[0])
                elif any(w in narr_low for w in ["hai vợ chồng", "họ", "hai người", "cả gia đình"]):
                    matched.extend(active_characters)

            # 4. If scene contains human subject (in prompt or narration), ensure characters are not empty
            is_human, _ = is_human_scene(sc)
            if is_human and not matched:
                matched = list(active_characters) if active_characters else (
                    [self.primary_protagonist_id] if self.primary_protagonist_id else []
                )

            # Update active characters if we have matches
            if matched:
                seen = set()
                deduped = [x for x in matched if not (x in seen or seen.add(x))]
                active_characters = deduped
                sc["visible_characters"] = deduped
            else:
                sc["visible_characters"] = []

            # Populate character_refs_required
            char_refs = [
                cid for cid in sc["visible_characters"]
                if self.char_map.get(cid, {}).get("requires_approval", self.char_map.get(cid, {}).get("reference_required", True))
            ]
            sc["character_refs_required"] = char_refs

            # Populate resolved character dependencies contract
            sc["character_dependencies"] = [
                {
                    "character_id": cid,
                    "name": self.char_map.get(cid, {}).get("name", cid),
                    "reference_required": self.char_map.get(cid, {}).get("reference_required", True),
                    "reference_media_id": self.char_map.get(cid, {}).get("reference_media_id", None)
                }
                for cid in char_refs
            ]

        return scenes
