"""Visual Planning Data for EP003 - Chiếc Hộp Gỗ Của Người Bà Quá Cố.

Contains:
- Character Bible
- Location Bible
- Prop Bible
- 45 Scene Definitions with continuous timeline mapping
- Dynamic Still parameters & Overlay specifications
"""
from __future__ import annotations

EPISODE_ID = "EP003"
TITLE = "Chiếc Hộp Gỗ Của Người Bà Quá Cố"
SERIES = "Sau Cánh Cửa"

CHARACTERS = [
    {
        "character_id": "CHAR_MAI",
        "name": "Mai",
        "gender": "FEMALE",
        "age": 32,
        "ethnicity": "Vietnamese",
        "face_description": (
            "Believable 32-year-old Vietnamese woman, gentle facial structure, intelligent and observant dark eyes, "
            "light natural makeup, realistic skin texture with slight natural imperfections, no glamour look."
        ),
        "hair": "Shoulder-length straight black hair, neatly tied back or parted simply.",
        "body_build": "Slender, medium build, typical modern urban Vietnamese woman.",
        "wardrobe_baseline": "Modest beige cardigan over a cream cotton blouse, casual dark trousers, practical canvas shoes.",
        "wardrobe_variants": {
            "attic_search": "Dark grey long-sleeve cotton shirt, dust-resistant work trousers, hair tied in low ponytail.",
            "office": "Smart-casual light blue linen button-up shirt, navy trousers.",
            "travel_nursing_home": "Warm knit dusty-rose cardigan, dark grey slacks, travel tote bag."
        },
        "emotional_baseline": "Restrained, thoughtful, navigating from initial curiosity and suspicion to deep empathy and reverence.",
        "role": "Protagonist, granddaughter investigating grandmother's secret past.",
        "relationship": "Granddaughter of Bà Hảo, niece of Chú Minh.",
        "timeline_age": "Present (2024, age 32)",
        "priority": "PRIMARY",
        "requires_approval": True,
        "reference_prompt": (
            "Documentary portrait of a 32-year-old Vietnamese woman (CHAR_MAI), natural black hair parted simply, "
            "thoughtful contemplative expression, light natural skin texture, wearing a modest beige knit cardigan over "
            "cream blouse, soft neutral daylight in domestic interior, 35mm cinematic lens, photorealistic documentary realism."
        )
    },
    {
        "character_id": "CHAR_BA_HAO_ELDER",
        "name": "Bà Hảo (Elder)",
        "gender": "FEMALE",
        "age": 85,
        "ethnicity": "Vietnamese",
        "face_description": (
            "Elderly Vietnamese grandmother in her 80s, wrinkled kind face, warm crow's feet around eyes, calm stoic gaze, "
            "dignified rural appearance, no heavy makeup."
        ),
        "hair": "Silver-white hair neatly tied in a small traditional bun.",
        "body_build": "Small, frail yet upright posture, weathered hands from decades of physical labor.",
        "wardrobe_baseline": "Traditional dark brown Vietnamese bà ba blouse, dark trousers, soft cotton slippers.",
        "wardrobe_variants": {},
        "emotional_baseline": "Peaceful, serene, guarding a lifetime promise with quiet dignity.",
        "role": "Deceased grandmother, creator and guardian of the secret trust fund.",
        "relationship": "Grandmother of Mai, mother figure to family, lifelong friend of Bà Thoa.",
        "timeline_age": "Elder years (2015-2022, age 75-85)",
        "priority": "SECONDARY",
        "requires_approval": False,
        "reference_prompt": (
            "Documentary portrait of an 82-year-old Vietnamese elderly woman (CHAR_BA_HAO_ELDER), silver hair in traditional "
            "low bun, wrinkled kind face, warm gentle eyes, weathered hands, wearing dark brown traditional bà ba silk blouse, "
            "soft window daylight, 35mm cinematic realism."
        )
    },
    {
        "character_id": "CHAR_BA_HAO_YOUNG",
        "name": "Bà Hảo (Young 1970s-1990s)",
        "gender": "FEMALE",
        "age": 32,
        "ethnicity": "Vietnamese",
        "face_description": (
            "Believable 1980s Vietnamese woman, resilient hardworking demeanor, earnest expression, natural beauty unadorned by cosmetics."
        ),
        "hair": "Thick black hair tied back in a utilitarian cloth band or braid.",
        "body_build": "Sturdy, hardworking build of an industrial textile laborer.",
        "wardrobe_baseline": "Faded blue cotton factory work uniform shirt, rolled-up sleeves, dark work trousers.",
        "wardrobe_variants": {
            "1992_land_signing": "Simple floral patterned cotton shirt from early 1990s, dark trousers."
        },
        "emotional_baseline": "Earnest, steadfast, determined to build a fund for post-war charity.",
        "role": "Young Bà Hảo in historical memories and archival photographs.",
        "relationship": "Younger self of Bà Hảo, coworker and soulmate-friend of young Bà Thoa.",
        "timeline_age": "Young adult (1975-1994, age 25-42)",
        "priority": "SECONDARY",
        "requires_approval": False,
        "reference_prompt": (
            "Archival documentary portrait of a 30-year-old Vietnamese working-class woman in the 1980s (CHAR_BA_HAO_YOUNG), "
            "sturdy build, earnest determined face, wearing faded blue cotton textile mill work shirt with rolled sleeves, "
            "subtle film grain, muted 1980s documentary tones."
        )
    },
    {
        "character_id": "CHAR_BA_THOA_ELDER",
        "name": "Bà Thoa (Elder)",
        "gender": "FEMALE",
        "age": 80,
        "ethnicity": "Vietnamese",
        "face_description": (
            "Elderly Vietnamese woman, 80 years old, delicate wrinkled features, gentle tearful eyes reflecting long endurance, "
            "physically disabled from past labor injury."
        ),
        "hair": "Sparse grey hair, combed neatly.",
        "body_build": "Frail seated in a manual wheelchair or resting in an armchair, frail hands.",
        "wardrobe_baseline": "Warm wool knit cardigan in soft teal over pale grey cotton pyjamas, plaid wool lap blanket.",
        "wardrobe_variants": {},
        "emotional_baseline": "Moved to tears, deeply relieved and grateful that the sacred promise survived.",
        "role": "Lifelong friend of Bà Hảo, surviving co-founder of the charity fund, resident of Lâm Đồng nursing home.",
        "relationship": "Tri kỷ (soulmate friend) of Bà Hảo, key witness to the secret pledge.",
        "timeline_age": "Present (2024, age 80)",
        "priority": "SECONDARY",
        "requires_approval": False,
        "reference_prompt": (
            "Documentary portrait of an 80-year-old Vietnamese woman (CHAR_BA_THOA_ELDER) sitting in a wheelchair, frail delicate frame, "
            "silver grey hair, expressive tearful yet peaceful eyes, wearing a teal knit sweater and plaid wool blanket over knees, "
            "warm sunlight in nursing home sunroom, 35mm photography."
        )
    },
    {
        "character_id": "CHAR_BA_THOA_YOUNG",
        "name": "Bà Thoa (Young 1970s-1990s)",
        "gender": "FEMALE",
        "age": 28,
        "ethnicity": "Vietnamese",
        "face_description": (
            "Young Vietnamese working woman in the 1980s, gentle smile, hardworking gaze, modest and unassuming."
        ),
        "hair": "Black hair tied in two modest braids or simple clip.",
        "body_build": "Slender textile factory worker.",
        "wardrobe_baseline": "Matching blue cotton textile factory work shirt, faded canvas apron.",
        "wardrobe_variants": {},
        "emotional_baseline": "Warm, hopeful, sharing deep camaraderie with young Bà Hảo.",
        "role": "Young Bà Thoa in archival photos and memory sequences.",
        "relationship": "Close comrade and coworker of young Bà Hảo.",
        "timeline_age": "Young adult (1975-1992, age 22-38)",
        "priority": "SECONDARY",
        "requires_approval": False,
        "reference_prompt": (
            "Archival vintage portrait of a 28-year-old Vietnamese woman in the 1980s (CHAR_BA_THOA_YOUNG), gentle smile, "
            "authentic vintage Vietnamese features, wearing a blue textile factory worker shirt, archival black and white "
            "photograph with soft sepia tint."
        )
    },
    {
        "character_id": "CHAR_CHU_MINH",
        "name": "Chú Minh",
        "gender": "MALE",
        "age": 58,
        "ethnicity": "Vietnamese",
        "face_description": (
            "Vietnamese man in his late 50s, kind weathered face, receding pepper-and-salt hair, reading glasses resting on "
            "chest or nose, honest and grounded countenance."
        ),
        "hair": "Short salt-and-pepper hair, thinning slightly at temples.",
        "body_build": "Average middle-aged Vietnamese build.",
        "wardrobe_baseline": "Dark olive polo shirt, khaki trousers, reading glasses hanging on a lanyard.",
        "wardrobe_variants": {},
        "emotional_baseline": "Initially cautious and nostalgic, becomes supportive and deeply respectful upon learning the full story.",
        "role": "Uncle of Mai, elder family member remembering past fragments.",
        "relationship": "Eldest living uncle to Mai, son/nephew generation of Bà Hảo.",
        "timeline_age": "Present (2024, age 58)",
        "priority": "SECONDARY",
        "requires_approval": False,
        "reference_prompt": (
            "Documentary portrait of a 58-year-old Vietnamese man (CHAR_CHU_MINH), salt-and-pepper hair, warm wise eyes, "
            "wearing wire-rimmed reading glasses and an olive polo shirt, seated in a traditional wooden Vietnamese living room, "
            "natural warm daylight, 35mm photography."
        )
    }
]

LOCATIONS = [
    {
        "location_id": "LOC_GAC_XEP_BAO_LOC",
        "name": "Căn gác xép nhà bà cố tại Bảo Lộc",
        "city_region": "Bảo Lộc, Lâm Đồng",
        "type": "INTERIOR",
        "architecture": (
            "Rustic traditional Vietnamese highland attic, exposed dark timber beams, wooden floorboards with visible grain, "
            "aged terracotta roof tiles with gaps letting in slivers of daylight, accumulation of vintage cardboard boxes and wooden trunks."
        ),
        "era": "Present (2024) with preserved historical items",
        "key_furniture": "Old wooden chests, bamboo drying trays, stacks of yellowed books, vintage wooden trunk on low bench.",
        "lighting": "Slanted golden daylight filtering through dust motes from small attic dormer window, warm contrast.",
        "color_material_characteristics": "Deep warm wood tones, dusty golden rays, weathered cedar and bamboo.",
        "story_function": "Where Mai discovers the mysterious wooden box and begins her investigation.",
        "reference_prompt": (
            "Interior photograph of a rustic wooden attic in an old Vietnamese house in Bảo Lộc, exposed cedar rafters, "
            "dust motes floating in diagonal beams of golden sunlight, vintage wooden storage boxes on floorboards, 35mm documentary realism."
        )
    },
    {
        "location_id": "LOC_NHA_MAI_HCM",
        "name": "Căn hộ của Mai tại TP. Hồ Chí Minh",
        "city_region": "TP. Hồ Chí Minh",
        "type": "INTERIOR",
        "architecture": (
            "Modern urban Vietnamese apartment, clean white walls, light oak wooden desk, bookshelf, balcony overlooking Saigon nightscape."
        ),
        "era": "Present (2024)",
        "key_furniture": "Study desk, warm desk lamp, laptop, ergonomic chair, photo frame on shelf.",
        "lighting": "Focused warm tungsten task light on desk, soft ambient city glow from window.",
        "color_material_characteristics": "Clean neutral grays, warm wood accents, urban evening palette.",
        "story_function": "Mai analyzes the box contents, wrestles with suspicion, examines financial clues.",
        "reference_prompt": (
            "Interior of a modern Vietnamese apartment study at night, wooden desk illuminated by an anglepoise lamp, papers neatly arranged, "
            "large window overlooking distant city lights of Ho Chi Minh City, subtle cinematic lighting."
        )
    },
    {
        "location_id": "LOC_NHA_CHU_MINH",
        "name": "Nhà riêng của Chú Minh",
        "city_region": "Bảo Lộc, Lâm Đồng",
        "type": "INTERIOR",
        "architecture": (
            "Traditional Vietnamese provincial house, polished dark wood furniture set (bộ bàn ghế gỗ), carved wooden ancestor altar with bronze "
            "incense burner in background, ceramic tea set on table."
        ),
        "era": "Present (2024)",
        "key_furniture": "Heavy wooden dining/tea table, wooden armchairs, glass display cabinet with family mementos, ancestor altar.",
        "lighting": "Gentle natural daylight through sheer lace curtains, warm inviting indoor ambiance.",
        "color_material_characteristics": "Warm mahogany wood, glazed ceramic green tea, muted white walls.",
        "story_function": "Mai shows the photo to Chú Minh; Chú Minh reveals Bà Thoa's identity and past.",
        "reference_prompt": (
            "Interior of a provincial Vietnamese living room in Lâm Đồng, traditional carved mahogany armchairs and low tea table with porcelain tea pot, "
            "ancestor altar softly lit in background, gentle daylight filtering through lace curtains, cinematic realism."
        )
    },
    {
        "location_id": "LOC_VIEN_DUONG_LAO_LAM_DONG",
        "name": "Viện dưỡng lão tại Lâm Đồng",
        "city_region": "Lâm Đồng (Highland region)",
        "type": "INTERIOR/EXTERIOR",
        "architecture": (
            "Highland rest home facility, colonial-influenced architecture, French shuttered windows, sunroom with potted orchids, "
            "manicured pine tree garden and stone pathways outside."
        ),
        "era": "Present (2024)",
        "key_furniture": "Wheelchair, comfortable cushioned armchairs, low wooden tea table, large bay windows overlooking pine hills.",
        "lighting": "Cool soft highland morning light mixed with gentle golden sunshine, misty pine background.",
        "color_material_characteristics": "Earthy highland tones, pine green, misty white, warm wood interiors.",
        "story_function": "Climax meeting with elderly Bà Thoa; Reveal 2 of the orphan shelter promise.",
        "reference_prompt": (
            "Bright sunlit dayroom of a highland nursing home in Lâm Đồng, large French windows looking out onto pine-covered hills in gentle mist, "
            "potted green ferns, calm peaceful documentary atmosphere, 35mm lens."
        )
    },
    {
        "location_id": "LOC_KHU_DAT_BAO_LOC",
        "name": "Mảnh đất vườn 650m2 tại Bảo Lộc",
        "city_region": "Bảo Lộc, Lâm Đồng",
        "type": "EXTERIOR",
        "architecture": (
            "Peaceful highland hillside garden plot, gentle sloping red basalt soil, rows of tea shrubs and fruit trees, wooden boundary fence, "
            "panoramic view of rolling mist-covered hills."
        ),
        "era": "Present (2024)",
        "key_furniture": "Rustic wooden boundary marker, small wooden bench under shade tree.",
        "lighting": "Bright warm morning highland sunshine, clear blue sky with drifting clouds.",
        "color_material_characteristics": "Vibrant tea foliage green, red basalt earth, mountain blue.",
        "story_function": "Ending resolution; site where the family and community will fulfill the shelter di nguyện.",
        "reference_prompt": (
            "Cinematic landscape of a 650-square-meter garden plot on a hillside in Bảo Lộc Vietnam, lush green tea bushes, red basalt soil, "
            "rustic timber boundary posts, distant mountain silhouette in morning sunlight, 35mm wide shot."
        )
    }
]

PROPS = [
    {
        "prop_id": "PROP_WOODEN_BOX",
        "name": "Chiếc hộp gỗ sờn cũ",
        "dimensions": "32cm x 22cm x 14cm",
        "material": "Aged Vietnamese jackfruit wood (gỗ mít) with natural grain, unvarnished weathered patina.",
        "hardware": "Small darkened brass hinges, brass clasp latch without a padlock.",
        "condition": "Layer of fine attic dust on lid, faint scuffs, corners smoothed by years of gentle handling.",
        "contents": "Yellowed passbook, official land transfer deed, handwritten note, black-and-white vintage photograph.",
        "continuity_notes": "Must retain exact rectangular proportions, distinct grain pattern, and brass hardware in all scenes."
    },
    {
        "prop_id": "PROP_VINTAGE_PHOTO_BAO_THOA",
        "name": "Bức ảnh ố vàng chụp Bà Hảo và Bà Thoa thời trẻ",
        "format": "Original 10cm x 15cm photographic print with slightly scalloped vintage borders.",
        "visual_content": (
            "Two young Vietnamese women (young Bà Hảo and young Bà Thoa) in early 1980s cotton work clothes standing side-by-side "
            "in front of a textile mill gate, gentle genuine smiles."
        ),
        "condition": "Sepia patina, subtle silver mirroring at edges, light crease on upper right corner, no tears.",
        "continuity_notes": "Consistent appearance whenever inspected; mystery clue in first half, emotional treasure in second half."
    },
    {
        "prop_id": "PROP_PASSBOOK_1994",
        "name": "Sổ tiết kiệm kỳ hạn dài năm 1994",
        "format": "1994 Vietnamese state commercial bank savings book, textured red cardstock cover.",
        "visual_content": "Official bank insignia, printed fields with handwritten blue ink entries, red circular bank seal.",
        "evidence_text": "Ngân hàng Nông nghiệp & Phát triển Nông thôn - Sổ Tiền Gửi Tiết Kiệm (1994) | Chủ sở hữu: Nguyễn Thị Hảo | Số tiền: 15.000.000 VNĐ",
        "continuity_notes": "Clean paper surface in image prompt, exact legal text rendered via overlay."
    },
    {
        "prop_id": "PROP_LAND_DEED_1992",
        "name": "Giấy chuyển nhượng quyền sử dụng đất vườn năm 1992",
        "format": "Official folded bureaucratic document, yellowed legal paper with typed typewriter text and red administrative stamp.",
        "evidence_text": "UBND Thị xã Bảo Lộc - Giấy Chứng Nhận Chuyển Nhượng Quyền Sử Dụng Đất (1992) | Thửa đất: 650m2 đất vườn | Đại diện đứng tên: Nguyễn Thị Hảo",
        "continuity_notes": "Clean paper surface in image prompt, exact legal text rendered via overlay."
    },
    {
        "prop_id": "PROP_HANDWRITTEN_NOTE",
        "name": "Tờ giấy viết tay ghi số và địa chỉ viện dưỡng lão",
        "format": "Folded piece of vintage lined notebook paper, faded blue ballpoint pen writing.",
        "evidence_text": "Ghi chép quỹ chung 1985-1994 | Liên hệ: Cơ sở chăm sóc người cao tuổi, Bảo Lộc - Lâm Đồng",
        "continuity_notes": "Used as key investigative bridge from family suspicion to Lâm Đồng journey."
    }
]

# 45 scenes configuration for EP003
# 15 VIDEO_RECOMMENDED (33.3%), 30 IMAGE_ONLY (66.7%)
# Visual spoiler guard: No mention or depiction of the joint charity trust / orphan shelter before Reveal 1 (Scene 31, Seg 61).
SCENE_SPECS = [
    {
        "scene_id": "SC_001",
        "source_segments": ["001", "002"],
        "narrative_function": "HOOK",
        "location_id": "LOC_GAC_XEP_BAO_LOC",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI", "CHAR_BA_HAO_ELDER"],
        "props": ["PROP_WOODEN_BOX"],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P1",
        "visual_mode_reason": "Hook hành động: Nhân vật bước vào gác xép bụi bặm, trèo thang gỗ và tiếp cận hiện trường bí mật.",
        "video_prompt": (
            "Start: A 32-year-old Vietnamese woman (CHAR_MAI) in work clothes enters a dusty rustic attic holding a small flashlight. "
            "Action: She carefully steps across wooden floorboards toward a dusty corner where an old wooden box rests on a timber chest. "
            "Camera: Slow cinematic push-in from behind her shoulder following her steady footsteps. "
            "End: She stops directly before the wooden box, flashlight beam illuminating its aged surface. No wardrobe change."
        ),
        "image_prompt": (
            "Cinematic documentary shot of a 32-year-old Vietnamese woman (CHAR_MAI) in a dark grey work shirt standing inside a dusty "
            "attic in Bảo Lộc, holding a flashlight illuminating a weathered wooden box (PROP_WOODEN_BOX) resting on an aged trunk, "
            "shafts of afternoon sunlight filtering through terracotta roof tiles, floating dust particles, 35mm photography, realistic skin texture."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "WOODEN_BOX", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_002",
        "source_segments": ["003", "004"],
        "narrative_function": "HOOK_INTRO",
        "location_id": "LOC_GAC_XEP_BAO_LOC",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI"],
        "props": ["PROP_WOODEN_BOX"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Khoảnh khắc tĩnh tâm lý: Nhân vật đứng sững nhìn chiếc hộp, mở đầu không gian suy ngẫm của Sau Cánh Cửa.",
        "video_prompt": None,
        "image_prompt": (
            "Medium close-up of a 32-year-old Vietnamese woman (CHAR_MAI) in a rustic attic, thoughtful and hesitant expression, "
            "gazing intently down at an old wooden box in her hands, subtle warm side-lighting from attic dormer window, "
            "shallow depth of field, photorealistic Vietnamese documentary drama, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "SUBTLE_REFRAME", "speed": "SLOW", "subject_anchor": "MAI_FACE", "safe_crop_zone": "CENTER_RIGHT"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_003",
        "source_segments": ["005", "006"],
        "narrative_function": "HOST_INTRO",
        "location_id": "LOC_GAC_XEP_BAO_LOC",
        "visible_characters": [],
        "story_characters": ["CHAR_MAI", "CHAR_BA_HAO_ELDER"],
        "props": ["PROP_WOODEN_BOX"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Cảnh thiết lập không gian tĩnh lặng mang tính biểu tượng của Sau Cánh Cửa.",
        "video_prompt": None,
        "image_prompt": (
            "Cinematic establishing shot of an antique weathered wooden box (PROP_WOODEN_BOX) resting on a dark timber table in a quiet "
            "highland Vietnamese room, soft golden light catching the faded brass latch and wood grain, tranquil documentary realism, 35mm film."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "WOODEN_BOX", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_004",
        "source_segments": ["007", "008"],
        "narrative_function": "EXPOSITION_MAI",
        "location_id": "LOC_NHA_MAI_HCM",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI", "CHAR_BA_HAO_ELDER"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Giới thiệu nhân vật Mai trong bối cảnh cuộc sống đô thị ổn định và thành đạt.",
        "video_prompt": None,
        "image_prompt": (
            "A 32-year-old Vietnamese woman (CHAR_MAI) in smart casual linen shirt working thoughtfully at a wooden desk in her apartment "
            "in Ho Chi Minh City, evening urban skyline softly visible outside window, warm ambient interior light, 35mm cinematic documentary."
        ),
        "image_motion": {"type": "PAN_RIGHT", "speed": "SLOW", "subject_anchor": "MAI_FIGURE", "safe_crop_zone": "CENTER_LEFT"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_005",
        "source_segments": ["009", "010"],
        "narrative_function": "EXPOSITION_REMEMBRANCE",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": [],
        "story_characters": ["CHAR_BA_HAO_ELDER"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Khoảnh khắc tưởng nhớ thiêng liêng: Bàn thờ gia tiên với di ảnh người bà quá cố.",
        "video_prompt": None,
        "image_prompt": (
            "A traditional Vietnamese wooden family altar in a provincial home, framed black and white portrait of an 82-year-old elderly "
            "Vietnamese grandmother (CHAR_BA_HAO_ELDER) with silver hair and kind smile, bronze incense burner with thin curl of smoke, "
            "soft reverent daylight, warm cinematic tones, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "STATIC_INTENTIONAL", "speed": "NORMAL", "subject_anchor": "ALTAR_PORTRAIT", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_006",
        "source_segments": ["011", "012"],
        "narrative_function": "DISCOVERY_OPENING",
        "location_id": "LOC_GAC_XEP_BAO_LOC",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI"],
        "props": ["PROP_WOODEN_BOX"],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P1",
        "visual_mode_reason": "Hành động vật lý quan trọng: Đôi tay nhân vật nhẹ nhàng lau bụi và nâng nắp chiếc hộp gỗ hé mở bí mật.",
        "video_prompt": (
            "Start: A 32-year-old Vietnamese woman (CHAR_MAI) kneels beside the weathered wooden box on the attic floor. "
            "Action: Her hands slowly unhook the small brass latch and gently lift the wooden lid open, revealing interior contents. "
            "Camera: Eye-level medium close-up steadily zooming slightly in on her hands and the opening lid. "
            "End: The lid rests open; she pauses, her expression turning to awe. No identity change, consistent attic lighting."
        ),
        "image_prompt": (
            "Medium shot of a 32-year-old Vietnamese woman (CHAR_MAI) in a dusty attic, her hands resting on the opened lid of an antique "
            "wooden box (PROP_WOODEN_BOX), looking inside with curiosity and wonder, soft diagonal sunbeam illuminating the wooden box interior, 35mm lens."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "BOX_AND_HANDS", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_007",
        "source_segments": ["013", "014"],
        "narrative_function": "EVIDENCE_OVERVIEW",
        "location_id": "LOC_GAC_XEP_BAO_LOC",
        "visible_characters": [],
        "story_characters": ["CHAR_MAI"],
        "props": ["PROP_WOODEN_BOX", "PROP_PASSBOOK_1994", "PROP_LAND_DEED_1992", "PROP_VINTAGE_PHOTO_BAO_THOA"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Chụp cận cảnh tĩnh toàn bộ chứng cứ bên trong hộp: sổ tiết kiệm, giấy tờ nhà đất và bức ảnh cũ.",
        "video_prompt": None,
        "image_prompt": (
            "High-angle top-down macro shot of the open antique wooden box interior, showing neatly stacked yellowed vintage Vietnamese financial documents, "
            "a red-covered 1994 bank passbook, an official folded land deed, and the edge of a sepia photograph, clean documentary surface, 35mm lens."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "BOX_CONTENTS", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_008",
        "source_segments": ["015", "016"],
        "narrative_function": "EVIDENCE_PHOTO",
        "location_id": "LOC_GAC_XEP_BAO_LOC",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI", "CHAR_BA_HAO_YOUNG", "CHAR_BA_THOA_YOUNG"],
        "props": ["PROP_VINTAGE_PHOTO_BAO_THOA"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Cận cảnh bức ảnh ố vàng hai người phụ nữ thời trẻ khơi dậy nghi vấn lớn trong lòng Mai.",
        "video_prompt": None,
        "image_prompt": (
            "Close-up of a 32-year-old Vietnamese woman (CHAR_MAI) holding a yellowed vintage photograph (PROP_VINTAGE_PHOTO_BAO_THOA) showing "
            "two young smiling Vietnamese women in 1980s work shirts, Mai's eyes filled with perplexity and curiosity, soft warm attic daylight, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "EVIDENCE_INSPECTION", "speed": "SLOW", "subject_anchor": "PHOTO_SURFACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_009",
        "source_segments": ["017", "018"],
        "narrative_function": "DOCUMENT_INSPECTION_MOTION",
        "location_id": "LOC_NHA_MAI_HCM",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI"],
        "props": ["PROP_PASSBOOK_1994", "PROP_LAND_DEED_1992"],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P2",
        "visual_mode_reason": "Hành động điều tra: Mai cẩn thận lật giở và trải từng tờ giấy chứng nhận nhà đất 1992 dưới ánh đèn bàn.",
        "video_prompt": (
            "Start: A 32-year-old Vietnamese woman (CHAR_MAI) seated at her apartment desk under a warm task lamp. "
            "Action: She gently unfolds the yellowed official 1992 land transfer deed, smoothing the creases with her fingertips. "
            "Camera: Close macro pan following her fingers as they reveal the vintage red stamp and handwritten ink details. "
            "End: Document laid flat on desk, her hands resting at the sides. Consistent warm night interior lighting."
        ),
        "image_prompt": (
            "Over-the-shoulder medium shot of a 32-year-old Vietnamese woman (CHAR_MAI) at a wooden desk at night, carefully unfolding "
            "a yellowed 1992 Vietnamese land transfer document under a focused warm desk lamp, red seal visible, quiet investigative atmosphere, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "DOCUMENT_SURFACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_010",
        "source_segments": ["019", "020"],
        "narrative_function": "EVIDENCE_PASSBOOK_OVERLAY",
        "location_id": "LOC_NHA_MAI_HCM",
        "visible_characters": [],
        "story_characters": ["CHAR_MAI"],
        "props": ["PROP_PASSBOOK_1994"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Hiển thị chứng cứ số 1: Sổ tiết kiệm 1994 với lớp phủ văn bản chính xác.",
        "video_prompt": None,
        "image_prompt": (
            "Macro photography of an authentic 1994 Vietnamese state commercial bank savings passbook (PROP_PASSBOOK_1994), textured red "
            "cardstock cover slightly faded, clean aged paper page open, clear official circular red stamp, warm directional light, 35mm lens."
        ),
        "image_motion": {"type": "EVIDENCE_INSPECTION", "speed": "SLOW", "subject_anchor": "PASSBOOK_DETAILS", "safe_crop_zone": "CENTER"},
        "requires_overlay": True,
        "overlay_data": {
            "overlay_type": "DOCUMENT",
            "overlay_text": "SỔ TIẾT KIỆM KỲ HẠN DÀI (1994)\nChủ sở hữu: Nguyễn Thị Hảo\nSố tiền gốc: 15.000.000 VNĐ",
            "overlay_position": "LOWER_THIRD",
            "font_style": "CLEAN_SERIF_DOCUMENTARY"
        }
    },
    {
        "scene_id": "SC_011",
        "source_segments": ["021", "022"],
        "narrative_function": "EVIDENCE_NOTE_OVERLAY",
        "location_id": "LOC_NHA_MAI_HCM",
        "visible_characters": [],
        "story_characters": ["CHAR_MAI"],
        "props": ["PROP_HANDWRITTEN_NOTE"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Hiển thị manh mối viết tay ghi địa chỉ viện dưỡng lão ở Lâm Đồng.",
        "video_prompt": None,
        "image_prompt": (
            "Macro shot of a folded piece of vintage Vietnamese lined notebook paper with faded blue ballpoint pen handwriting (PROP_HANDWRITTEN_NOTE), "
            "aged paper with soft yellow patina, resting on dark polished wood, soft warm desk lamp illumination, sharp focus, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "HANDWRITING", "safe_crop_zone": "CENTER"},
        "requires_overlay": True,
        "overlay_data": {
            "overlay_type": "DOCUMENT",
            "overlay_text": "GHI CHÉP TÍCH LŨY QUỸ CHUNG (1985-1994)\nĐịa chỉ liên hệ: Cơ sở chăm sóc người cao tuổi, Bảo Lộc - Lâm Đồng",
            "overlay_position": "LOWER_THIRD",
            "font_style": "CLEAN_SERIF_DOCUMENTARY"
        }
    },
    {
        "scene_id": "SC_012",
        "source_segments": ["023", "024"],
        "narrative_function": "PSYCHOLOGICAL_TENSION",
        "location_id": "LOC_NHA_MAI_HCM",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P2",
        "visual_mode_reason": "Chuyển động nội tâm căng thẳng: Mai đứng dậy đi lại trong phòng, quay đầu nhìn lại bàn làm việc đầy băn khoăn.",
        "video_prompt": (
            "Start: A 32-year-old Vietnamese woman (CHAR_MAI) stands near her apartment window looking out at the dark night sky. "
            "Action: She turns around, pacing slowly across the wooden floor with folded arms, stopping to look back at the desk documents. "
            "Camera: Medium tracking shot following her subtle movement, capturing conflicted facial expression. "
            "End: She pauses beside the desk, looking down with furrowed brow. Consistent night apartment lighting."
        ),
        "image_prompt": (
            "Medium shot of a 32-year-old Vietnamese woman (CHAR_MAI) standing in her dimly lit apartment living room, arms crossed, "
            "troubled introspective gaze toward the study table, city night lights blurred in the background window, cinematic realism, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "PAN_LEFT", "speed": "SLOW", "subject_anchor": "MAI_FIGURE", "safe_crop_zone": "CENTER_RIGHT"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_013",
        "source_segments": ["025", "026"],
        "narrative_function": "FALSE_LEAD_SUSPICION",
        "location_id": "LOC_NHA_MAI_HCM",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI", "CHAR_BA_HAO_ELDER"],
        "props": ["PROP_VINTAGE_PHOTO_BAO_THOA"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Tạo dựng sự nghi ngờ chính đáng (False Lead): Mai tự hỏi liệu bà cố có một mối tình bí mật hay gia đình thứ hai.",
        "video_prompt": None,
        "image_prompt": (
            "Intimate close-up of a 32-year-old Vietnamese woman (CHAR_MAI) staring at the vintage photo under the harsh lamp, "
            "her reflection faintly visible on the glass desk surface, deep suspicion and confusion etched on her face, 35mm film."
        ),
        "image_motion": {"type": "SUBTLE_REFRAME", "speed": "SLOW", "subject_anchor": "MAI_FACE", "safe_crop_zone": "CENTER_LEFT"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_014",
        "source_segments": ["027", "028"],
        "narrative_function": "DECISION_TO_INVESTIGATE",
        "location_id": "LOC_NHA_MAI_HCM",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P2",
        "visual_mode_reason": "Hành động quyết tâm: Mai lấy áo khoác và túi xách, quyết định lên đường tìm Chú Minh để làm rõ chân tướng.",
        "video_prompt": (
            "Start: A 32-year-old Vietnamese woman (CHAR_MAI) places the documents inside a protective leather folder. "
            "Action: She puts the folder into her canvas travel tote, picks up her knit cardigan from the chair, and walks toward the front door. "
            "Camera: Steady medium shot tracking her movement across the living room toward the door. "
            "End: Hand turning the doorknob, stepping forward with determined expression. No wardrobe change."
        ),
        "image_prompt": (
            "A 32-year-old Vietnamese woman (CHAR_MAI) in a dusty-rose knit cardigan holding a travel bag and folder, standing by the apartment "
            "doorway in morning daylight, resolute and focused expression, modern Vietnamese domestic environment, 35mm photography."
        ),
        "image_motion": {"type": "PAN_RIGHT", "speed": "SLOW", "subject_anchor": "MAI_FIGURE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_015",
        "source_segments": ["029", "030"],
        "narrative_function": "INTERNAL_HYPOTHESIS",
        "location_id": "LOC_NHA_MAI_HCM",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI", "CHAR_BA_HAO_YOUNG"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Không gian trầm tư tưởng tượng về quá khứ chưa biết của người bà.",
        "video_prompt": None,
        "image_prompt": (
            "Atmospheric cinematic shot of a 32-year-old Vietnamese woman (CHAR_MAI) sitting in contemplative silence beside a sunny window, "
            "warm morning dust motes, silhouette framed against sheer curtains, realistic emotional depth, muted colors, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "SLOW_PULL_OUT", "speed": "SLOW", "subject_anchor": "MAI_SILHOUETTE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_016",
        "source_segments": ["031", "032"],
        "narrative_function": "DOUBT_CRISIS",
        "location_id": "LOC_NHA_MAI_HCM",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI"],
        "props": ["PROP_PASSBOOK_1994"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Khủng hoảng niềm tin: Hình ảnh người bà hoàn hảo bị lung lay trước chứng cứ tài sản lớn.",
        "video_prompt": None,
        "image_prompt": (
            "Close-up of a 32-year-old Vietnamese woman (CHAR_MAI), hand pressed gently against her forehead in deep thought, "
            "the 1994 passbook lying on the table before her, subtle natural light, raw emotional vulnerability, 35mm lens."
        ),
        "image_motion": {"type": "STATIC_INTENTIONAL", "speed": "NORMAL", "subject_anchor": "MAI_FACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_017",
        "source_segments": ["033", "034"],
        "narrative_function": "SEARCHING_MEMORY",
        "location_id": "LOC_NHA_MAI_HCM",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "MEDIUM",
        "video_priority": "P2",
        "visual_mode_reason": "Hành động tìm kiếm: Mai tìm trên giá sách cuốn an-bum ảnh cũ của gia đình để đối chiếu ký ức.",
        "video_prompt": (
            "Start: A 32-year-old Vietnamese woman (CHAR_MAI) stands in front of a wooden bookshelf in the living room. "
            "Action: She pulls down an old fabric-covered family photo album, opens it carefully, and turns the heavy parchment pages. "
            "Camera: Medium close-up slowly tilting down from her face to her hands turning the album pages. "
            "End: Her fingers pause on an empty photo sleeve; she shakes her head gently. Consistent soft daylight."
        ),
        "image_prompt": (
            "Medium shot of a 32-year-old Vietnamese woman (CHAR_MAI) leafing through a vintage family photo album on a wooden shelf, "
            "warm natural afternoon light streaming into the room, dust specks in air, authentic Vietnamese living space, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "PAN_LEFT", "speed": "SLOW", "subject_anchor": "ALBUM_PAGES", "safe_crop_zone": "CENTER_RIGHT"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_018",
        "source_segments": ["035", "036"],
        "narrative_function": "MAZE_OF_MEMORY",
        "location_id": "LOC_NHA_MAI_HCM",
        "visible_characters": [],
        "story_characters": ["CHAR_MAI"],
        "props": ["PROP_HANDWRITTEN_NOTE"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Tĩnh vật ẩn dụ: Những con số bí ẩn và ghi chú cổ xưa đặt bên cạnh chiếc tách trà nguội.",
        "video_prompt": None,
        "image_prompt": (
            "Still life composition of the handwritten note (PROP_HANDWRITTEN_NOTE) resting beside a ceramic teacup on dark polished Vietnamese mahogany wood, "
            "soft window lighting creating long gentle shadows, mood of quiet mystery, 35mm documentary realism."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "NOTE_PAPER", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_019",
        "source_segments": ["037", "038"],
        "narrative_function": "ARRIVAL_UNCLE_MINH",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI", "CHAR_CHU_MINH"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P2",
        "visual_mode_reason": "Hành động di chuyển ngoại cảnh: Mai bước qua cổng ngõ cây xanh vào sân nhà Chú Minh ở Bảo Lộc.",
        "video_prompt": (
            "Start: A 32-year-old Vietnamese woman (CHAR_MAI) carrying her shoulder bag walks through a modest wrought-iron gate. "
            "Action: She steps along a brick path lined with potted highland flowers, stepping up to the wooden front door and knocking gently. "
            "Camera: Wide tracking shot moving smoothly along with her footsteps, capturing the peaceful garden and rustic house exterior. "
            "End: The wooden door begins to open from inside; she smiles politely. Soft highland morning daylight."
        ),
        "image_prompt": (
            "Exterior shot of a 32-year-old Vietnamese woman (CHAR_MAI) walking up to the wooden entrance door of a provincial single-story home "
            "in Bảo Lộc, lush highland potted plants and ferns, gentle morning sunlight through tree branches, cinematic realism, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "PAN_RIGHT", "speed": "SLOW", "subject_anchor": "MAI_FIGURE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_020",
        "source_segments": ["039", "040"],
        "narrative_function": "UNCLE_MINH_TEA",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": ["CHAR_MAI", "CHAR_CHU_MINH"],
        "story_characters": ["CHAR_MAI", "CHAR_CHU_MINH"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "MEDIUM",
        "video_priority": "P2",
        "visual_mode_reason": "Tương tác nhân vật chân thực: Chú Minh rót trà nóng tiếp cháu gái và lắng nghe câu hỏi.",
        "video_prompt": (
            "Start: A 58-year-old Vietnamese man (CHAR_CHU_MINH) with salt-and-pepper hair sits at a carved mahogany tea table opposite Mai. "
            "Action: He lifts a white porcelain teapot, pours steaming green tea into a small ceramic cup, and sets it down before looking up attentively. "
            "Camera: Medium two-shot, slowly zooming in toward Chú Minh's face as he observes Mai. "
            "End: Chú Minh leans back in his armchair, listening with gentle curiosity. Soft indoor natural light."
        ),
        "image_prompt": (
            "Medium two-shot of a 58-year-old Vietnamese man (CHAR_CHU_MINH) pouring green tea for a 32-year-old Vietnamese woman (CHAR_MAI) "
            "at a traditional carved wooden table in a provincial living room, porcelain tea set, ancestor altar in background, warm daylight, 35mm."
        ),
        "image_motion": {"type": "SUBTLE_REFRAME", "speed": "SLOW", "subject_anchor": "TEA_TABLE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_021",
        "source_segments": ["041", "042"],
        "narrative_function": "RECOGNITION_PHOTO",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": ["CHAR_CHU_MINH"],
        "story_characters": ["CHAR_CHU_MINH", "CHAR_BA_THOA_YOUNG"],
        "props": ["PROP_VINTAGE_PHOTO_BAO_THOA"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Khoảnh khắc nhận ra người quen: Chú Minh đeo kính lão, ánh mắt ngấn lệ xúc động khi nhìn bức ảnh bà Thoa.",
        "video_prompt": None,
        "image_prompt": (
            "Close-up of a 58-year-old Vietnamese man (CHAR_CHU_MINH) wearing reading glasses, holding the yellowed vintage photograph "
            "(PROP_VINTAGE_PHOTO_BAO_THOA), eyes wide with sudden recognition and nostalgia, warm side daylight, realistic skin texture, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "MINH_FACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_022",
        "source_segments": ["043", "044"],
        "narrative_function": "HISTORICAL_RECALL_THOA",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": ["CHAR_CHU_MINH"],
        "story_characters": ["CHAR_CHU_MINH", "CHAR_BA_THOA_ELDER", "CHAR_BA_HAO_ELDER"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Chú Minh kể lại câu chuyện về người bạn tri kỷ tên Thoa từng làm việc tại xưởng dệt và bị tàn tật sau tai nạn.",
        "video_prompt": None,
        "image_prompt": (
            "Medium shot of a 58-year-old Vietnamese man (CHAR_CHU_MINH) speaking with calm reverence and deep emotion, looking slightly "
            "past the camera as he recalls past memories, seated in his wooden living room, gentle natural light, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "PAN_LEFT", "speed": "SLOW", "subject_anchor": "MINH_FIGURE", "safe_crop_zone": "CENTER_LEFT"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_023",
        "source_segments": ["045", "046"],
        "narrative_function": "NEW_PERSPECTIVE",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Góc nhìn mới hé lộ: Người phụ nữ lạ không phải tình địch mà là bạn tri kỷ, mở ra cuộc điều tra sâu sắc hơn.",
        "video_prompt": None,
        "image_prompt": (
            "Medium close-up of a 32-year-old Vietnamese woman (CHAR_MAI) listening intently, eyes reflecting relief mixed with deeper curiosity, "
            "holding a steaming ceramic teacup, warm ambient lighting, 35mm cinematic documentary."
        ),
        "image_motion": {"type": "STATIC_INTENTIONAL", "speed": "NORMAL", "subject_anchor": "MAI_FACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_024",
        "source_segments": ["047", "048"],
        "narrative_function": "PRESENTING_DOCUMENTS",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": ["CHAR_MAI", "CHAR_CHU_MINH"],
        "story_characters": ["CHAR_MAI", "CHAR_CHU_MINH"],
        "props": ["PROP_PASSBOOK_1994", "PROP_LAND_DEED_1992"],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "MEDIUM",
        "video_priority": "P2",
        "visual_mode_reason": "Hành động đối chiếu: Mai trải sổ tiết kiệm và giấy chứng nhận quyền sử dụng đất lên bàn gỗ trước mặt Chú Minh.",
        "video_prompt": (
            "Start: A 32-year-old Vietnamese woman (CHAR_MAI) takes out the 1994 passbook and 1992 land deed from her leather folder. "
            "Action: She slides both documents across the mahogany table toward Chú Minh. Chú Minh leans forward, putting on his glasses to inspect them. "
            "Camera: Slow over-the-shoulder push-in from Mai toward Chú Minh's hands receiving the documents. "
            "End: Chú Minh holds the land deed under the light, eyes widening. Consistent warm interior lighting."
        ),
        "image_prompt": (
            "Medium two-shot of a 32-year-old Vietnamese woman (CHAR_MAI) and a 58-year-old man (CHAR_CHU_MINH) studying vintage papers laid out "
            "on a dark mahogany table, red stamps and aged documents catching the soft daylight, authentic Vietnamese family scene, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "TABLE_DOCUMENTS", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_025",
        "source_segments": ["049", "050"],
        "narrative_function": "EVIDENCE_RECEIPT_OVERLAY",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": [],
        "story_characters": ["CHAR_MAI", "CHAR_CHU_MINH"],
        "props": ["PROP_PASSBOOK_1994"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Chụp cận cảnh giấy biên nhận tiền gửi định kỳ có tên bà Hảo.",
        "video_prompt": None,
        "image_prompt": (
            "Macro shot of an aged paper savings slip and bank receipt from the early 1990s, clean typed Vietnamese lettering, official blue ink stamps, "
            "resting on dark timber surface, soft diffused lighting, 35mm lens."
        ),
        "image_motion": {"type": "EVIDENCE_INSPECTION", "speed": "SLOW", "subject_anchor": "RECEIPT_SURFACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": True,
        "overlay_data": {
            "overlay_type": "DOCUMENT",
            "overlay_text": "BIÊN NHẬN TIỀN GỬI ĐỊNH KỲ (1994)\nTài khoản tích lũy tương trợ | Người đại diện: Nguyễn Thị Hảo",
            "overlay_position": "LOWER_THIRD",
            "font_style": "CLEAN_SERIF_DOCUMENTARY"
        }
    },
    {
        "scene_id": "SC_026",
        "source_segments": ["051", "052"],
        "narrative_function": "EVIDENCE_OLD_LETTERS",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": [],
        "story_characters": ["CHAR_BA_HAO_YOUNG", "CHAR_BA_THOA_YOUNG"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Chụp cận cảnh những bức thư tay bằng mực tím phai màu giữa hai người bạn thời trẻ.",
        "video_prompt": None,
        "image_prompt": (
            "Macro photograph of handwritten personal letters written in faded violet ink on yellowed thin paper, delicate Vietnamese cursive script, "
            "stacked neatly with soft creases, soft natural window light, historical authenticity, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "LETTERS_SURFACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_027",
        "source_segments": ["053", "054"],
        "narrative_function": "FRIENDSHIP_BOND",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": ["CHAR_CHU_MINH"],
        "story_characters": ["CHAR_CHU_MINH", "CHAR_BA_HAO_YOUNG", "CHAR_BA_THOA_YOUNG"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Chú Minh xúc động chia sẻ về giao ước thanh cao giữa hai người phụ nữ lao động nghèo.",
        "video_prompt": None,
        "image_prompt": (
            "Medium shot of a 58-year-old Vietnamese man (CHAR_CHU_MINH) looking warmly toward Mai, eyes glistening with quiet admiration, "
            "his hand resting gently on the wooden armrest, soft indoor light, cinematic documentary, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "PAN_RIGHT", "speed": "SLOW", "subject_anchor": "MINH_FACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_028",
        "source_segments": ["055", "056"],
        "narrative_function": "DISPELLING_SUSPICION",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Sự nghi ngờ vụ lợi hoàn toàn tan biến trong lòng Mai, thay bằng lòng tôn kính sâu sắc.",
        "video_prompt": None,
        "image_prompt": (
            "Close-up of a 32-year-old Vietnamese woman (CHAR_MAI), a soft peaceful smile breaking through her previous anxiety, "
            "eyes shining with understanding and pride, warm natural light framing her face, 35mm lens."
        ),
        "image_motion": {"type": "STATIC_INTENTIONAL", "speed": "NORMAL", "subject_anchor": "MAI_FACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_029",
        "source_segments": ["057", "058"],
        "narrative_function": "FLASHBACK_TEXTILE_MILL",
        "location_id": "LOC_GAC_XEP_BAO_LOC",
        "visible_characters": ["CHAR_BA_HAO_YOUNG", "CHAR_BA_THOA_YOUNG"],
        "story_characters": ["CHAR_BA_HAO_YOUNG", "CHAR_BA_THOA_YOUNG"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P1",
        "visual_mode_reason": "Tái hiện quá khứ lao động: Hai nữ công nhân trẻ đứng bên máy dệt vải năm 1980s, cùng chia sẻ nhọc nhằn và gom góp từng đồng.",
        "video_prompt": (
            "Start: A 32-year-old Vietnamese woman (CHAR_BA_HAO_YOUNG) and a 28-year-old woman (CHAR_BA_THOA_YOUNG) stand side-by-side in a 1980s textile factory. "
            "Action: Both women skillfully operate a vintage mechanical weaving loom, exchanging a warm supportive smile amidst rhythmic loom motion. "
            "Camera: Medium lateral dolly tracking past spinning yarn spools, capturing their earnest, hardworking expressions. "
            "End: They pause at shift end, wiping their brows and sharing a humble tin water canteen. Muted 1980s documentary tones, film grain."
        ),
        "image_prompt": (
            "Archival documentary scene from the 1980s: Two young Vietnamese women (CHAR_BA_HAO_YOUNG and CHAR_BA_THOA_YOUNG) in faded blue factory workwear "
            "working together at a textile weaving loom, cotton fibers in the air, warm industrial sunlight, subtle film grain, realistic working-class dignity, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "PAN_LEFT", "speed": "SLOW", "subject_anchor": "WORKERS_FIGURES", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_030",
        "source_segments": ["059", "060"],
        "narrative_function": "EVIDENCE_LAND_DEED_OVERLAY",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": [],
        "story_characters": ["CHAR_BA_HAO_YOUNG", "CHAR_BA_THOA_YOUNG"],
        "props": ["PROP_LAND_DEED_1992"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Hiển thị chứng cứ đất đai 650m2 trước khi bước vào Reveal 1.",
        "video_prompt": None,
        "image_prompt": (
            "Macro shot of an official 1992 Vietnamese land transfer document (PROP_LAND_DEED_1992), typed Vietnamese administrative text, "
            "official round red seal of Bảo Lộc town authorities, aged folded paper on dark wood, clean documentary focus, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "EVIDENCE_INSPECTION", "speed": "SLOW", "subject_anchor": "DEED_SEAL", "safe_crop_zone": "CENTER"},
        "requires_overlay": True,
        "overlay_data": {
            "overlay_type": "DOCUMENT",
            "overlay_text": "GIẤY CHUYỂN NHƯỢNG QUYỀN SỬ DỤNG ĐẤT (1992)\nThửa đất: 650m2 đất vườn tại Bảo Lộc, Lâm Đồng\nĐại diện đứng tên: Nguyễn Thị Hảo",
            "overlay_position": "LOWER_THIRD",
            "font_style": "CLEAN_SERIF_DOCUMENTARY"
        }
    },
    {
        "scene_id": "SC_031",
        "source_segments": ["061", "062"],
        "narrative_function": "REVEAL_1_TRUTH",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": [],
        "story_characters": ["CHAR_BA_HAO_YOUNG", "CHAR_BA_THOA_YOUNG"],
        "props": ["PROP_VINTAGE_PHOTO_BAO_THOA", "PROP_PASSBOOK_1994", "PROP_LAND_DEED_1992"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "BƯỚC NGOẶT 1 (REVEAL 1): Tài sản là quỹ chung danh dự của hai người phụ nữ lao động nghèo. Chọn IMAGE_ONLY tĩnh lặng để giọng đọc chiếm trọn cảm xúc.",
        "video_prompt": None,
        "image_prompt": (
            "Artistic documentary composition of the vintage sepia photograph of Vietnamese coworkers Bà Hảo and Bà Thoa (PROP_VINTAGE_PHOTO_BAO_THOA) resting "
            "harmoniously beside the 1994 passbook and 1992 land deed on a polished dark timber surface, soft sacred morning sunlight, 35mm film."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "PHOTO_AND_DOCUMENTS", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_032",
        "source_segments": ["063", "064"],
        "narrative_function": "HONOR_AGREEMENT",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": [],
        "story_characters": ["CHAR_BA_HAO_YOUNG", "CHAR_BA_THOA_YOUNG"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Tôn vinh lời hứa thiêng liêng: Bức tranh tình bạn cao cả vượt qua thời gian và gian khó.",
        "video_prompt": None,
        "image_prompt": (
            "Black-and-white archival photograph from 1985 of two young Vietnamese working women (young Bà Hảo and young Bà Thoa) sitting on a wooden bench, "
            "sharing a simple meal from an enamel tiffin carrier, genuine smiles, soft vintage grain, timeless dignity, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "SLOW_PULL_OUT", "speed": "SLOW", "subject_anchor": "TWO_FRIENDS", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_033",
        "source_segments": ["065", "066"],
        "narrative_function": "GUARDIAN_OF_PROMISE",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": [],
        "story_characters": ["CHAR_BA_HAO_ELDER"],
        "props": ["PROP_WOODEN_BOX"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Hình ảnh người bà âm thầm giữ gìn trách nhiệm và bảo quản quỹ chung suốt gần ba mươi năm.",
        "video_prompt": None,
        "image_prompt": (
            "Vintage memory portrait of an 80-year-old Vietnamese grandmother (CHAR_BA_HAO_ELDER) seated in soft window light, her wrinkled weathered hands "
            "gently resting on the closed wooden box on her lap, a serene and resolute gaze, photorealistic documentary realism, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "STATIC_INTENTIONAL", "speed": "NORMAL", "subject_anchor": "BA_HAO_FIGURE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_034",
        "source_segments": ["067", "068"],
        "narrative_function": "EMOTIONAL_REALIZATION",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P2",
        "visual_mode_reason": "Khoảnh khắc xúc động sâu sắc: Mai nhìn ra cửa sổ trời mưa bay, đôi mắt ngấn lệ tự hào về người bà.",
        "video_prompt": (
            "Start: A 32-year-old Vietnamese woman (CHAR_MAI) stands beside a French colonial window in Chú Minh's house. "
            "Action: Raindrops trickle down the glass pane outside; she reaches up, gently touching the cool glass as a single tear rolls down her cheek. "
            "Camera: Close-up slowly reframing from the rain streaks on the window to her emotional, proud expression. "
            "End: She wipes her cheek, a warm smile of gratitude emerging. Soft highland overcast lighting."
        ),
        "image_prompt": (
            "Cinematic close-up of a 32-year-old Vietnamese woman (CHAR_MAI) looking through a rain-streaked window in Lâm Đồng, "
            "soft tear on her cheek, expression of profound emotional pride and reverence, muted highland rainy daylight, 35mm lens."
        ),
        "image_motion": {"type": "SUBTLE_REFRAME", "speed": "SLOW", "subject_anchor": "MAI_FACE", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_035",
        "source_segments": ["069", "070"],
        "narrative_function": "FAMILY_COMMITMENT",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": ["CHAR_MAI", "CHAR_CHU_MINH"],
        "story_characters": ["CHAR_MAI", "CHAR_CHU_MINH"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P2",
        "visual_mode_reason": "Hành động quyết tâm gia đình: Chú Minh đặt tay lên tay Mai, đồng thuận thực hiện di nguyện của bà cố.",
        "video_prompt": (
            "Start: Chú Minh (58, male) and Mai (32, female) sit facing each other across the wooden tea table. "
            "Action: Chú Minh leans forward with a firm nod, placing his weathered hand over Mai's hand in mutual agreement. "
            "Camera: Medium shot slowly pushing in on their clasped hands, then tilting up to their resolute, unified faces. "
            "End: Mai nods firmly back, their shared determination clear. Consistent warm indoor provincial lighting."
        ),
        "image_prompt": (
            "Medium two-shot of a 58-year-old Vietnamese man (CHAR_CHU_MINH) placing his reassuring hand over the hand of a 32-year-old woman (CHAR_MAI) "
            "at a wooden dining table, expressions of deep solidarity and family agreement, warm natural lighting, 35mm documentary."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "CLASPED_HANDS", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_036",
        "source_segments": ["071", "072"],
        "narrative_function": "SPIRITUAL_LEGACY",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": [],
        "story_characters": ["CHAR_BA_HAO_ELDER", "CHAR_BA_THOA_ELDER"],
        "props": ["PROP_WOODEN_BOX"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Bí mật chuyển hóa thành di sản tinh thần: Chiếc hộp gỗ nằm yên bình cạnh bình hoa cúc vàng.",
        "video_prompt": None,
        "image_prompt": (
            "Still life of the open wooden box (PROP_WOODEN_BOX) resting on a polished Vietnamese timber sideboard beside a vase of fresh yellow chrysanthemums, "
            "gentle sunshine illuminating the warm wood grain, atmosphere of peace and fulfillment, 35mm lens."
        ),
        "image_motion": {"type": "PAN_LEFT", "speed": "SLOW", "subject_anchor": "BOX_AND_FLOWERS", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_037",
        "source_segments": ["073", "074"],
        "narrative_function": "PHILOSOPHICAL_REFLECTION",
        "location_id": "LOC_NHA_CHU_MINH",
        "visible_characters": [],
        "story_characters": [],
        "props": ["PROP_VINTAGE_PHOTO_BAO_THOA"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Chiêm nghiệm triết lý: Giá trị nhân văn của những lời hứa danh dự thầm lặng.",
        "video_prompt": None,
        "image_prompt": (
            "Artistic close-up of weathered aged Vietnamese hands holding the 1980s photograph of two friends, sunlight filtering across wrinkled skin, "
            "symbolizing enduring loyalty and moral responsibility, documentary realism, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "STATIC_INTENTIONAL", "speed": "NORMAL", "subject_anchor": "HANDS_AND_PHOTO", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_038",
        "source_segments": ["075", "076"],
        "narrative_function": "JOURNEY_TO_NURSING_HOME",
        "location_id": "LOC_VIEN_DUONG_LAO_LAM_DONG",
        "visible_characters": ["CHAR_MAI"],
        "story_characters": ["CHAR_MAI"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P2",
        "visual_mode_reason": "Hành trình thực địa: Mai đi xe dọc theo con đường đèo uốn lượn mù sương ở Lâm Đồng hướng về viện dưỡng lão.",
        "video_prompt": (
            "Start: A passenger car drives along a scenic winding mountain road in Lâm Đồng surrounded by towering pine trees and soft morning mist. "
            "Action: The car turns into the stone driveway of a peaceful French-colonial style rest home facility. Mai steps out carrying her folder. "
            "Camera: Wide cinematic landscape pan from the misty highland valley following the car to the facility gates. "
            "End: Mai walks up the stone steps toward the glass sunroom doors. Highland morning sunlight breaking through mist."
        ),
        "image_prompt": (
            "Cinematic landscape of a peaceful colonial-style rest home in Lâm Đồng nestled among pine-covered hills, a 32-year-old Vietnamese woman "
            "(CHAR_MAI) in a warm cardigan walking up the front stone pathway, soft morning highland mist, documentary realism, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "PAN_RIGHT", "speed": "SLOW", "subject_anchor": "BUILDING_AND_MAI", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_039",
        "source_segments": ["077", "078"],
        "narrative_function": "REVEAL_2_ORPHAN_SHELTER",
        "location_id": "LOC_VIEN_DUONG_LAO_LAM_DONG",
        "visible_characters": ["CHAR_MAI", "CHAR_BA_THOA_ELDER"],
        "story_characters": ["CHAR_MAI", "CHAR_BA_THOA_ELDER", "CHAR_BA_HAO_ELDER"],
        "props": ["PROP_VINTAGE_PHOTO_BAO_THOA"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "BƯỚC NGOẶT 2 (REVEAL 2): Gặp gỡ bà Thoa tại viện dưỡng lão; đích đến thực sự của quỹ là mái ấm tình thương cho trẻ mồ côi. Giữ ảnh tĩnh để khoảnh khắc thiêng liêng đọng lại.",
        "video_prompt": None,
        "image_prompt": (
            "Medium shot inside a bright sunroom in Lâm Đồng: An 80-year-old Vietnamese woman in a wheelchair (CHAR_BA_THOA_ELDER) holding the vintage photograph, "
            "tears glistening in her gentle eyes, as a 32-year-old woman (CHAR_MAI) kneels gently beside her holding her hand, morning light, emotional truth, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "TWO_WOMEN", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_040",
        "source_segments": ["079", "080"],
        "narrative_function": "GARDEN_WALK_TOGETHER",
        "location_id": "LOC_VIEN_DUONG_LAO_LAM_DONG",
        "visible_characters": ["CHAR_MAI", "CHAR_BA_THOA_ELDER"],
        "story_characters": ["CHAR_MAI", "CHAR_BA_THOA_ELDER"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P2",
        "visual_mode_reason": "Hành động kết nối thế hệ: Mai đẩy xe lăn cho bà Thoa dạo bước trong sân vườn đầy nắng thông xanh.",
        "video_prompt": (
            "Start: Mai (32, female) stands behind Bà Thoa's (80, female) manual wheelchair in the facility's courtyard garden. "
            "Action: Mai slowly pushes the wheelchair along the paved brick path under tall pine trees, Bà Thoa looking up and smiling warmly. "
            "Camera: Lateral tracking shot moving alongside them, capturing gentle conversation and sun dappling through pine needles. "
            "End: They pause by a flowering hydrangeas bed, bathed in warm golden highland sunlight. Consistent attire."
        ),
        "image_prompt": (
            "Medium shot of a 32-year-old Vietnamese woman (CHAR_MAI) gently wheeling an 80-year-old woman in a wheelchair (CHAR_BA_THOA_ELDER) "
            "along a brick garden path lined with hydrangeas and tall pine trees in Lâm Đồng, golden morning sunshine, tranquil warmth, 35mm."
        ),
        "image_motion": {"type": "PAN_RIGHT", "speed": "SLOW", "subject_anchor": "WHEELCHAIR_WALK", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_041",
        "source_segments": ["081", "082"],
        "narrative_function": "GENERATIONAL_HANDSHAKE",
        "location_id": "LOC_VIEN_DUONG_LAO_LAM_DONG",
        "visible_characters": ["CHAR_MAI", "CHAR_BA_THOA_ELDER"],
        "story_characters": ["CHAR_MAI", "CHAR_BA_THOA_ELDER"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Cận cảnh bàn tay trẻ tuổi của Mai đan chặt bàn tay già nua nhăn nheo của bà Thoa.",
        "video_prompt": None,
        "image_prompt": (
            "Close-up of young smooth Vietnamese hands (CHAR_MAI) clasped gently around elderly, wrinkled, weathered Vietnamese hands (CHAR_BA_THOA_ELDER), "
            "warm natural highland sunlight, symbol of generational promise and continuity, 35mm macro lens."
        ),
        "image_motion": {"type": "STATIC_INTENTIONAL", "speed": "NORMAL", "subject_anchor": "HANDS_CLASPED", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_042",
        "source_segments": ["083", "084"],
        "narrative_function": "HIGHLAND_MIST_REFLECTION",
        "location_id": "LOC_KHU_DAT_BAO_LOC",
        "visible_characters": [],
        "story_characters": [],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Khung cảnh chiêm nghiệm Sau Cánh Cửa: Đồi chè Bảo Lộc trong nắng sớm thanh khiết.",
        "video_prompt": None,
        "image_prompt": (
            "Cinematic landscape of rolling Vietnamese tea plantations and distant mountains in Bảo Lộc under early morning golden hour, "
            "thin layers of mist hovering above vibrant green rows of tea bushes, tranquil cinematic documentary beauty, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "PAN_LEFT", "speed": "SLOW", "subject_anchor": "TEA_HILLS", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_043",
        "source_segments": ["085", "086"],
        "narrative_function": "BLUEPRINT_OF_SHELTER",
        "location_id": "LOC_KHU_DAT_BAO_LOC",
        "visible_characters": [],
        "story_characters": ["CHAR_MAI", "CHAR_CHU_MINH"],
        "props": [],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Bản vẽ phác thảo mái ấm tình thương trẻ em đặt trên bàn gỗ ngoài trời bên mảnh đất 650m2.",
        "video_prompt": None,
        "image_prompt": (
            "Macro shot of architectural blueprints and sketches for a modest community children's shelter, titled in clean Vietnamese text, "
            "resting on a rustic wooden table with a view of green hills in the soft background, bright hopeful daylight, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "SLOW_PUSH_IN", "speed": "SLOW", "subject_anchor": "BLUEPRINT_DETAILS", "safe_crop_zone": "CENTER"},
        "requires_overlay": True,
        "overlay_data": {
            "overlay_type": "DOCUMENT",
            "overlay_text": "DỰ ÁN MÁI ẤM TÌNH THƯƠNG (TIẾP NỐI DI NGUYỆN)\nĐịa điểm: Thửa đất 650m2, Bảo Lộc - Lâm Đồng\nĐơn vị phối hợp: Gia đình & Đại diện cộng đồng",
            "overlay_position": "LOWER_THIRD",
            "font_style": "CLEAN_SERIF_DOCUMENTARY"
        }
    },
    {
        "scene_id": "SC_044",
        "source_segments": ["087", "088"],
        "narrative_function": "GROUNDBREAKING_WALK",
        "location_id": "LOC_KHU_DAT_BAO_LOC",
        "visible_characters": ["CHAR_MAI", "CHAR_CHU_MINH"],
        "story_characters": ["CHAR_MAI", "CHAR_CHU_MINH", "CHAR_BA_THOA_ELDER"],
        "props": [],
        "visual_mode": "VIDEO_RECOMMENDED",
        "motion_value": "HIGH",
        "video_priority": "P1",
        "visual_mode_reason": "Hành động kết thúc giàu ý nghĩa: Mai, Chú Minh và các thành viên gia đình cùng bước đi trên mảnh đất đồi chè, hướng về tương lai.",
        "video_prompt": (
            "Start: Mai (32, female) and Chú Minh (58, male) stand side by side on the hillside boundary of the 650m2 garden plot in Bảo Lộc. "
            "Action: They walk slowly together across the green grass toward the edge of the hill, Chú Minh pointing toward the distant sunlit mountain valley. "
            "Camera: Wide tracking shot moving slowly backwards ahead of them, framing their hopeful strides against the vast blue sky. "
            "End: They stop side-by-side looking at the sunrise over the valley, smiling with deep peace. Crisp morning sunlight."
        ),
        "image_prompt": (
            "Wide cinematic shot of a 32-year-old Vietnamese woman (CHAR_MAI) and a 58-year-old man (CHAR_CHU_MINH) walking together on a green "
            "hillside in Bảo Lộc overlooking tea valleys, warm morning sun flare, blue sky, feeling of hope, closure and new beginning, cinematic 35mm documentary photography."
        ),
        "image_motion": {"type": "PAN_RIGHT", "speed": "SLOW", "subject_anchor": "TWO_FIGURES", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    },
    {
        "scene_id": "SC_045",
        "source_segments": ["089", "090"],
        "narrative_function": "FINAL_FAREWELL",
        "location_id": "LOC_NHA_MAI_HCM",
        "visible_characters": [],
        "story_characters": ["CHAR_MAI", "CHAR_BA_HAO_ELDER", "CHAR_BA_THOA_ELDER"],
        "props": ["PROP_WOODEN_BOX", "PROP_VINTAGE_PHOTO_BAO_THOA"],
        "visual_mode": "IMAGE_ONLY",
        "motion_value": "LOW",
        "video_priority": None,
        "visual_mode_reason": "Hình ảnh kết tập: Khung ảnh kỷ niệm mới chụp Mai cùng bà Thoa đặt trang trọng bên chiếc hộp gỗ mở nắp.",
        "video_prompt": None,
        "image_prompt": (
            "Closing still of a modern Vietnamese wooden credenza: Beside the historic open wooden box (PROP_WOODEN_BOX) sits a freshly framed photograph "
            "of Mai gently embracing elderly Bà Thoa, warm domestic twilight lighting, golden Sau Cánh Cửa documentary warmth, 35mm lens."
        ),
        "image_motion": {"type": "SLOW_PULL_OUT", "speed": "SLOW", "subject_anchor": "FRAMED_PHOTO", "safe_crop_zone": "CENTER"},
        "requires_overlay": False,
        "overlay_data": None
    }
]
