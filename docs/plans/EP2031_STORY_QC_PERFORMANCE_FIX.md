# EP2031 — Story QC correctness and latency

Baseline: `c853f29ea5ff0759fbc057e0d156b7ee36734c14`.
Scope: fix the production source-to-Story Bible generator/QC, without editing the user's transcript or an existing script. Preserve the selected factual source, direction, topic and duration. Audio Formula V1, TTS, Visual, Flow and assembler code are outside this change.

## Reproduced failure

The original Studio job `5c174713780a41608733cfaf87b5c466` completed after approximately **17 minutes 31 seconds** and **64 provider calls**, but saved a **FAIL** Story QC report. Transport completion did not imply QC acceptance. The UI screenshot at 839 seconds showed many successful provider responses; a slow or unavailable provider was not the sole cause.

The saved best draft had two misleading blockers:

- `UNRESOLVED_CORE_PROP`: the opening phrase “hình ảnh một nữ sale” was treated as a physical photograph requiring an investigative payoff.
- `UNRESOLVED_SETUP`: the ending explicitly limited the information to what the source supplied, while the reviewer warned what would happen **if a later script added an outcome**. That conditional writing guidance was counted as a present defect.

The factual audit split approximately 50 short Story Bible leaves into groups of ten, twice. Repair rounds reviewed modified drafts repeatedly; the service then re-audited the already audited returned draft. Only successful source reviews were reusable. Changing the names of outstanding findings at equal severity could keep repair running despite no measurable improvement.

Evidence, including the original report and measured job statistics: [narrative-evidence/EP2031-story-qc.json](narrative-evidence/EP2031-story-qc.json).

## Code corrections

1. Disambiguate descriptive “hình ảnh” from photographic evidence. Explicit photo, camera and screen mentions remain subject to the physical-prop gate; the semantic reviewer still checks promises and payoffs.
2. Source Story review separates `DEFECT` from `GUIDANCE`. A present defect remains blocking. Guidance requires complete grounded audit checks before acceptance. Contradictory “no defect” findings are retried and fail closed if still invalid. A factual retelling preserves attribution and uncertainty, including a source's hypothetical nature; it does not independently verify the source.
3. Short Bible fields use at most 20 leaves / 6,000 characters per batch. An indivisible longer leaf remains intact. Scripts retain ten segments per batch. Each independent pass still covers **every** item, checks exact quotes and source references, and separately reviews the mode contract.
4. Within one QC engine/job, completed source reviews, including negative results, are reused only for the same full Bible/context hash, provider and requested model. Errors are never cached. Reusing a negative review retains FAIL.
5. Bind the complete Story QC report to its Bible hash. The generation service reuses the returned repair report only when this hash matches; otherwise it audits again.
6. Stop source repair after a non-improving round, repeated content or any reviewer error. Retain the best known draft and its honest status. Genuine improvements can continue within the existing three-round bound. Legacy repair behavior remains unchanged.

Source policy versions are now `source-review-v3-attributed-limits` and `semantic-v32-observed-source-defects`. Earlier source reviews need fresh validation; a version change is not approval.

## Validation

Regression coverage exercises full leaf coverage in both passes, response-size bounds, invalid quote rejection, negative cache reuse and invalidation, errors never cached, genuine photos still blocked, guidance versus current defects, contradictory reviewer output, repair stopping and service-level report reuse with stale-hash fallback.

Live acceptance and full-test results are recorded below after completion. The original app remains open on port 8765; the separately started test backend uses the actual `.venv` and production Studio UI/API on port 8772. No mocked provider or manually rewritten artifact is used for live acceptance.

### Live result — 05 October 2026

- Started from the Sources screen on port 8772, selecting the same EP2031 and its already selected third direction, and clicked **Tạo cốt truyện từ hướng đã chọn**. The UI automatically opened the new Story Bible.
- Completed in **163.09 seconds**, with **11 actual provider calls**, **no repair rounds**, and **QC PASS / zero issues**. The original job's timestamps span 1,052.02 seconds (its UI log rounded to 1,051 seconds) with 64 calls. This is one measured run, not a guaranteed duration for every source/provider.
- New Story request ID: `114511c9-7a04-4e01-9a01-37ae4c740c92`.
- Provider: `openai_compatible`, requested model `auto`; actual model recorded honestly as `proxy auto — chưa xác định` because the proxy does not identify the upstream model.
- All **48 atomic Story fields** were checked in **each** of two complete source passes (three factual batches plus the mode contract per pass). The two separate grounded semantic passes also validate successfully under the current policy.
- Read the whole Story Bible: it attributes the hypothetical career narrative to the source, does not invent a verified identity, follows the source's sequence and limits the ending to the reported job change. Descriptive “hình ảnh” no longer creates a false photo investigation.
- Browser reload and reselect EP2031: the same request ID/hash and QC PASS remain. Story remains `NEEDS_REVIEW`, and downstream Script/Audio remain `STALE`; this run does not approve them or certify a completed MC script, TTS or rendered video.
- Screenshot: [narrative-evidence/EP2031-story-qc-pass.png](narrative-evidence/EP2031-story-qc-pass.png). The existing 8765 process has not been closed/restarted and still contains the old Python code; use the test web at 8772 to see the fix now.

### Automated results

- Related source tests: **102 passed**, including 14 new regression cases.
- Expanded isolated selection: **188 passed + 6 subtests**, including Story contracts, semantic review, lineage guards and Audio flow.
- Full suite in a separate local checkout: **838 passed, 15 failed, 10 errors, 5 skipped + 6 subtests**. Compared failure/error IDs against the prior isolated baseline: **zero new failures**, the same 25 existing failures/errors remain. Do not call this a completely passing full suite.
- Exact suite metadata and unchanged failure IDs: [narrative-evidence/story-qc-tests.json](narrative-evidence/story-qc-tests.json).
- Python-only change: no frontend source or asset changes, so no dist rebuild is needed.

### Manual verification

1. Open `http://127.0.0.1:8772/`, select EP2031 and open **Cốt truyện**. Confirm **QC ĐẠT (PASS)** and **CHỜ DUYỆT**.
2. In **Nguồn tham khảo**, confirm the source revision, mode and selected third direction are preserved. To exercise a new AI run, click **Tạo cốt truyện từ hướng đã chọn** once; this intentionally creates new lineage and stales downstream artifacts.
3. Watch the processing log for source pass `1/2` and `2/2` with numbered groups. Completion should display the real elapsed time; provider latency/real defects may vary.
4. Reload and reselect EP2031. Confirm the newly stored Story and QC match. Review/approve the Story yourself before proceeding to the MC script; a Story QC PASS alone does not establish publication quality.
