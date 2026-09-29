# SAU CÁNH CỬA STUDIO — DESIGN SYSTEM MASTER
## UI/UX Pro Max Specification for Desktop Video Production Studio

> **Specification Source:** Generated via UI/UX Pro Max (`ui-ux-pro-max-skill`)  
> **Product Category:** AI Desktop Video Production Studio / Professional Creator Tool  
> **Target Platform:** Windows 10/11 Desktop (Optimized for 1366×768, 1920×1080, 2560×1440)  
> **Aesthetic Direction:** Professional, Dark-First, Content-Centric, High Information Density, Minimalist Cinematic  
> **Dials Configuration:** `variance: 3` (Consistent & structured) | `motion: 2` (Fast, non-distracting 150-250ms) | `density: 9` (Professional studio density)

---

## 1. Design Principles & Anti-Pattern Rules

1. **Content-First, Not Chrome-Heavy:** Visual thumbnails, waveforms, video clips, and script texts are the primary focus. UI chrome must recede into neutral dark tones.
2. **Never Wonder "What Next?":** Every screen and dashboard must clearly surface the **Next Best Action** (`VIỆC TIẾP THEO`) without requiring manual investigation.
3. **High Density without Clutter:** Use a 4px base grid, compact row heights (32px–40px), precise 1px borders, and clear typographic hierarchy. Avoid oversized SaaS landing page cards, excessive empty whitespace, and fluffy padding.
4. **Zero Emoji in Production UI:** All icons must be crisp SVG outline vectors (Lucide icon system).
5. **No Color-Only State Indicators:** Every status badge must combine color with a clear textual label and icon (e.g., `APPROVED`, `NEEDS_REVIEW`, `STALE`, `FAILED`).
6. **No Technical Leaks in Standard Mode:** Normal UX presents friendly names (`Bà Hảo (Trẻ)`) rather than raw internal keys (`CHAR_BA_HAO_YOUNG`). An **Advanced Mode** toggle reveals technical IDs, hashes, and JSON schemas on demand.
7. **Authoritative Audio Clock:** Timecodes (`00:04:48.750`) and audio boundaries strictly drive all visual and timeline alignment.

---

## 2. Color Palette & Semantic Tokens

### 2.1 Base Neutrals (Dark Studio Slate)
| Token | Hex | Role | Usage |
| :--- | :--- | :--- | :--- |
| `--color-background` | `#0B0F17` | Canvas Base | Application background, canvas void |
| `--color-surface` | `#111827` | Primary Surface | Sidebars, main workspace panels, modals |
| `--color-card` | `#161F36` | Card / Item Surface | Storyboard cards, script segment rows, inspector |
| `--color-card-hover` | `#1E293B` | Interactive Hover | Row hover, active card highlight |
| `--color-border` | `#28354D` | Subtle Border | 1px dividers, track separators, card outlines |
| `--color-border-focus` | `#3B82F6` | Focus Ring | Keyboard focus ring (WCAG 2.1 compliant) |

### 2.2 Text & Contrast Hierarchy
| Token | Hex | Role | Contrast Ratio |
| :--- | :--- | :--- | :--- |
| `--color-foreground` | `#F8FAFC` | High-emphasis | Headers, primary titles, script text (15.2:1) |
| `--color-foreground-muted` | `#94A3B8` | Medium-emphasis | Subtitles, scene metadata, segment numbers (7.8:1) |
| `--color-foreground-subtle` | `#64748B` | Low-emphasis | Timestamps, technical notes, empty hints (4.6:1) |

### 2.3 Semantic & Pipeline Accents
| Token | Hex | Role | Meaning |
| :--- | :--- | :--- | :--- |
| `--color-brand` | `#E11D48` | Sau Cánh Cửa Crimson | Brand mark, primary highlights, golden badges |
| `--color-action` | `#2563EB` | Production Action Blue | Primary buttons, execute, generate, export |
| `--color-success` | `#10B981` | Emerald | Approved, Passed QC, Complete, Matched |
| `--color-warning` | `#F59E0B` | Amber | Needs Review, Stale Artifact, Fallback Active |
| `--color-danger` | `#EF4444` | Red | Failed, Discontinuity, Missing Essential Asset |
| `--color-video-badge` | `#8B5CF6` | Purple Violet | Video Recommended Badge (`VIDEO_RECOMMENDED`) |
| `--color-image-badge` | `#06B6D4` | Cyan Teal | Image Only Badge (`IMAGE_ONLY`) |

---

## 3. Typography & Vietnamese Localization

- **Primary UI Font:** `Inter`, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif.
  - Full native rendering for Vietnamese diacritics (`ă, â, đ, ê, ô, ơ, ư`).
- **Monospace Font:** `JetBrains Mono`, `Consolas`, monospace.
  - Reserved strictly for timecodes (`00:12:10.627`), segment numbers, hashes, and technical logs.

### Scale:
- `text-xs` (11px / 16px line): Metadata labels, timecode markers, tag badges.
- `text-sm` (13px / 18px line): Default UI text, buttons, inspector inputs, scene cards.
- `text-base` (15px / 24px line): Script narration body, story premise.
- `text-lg` (18px / 26px line): Panel titles, modal headers.
- `text-xl` (20px / 28px line): Screen titles, episode names.

---

## 4. Layout & Zone Architecture

```text
+-----------------------------------------------------------------------------------------------+
| TOP PROJECT BAR (Height: 48px)                                                                |
| [Logo] Sau Cánh Cửa Studio | EP003 - Chiếc Hộp Gỗ... [Saved ✓] | [Quick Actions] [Settings]   |
+-----------------------------------------------------------------------------------------------+
| PIPELINE PROGRESS BAR (Height: 40px)                                                          |
| 01 Idea -> 02 Story -> 03 Script -> 04 Audio -> 05 Visual -> 06 Flow -> 07 Assets -> ...     |
+---------------+---------------------------------------------------------------+---------------+
| LEFT SIDEBAR  | CENTER WORKSPACE                                              | RIGHT         |
| (Width: 220px)| (Flexible Canvas, High Density)                              | INSPECTOR     |
| - Tổng quan   |                                                               | (Width: 320px)|
| - Ý tưởng     | [Prominent NEXT ACTION Banner: VIỆC TIẾP THEO]                | Context-aware |
| - Cốt truyện  |                                                               | properties,   |
| - Kịch bản    | Work area for active stage:                                   | QC details,   |
| - Audio       | - Storyboard Grid / List                                      | prompts,      |
| - Visual Plan | - Script 2-Panel View                                         | overrides     |
| - Google Flow | - Waveform Audio Player                                       |               |
| - Assets      | - Timeline Tracks (V2, V1, A2, A1)                            |               |
| - Timeline    | - Render Status / Video Player                                |               |
| - Xuất Video  |                                                               |               |
| - QC Master   |                                                               |               |
+---------------+---------------------------------------------------------------+---------------+
| BOTTOM JOB & STATUS BAR (Height: 32px)                                                        |
| [Jobs: 1 Running] Rendering EP003: 48% | FFmpeg 9.0 Active | Disk: 142GB Free | UTF-8         |
+-----------------------------------------------------------------------------------------------+
```

---

## 5. Pipeline Stages & Approval Model

Each pipeline stage follows an explicit state machine:
- `NOT_STARTED`: Gray neutral state.
- `IN_PROGRESS`: Blue pulsating indicator.
- `NEEDS_REVIEW`: Amber badge with notification dot.
- `APPROVED` / `COMPLETE`: Emerald checkmark.
- `STALE`: Amber warning icon indicating upstream modification invalidated this stage.
- `FAILED`: Red alert requiring user intervention or retry.

### Dependency Cascade:
- Modifying `Script` $\to$ Marks `Audio`, `Visual Plan`, `Flow Export`, `Timeline` as **`STALE`**.
- Modifying `Audio Master` $\to$ Marks `Timeline` and `Assembler Render` as **`STALE`**.
- Modifying `Visual Plan` $\to$ Marks `Google Flow Export` as **`STALE`**.

---

## 6. Interaction Guidelines & Shortcuts

- **Click-to-Select:** Selecting any scene or asset immediately populates the Right Inspector.
- **Instant Video Fallback:** If an Omni video is missing, low quality, or rejected, clicking **"Dùng ảnh"** immediately reassigns the Dynamic Still V9.3.2 pipeline without breaking the visual plan.
- **Shortcuts:**
  - `Space`: Play / Pause preview player
  - `Ctrl + S`: Save project state
  - `Ctrl + O`: Open / Switch episode project
  - `Left / Right`: Jump previous / next scene in timeline
  - `F`: Fullscreen player preview
  - `Tab / Shift+Tab`: Cycle through interactive fields

---

## 7. Pre-Delivery Quality Checklist

- [x] Full Dark-First UI optimized for long editing sessions.
- [x] Contrast ratio $>4.5:1$ for normal text, $>7:1$ for headers.
- [x] Lucide SVG icons used exclusively (no emoji icons).
- [x] `cursor-pointer` applied to all clickable controls.
- [x] Smooth 150ms transitions on hover and active states.
- [x] Clear non-modal confirmation dialogs for destructive actions.
- [x] Responsive layout supporting 1366×768, 1920×1080, and 2560×1440.
