# EP2031 — failed Full Script outline request

Baseline: `4c6b7d585c3701635e008cb58af4a55912fae492`.
The user's screenshot was from the existing Studio on port 8765, using an approved Story Bible from the earlier QC policy. The selected direction was changed by the user to the living-space/career story; this fix keeps that selection and does not replace it with the previous test direction.

## Failure and cause

- The production request was a text request to `/v1/chat/completions`, model `auto`, for JSON scene planning. No Studio image-generation endpoint/tool was called.
- The proxy returned HTTP 502 wrapping upstream `status=413`. The proxy's diagnostic panel also displayed an “image generation tool” error. That string is proxy/upstream output; it does not establish that Studio submitted an image request. No account identity or credential from that panel is copied into this report.
- `scene_outline._prompt` excluded `adaptation_context` from the Story JSON, but included the entire `story_qc_report`: reviewer payloads, all quote evidence and request records. The source itself already appeared separately in the writer context. This added **89,571 UTF-8 bytes of review diagnostics** to a creative prompt.
- For the actual approved Story `f80729b2-41f8-43e6-a60c-ab5f3e337682`, the baseline outline prompt was **171,776 bytes**. Removing non-creative diagnostics/state reduces it to **82,100 bytes** while preserving all source units, current story facts, ending and locks. These figures measure the exact prompt content; serialized HTTP payload size differs.
- `build_scene_outline` swallowed the provider exception and returned `None`. The generation service then reported a plot-contract failure, incorrectly directing the user to rewrite a story that had passed QC.

## Fix

1. Source outline prompts exclude QC reports, approval/status bookkeeping and a previous outline. Full source text, selected mode/brief, actual canon, locked facts and payoff requirements remain intact. Review reports and lineage remain stored on disk; nothing is truncated in the source.
2. The source outline system instruction explicitly asks for **text JSON**, without image/video generation or tool calls.
3. Required production outline provider errors propagate their original cause to the Studio job/error banner. Optional legacy callers still retain their `None` fallback. Invalid scene content still receives one bounded corrective attempt and remains blocked if it does not fulfill the contract.
4. Provider failure on that corrective attempt also preserves the original exception. The service cannot overwrite the script or call the writer after an outline transport failure. A successful preflight Story audit may update its QC report, without changing story canon or source lineage.
5. A shared `story_prompt_data` serializer applies the same exclusion to source script semantic review and both providers' source Story repair. Source segment repair excludes the duplicate `adaptation_context`, which is already sent through `writer_context`. Current scene plans, all prose, source units and actual requested repair findings remain available.

On the retained 81-segment draft, the exact script semantic prompt falls from **199,006 to 120,208 bytes**. For its actual eight flagged IDs, the repair prompt falls from **186,519 to 120,282 bytes**. These are prompt sizes, not a claim about the proxy's configured limit.

No changes to Audio Formula V1, TTS, Visual, Flow, assembler, provider credentials or model selection. No manual transcript/script edits.

## Verification

Regression cases cover all three source modes, large diagnostic reports having no effect on creative prompt size, preservation of canon/source/locks, required versus optional outline behavior, exceptions on the corrective attempt and Studio service preservation of the existing script on provider failure.

Live verification uses the actual `.venv`, configured OpenAI-compatible `auto` provider and production Studio UI/API on port 8772. The existing user's app remains open on port 8765. Results and manual steps are recorded here after the real job completes.

The first live attempt passed scene planning (14 scenes, about 20 seconds) and wrote **81 segments / 4,164 words**. It finished after 585 seconds with **NEEDS_REVISION**, not acceptance: source review rejected a nonliteral quote for paragraph 076, native review found repeated events, and segment repair hit the same upstream 413 because its source was duplicated. The draft was retained, and those downstream payload paths were then fixed. A production UI Auto-Repair run is recorded separately; this report does not turn the first attempt into PASS.

Evidence: [narrative-evidence/EP2031-outline-payload.json](narrative-evidence/EP2031-outline-payload.json).

### Final live result — transport fixed, script acceptance failed

- UI Auto-Repair with all final changes took **926.945 seconds / 64 calls**, with three bounded revision rounds. All three segment batches applied (9/9, 7/7, 7/7) and **zero upstream 413** occurred in this run.
- The saved result has **81 segments / 4,167 words**, script request **`1ed3f3cc-d833-4705-a59a-7a1751bb3d67`**, parent **`e406d823-0b15-4aa9-a9c1-c468561fdc84`**, still tied to Story **`f80729b2-41f8-43e6-a60c-ab5f3e337682`**. Requested model is `auto`; the proxy does not disclose the actual model. Do not label it Gemini or assert a particular underlying model.
- Final **NEEDS_REVISION**, not PASS. A source reviewer inserted a period into its quotation for item 049 where the real sentence continues with a comma. Its quote fails contiguous verbatim validation after one correction; source review remains ERROR. Native reviews also identify repeated blocks. A `GARBLED_VIETNAMESE` finding mentions caption errors absent from the cited Script paragraph; this is a reviewer limitation, not independently confirmed faulty Script spelling.
- Read all 81 paragraphs: genuine repetition remains in 013–024, 025–036 and 072–081, with overly repeated attribution. This draft is **not accepted as natural/publishable**. Fixing payload size does not certify script quality. No manual source/script patching or gate relaxation was used.
- Reload preserves the new request and text. Story and source lineage hashes match, leakage count is zero, but `is_current=false` and `audio_gate_allowed=false` because QC is incomplete/failed. Script stage remains NEEDS_REVIEW, dependent stages STALE.
- Screenshot: [narrative-evidence/EP2031-outline-payload-ui.png](narrative-evidence/EP2031-outline-payload-ui.png).

### Manual verification

1. Open **http://127.0.0.1:8772/**, select EP2031 and Kịch bản. Port 8765 is the original running process and has not reloaded these Python changes.
2. Verify 4,167 words / 81 paragraphs and the visible QC CHƯA ĐẠT banner. Approval/Audio transition must be disabled.
3. Reload the browser; confirm unchanged text and request ID in Advanced Mode. Do not mistake persisted text for approved text.
4. When another provider request fails, inspect the reported HTTP cause; required outline failures must no longer be replaced by a generic plot-contract warning. A new generation can require Story preflight QC under the current policy.
5. The retained draft still needs generator/reviewer quality work on repeated blocks and quotation errors. Do not click regeneration indefinitely, approve it, or start TTS as acceptance of this patch.

### Automated results

- Final related selection: **160 passed**.
- Expanded isolated selection: **227 passed + 6 subtests**.
- Full suite in an isolated checkout: **847 passed, 15 failed, 10 errors, 5 skipped + 6 subtests**. The failure/error IDs are exactly the same 25 as baseline; no new failures. These existing failures mean the full suite is not wholly passing.
- [narrative-evidence/outline-payload-tests.json](narrative-evidence/outline-payload-tests.json) contains exact counts and baseline comparison.
- Python-only change; frontend/dist are unchanged and do not need rebuilding.
