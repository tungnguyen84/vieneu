"""Visual Planning Data for EP011 - Bức Ảnh Lạ Trong Điện Thoại Cũ.

Contains:
- Character Bible
- Location Bible
- Prop Bible
- 45 Scene Definitions with continuous timeline mapping
- Dynamic Still parameters & Overlay specifications
"""
from __future__ import annotations

EPISODE_ID = "EP011"
TITLE = "Bức Ảnh Lạ Trong Điện Thoại Cũ"
SERIES = "Sau Cánh Cửa"

CHARACTERS = [
    {
        "character_id": "CHAR_LINH",
        "name": "Linh",
        "gender": "FEMALE",
        "age": 32,
        "ethnicity": "Vietnamese",
        "face_description": (
            "Believable 32-year-old Vietnamese woman, delicate expressive features, thoughtful and sensitive dark eyes, "
            "natural skin texture with subtle laugh lines, restrained emotion, modern urban demeanor, no glamour fashion look."
        ),
        "hair": "Dark brown shoulder-length hair, worn down naturally or gathered loosely with a hair clip.",
        "body_build": "Slender, medium height, contemporary Vietnamese professional woman.",
        "wardrobe_baseline": "Soft knitted cream crewneck sweater, dark tailored trousers, discreet silver wedding ring.",
        "wardrobe_variants": {
            "home_cleaning": "Comfortable oversized navy cotton t-shirt, relaxed grey lounge pants, hair tied in high bun.",
            "travel_nam_dinh": "Dark olive trench coat over cream wool sweater, cross-body canvas bag, flat leather walking shoes."
        },
        "emotional_baseline": "Loving wife, deeply anxious upon discovering ambiguous photo, determined to seek truth, moved to tears and deep forgiveness upon understanding.",
        "role": "Protagonist, wife investigating husband's secret.",
        "relationship": "Wife of Nam for 7 years.",
        "timeline_age": "Present (2024, age 32)",
        "priority": "PRIMARY",
        "requires_approval": True,
        "reference_prompt": (
            "Documentary portrait of a 32-year-old Vietnamese woman (CHAR_LINH), natural dark hair, sensitive intelligent expression, "
            "soft natural skin texture, wearing a cream knitted crewneck sweater, soft morning domestic light in living room, "
            "35mm lens, photorealistic documentary drama."
        )
    },
    {
        "character_id": "CHAR_NAM_PRESENT",
        "name": "Nam (Present)",
        "gender": "MALE",
        "age": 35,
        "ethnicity": "Vietnamese",
        "face_description": (
            "Believable 35-year-old Vietnamese man, earnest and hardworking face, tired eyes showing the wear of late-night shifts "
            "and a hidden burden, calm honest demeanor, no heavy styling."
        ),
        "hair": "Short neat black hair, slightly rumpled from long working hours.",
        "body_build": "Lean, athletic build of a field engineer.",
        "wardrobe_baseline": "Dark charcoal work jacket over a light grey henley shirt, dark denim jeans, sturdy work shoes, discreet silver wedding band.",
        "wardrobe_variants": {
            "home_relax": "Simple white cotton t-shirt, dark shorts."
        },
        "emotional_baseline": "Guilt-ridden and protective, carrying a decade-long secret alone, overwhelmed with relief and remorse during the confrontation.",
        "role": "Protagonist's husband, engineer, secret protector and financial sponsor of baby An.",
        "relationship": "Husband of Linh, older cousin to deceased Thảo, loving uncle/guardian to An.",
        "timeline_age": "Present (2024, age 35)",
        "priority": "PRIMARY",
        "requires_approval": True,
        "reference_prompt": (
            "Documentary portrait of a 35-year-old Vietnamese man (CHAR_NAM_PRESENT), earnest honest face, subtle signs of exhaustion "
            "around dark eyes, short black hair, wearing a dark charcoal work jacket over grey henley, soft evening indoor lighting, "
            "35mm cinematic realism."
        )
    },
    {
        "character_id": "CHAR_NAM_YOUNG_2012",
        "name": "Nam (Young 2012)",
        "gender": "MALE",
        "age": 23,
        "ethnicity": "Vietnamese",
        "face_description": (
            "Young Vietnamese man in his early 20s, leaner and more youthful version of Nam, earnest worry and grief on his face, unstyled black hair."
        ),
        "hair": "Slightly longer shaggy black college student haircut.",
        "body_build": "Lean, slender young graduate.",
        "wardrobe_baseline": "Faded hooded zipper sweatshirt over a striped t-shirt, dark trousers.",
        "wardrobe_variants": {},
        "emotional_baseline": "Distressed, desperate to protect his dying cousin and save the newborn baby.",
        "role": "Young Nam in 2012-2013 hospital memories and phone photo.",
        "relationship": "Younger self of Nam, cousin standing vigil for Thảo.",
        "timeline_age": "Past (2012-2013, age 23-24)",
        "priority": "SECONDARY",
        "requires_approval": False,
        "reference_prompt": (
            "Archival documentary portrait of a 23-year-old Vietnamese young man in 2012 (CHAR_NAM_YOUNG_2012), lean frame, anxious tired face, "
            "wearing a faded hooded jacket, fluorescent hospital corridor lighting in 2012, subtle digital grain."
        )
    },
    {
        "character_id": "CHAR_THAO_2012",
        "name": "Thảo (2012)",
        "gender": "FEMALE",
        "age": 21,
        "ethnicity": "Vietnamese",
        "face_description": (
            "Young Vietnamese rural woman in her early 20s, pale delicate face, exhausted from childbirth yet possessing a peaceful maternal smile, no makeup."
        ),
        "hair": "Long black hair resting loosely over a white hospital pillow.",
        "body_build": "Frail, bedridden hospital patient.",
        "wardrobe_baseline": "Standard light green or faded pink provincial hospital maternity gown.",
        "wardrobe_variants": {},
        "emotional_baseline": "Maternal tenderness, frail peace, placing absolute trust in her cousin Nam.",
        "role": "Deceased cousin in the mysterious phone photograph, mother of baby An.",
        "relationship": "Orphaned cousin sheltered by Nam's family, mother of An, deceased 2013.",
        "timeline_age": "Past (2012-2013, age 21-22)",
        "priority": "SECONDARY",
        "requires_approval": False,
        "reference_prompt": (
            "Documentary portrait of a 21-year-old Vietnamese young woman (CHAR_THAO_2012) lying in a provincial hospital bed, pale gentle face, "
            "holding a swaddled infant close, wearing a pale green hospital gown, soft window light, authentic 2012 documentary feeling."
        )
    },
    {
        "character_id": "CHAR_BE_AN_PRESENT",
        "name": "Bé An (Present)",
        "gender": "FEMALE",
        "age": 11,
        "ethnicity": "Vietnamese",
        "face_description": (
            "Bright, cheerful 11-year-old Vietnamese schoolgirl, round lively face, bright innocent eyes, healthy sun-kissed skin, radiant genuine smile."
        ),
        "hair": "Shoulder-length black hair tied in a cheerful ponytail with a bright hair tie.",
        "body_build": "Healthy 11-year-old child.",
        "wardrobe_baseline": "Colorful hoodie and casual jeans, or neat elementary student school uniform.",
        "wardrobe_variants": {},
        "emotional_baseline": "Happy, innocent, thriving in a loving adoptive family while knowing Nam as a loving 'Chú'.",
        "role": "The child at the center of the mystery, thriving evidence of Nam's silent devotion.",
        "relationship": "Daughter of Thảo, niece/sponsored ward of Nam.",
        "timeline_age": "Present (2024, age 11)",
        "priority": "SECONDARY",
        "requires_approval": False,
        "reference_prompt": (
            "Documentary photograph of an 11-year-old Vietnamese girl (CHAR_BE_AN_PRESENT) with cheerful ponytailed hair, bright happy smile, "
            "wearing a colorful yellow hoodie in an afternoon public park, warm sunshine, cinematic realism."
        )
    },
    {
        "character_id": "CHAR_BE_AN_INFANT_2012",
        "name": "Bé An (Infant 2012-2013)",
        "gender": "FEMALE",
        "age": 0,
        "ethnicity": "Vietnamese",
        "face_description": "Newborn Vietnamese baby, tiny delicate face, peaceful sleeping expression.",
        "hair": "Fine dark baby fuzz.",
        "body_build": "Infant swaddled tightly in patterned hospital swaddle.",
        "wardrobe_baseline": "Yellow or white flannel baby blanket with tiny floral print.",
        "wardrobe_variants": {},
        "emotional_baseline": "Peaceful sleeping newborn.",
        "role": "The baby in the mysterious Nokia photo.",
        "relationship": "Newborn infant of Thảo.",
        "timeline_age": "Past (2012-2013)",
        "priority": "BACKGROUND",
        "requires_approval": False,
        "reference_prompt": (
            "Close-up documentary shot of a sleeping Vietnamese newborn infant swaddled snugly in a cotton baby blanket, soft natural hospital nursery light."
        )
    },
    {
        "character_id": "CHAR_NURSE_OLD",
        "name": "Y tá trưởng bệnh viện Nam Định",
        "gender": "FEMALE",
        "age": 58,
        "ethnicity": "Vietnamese",
        "face_description": (
            "Experienced 58-year-old Vietnamese hospital head nurse, kind compassionate face with reading glasses, professional calm demeanor."
        ),
        "hair": "Neat short salt-and-pepper hair tucked under a white medical nurse cap.",
        "body_build": "Maternal, sturdy build.",
        "wardrobe_baseline": "Standard Vietnamese hospital nurse white tunic with light blue collar piping, nurse cap.",
        "wardrobe_variants": {},
        "emotional_baseline": "Helpful, empathetic, remembering the poignant 2013 case clearly.",
        "role": "Witness at Nam Định hospital providing initial clues about Thảo's tragedy.",
        "relationship": "Hospital staff attending Thảo in 2013.",
        "timeline_age": "Present (2024, age 58)",
        "priority": "BACKGROUND",
        "requires_approval": False,
        "reference_prompt": (
            "Documentary portrait of a 58-year-old Vietnamese hospital nurse (CHAR_NURSE_OLD) in white uniform and nurse cap, wearing reading glasses, "
            "behind an administrative counter in a provincial hospital, soft fluorescent lighting."
        )
    }
]

LOCATIONS = [
    {
        "location_id": "LOC_KHO_DO_CU",
        "name": "Góc kho chứa đồ cũ / phòng làm việc nhỏ trong nhà Nam & Linh",
        "city_region": "Hà Nội",
        "type": "INTERIOR",
        "architecture": (
            "Compact domestic storage area / small utility room in an urban Vietnamese apartment, metal utility shelves, "
            "cardboard storage boxes labeled with marker, old computer tower, vintage wooden desk under warm bulb."
        ),
        "era": "Present (2024)",
        "key_furniture": "Storage shelving, cardboard boxes, vintage small desk, desk lamp with warm tungsten bulb.",
        "lighting": "Warm tungsten domestic lamp casting deep cozy shadows, subtle dust particles in air.",
        "color_material_characteristics": "Warm neutral browns, aged paper cardboard, dusty surfaces.",
        "story_function": "Where Linh finds the old Nokia phone and starts charging it.",
        "reference_prompt": (
            "Interior shot of a cozy storage nook in a Vietnamese urban apartment, cardboard archive boxes on wooden shelves, "
            "a small desk with a warm glowing lamp, quiet domestic realism, 35mm lens."
        )
    },
    {
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "name": "Phòng khách căn hộ Linh và Nam",
        "city_region": "Hà Nội",
        "type": "INTERIOR",
        "architecture": (
            "Tastefully decorated modern Vietnamese apartment living room, minimalist wooden coffee table, grey fabric sofa, "
            "indoor potted monstera plant, dining table in background, framed wedding picture on credenza."
        ),
        "era": "Present (2024)",
        "key_furniture": "Grey fabric sofa, low oak coffee table, wooden dining table with chairs, credenza with photo frames.",
        "lighting": "Soft natural daylight through sheer white curtains, changing to intimate warm lamps at night.",
        "color_material_characteristics": "Warm beige, muted grey, natural light wood grain.",
        "story_function": "Central domestic setting for marital intimacy, doubt, confrontation, and reconciliation.",
        "reference_prompt": (
            "Interior of a tastefully furnished contemporary Vietnamese apartment living room, soft grey sofa, oak coffee table, "
            "potted green houseplant, sheer curtains diffusing afternoon daylight, authentic modern domestic life, 35mm photography."
        )
    },
    {
        "location_id": "LOC_BENH_VIEN_NAM_DINH_2012",
        "name": "Bệnh viện đa khoa tỉnh Nam Định",
        "city_region": "Nam Định",
        "type": "INTERIOR",
        "architecture": (
            "Provincial Vietnamese state hospital corridor and records desk, mint-green painted lower half walls, worn terrazzo flooring, "
            "battered wooden office desks with paper medical binders, modest ceiling fluorescent tubes."
        ),
        "era": "2012-2013 and Present (2024)",
        "key_furniture": "Nurses' administrative desk, wooden bench outside consultation rooms, file cabinets.",
        "lighting": "Cool diffused fluorescent overhead lighting mixed with daylight from end-of-hallway windows.",
        "color_material_characteristics": "Pale mint green, weathered cream, faded linoleum/terrazzo.",
        "story_function": "Where the 2012 photo was taken, and where Linh investigates the 2013 maternity records.",
        "reference_prompt": (
            "Interior hallway of a provincial Vietnamese public hospital, pale green painted walls, terrazzo floor, wooden consultation doors, "
            "cool fluorescent light mixed with distant window daylight, realistic documentary texture, 35mm lens."
        )
    },
    {
        "location_id": "LOC_NHA_CU_THAO_NGOAI_O",
        "name": "Căn nhà cấp 4 cũ của Thảo ở ngoại ô Nam Định",
        "city_region": "Ngoại ô Nam Định",
        "type": "INTERIOR/EXTERIOR",
        "architecture": (
            "Modest rural Vietnamese single-story brick house (nhà cấp 4), weathered red brick walls, corrugated fiber cement roof, "
            "simple wooden door, small gravel courtyard with banana trees and bougainvillea."
        ),
        "era": "Present (2024)",
        "key_furniture": "Old wooden writing table, rustic wooden wardrobe, keepsake tin box.",
        "lighting": "Gentle natural daylight filtering through wooden slatted window shutters, quiet nostalgic dust.",
        "color_material_characteristics": "Earthy clay brick, weathered wood, rural northern Vietnamese silence.",
        "story_function": "Where Linh finds Thảo's keepsake box containing the 2013 adoption papers and letters.",
        "reference_prompt": (
            "Interior of a quiet rural single-story Vietnamese home in suburban Nam Định, weathered wooden table under a shuttered window, "
            "soft shafts of daylight, rustic quietness, 35mm documentary realism."
        )
    },
    {
        "location_id": "LOC_CONG_VIEN_CHIEU",
        "name": "Công viên thành phố buổi chiều muộn",
        "city_region": "Hà Nội",
        "type": "EXTERIOR",
        "architecture": (
            "Spacious urban park in Hanoi, paved lakeside walking path, mature leafy shade trees with golden afternoon sun, "
            "green grassy lawns, wooden park benches."
        ),
        "era": "Present (2024)",
        "key_furniture": "Park benches, iron lamp posts along paved path.",
        "lighting": "Golden hour late-afternoon sunshine casting long warm shadows, luminous sky.",
        "color_material_characteristics": "Golden amber, lush park greens, shimmering lake water.",
        "story_function": "Ending scene: Linh, Nam, and 11-year-old An walking happily together as an expanded family.",
        "reference_prompt": (
            "Wide cinematic shot of an urban park path by a lake in Hanoi during late afternoon golden hour, amber sunlight through tree branches, "
            "tranquil public park ambiance, feeling of familial warmth and peace, 35mm photography."
        )
    }
]

PROPS = [
    {
        "prop_id": "PROP_OLD_PHONE_01",
        "name": "Điện thoại Nokia cũ thời sinh viên",
        "brand_neutral_desc": "Vintage brand-neutral grey/silver candybar feature phone from early 2010s, monochrome/low-res color LCD screen, physical numeric keypad.",
        "dimensions": "10.5cm x 4.5cm x 1.4cm",
        "hardware": "Small round 2mm pin charging jack connected to a thin black charging cable, slightly worn rubber keypad buttons.",
        "condition": "Faint hairline scratches on plastic screen cover, edge wear on silver trim, perfectly preserved operational state.",
        "contents": "Saved 2012 hospital photograph in gallery, contact list with repeated calls to 'Công việc'.",
        "continuity_notes": "Key prop of the episode. Must retain exact physical shape, dark grey casing, and screen aspect ratio across all scenes."
    },
    {
        "prop_id": "PROP_HOSPITAL_PHOTO_2012",
        "name": "Bức ảnh trong màn hình điện thoại / kỷ vật",
        "format": "Low-resolution 2012 digital phone camera photograph displayed on phone LCD, or printed snapshot in keepsake box.",
        "visual_content": (
            "Young Nam (23, male) in a casual hoodie standing beside young Thảo (21, female) resting in a green hospital gown, "
            "holding a swaddled infant wrapped in a yellow blanket at Nam Định provincial hospital in August 2012."
        ),
        "condition": "Digital screen pixels visible on LCD display; poignant, genuine, ambiguous to an outsider.",
        "continuity_notes": "Must maintain exact character ages and hospital room setting whenever seen."
    },
    {
        "prop_id": "PROP_SILVER_BRACELET",
        "name": "Chiếc vòng tay trẻ em bằng bạc",
        "dimensions": "Diameter 4.5cm, adjustable open cuff design.",
        "material": "Solid sterling silver, polished surface with delicate gentle patina.",
        "engraving": "Hand-engraved inscription on the outer curved surface: 'An - 15/08/2013'.",
        "condition": "Immaculately kept in a small red velvet drawstring pouch inside Nam's memento drawer.",
        "continuity_notes": "Appears in drawer search, comparison with phone photo, and climax reconciliation."
    },
    {
        "prop_id": "PROP_ADOPTION_RECORD_2013",
        "name": "Giấy tờ bảo lãnh viện phí và hồ sơ nhận con nuôi 2013",
        "format": "Official stamped Vietnamese notarized agreement on legal paper, dated late 2013.",
        "evidence_text": "Biên Bản Thỏa Thuận Bảo Lãnh Nuôi Dưỡng Trẻ Mồ Côi (2013) | Đại diện bảo lãnh: Nguyễn Hoài Nam | Người nhận nuôi hợp pháp: Gia đình hiếm muộn",
        "continuity_notes": "Clean legal paper surface in image prompt, exact legal text rendered via overlay."
    },
    {
        "prop_id": "PROP_BANK_TRANSFER_NOTES",
        "name": "Giấy sao kê / ghi chép các khoản chu cấp làm thêm",
        "format": "Small personal ledger notebook with handwritten dates and monthly amounts from 2013 to 2024.",
        "evidence_text": "Nhật ký chu cấp bé An (2013 - 2024): Tiền làm thêm ca đêm, hỗ trợ học phí và sinh hoạt định kỳ qua tài khoản gia đình nhận nuôi.",
        "continuity_notes": "Demonstrates Nam's ten years of quiet, honest sacrifice."
    }
]

# 45 scenes configuration for EP011
# 15 VIDEO_RECOMMENDED (33.3%), 30 IMAGE_ONLY (66.7%)
# Visual spoiler guard: No depiction of Nam having a romantic relationship with Thảo, and no disclosure of the adoptive family sponsorship before Reveal 1 (Scene 31, Seg 61).
SCENE_SPECS = [
    {
        "scene_id": "SC_001",
        "source_segments": ["001", "002"],
        "narrative_function": "HOOK",
        "location_id": "LOC_KHO_DO_CU",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "props": ["PROP_OLD_PHONE_01"],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P1",
        "visual_mode_reason": "Hook hành động: Linh cắm sạc cho chiếc điện thoại Nokia cũ, màn hình nhấp nháy sáng bừng sau hơn mười năm.",
        "video_prompt": (
            "Start: A 32-year-old Vietnamese woman (CHAR_LINH) in casual home clothes sits at a dusty storage desk holding an old grey feature phone. "
            "Action: Her hands plug the thin cylindrical charging pin into the base of the phone; after a two-second pause, the LCD screen suddenly flickers on. "
            "Camera: Macro close-up on her hands and the phone screen as the pale blue backlight illuminates her fingers. "
            "End: Linh raises the phone toward her eyes with startled curiosity. Domestic storage room lighting."
        ),
        "image_prompt": (
            "Cinematic documentary close-up of a 32-year-old Vietnamese woman (CHAR_LINH) in casual navy clothes plugging a charging cable "
            "into a vintage grey feature phone (PROP_OLD_PHONE_01) in a cozy storage room, the screen illuminating with a soft blue glow, "
            "dust particles in the warm lamplight, realistic skin texture, 35mm lens."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "PHONE_SCREEN", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_002",
        "source_segments": ["003", "004"],
        "narrative_function": "HOOK_SHOCK",
        "location_id": "LOC_KHO_DO_CU",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "props": ["PROP_OLD_PHONE_01"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Khoảnh khắc bàng hoàng tĩnh lặng: Linh sững sờ khi nhìn thấy bức ảnh lạ năm 2012 trên màn hình.",
        "video_prompt": None,
        "image_prompt": (
            "Close-up of a 32-year-old Vietnamese woman (CHAR_LINH), eyes wide in disbelief and growing sorrow, holding the glowing phone, "
            "soft bluish screen light reflecting in her dark pupils, warm domestic shadows around her, photorealistic documentary realism, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "SUBTLE_REFRAME", "speed": "SLOW", "subject_anchor": "LINH_FACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_003",
        "source_segments": ["005", "006"],
        "narrative_function": "HOST_INTRO",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": [],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Thiết lập không gian Sau Cánh Cửa: Căn phòng khách gia đình êm đềm chứa đựng góc khuất thầm lặng.",
        "video_prompt": None,
        "image_prompt": (
            "Cinematic establishing shot of a tasteful Vietnamese apartment living room, sheer white curtains filtering soft afternoon daylight, "
            "a comfortable grey sofa, framed photos on a wooden credenza, quiet domestic harmony, 35mm photography."
        ),
        "image_motion": {"type": "PAN_LEFT", "speed": "SLOW", "subject_anchor": "LIVING_ROOM", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_004",
        "source_segments": ["007", "008"],
        "narrative_function": "MARITAL_HARMONY",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": [],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Bức tranh gia đình hạnh phúc: Khung ảnh cưới 7 năm trước của Linh và Nam trên bàn gỗ.",
        "video_prompt": None,
        "image_prompt": (
            "Close-up of a framed wedding photograph on a wooden credenza: A smiling young Vietnamese couple (Linh and Nam) dressed in elegant wedding attire, "
            "warm natural light catching the glass frame, a small vase of dried lavender beside it, cinematic realism, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "STATIC_INTENTIONAL", "speed": "NORMAL", "subject_anchor": "WEDDING_FRAME", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_005",
        "source_segments": ["009", "010"],
        "narrative_function": "EXPOSITION_LINH_WORK",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Giới thiệu Linh trong công việc thiết kế nội thất tỉ mỉ, trân trọng tổ ấm gia đình.",
        "video_prompt": None,
        "image_prompt": (
            "A 32-year-old Vietnamese woman (CHAR_LINH) in a cream sweater working at an oak drafting table, architectural interior sketches and fabric swatches, "
            "soft natural daylight, thoughtful artistic atmosphere, 35mm lens."
        ),
        "image_motion": {"type": "PAN_RIGHT", "speed": "SLOW", "subject_anchor": "LINH_WORKING", "safe_crop_zone": "CENTER_LEFT"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_006",
        "source_segments": ["011", "012"],
        "narrative_function": "NAM_HOMECOMING",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": ["CHAR_NAM_PRESENT"],
        "story_characters": ["CHAR_NAM_PRESENT", "CHAR_THAO_2012"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P2",
        "visual_mode_reason": "Hành động trở về: Nam đi làm về, bước qua cửa căn hộ, tháo áo khoác bảo hộ với vẻ mệt mỏi nhưng luôn chu đáo.",
        "video_prompt": (
            "Start: A 35-year-old Vietnamese man (CHAR_NAM_PRESENT) enters the apartment doorway carrying a dark engineering work bag. "
            "Action: He sets down his bag, unzips his dark charcoal work jacket, and hangs it neatly on the wooden wall peg, letting out a weary breath. "
            "Camera: Medium tracking shot from living room entrance following him inside, capturing his tired but gentle expression. "
            "End: He turns around toward the living room, offering a soft affectionate smile. Warm evening apartment lighting."
        ),
        "image_prompt": (
            "Medium shot of a 35-year-old Vietnamese man (CHAR_NAM_PRESENT) in a charcoal jacket standing in the entryway of a warm apartment, "
            "taking off his coat, subtle exhaustion around his kind eyes, soft warm domestic hallway light, 35mm documentary realism."
        ),
        "image_motion": {"type": "PAN_LEFT", "speed": "SLOW", "subject_anchor": "NAM_FIGURE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_007",
        "source_segments": ["013", "014"],
        "narrative_function": "STORAGE_CLEANING",
        "location_id": "LOC_KHO_DO_CU",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Linh dọn dẹp các thùng các-tông kỷ vật cũ trong phòng lưu trữ.",
        "video_prompt": None,
        "image_prompt": (
            "A 32-year-old Vietnamese woman (CHAR_LINH) in casual home t-shirt kneeling on the floor of a small storage room, "
            "opening an old cardboard archive box labeled with university mementos, soft warm tungsten lamp illumination, dust specks, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "LINH_AND_BOX", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_008",
        "source_segments": ["015", "016"],
        "narrative_function": "PHONE_GALLERY_SCROLL",
        "location_id": "LOC_KHO_DO_CU",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_YOUNG_2012"],
        "props": ["PROP_OLD_PHONE_01"],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P1",
        "visual_mode_reason": "Hành động tương tác thiết bị: Ngón tay Linh bấm phím điều hướng trên chiếc điện thoại Nokia cũ, màn hình chuyển sang bức ảnh lạ.",
        "video_prompt": (
            "Start: Close macro view of Linh's hand holding the vintage grey Nokia phone. "
            "Action: Her thumb slowly presses the central navigation key; the low-resolution color screen scrolls through photo filenames until an image opens. "
            "Camera: Macro focus on the screen as the 2012 hospital image loads pixel by pixel under her thumb. "
            "End: The photo is fully displayed, her thumb freezing in place as her hand slightly trembles. Warm desk lamplight."
        ),
        "image_prompt": (
            "Macro photography of a Vietnamese woman's hand holding an illuminated vintage feature phone (PROP_OLD_PHONE_01), thumb resting on the keypad, "
            "the screen displaying an authentic 2012 photo of a young man and woman with an infant in a hospital, warm lighting, 35mm lens."
        ),
        "image_motion": {"type": "EVIDENCE_INSPECTION", "speed": "SLOW", "subject_anchor": "PHONE_DISPLAY", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_009",
        "source_segments": ["017", "018"],
        "narrative_function": "EVIDENCE_PHOTO_SCREEN_OVERLAY",
        "location_id": "LOC_KHO_DO_CU",
        "visible_characters": [],
        "story_characters": ["CHAR_NAM_YOUNG_2012", "CHAR_THAO_2012", "CHAR_BE_AN_INFANT_2012"],
        "props": ["PROP_OLD_PHONE_01", "PROP_HOSPITAL_PHOTO_2012"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Chụp cận cảnh màn hình điện thoại hiển thị bức ảnh bệnh viện tỉnh Nam Định năm 2012 kèm lớp phủ thông tin.",
        "video_prompt": None,
        "image_prompt": (
            "Direct top-down macro shot of the vintage feature phone LCD screen (PROP_OLD_PHONE_01), displaying a poignant 2012 Vietnamese hospital snapshot "
            "of young Nam and a young woman (Thảo) holding a newborn infant, soft pixel grid texture of vintage display, clean documentary focus, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "EVIDENCE_INSPECTION", "speed": "SLOW", "subject_anchor": "SCREEN_CENTER", "safe_crop_zone": "CENTER"},
        "requires_overlay": True,
        "overlay_data": {
            "overlay_type": "PHONE_SCREEN",
            "overlay_text": "HÌNH ẢNH: 12/08/2012 - 14:25\nĐịa điểm: Khoa Sản - Bệnh viện Đa khoa Tỉnh Nam Định\nChi tiết: Nam bế bé sơ sinh bên cạnh sản phụ trẻ",
            "overlay_position": "LOWER_THIRD",
            "font_style": "CLEAN_SERIF_DOCUMENTARY"
        }
    },
    {
        "scene_id": "SC_010",
        "source_segments": ["019", "020"],
        "narrative_function": "BEWILDERMENT",
        "location_id": "LOC_KHO_DO_CU",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH"],
        "props": ["PROP_OLD_PHONE_01"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Cảm xúc hoang mang bắt đầu xâm chiếm: Linh ngồi bất động nhìn chiếc điện thoại trên bàn.",
        "video_prompt": None,
        "image_prompt": (
            "Medium shot of a 32-year-old Vietnamese woman (CHAR_LINH) seated at the storage desk, hands clasped tightly under her chin, "
            "gazing at the glowing phone with deep confusion and heart-wrenching suspicion, warm tungsten shadows, 35mm film."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "LINH_FACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_011",
        "source_segments": ["021", "022"],
        "narrative_function": "EVIDENCE_CALL_LOG_OVERLAY",
        "location_id": "LOC_KHO_DO_CU",
        "visible_characters": [],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "props": ["PROP_OLD_PHONE_01"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Hiển thị chứng cứ nhật ký cuộc gọi: Danh bạ lưu tên 'Công việc' với các cuộc gọi đêm muộn và cuối tuần.",
        "video_prompt": None,
        "image_prompt": (
            "Macro photography of the vintage feature phone screen displaying a call log menu in Vietnamese, monochrome/color low-res font listing incoming "
            "and outgoing calls under contact name 'Cong Viec', clean documentary angle, soft warm backlighting, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "EVIDENCE_INSPECTION", "speed": "SLOW", "subject_anchor": "CALL_LOG", "safe_crop_zone": "CENTER"},
        "requires_overlay": True,
        "overlay_data": {
            "overlay_type": "PHONE_SCREEN",
            "overlay_text": "NHẬT KÝ CUỘC GỌI: 'CÔNG VIỆC'\n23:45 - Cuộc gọi đi (12 phút)\nThứ Bảy, 22:15 - Cuộc gọi nhỡ (3 lần)\nGhi chú: Tần suất liên tục vào ban đêm & cuối tuần",
            "overlay_position": "LOWER_THIRD",
            "font_style": "CLEAN_SERIF_DOCUMENTARY"
        }
    },
    {
        "scene_id": "SC_012",
        "source_segments": ["023", "024"],
        "narrative_function": "SECRET_VIBRATION",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P2",
        "visual_mode_reason": "Tình huống căng thẳng gia đình: Nam ngồi làm việc ở bàn ăn, điện thoại rung lên trong đêm, Linh kín đáo quan sát từ cửa phòng.",
        "video_prompt": (
            "Start: Nam (35, male) sits at the dining table with a laptop, the room lit only by the screen and a dining pendant lamp. "
            "Action: His phone buzzes silently on the wood; he checks the caller ID with a fleeting look of tension and promptly flips the phone face down. "
            "Camera: Slow pan from Linh's shadowed face watching in silence from the hallway doorway over to Nam's tense back. "
            "End: Nam takes a deep breath and types on his keyboard. Intimate low-key evening domestic lighting."
        ),
        "image_prompt": (
            "Atmospheric low-key shot of a modern Vietnamese apartment at night: A 35-year-old man (CHAR_NAM_PRESENT) at a dining table "
            "turning his phone screen-down, while in the shadowed foreground doorway, a 32-year-old woman (CHAR_LINH) watches quietly, cinematic realism, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "PAN_LEFT", "speed": "SLOW", "subject_anchor": "NAM_AND_LINH", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_013",
        "source_segments": ["025", "026"],
        "narrative_function": "FALSE_LEAD_FAIRNESS",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Nghi vấn hợp lý (False Lead Fairness): Linh đứng bên cửa sổ ban đêm, cảm giác bị phản bội dâng trào nhưng không bịa đặt hình ảnh sai sự thật.",
        "video_prompt": None,
        "image_prompt": (
            "A 32-year-old Vietnamese woman (CHAR_LINH) standing by the apartment balcony window at night, city lights blurred outside, "
            "tears shining in her eyes, arms wrapped around herself defensively, raw emotional pain, 35mm lens."
        ),
        "image_motion": {"type": "SLOW_PULL_OUT", "speed": "SLOW", "subject_anchor": "LINH_FIGURE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_014",
        "source_segments": ["027", "028"],
        "narrative_function": "DRAWER_SEARCH",
        "location_id": "LOC_KHO_DO_CU",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P2",
        "visual_mode_reason": "Hành động điều tra: Linh quay lại kho đồ cũ, kéo ngăn kéo bàn gỗ tìm kiếm thêm vật chứng của Nam.",
        "video_prompt": (
            "Start: A 32-year-old Vietnamese woman (CHAR_LINH) stands in front of the vintage desk in the storage room. "
            "Action: She slowly slides the wooden desk drawer all the way open, carefully moving aside old certificates and student notebooks. "
            "Camera: Overhead medium close-up tracking into the opening drawer. "
            "End: Her hand discovers a small red velvet drawstring pouch tucked in the back corner. Consistent warm storage lighting."
        ),
        "image_prompt": (
            "Medium shot of a 32-year-old Vietnamese woman (CHAR_LINH) searching through the open wooden drawer of an old desk, "
            "discovering a small red velvet pouch among old student certificates and papers, warm overhead lamp light, 35mm."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "DRAWER_INTERIOR", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_015",
        "source_segments": ["029", "030"],
        "narrative_function": "DISCOVERY_SILVER_BRACELET",
        "location_id": "LOC_KHO_DO_CU",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH"],
        "props": ["PROP_SILVER_BRACELET"],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P1",
        "visual_mode_reason": "Hành động mở kỷ vật: Linh nhẹ nhàng kéo dây túi nhung và nhấc chiếc vòng bạc trẻ em ra ánh sáng.",
        "video_prompt": (
            "Start: Linh's hands gently hold the small red velvet pouch over the wooden desk. "
            "Action: Her fingers loosen the drawstring and tip the pouch, letting a small polished silver baby bracelet slide into her palm. "
            "Camera: Extreme close-up on her palm as the silver bracelet catches the warm lamplight, turning it to inspect the engraving. "
            "End: She lifts the bracelet close to her eyes, reading the engraved letters. Soft warm lamp illumination."
        ),
        "image_prompt": (
            "Close-up of a delicate polished sterling silver baby bracelet (PROP_SILVER_BRACELET) resting in the open palm of a 32-year-old "
            "Vietnamese woman (CHAR_LINH), fine engraved inscription catching the light, emotional tension, 35mm macro lens."
        ),
        "image_motion": {"type": "EVIDENCE_INSPECTION", "speed": "SLOW", "subject_anchor": "BRACELET_PALM", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_016",
        "source_segments": ["031", "032"],
        "narrative_function": "EVIDENCE_BRACELET_ENGRAVING_OVERLAY",
        "location_id": "LOC_KHO_DO_CU",
        "visible_characters": [],
        "story_characters": ["CHAR_LINH"],
        "props": ["PROP_SILVER_BRACELET", "PROP_OLD_PHONE_01"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Chụp cận cảnh chiếc vòng bạc khắc tên 'An - 15/08/2013' đặt cạnh chiếc điện thoại Nokia kèm lớp phủ văn bản.",
        "video_prompt": None,
        "image_prompt": (
            "Macro still life photography of the small silver baby bracelet (PROP_SILVER_BRACELET) placed neatly beside the vintage feature phone "
            "(PROP_OLD_PHONE_01) on dark aged Vietnamese wood, clear sharp focus on the silver band and phone casing, warm directional light, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "EVIDENCE_INSPECTION", "speed": "SLOW", "subject_anchor": "BRACELET_DETAILS", "safe_crop_zone": "CENTER"},
        "requires_overlay": True,
        "overlay_data": {
            "overlay_type": "DOCUMENT",
            "overlay_text": "KỶ VẬT KHẮC TÊN:\n'An - 15/08/2013'\nVòng tay bạc trẻ em sơ sinh\nĐối chiếu: Trùng khớp mốc thời gian sau bức ảnh bệnh viện",
            "overlay_position": "LOWER_THIRD",
            "font_style": "CLEAN_SERIF_DOCUMENTARY"
        }
    },
    {
        "scene_id": "SC_017",
        "source_segments": ["033", "034"],
        "narrative_function": "CALENDAR_AND_SUSPICION",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Linh đối chiếu các khoản chi tiêu chuyển khoản định kỳ và những chuyến đi về quê của Nam trong sổ tay.",
        "video_prompt": None,
        "image_prompt": (
            "A 32-year-old Vietnamese woman (CHAR_LINH) seated at the dining table with a desk calendar and personal expense ledger, "
            "pen in hand, calculating recurring monthly dates, deeply troubled and anxious expression, afternoon window light, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "PAN_RIGHT", "speed": "SLOW", "subject_anchor": "LINH_AND_NOTEBOOK", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_018",
        "source_segments": ["035", "036"],
        "narrative_function": "TEARS_AND_RESOLVE",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P2",
        "visual_mode_reason": "Chuyển biến tâm lý: Linh lau giọt nước mắt lăn trên má, đứng dậy quyết tâm đi tìm chân tướng sự thật trước khi đối chất.",
        "video_prompt": (
            "Start: A 32-year-old Vietnamese woman (CHAR_LINH) sits with head in hands at the dining table, tears falling. "
            "Action: She raises her head, wipes the tear from her cheek with her sleeve, takes a deep breath, and stands up with resolute posture. "
            "Camera: Close-up slowly zooming out to medium shot, capturing the shift from despair to determination. "
            "End: She packs her notebook and travel bag. Soft natural daylight."
        ),
        "image_prompt": (
            "Cinematic close-up of a 32-year-old Vietnamese woman (CHAR_LINH) wiping a tear from her cheek, resolute and determined gaze, "
            "natural lighting framing her face, dignified vulnerability, 35mm film."
        ),
        "image_motion": {"type": "SUBTLE_REFRAME", "speed": "SLOW", "subject_anchor": "LINH_FACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_019",
        "source_segments": ["037", "038"],
        "narrative_function": "JOURNEY_NAM_DINH",
        "location_id": "LOC_BENH_VIEN_NAM_DINH_2012",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P2",
        "visual_mode_reason": "Hành trình thực địa: Linh đi xe khách về Nam Định, bước xuống xe và đi bộ về phía bệnh viện tỉnh trong sương sớm.",
        "video_prompt": (
            "Start: An intercity passenger coach pulls up to a bus stop near Nam Định provincial hospital. "
            "Action: Linh (32, female) in an olive trench coat steps down from the bus carrying her shoulder bag, walking purposefully down the street toward the hospital gate. "
            "Camera: Medium tracking shot following her stride past provincial shops and motorbikes. "
            "End: She pauses before the hospital entrance sign, taking a steadying breath. Overcast daylight."
        ),
        "image_prompt": (
            "Documentary exterior shot of a 32-year-old Vietnamese woman (CHAR_LINH) in an olive trench coat walking past the front gate "
            "of Nam Định provincial hospital, quiet northern Vietnamese provincial street in the morning, realistic atmospheric depth, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "PAN_LEFT", "speed": "SLOW", "subject_anchor": "LINH_WALKING", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_020",
        "source_segments": ["039", "040"],
        "narrative_function": "HOSPITAL_CORRIDOR_SEARCH",
        "location_id": "LOC_BENH_VIEN_NAM_DINH_2012",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P1",
        "visual_mode_reason": "Hành động điều tra hiện trường: Linh bước đi dọc hành lang bệnh viện tỉnh, tiến lại quầy lưu trữ hồ sơ y tế.",
        "video_prompt": (
            "Start: Linh (32, female) walks down the echoing mint-green corridor of the provincial hospital. "
            "Action: She walks past consultation room doors, approaches the nurses' administrative counter, and takes out the phone from her bag. "
            "Camera: Steady forward tracking shot leading her down the corridor, capturing the authentic provincial hospital environment. "
            "End: She stops before a senior nurse at the counter, politely greeting her. Cool fluorescent overhead hospital lighting."
        ),
        "image_prompt": (
            "Medium shot of a 32-year-old Vietnamese woman (CHAR_LINH) walking through the mint-green hallway of a provincial public hospital "
            "in Nam Định, holding her bag, cool fluorescent lighting, authentic Vietnamese public medical facility, 35mm lens."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "LINH_CORRIDOR", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_021",
        "source_segments": ["041", "042"],
        "narrative_function": "NURSE_TESTIMONY",
        "location_id": "LOC_BENH_VIEN_NAM_DINH_2012",
        "visible_characters": ["CHAR_LINH", "CHAR_NURSE_OLD"],
        "story_characters": ["CHAR_LINH", "CHAR_NURSE_OLD", "CHAR_THAO_2012", "CHAR_NAM_PRESENT"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Cuộc trao đổi xúc động: Y tá già nhận ra thông tin về cô gái tên Thảo từng sinh con và qua đời sau tai biến.",
        "video_prompt": None,
        "image_prompt": (
            "Medium two-shot of an experienced 58-year-old Vietnamese hospital nurse (CHAR_NURSE_OLD) in white uniform speaking with compassionate solemnity "
            "to a 32-year-old woman (CHAR_LINH) across a wooden hospital counter, medical archive binders in background, fluorescent light, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "STATIC_INTENTIONAL", "speed": "NORMAL", "subject_anchor": "NURSE_AND_LINH", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_022",
        "source_segments": ["043", "044"],
        "narrative_function": "CLUES_DEEPENING",
        "location_id": "LOC_BENH_VIEN_NAM_DINH_2012",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Linh đứng ngoài cổng bệnh viện cầm mảnh giấy ghi địa chỉ nhà cũ của Thảo ở ngoại ô.",
        "video_prompt": None,
        "image_prompt": (
            "Medium shot of a 32-year-old Vietnamese woman (CHAR_LINH) standing outside the hospital building, looking at a handwritten address note "
            "in her hand, thoughtful and complex expression as the puzzle pieces shift, overcast provincial morning sky, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "SUBTLE_REFRAME", "speed": "SLOW", "subject_anchor": "LINH_FACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_023",
        "source_segments": ["045", "046"],
        "narrative_function": "SUBURBAN_ARRIVAL",
        "location_id": "LOC_NHA_CU_THAO_NGOAI_O",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P2",
        "visual_mode_reason": "Hành động tiếp cận: Linh đi bộ dọc con ngõ gạch đỏ ngoại ô Nam Định, đẩy cánh cổng sắt nhỏ bước vào sân nhà Thảo.",
        "video_prompt": (
            "Start: Linh (32, female) walks down a quiet narrow village lane lined with weathered brick walls in suburban Nam Định. "
            "Action: She reaches a small rusted iron gate, pushes it open with a soft metallic creak, and steps into the quiet overgrown courtyard. "
            "Camera: Low tracking shot moving forward with her, showing the mossy bricks and rustic single-story house facade. "
            "End: She walks up to the wooden front door, pausing respectfully before turning the latch. Soft misty daylight."
        ),
        "image_prompt": (
            "A 32-year-old Vietnamese woman (CHAR_LINH) in an olive trench coat walking into the courtyard of an old brick village house "
            "in suburban Nam Định, overgrown moss, potted plants, quiet northern Vietnamese rural atmosphere, 35mm photography."
        ),
        "image_motion": {"type": "PAN_RIGHT", "speed": "SLOW", "subject_anchor": "LINH_FIGURE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_024",
        "source_segments": ["047", "048"],
        "narrative_function": "ENTER_THAO_ROOM",
        "location_id": "LOC_NHA_CU_THAO_NGOAI_O",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P1",
        "visual_mode_reason": "Hành động khám phá mấu chốt: Linh bước vào căn phòng nhỏ im lìm, mở chiếc hộp kỷ vật trên bàn gỗ chứa đầy giấy tờ quan trọng.",
        "video_prompt": (
            "Start: Linh (32, female) steps quietly into a dimly lit rural bedroom where dust motes float in shafts of sunlight. "
            "Action: She approaches the wooden writing desk, gently lifts the lid of a tin keepsake box, and reveals stacked old letters and documents. "
            "Camera: Medium shot panning down from her respectful face to her hands lifting the box lid. "
            "End: Her fingers carefully touch an official notarized legal paper inside. Warm diffused window light."
        ),
        "image_prompt": (
            "Medium shot of a 32-year-old Vietnamese woman (CHAR_LINH) inside a quiet rustic room in Nam Định, opening a vintage keepsake box "
            "on a wooden table, soft shafts of sunlight illuminating floating dust, atmosphere of preserved history, 35mm lens."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "KEEPSAKE_BOX", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_025",
        "source_segments": ["049", "050"],
        "narrative_function": "EVIDENCE_ADOPTION_DRAFT_OVERLAY",
        "location_id": "LOC_NHA_CU_THAO_NGOAI_O",
        "visible_characters": [],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_YOUNG_2012"],
        "props": ["PROP_ADOPTION_RECORD_2013"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Chụp cận cảnh hồ sơ thỏa thuận hỗ trợ y tế & bảo lãnh nuôi dưỡng năm 2013 mang chữ ký của Nam kèm lớp phủ văn bản.",
        "video_prompt": None,
        "image_prompt": (
            "Macro shot of an official 2013 Vietnamese medical and guardianship agreement paper, typed formal layout, blue ink signatures, "
            "notary stamp in red ink, resting on dark weathered wood, soft natural window light, sharp documentary focus, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "EVIDENCE_INSPECTION", "speed": "SLOW", "subject_anchor": "LEGAL_DOCUMENT", "safe_crop_zone": "CENTER"},
        "requires_overlay": True,
        "overlay_data": {
            "overlay_type": "DOCUMENT",
            "overlay_text": "BIÊN BẢN BẢO LÃNH VIỆN PHÍ & HỒ SƠ CON NUÔI (2013)\nNgười đại diện bảo lãnh: Nguyễn Hoài Nam\nNội dung: Cam kết hỗ trợ chi phí và tìm gia đình nhận nuôi hợp pháp",
            "overlay_position": "LOWER_THIRD",
            "font_style": "CLEAN_SERIF_DOCUMENTARY"
        }
    },
    {
        "scene_id": "SC_026",
        "source_segments": ["051", "052"],
        "narrative_function": "NAM_HANDWRITTEN_LETTER",
        "location_id": "LOC_NHA_CU_THAO_NGOAI_O",
        "visible_characters": [],
        "story_characters": ["CHAR_NAM_YOUNG_2012", "CHAR_THAO_2012"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Cận cảnh bức thư tay đầy giằng xé và trách nhiệm của Nam gửi lại bên giường bệnh.",
        "video_prompt": None,
        "image_prompt": (
            "Macro photography of a handwritten letter in Vietnamese, blue ballpoint pen on lined paper, sincere emotional handwriting, "
            "slight creases where tears once fell, resting on rustic wooden desk, soft warm sidelight, 35mm lens."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "LETTER_TEXT", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_027",
        "source_segments": ["053", "054"],
        "narrative_function": "ADOPTIVE_FAMILY_RECORD",
        "location_id": "LOC_NHA_CU_THAO_NGOAI_O",
        "visible_characters": [],
        "story_characters": ["CHAR_NAM_YOUNG_2012", "CHAR_BE_AN_INFANT_2012"],
        "props": ["PROP_ADOPTION_RECORD_2013"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Hồ sơ xác nhận gia đình hiếm muộn nhận nuôi bé An: Nam chỉ đóng vai trò người bảo lãnh danh dự.",
        "video_prompt": None,
        "image_prompt": (
            "Macro shot of legal adoption consent papers dated late 2013, clean official Vietnamese administrative formatting, red circular seals, "
            "documenting the formal legal adoption of infant An by a loving infertile family, documentary realism, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "PAN_LEFT", "speed": "SLOW", "subject_anchor": "DOCUMENT_SEALS", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_028",
        "source_segments": ["055", "056"],
        "narrative_function": "WALL_CRUMBLES",
        "location_id": "LOC_NHA_CU_THAO_NGOAI_O",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Bức tường nghi ngờ sụp đổ hoàn toàn: Linh ôm tập thư vào ngực, bàng hoàng nhận ra tấm lòng cao thượng của chồng.",
        "video_prompt": None,
        "image_prompt": (
            "Medium close-up of a 32-year-old Vietnamese woman (CHAR_LINH) pressing the letters against her chest, eyes closed, tears streaming "
            "down her cheeks in overwhelming relief, profound empathy, and awe, soft window light, 35mm film."
        ),
        "image_motion": {"type": "STATIC_INTENTIONAL", "speed": "NORMAL", "subject_anchor": "LINH_FACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_029",
        "source_segments": ["057", "058"],
        "narrative_function": "MEMORY_THAO_PEACE",
        "location_id": "LOC_BENH_VIEN_NAM_DINH_2012",
        "visible_characters": ["CHAR_THAO_2012"],
        "story_characters": ["CHAR_THAO_2012", "CHAR_NAM_YOUNG_2012"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Ký ức năm 2012: Thảo mỉm cười thanh thản trên giường bệnh, trao gửi niềm tin tuyệt đối nơi người anh họ.",
        "video_prompt": None,
        "image_prompt": (
            "Archival memory portrait of a 21-year-old Vietnamese young woman (CHAR_THAO_2012) in a pale hospital gown resting against pillows, "
            "serene maternal smile, holding a swaddled newborn, soft natural morning window light, subtle 2012 documentary grain, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "SLOW_PULL_OUT", "speed": "SLOW", "subject_anchor": "THAO_FIGURE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_030",
        "source_segments": ["059", "060"],
        "narrative_function": "YOUNG_NAM_GRIEF",
        "location_id": "LOC_BENH_VIEN_NAM_DINH_2012",
        "visible_characters": ["CHAR_NAM_YOUNG_2012"],
        "story_characters": ["CHAR_NAM_YOUNG_2012"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P1",
        "visual_mode_reason": "Tái hiện quá khứ 2013: Nam trẻ tuổi ngồi ôm đầu tuyệt vọng ngoài hành lang phòng cấp cứu khi Thảo qua đời, tự hứa sẽ lo cho đứa bé.",
        "video_prompt": (
            "Start: Young Nam (23, male) sits alone on a cold wooden bench in a dimly lit hospital corridor at night. "
            "Action: He buries his face in his hands, trembling with silent grief, then slowly looks up with tear-streaked eyes, clenching his fists in resolve. "
            "Camera: Low dolly shot moving slowly toward him as hospital staff walk past in the distant background. "
            "End: He stands up slowly, walking toward the nursery glass window. Cool fluorescent hospital lighting."
        ),
        "image_prompt": (
            "Dramatic archival memory shot from 2013: A 23-year-old Vietnamese young man (CHAR_NAM_YOUNG_2012) sitting on a hospital bench outside an intensive care ward, "
            "head in hands, raw sorrow and immense moral burden, cool flickering fluorescent light, 35mm documentary realism."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "YOUNG_NAM", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_031",
        "source_segments": ["061", "062"],
        "narrative_function": "REVEAL_1_TRUTH",
        "location_id": "LOC_NHA_CU_THAO_NGOAI_O",
        "visible_characters": [],
        "story_characters": ["CHAR_NAM_YOUNG_2012", "CHAR_THAO_2012", "CHAR_BE_AN_INFANT_2012"],
        "props": ["PROP_ADOPTION_RECORD_2013", "PROP_SILVER_BRACELET"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "BƯỚC NGOẶT 1 (REVEAL 1): Nam không phải cha ruột, Thảo là em họ mồ côi đã mất; Nam đứng ra bảo lãnh hồ sơ nhận nuôi cho gia đình hiếm muộn. IMAGE_ONLY tĩnh lặng để giọng đọc chiếm trọn cao trào.",
        "video_prompt": None,
        "image_prompt": (
            "Solemn macro still life of the official 2013 Vietnamese adoption guardianship certificate bearing Nam's signature (PROP_ADOPTION_RECORD_2013), "
            "the silver baby bracelet 'An - 15/08/2013' resting on top of the legal seal, bathed in warm reverent sunlight, 35mm film."
        ),
        "image_motion": {"type": "EVIDENCE_INSPECTION", "speed": "SLOW", "subject_anchor": "DOCUMENT_AND_BRACELET", "safe_crop_zone": "CENTER"},
        "requires_overlay": True,
        "overlay_data": {
            "overlay_type": "DOCUMENT",
            "overlay_text": "BƯỚC NGOẶT 1 (XÁC MINH SỰ THẬT):\nNgười trong ảnh: Thảo (Em họ mồ côi của Nam, mất năm 2013)\nNam đứng ra làm người bảo lãnh pháp lý cho gia đình hiếm muộn nhận nuôi bé An",
            "overlay_position": "LOWER_THIRD",
            "font_style": "CLEAN_SERIF_DOCUMENTARY"
        }
    },
    {
        "scene_id": "SC_032",
        "source_segments": ["063", "064"],
        "narrative_function": "PURE_DEVOTION",
        "location_id": "LOC_NHA_CU_THAO_NGOAI_O",
        "visible_characters": [],
        "story_characters": ["CHAR_NAM_PRESENT", "CHAR_THAO_2012"],
        "props": ["PROP_SILVER_BRACELET"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Biểu tượng của tình yêu thương và lời hứa không vụ lợi: Chiếc vòng bạc tỏa sáng dưới ánh nắng chiều.",
        "video_prompt": None,
        "image_prompt": (
            "Artistic close-up of the small engraved silver bracelet resting on weathered red Vietnamese brick, soft warm sunlight gleaming on the metal, "
            "symbolizing pure selfless devotion and an unbroken promise, cinematic documentary realism, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "STATIC_INTENTIONAL", "speed": "NORMAL", "subject_anchor": "SILVER_BRACELET", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_033",
        "source_segments": ["065", "066"],
        "narrative_function": "MEMORY_NAM_HOLDING_BABY",
        "location_id": "LOC_BENH_VIEN_NAM_DINH_2012",
        "visible_characters": ["CHAR_NAM_YOUNG_2012", "CHAR_BE_AN_INFANT_2012"],
        "story_characters": ["CHAR_NAM_YOUNG_2012", "CHAR_BE_AN_INFANT_2012"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Ký ức năm 2013: Nam trẻ tuổi bế đứa trẻ sơ sinh đỏ hỏn trong vòng tay với ánh mắt nguyện chở che.",
        "video_prompt": None,
        "image_prompt": (
            "Emotional archival documentary photo from 2013: A 23-year-old Vietnamese young man (CHAR_NAM_YOUNG_2012) gently cradling a newborn baby "
            "swaddled in yellow flannel in a quiet hospital room, eyes glistening with tears of protective love, soft natural light, 35mm."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "NAM_AND_BABY", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_034",
        "source_segments": ["067", "068"],
        "narrative_function": "EVIDENCE_TRANSFERS_OVERLAY",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": [],
        "story_characters": ["CHAR_NAM_PRESENT"],
        "props": ["PROP_BANK_TRANSFER_NOTES"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Hiển thị chứng từ chuyển khoản và sao kê mười năm chắt chiu tiền làm thêm của Nam gửi nuôi dưỡng bé An.",
        "video_prompt": None,
        "image_prompt": (
            "Macro photography of a personal savings ledger and Vietnamese bank transaction slips spread on an oak table, handwritten records of regular monthly "
            "support payments over ten years, official blue stamps, soft warm domestic lighting, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "EVIDENCE_INSPECTION", "speed": "SLOW", "subject_anchor": "TRANSACTION_SLIPS", "safe_crop_zone": "CENTER"},
        "requires_overlay": True,
        "overlay_data": {
            "overlay_type": "TRANSACTION",
            "overlay_text": "SAO KÊ HỖ TRỢ NUÔI DƯỠNG (2013 - 2024)\nKhoản trích: Thu nhập từ các ca làm thêm kỹ thuật ban đêm\nMục đích: Chi phí học tập & sinh hoạt cho bé An qua gia đình nhận nuôi",
            "overlay_position": "LOWER_THIRD",
            "font_style": "CLEAN_SERIF_DOCUMENTARY"
        }
    },
    {
        "scene_id": "SC_035",
        "source_segments": ["069", "070"],
        "narrative_function": "LATE_NIGHT_WORK_MEMORY",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": ["CHAR_NAM_PRESENT"],
        "story_characters": ["CHAR_NAM_PRESENT"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Ký ức Nam làm việc cật lực thâu đêm tại bàn máy tính để có thêm thu nhập chu cấp, gánh vác trong lặng lẽ.",
        "video_prompt": None,
        "image_prompt": (
            "Atmospheric documentary scene: A 35-year-old Vietnamese engineer (CHAR_NAM_PRESENT) working late into the night at a computer workstation, "
            "desk illuminated by a single warm desk lamp, technical blueprints and coffee mug, exhausted yet steadfast expression, 35mm."
        ),
        "image_motion": {"type": "PAN_LEFT", "speed": "SLOW", "subject_anchor": "NAM_WORKING", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_036",
        "source_segments": ["071", "072"],
        "narrative_function": "LINH_COMPASSIONATE_TEARS",
        "location_id": "LOC_NHA_CU_THAO_NGOAI_O",
        "visible_characters": ["CHAR_LINH"],
        "story_characters": ["CHAR_LINH"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Linh ngồi giữa những lá thư và giấy tờ, không còn một chút giận hờn, chỉ còn lòng khâm phục và xót xa cho chồng.",
        "video_prompt": None,
        "image_prompt": (
            "Medium close-up of a 32-year-old Vietnamese woman (CHAR_LINH) sitting in the quiet room, a tender compassionate smile emerging through tears, "
            "warm golden sunlight breaking through the wooden shutters onto her face, emotional catharsis, 35mm lens."
        ),
        "image_motion": {"type": "SUBTLE_REFRAME", "speed": "SLOW", "subject_anchor": "LINH_FACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_037",
        "source_segments": ["073", "074"],
        "narrative_function": "DUSK_WAITING",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": [],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Căn hộ lúc hoàng hôn: Linh đã trở về Hà Nội, chuẩn bị bước vào cuộc nói chuyện chân thành nhất cuộc đời.",
        "video_prompt": None,
        "image_prompt": (
            "Interior establishing shot of the Vietnamese apartment living room at twilight, warm table lamp glowing, tea pot steeping, "
            "outside window showing the deep blue evening sky of Hanoi, peaceful contemplative suspense, 35mm photography."
        ),
        "image_motion": {"type": "PAN_RIGHT", "speed": "SLOW", "subject_anchor": "TWILIGHT_ROOM", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_038",
        "source_segments": ["075", "076"],
        "narrative_function": "CONFRONTATION_DOORWAY",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "props": ["PROP_SILVER_BRACELET", "PROP_OLD_PHONE_01"],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P1",
        "visual_mode_reason": "Khoảnh khắc đối đầu cao trào: Nam bước vào nhà, thấy Linh đang đứng đợi bên bàn cùng chiếc điện thoại và vòng bạc.",
        "video_prompt": (
            "Start: Nam (35, male) enters the apartment carrying his work bag, stopping dead in his tracks. "
            "Action: Linh (32, female) stands up slowly from the dining table where the old phone and silver bracelet rest; she looks at him with moist, earnest eyes. "
            "Camera: Medium two-shot steadily pushing in toward Nam as his bag slips from his hand and his face turns pale. "
            "End: Nam takes a trembling step forward, his voice choked. Intimate warm evening domestic lighting."
        ),
        "image_prompt": (
            "Medium two-shot in a warm apartment living room: A 35-year-old Vietnamese man (CHAR_NAM_PRESENT) frozen at the entrance, "
            "while his 32-year-old wife (CHAR_LINH) stands by the table holding the silver bracelet, intense emotional truth, 35mm documentary."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "NAM_AND_LINH", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_039",
        "source_segments": ["077", "078"],
        "narrative_function": "REVEAL_2_EMOTIONAL_TRUTH",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "BƯỚC NGOẶT 2 (REVEAL 2): Bản chất sự việc được làm sáng tỏ trọn vẹn: Nam thú nhận mặc cảm nghèo khó và lời hứa bên giường bệnh; Linh trách giận sự giấu giếm nhưng mở lòng thấu hiểu.",
        "video_prompt": None,
        "image_prompt": (
            "Emotional medium two-shot: A 35-year-old Vietnamese man (CHAR_NAM_PRESENT) seated with head bowed in raw vulnerability, "
            "while his wife (CHAR_LINH) stands beside him, one hand resting gently on his shoulder, both faces marked by honest tears, 35mm film."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "COUPLE_EMBRACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_040",
        "source_segments": ["079", "080"],
        "narrative_function": "HOLDING_HANDS_RECONCILIATION",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P2",
        "visual_mode_reason": "Hành động hàn gắn: Linh ngồi xuống đối diện Nam, nắm chặt đôi bàn tay chai sần của chồng qua bàn ăn.",
        "video_prompt": (
            "Start: Nam and Linh sit opposite each other across the wooden dining table, tearful and silent. "
            "Action: Linh reaches both hands across the table, firmly grasping Nam's trembling hands; Nam looks up into her eyes, breaking into a tearful, relieved nod. "
            "Camera: Close-up on their clasped hands with wedding rings, slowly tilting up to their connected gazes. "
            "End: Nam brings her hands to his forehead in deep gratitude. Soft warm indoor lamplight."
        ),
        "image_prompt": (
            "Close-up of two pairs of Vietnamese hands clasped tightly across a wooden dining table, silver wedding rings catching warm domestic lamplight, "
            "symbolizing forgiveness, shared responsibility, and renewed marital trust, 35mm macro lens."
        ),
        "image_motion": {"type": "STATIC_INTENTIONAL", "speed": "NORMAL", "subject_anchor": "HANDS_CLASPED", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_041",
        "source_segments": ["081", "082"],
        "narrative_function": "MARRIAGE_REFLECTION",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": [],
        "story_characters": [],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Chiêm nghiệm Sau Cánh Cửa: Hôn nhân cần sự bao dung đi đôi với sự minh bạch từ nay về sau.",
        "video_prompt": None,
        "image_prompt": (
            "Artistic still life on an oak credenza in a Vietnamese home: Two ceramic cups of tea with steam rising in morning sunlight, beside a small green succulent, "
            "atmosphere of healing, honesty, and peaceful domestic dawn, cinematic realism, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "PAN_LEFT", "speed": "SLOW", "subject_anchor": "TEA_CUPS", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_042",
        "source_segments": ["083", "084"],
        "narrative_function": "LOOKING_AT_AN_ALBUM",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT"],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT", "CHAR_BE_AN_PRESENT"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Vợ chồng cùng nhau xem những bức ảnh trưởng thành của bé An qua từng năm tháng do gia đình nhận nuôi gửi tặng.",
        "video_prompt": None,
        "image_prompt": (
            "Medium two-shot of a 32-year-old Vietnamese woman (CHAR_LINH) and a 35-year-old Vietnamese man (CHAR_NAM_PRESENT) sitting together on the sofa, "
            "smiling warmly as they look at photos of a growing cheerful schoolgirl (An), soft morning daylight, harmonious love, 35mm."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "COUPLE_ALBUM", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_043",
        "source_segments": ["085", "086"],
        "narrative_function": "MEETING_AN_CAFE",
        "location_id": "LOC_CONG_VIEN_CHIEU",
        "visible_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT", "CHAR_BE_AN_PRESENT"],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT", "CHAR_BE_AN_PRESENT"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Gặp gỡ bé An: Linh và Nam ngồi trò chuyện cùng bé An tại quán cà phê sân vườn rợp bóng cây, sự gắn kết tự nhiên.",
        "video_prompt": None,
        "image_prompt": (
            "A cheerful 11-year-old Vietnamese schoolgirl (CHAR_BE_AN_PRESENT) smiling brightly across a garden cafe table toward Linh and Nam, "
            "warm golden sunshine through green foliage, atmosphere of openhearted acceptance and family extension, 35mm lens."
        ),
        "image_motion": {"type": "SUBTLE_REFRAME", "speed": "SLOW", "subject_anchor": "AN_AND_COUPLE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_044",
        "source_segments": ["087", "088"],
        "narrative_function": "PARK_WALK_TOGETHER",
        "location_id": "LOC_CONG_VIEN_CHIEU",
        "visible_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT", "CHAR_BE_AN_PRESENT"],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT", "CHAR_BE_AN_PRESENT"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P1",
        "visual_mode_reason": "Hành động kết thúc ấm áp: Ba người (Linh, Nam, và bé An) cùng nhau đi dạo trong công viên dưới ánh nắng chiều dịu dàng.",
        "video_prompt": (
            "Start: Linh (32, female), Nam (35, male), and 11-year-old An walk side by side along an urban park pathway beside a lake. "
            "Action: An skips cheerfully between them holding both their hands; Nam looks down at An with a joyful smile, while Linh exchanges a loving look with Nam. "
            "Camera: Wide tracking shot moving backwards ahead of the three, framing them against shimmering lake water and golden trees. "
            "End: They continue walking into the soft golden sunset. Warm, tranquil golden hour lighting."
        ),
        "image_prompt": (
            "Wide cinematic shot of a Vietnamese family trio: A 32-year-old woman (CHAR_LINH), a 35-year-old man (CHAR_NAM_PRESENT), and an 11-year-old girl "
            "(CHAR_BE_AN_PRESENT) walking together along a tree-lined lakeside park in Hanoi, golden hour amber sunlight, authentic heartwarming closure, 35mm."
        ),
        "image_motion": {"type": "PAN_RIGHT", "speed": "SLOW", "subject_anchor": "FAMILY_TRIO", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_045",
        "source_segments": ["089", "090"],
        "narrative_function": "FINAL_FAREWELL",
        "location_id": "LOC_PHONG_KHACH_LINH_NAM",
        "visible_characters": [],
        "story_characters": ["CHAR_LINH", "CHAR_NAM_PRESENT", "CHAR_BE_AN_PRESENT"],
        "props": ["PROP_OLD_PHONE_01", "PROP_SILVER_BRACELET"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Hình ảnh kết tập: Chiếc điện thoại cũ và vòng bạc nằm yên bình bên bức ảnh mới chụp ba người trong công viên.",
        "video_prompt": None,
        "image_prompt": (
            "Closing still of a modern Vietnamese oak credenza: Beside the retired vintage feature phone (PROP_OLD_PHONE_01) and silver bracelet rests a newly printed "
            "photograph of Linh, Nam, and An smiling together in the park, soft evening ambient light, golden warmth of Sau Cánh Cửa, 35mm photography."
        ),
        "image_motion": {"type": "SLOW_PULL_OUT", "speed": "SLOW", "subject_anchor": "CREDENZA_KEEPSAKES", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    }
]
