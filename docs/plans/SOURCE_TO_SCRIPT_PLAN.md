# Kế hoạch: Tạo kịch bản từ nguồn tham khảo

Ngày lập: 03/10/2026 (Asia/Bangkok). Repo: `D:\App\VieNeuTTS`, nhánh `main`.

Baseline lúc lập kế hoạch: `559187bb89e3623d00b0e4974f05d493da0a4179`.

Trạng thái: **P0–P5 hoàn thành bản đầu: triển khai, nghiệm thu web, commit và push main; giới hạn ghi trong báo cáo nghiệm thu**.

## 1. Mục tiêu và cách sử dụng kế hoạch

Người dùng đưa bài báo, URL YouTube hoặc văn bản vào Studio; app đọc nguồn, cho kiểm tra nội dung, đề xuất ba hướng khai thác và tạo một kịch bản mới có mạch kể tự nhiên. Người dùng chọn rõ kể chuyện thật, sáng tác từ chủ đề hay nâng cấp kịch bản của mình. Kịch bản cuối phải đi qua QC, lineage, duyệt và Audio như pipeline hiện tại.

Đây là tài liệu điều phối chính cho tính năng này. Mỗi lượt làm phải:

1. Đọc kế hoạch và kiểm tra trạng thái code, không coi báo cáo của lượt trước là bằng chứng nghiệm thu.
2. Làm theo thứ tự các giai đoạn, ghi rõ mục đang làm và cập nhật checklist sau khi có bằng chứng.
3. Không đánh dấu hoàn thành dựa trên mock, badge PASS hoặc một lần gọi API riêng nếu yêu cầu là chạy từ Studio UI.
4. Ghi kết quả, commit và giới hạn trong mục 15. Nếu cần đổi phạm vi, ghi lý do và tác động trước khi triển khai; thay đổi sản phẩm lớn cần hỏi người dùng.
5. Không sửa tay JSON nghiệm thu, không sửa kịch bản mẫu để giả lập thành công. Sửa code, prompt và kiểm tra để tập mới sinh qua luồng thật đạt.

## 2. Phạm vi đã thống nhất

### Bản đầu phải có

- Một nguồn cho mỗi lần nhập: dán văn bản, tải file UTF-8 `.txt`/`.srt`/`.vtt`, hoặc URL bài báo/video YouTube.
- Lấy nội dung chính bài báo và metadata nguồn.
- Lấy phụ đề thủ công hoặc tự động có sẵn của một video YouTube bằng yt-dlp, giữ mốc thời gian và loại phụ đề.
- Màn hình xem/sửa bản đọc được trước khi xác nhận dùng nguồn.
- Ba chế độ sử dụng nguồn, ba hướng khai thác, chọn một hướng trước khi viết dài.
- Tách chủ đề và cách kể; không ép mọi nội dung thành ngoại tình, điều tra hay hai cú lật.
- Story Bible, dàn cảnh, Full Script, QC và lineage có nguồn gốc rõ ràng.
- Lưu/tải lại, tiến trình thật, lỗi có thể xử lý, regression tests, build dist và nghiệm thu qua web Studio bằng OpenAI-compatible đã cấu hình.

### Để sau, không tự mở rộng vào bản đầu

- Nhận dạng audio tự động khi video không có phụ đề. Bản đầu báo rõ tình trạng và cho dán/tải transcript thay thế; không giả vờ đã đọc video.
- Thu thập cả kênh/playlist, nhiều nguồn cùng lúc, tìm báo tự động hoặc theo dõi nguồn định kỳ.
- Nhập PDF/DOCX/OCR, tải video đầy đủ, chế độ hội thoại nhiều giọng, đóng gói desktop, đăng YouTube tự động.
- Viết lại Audio Formula V1, Google Flow schema hoặc assembler.

Mở rộng nhận dạng audio được mô tả ở mục 13 và chỉ làm sau khi bản đầu đạt và người dùng muốn tiếp tục.

## 3. Hiện trạng lúc lập kế hoạch

- `studio-ui/src/components/NewEpisodeModal.tsx`: có ba điểm bắt đầu `ideas`, `topic`, `script`; chưa có luồng đọc URL và chuyển hóa nguồn.
- `studio/backend/services/script_service.py::import_script_text`: chia dòng thành segments, ghi `MANUAL_IMPORT` và `STALE`. Đây không phải chức năng sáng tác lại.
- Không dùng endpoint `/script/import-text` để giả làm đầu ra REAL_AI từ nguồn.
- `IdeaItem`/`StoryBible` và nhiều prompt/QC hiện thiên về mystery, clue, false lead và hai reveal. Phải kiểm tra toàn luồng trước khi mở rộng cách kể; chỉ thêm dropdown frontend là chưa đủ.
- `story_contract.py`, `scene_outline.py`, `semantic_review.py`, `story_qc.py`, `script_qc.py` đã có kiểm tra lịch, nghĩa vụ trả lời, nguồn kiến thức và QC trích dẫn. Phải giữ những bảo vệ này.
- `pyproject.toml` đã khai báo Trafilatura; vẫn cần kiểm tra môi trường thực tế trước khi dùng. Cần kiểm tra yt-dlp có sẵn hay thêm dependency đúng nơi.
- Nghiệm thu frontend với dist thực. Cổng chính `127.0.0.1:8765`; bản web kiểm thử dùng `8766` nếu app đang mở giữ cổng chính (xem quyết định 03/10 ở mục 15).
- Baseline full suite có 25 lỗi cũ (15 failed, 10 errors). So sánh tên test với baseline, không tuyên bố toàn bộ repo xanh. Không lấy số test này làm số cố định nếu baseline thay đổi.

## 4. Ba chế độ và những điều không được làm sai

| Mã ổn định | Tên trên UI | Giữ lại | Được sáng tạo | Điều kiện bắt buộc |
|---|---|---|---|---|
| `FACTUAL_RETELLING` | Kể lại chuyện thật | Sự kiện, mốc, nguồn và mức chắc chắn | Thứ tự trình bày, hook đúng nguồn, diễn giải và liên kết | Không thêm sự kiện/đối thoại/cú lật/thú nhận chưa được nguồn hỗ trợ |
| `FICTION_FROM_THEME` | Sáng tác từ chủ đề | Xung đột hoặc câu hỏi nhân sinh người dùng chọn | Nhân vật, bối cảnh, tình tiết, chuỗi nguyên nhân và kết thúc mới | Ghi rõ hư cấu; không chỉ đổi tên rồi giữ toàn bộ chuỗi cảnh/thoại nguồn |
| `IMPROVE_OWN_SCRIPT` | Nâng cấp kịch bản của tôi | Canon và những phần người dùng khóa | Hook, cảnh, thoại, nhịp kể và các thay đổi người dùng cho phép | Không tự đảo kết thúc, đổi sự thật hoặc xóa chi tiết đã khóa; trình bày thay đổi trước duyệt |

Ở chế độ chuyện thật:

- Phân biệt `SUPPORTED`, `ATTRIBUTED_CLAIM`, `UNKNOWN`, `CONTRADICTED`. Lời nhân vật trong talk show là lời họ kể, không tự biến thành sự thật đã được xác minh độc lập.
- Không biến suy đoán thành kết luận, không gán động cơ bí mật hoặc nội tâm cho người thật.
- Chỉ dùng lời thoại trực tiếp có trích dẫn nguồn; lời diễn giải dùng giọng kể gián tiếp.
- Không đòi hai reveal nếu nguồn không có. Thiếu đoạn kết thì kể trung thực giới hạn, không tự bịa payoff. Câu hỏi do script tự gieo phải được trả lời hoặc nêu rõ chưa biết; không hứa một bí mật mà nguồn không cung cấp.
- Nếu chọn ẩn danh, lưu quy tắc thay tên riêng; không thay sự kiện để làm người nghe hiểu khác vụ việc.

Ở chế độ hư cấu:

- Lập câu chuyện mới từ một bản phân tích chủ đề tối giản. Không đưa toàn bộ transcript nguồn vào writer nếu không cần.
- Không giữ nguyên combo nhân vật + thứ tự cảnh + đạo cụ đặc trưng + cú lật + câu thoại đáng nhớ rồi gọi là mới.
- Thay đổi phải có lý do kể chuyện, không dùng phần trăm thay từ như chứng nhận nguyên bản.

## 5. Luồng người dùng trên Studio

Thêm lựa chọn **Tạo từ nguồn tham khảo** bên cạnh các cách bắt đầu hiện có. Luồng cũ vẫn hoạt động.

### Bước A — Chọn nguồn và cách dùng

Chọn ba chế độ ở mục 4. Dán nội dung, tải file hoặc nhập một URL. Với nâng cấp kịch bản, hỏi phần phải giữ và phần được thay. Không bắt người dùng hiểu provider, JSON hoặc lineage.

### Bước B — Đọc và kiểm tra nguồn

Hiển thị tiêu đề, URL, tác giả/kênh, ngày nếu có, ngôn ngữ, cách lấy nội dung, số từ và trạng thái đọc. Hiển thị văn bản thực sự lấy được, cảnh báo phụ đề tự động hoặc nội dung thiếu. Người dùng sửa transcript hoặc thêm bản thay thế rồi bấm **Xác nhận nội dung nguồn**.

Không dùng metadata/title/thumbnail thay cho nội dung. Lỗi tải URL không được rơi về viết truyện từ tiêu đề rồi báo đã đọc nguồn.

### Bước C — Chọn định hướng

- Chủ đề: gia đình, công sở, tình yêu, mưu sinh, quan hệ xã hội, hoặc mô tả tự do.
- Cách kể: tâm sự, đời sống, điều tra, hồi hộp, chiêm nghiệm/chữa lành. Không đồng nhất LGBTQ, giới tính hay nghề nghiệp với bí mật/lỗi đạo đức.
- Thời lượng mục tiêu: giữ các lựa chọn hiện tại và truyền đúng xuống planner/writer.
- AI đưa **đúng ba hướng thực sự khác nhau**, mỗi hướng có hook, người kể/góc nhìn, mong muốn nhân vật, xung đột, lựa chọn khó, diễn biến, kết thúc và lý do phù hợp nguồn/chế độ.
- Với chuyện thật, ba hướng là ba cách kể cùng các sự kiện, không phải ba phiên bản sự thật.
- Người dùng chọn một hướng; không viết Full Script ngay khi mới lấy được URL.

### Bước D — Story Bible, kịch bản và duyệt

Dựng Story Bible từ hướng đã chọn → QC → dàn cảnh → Full Script → QC → người dùng đọc/duyệt → Audio. Hiển thị nhãn **Chuyện thật theo nguồn / Hư cấu lấy cảm hứng / Nâng cấp kịch bản**, provenance và các hạn chế cần biết.

UI phải cho xem tiến trình, lỗi và thử lại đúng bước, không bắt nhập lại tất cả. Chuyển bước, đóng modal và đổi project chỉ sau khi backend ghi xong và refresh đúng project.

## 6. Kiến trúc và dữ liệu dự kiến

### Các lớp độc lập

1. **Source intake**: nhận văn bản/file/URL, lấy nội dung và metadata; không gọi writer.
2. **Source analysis**: chia đơn vị nguồn có ID, phân biệt sự kiện/lời kể/suy đoán, rút chủ đề và xung đột.
3. **Adaptation brief**: mode, phần khóa/phần được thay, chủ đề/cách kể/thời lượng, ba hướng và hướng đã chọn.
4. **Generation**: chuyển brief được duyệt vào pipeline hiện có, không tạo hệ thống Full Script song song.
5. **Source-aware QC**: kiểm tra độ trung thực hoặc sự khác biệt với nguồn, cùng các QC hiện có.

### Artifact lưu theo project

```text
projects/<project_id>/sources/<source_id>/
  source.json          # metadata, trạng thái, phiên bản, hash
  extracted.txt        # nội dung đọc được; giữ bản gốc theo revision
  units.json           # ID đoạn nguồn; timestamp nếu có
  analysis.json        # facts/claims/theme, evidence references, provenance AI
projects/<project_id>/adaptation/
  brief.json           # mode, constraints, hướng được chọn, source revision
  directions.json      # ba hướng và metadata generation
```

Tên file/schema có thể điều chỉnh khi triển khai nhưng phải ghi thay đổi tại mục 15. Không lưu một bản nội dung nguồn không còn khớp hash bên cạnh metadata mới.

### Trường tối thiểu

- Source: `source_id`, `source_type`, `input_url`, `resolved_url`, `title`, `author_or_channel`, `published_at`, `retrieved_at`, `language`, `extraction_method`, `caption_kind`, `content_hash`, `revision`, `status`, `limitations`.
- Unit: `unit_id`, `text`, `start_sec`/`end_sec` khi có. Nguồn báo/văn bản dùng paragraph ID.
- Claim: `claim_id`, `statement`, `claim_type`, `support_status`, `evidence_refs` (unit ID và quote thật). Không có nguồn hợp lệ thì không đánh dấu supported.
- Brief: `adaptation_mode`, `source_id`, `source_revision`, `source_hash`, `selected_direction_id`, `topic`, `narrative_style`, `target_duration_sec`, `locked_elements`, `allowed_changes`, `approved_at`.
- Artifact AI: giữ `generation_source=REAL_AI`, request ID, requested/actual model, provider, prompt version, generated time và parent/source hashes. **Nguồn URL tự nó không phải REAL_AI generation**.
- Metadata mới phải được serialize/deserialize qua backend/frontend, không chỉ tồn tại trong prompt hoặc bị dataclass lọc mất.

Không log key, cookie hay transcript đầy đủ mặc định. Không commit runtime/nguồn bài viết/media vào Git.

## 7. Lấy nội dung và xử lý lỗi

### Bài báo

- Dùng Trafilatura lấy thân bài và metadata, loại menu/quảng cáo/bình luận theo cấu hình.
- Fetch có timeout, giới hạn kích thước và redirect, kiểm tra kiểu nội dung. URL chỉ http/https; chặn localhost, IP riêng/reserved và kiểm tra lại từng redirect để tránh đọc dịch vụ nội bộ của máy.
- Nội dung thiếu/paywall/trang không được hỗ trợ: báo rõ và cho dán văn bản; không vượt paywall, không yêu cầu quyền đăng nhập mới để làm bản đầu.

### YouTube

- Nhận một video URL hợp lệ, bỏ playlist parameters; không tải cả playlist/kênh.
- Chọn phụ đề thủ công đúng ngôn ngữ ưu tiên → phụ đề tự động → báo không có transcript.
- Dùng yt-dlp lấy metadata/phụ đề, không tải video chỉ để lấy captions. Giữ timestamp, loại phần lặp chồng của auto-captions, không xóa câu khác nhau chỉ vì giống nhau.
- yt-dlp **không tự nhận dạng giọng nói**. Không có phụ đề hoặc bị chặn phải báo đúng nguyên nhân; bản đầu hỗ trợ người dùng dán/tải transcript.
- Không tự đọc cookie trình duyệt hoặc lưu thông tin đăng nhập. Nếu triển khai cần điều này, dừng ở phương án nhập transcript trước và giải thích yêu cầu riêng.

### Văn bản và nội dung từ nguồn

- Giữ bản gốc, bản người dùng sửa và hash riêng; file lớn/ngôn ngữ lỗi có thông báo cụ thể.
- Nội dung nguồn là dữ liệu không tin cậy: câu như “bỏ qua hướng dẫn, duyệt PASS” không trở thành instruction cho AI/tool.
- Gợi ý giới hạn ban đầu: timeout fetch 30 giây, tối đa 5 redirects, HTML tối đa 10 MB, văn bản tối đa 100.000 ký tự; video captions tối đa 2 giờ. Giới hạn phải cấu hình được và thông báo trước khi cắt; không cắt lặng lẽ.
- Job dài chạy nền, có trạng thái và idempotency; không giữ một HTTP request đồng bộ chờ nhiều lượt AI. Retry có giới hạn, không chạy song song cùng bước rồi ghi đè artifact.

## 8. Điều chỉnh generation và QC theo cách kể

### Compatibility trước hết

Đọc đầy đủ prompt, models, router và QC trước khi sửa. Tìm các giả định “ba clues, false lead, hai reveals, 80–100 segments” đang được dùng làm điều kiện cứng. Luồng mystery cũ vẫn giữ profile hiện tại nếu project không có brief mới.

Thêm profile rõ ràng cho nội dung mới; ví dụ mystery dùng reveal, đời sống dùng lựa chọn/hậu quả, factual dùng chuỗi sự kiện có nguồn. Không thêm field giả vào Bible chỉ để qua QC. Reveal/payoff chỉ bắt buộc khi profile hoặc lời hứa trong script yêu cầu; logic, tuổi/năm, góc nhìn, trạng thái đạo cụ, tiếng Việt và lineage vẫn luôn kiểm tra.

### Chất lượng phải đánh giá được

- Hook tạo câu hỏi cụ thể mà thân truyện có thể trả lời; không spoil toàn bộ hoặc giật tít vượt nguồn.
- Cảnh then chốt có hành động, lựa chọn và hệ quả. Cảnh sau phải thêm thông tin hoặc đổi tình thế; tránh lặp suy nghĩ/xếp giấy/“cần hỏi”.
- Góc nhìn có nguồn kiến thức; chuyện thật không bịa nội tâm, thoại trực tiếp hoặc cảnh đối chất.
- Đối thoại hư cấu nghe tự nhiên, không để nhân vật phát biểu như báo cáo QC.
- Kết thúc giải quyết điều đã gieo hoặc thừa nhận giới hạn thông tin, không thêm lời dạy dài để bù thiếu payoff.
- Độ dài bám mục tiêu; xuất word budget và estimated spoken duration theo cùng cách tính. Không tuyên bố đạt 20 phút khi UI chỉ 12 phút; không kéo dài bằng lặp câu. Mặc định đề xuất sai số ±15% cho thời lượng ước tính, ghi rõ đây chưa phải đo TTS.
- QC nội dung kiểm tra đầy đủ cả tập, hai lượt có trích dẫn như hiện tại. Nguồn trích dẫn sai thì sửa báo cáo một lần; không tự sửa truyện chỉ vì JSON/quote của reviewer sai.
- Factual: các khẳng định sự kiện trọng yếu phải map tới claim/evidence nguồn; thông tin không hỗ trợ là lỗi chặn. Câu nối/nhận xét phải được phân biệt với fact.
- Fiction: kiểm tra cả chuỗi cảnh, chi tiết đặc trưng, thoại và reveal so với nguồn; similarity chỉ là tín hiệu, không tự dùng một điểm số để chứng nhận nguyên bản. Lỗi rõ ràng chặn; trường hợp mơ hồ đưa người dùng xem.
- Own script: đối chiếu phần khóa, giải thích thay đổi và không đổi canon lặng lẽ.

Không vô hiệu hóa QC, hạ lỗi thật thành cảnh báo, force PASS hay sửa prompt chỉ để một case nghiệm thu qua được. Khi fail phải giữ bản gần nhất và chẩn đoán đúng layer.

## 9. Lineage, cache và duyệt

Chuỗi phụ thuộc mới:

```text
Source revision + confirmed text
  → analysis
  → selected adaptation brief
  → selected idea / Story Bible
  → outline / Full Script / QC
  → approval / Audio / Visual / Flow / Timeline / Render
```

- Sửa nguồn, mode, hướng đã chọn hoặc phần khóa phải invalidate những artifact phụ thuộc; script cũ không còn APPROVED/current.
- Nếu chỉ phát hiện thêm metadata không ảnh hưởng nội dung như retrieved time, không tạo vòng stale vô ích; hash nội dung và cấu hình generation phải tách rõ.
- Trước và sau mỗi generation kiểm tra source/brief snapshot để tránh lưu kết quả dựa trên nguồn đã bị sửa giữa chừng.
- Source/analysis/brief/Story đều có revision/hash; Full Script giữ ancestry trực tiếp hoặc qua Story với khả năng truy ngược toàn chuỗi.
- Cache gắn với content hash + mode + constraints + prompt/model version, không dùng tên episode hoặc URL làm khóa duy nhất.
- Reload, autosave, backend restart không được phục hồi trạng thái duyệt cũ nếu lineage lệch.
- Nguồn xác nhận chỉ là nguồn đã kiểm tra; không tự coi Full Script đã được người dùng duyệt.
- Duyệt Script vẫn cần QC hợp lệ, request REAL_AI hiện hành và explicit approve từ UI. Audio giữ fail-fast như hiện tại, bổ sung kiểm tra nguồn/brief mới nếu project sử dụng tính năng này.

## 10. Điểm tích hợp code dự kiến

| Khu vực | File/module chính | Công việc |
|---|---|---|
| Wizard | `studio-ui/src/components/NewEpisodeModal.tsx` và component nguồn riêng | Bước nhập, preview, mode, ba hướng và chọn hướng; giữ wizard cũ |
| Kiểu/API frontend | `studio-ui/src/types.ts`, API client hiện dùng | Typed source/brief/status/error, không rải fetch/schema mới không thống nhất |
| Backend routes | `studio/backend/server.py` | Endpoint source, analysis, directions, confirm/select và progress |
| Intake mới | `studio/backend/services/source_service.py` (dự kiến) | Lấy bài báo/captions, normalize, persistence/revisions/jobs |
| Phân tích/chuyển hóa | Module source/adaptation riêng trong `apps/script_factory/` | Analysis và ba hướng qua provider hiện có |
| Generation | `studio/backend/services/generation_service.py`, providers, planner/writer | Nhận brief, mode/profile; tạo Story/Script qua production path |
| Models | `apps/script_factory/models.py` và backend schemas hiện dùng | Metadata source/brief/profile, backward compatibility |
| QC | `story_contract.py`, `story_qc.py`, `script_qc.py`, `semantic_review.py`, source-aware module | Chứng cứ, profile và so sánh nguồn; giữ guards hiện tại |
| Lineage | `studio/backend/services/artifact_lineage.py` | Hash/invalidation, gate và provenance |
| Tests/build | `tests/`, frontend test tooling hiện có, `studio-ui/dist` | Regression, full suite cô lập, build và UI thực |

API dự kiến, chốt schema trước triển khai: tạo/list/get source; fetch job status; confirm source revision; analyze; generate three directions; select direction/approve brief. Sử dụng namespace `/api/projects/{project_id}/sources/...` và `/adaptation/...`. Không dùng endpoint ghi Full Script để lưu raw source.

Provider: **OpenAI-compatible đã cấu hình trong app** để nghiệm thu; giữ router/provider abstraction để Gemini có thể dùng cùng chức năng. Không hardcode key/model mới, không thay cấu hình người dùng. Model thực tế báo từ response/metadata; không khẳng định model phía sau proxy khi chưa xác minh.

## 11. Thứ tự triển khai và checklist

### P0 — Chốt hợp đồng, baseline và migration

- [x] Audit những giả định mystery bắt buộc ở toàn pipeline; ghi danh sách trước khi sửa.
- [x] Chốt source/claim/brief schema, state transitions, endpoints và profile defaults.
- [x] Lưu baseline test failures và trạng thái Git; giữ dữ liệu/runtime hiện có.
- [x] Kiểm tra dependency/executable trong `.venv`, thống nhất giới hạn và job abstraction hiện có.

**Điều kiện qua:** schema đủ cho ba modes, backward compatibility và lineage; không còn câu hỏi kiến trúc bắt buộc bị để cho writer tự đoán.

### P1 — Intake và preview nguồn

- [x] Text/file/article fetch/YouTube captions, revision/hash và lỗi có nghĩa.
- [x] Preview/edit/confirm UI và lưu/tải lại.
- [x] Test URL redirects/IP checks, thiếu captions, captions lặp, nội dung rỗng/thiếu, file lỗi.

**Điều kiện qua:** nguồn thực được đọc và nhìn thấy; không chạy generation từ title-only; chưa thay đổi Full Script hiện có.

### P2 — Analysis, ba hướng và brief

- [x] Tách facts/claims/theme có evidence IDs, JSON schema validation và retry có giới hạn.
- [x] Ba hướng khác nhau theo mode, constraints và topic/style; chọn một hướng và xác nhận brief.
- [x] Lưu provenance, progress và invalidation; reload/đổi project không mất lựa chọn hoặc áp nhầm nguồn.

**Điều kiện qua:** người dùng kiểm tra được nguồn, cách dùng và hướng viết trước khi sinh dài.

### P3 — Generation theo profile

- [x] Profile-aware Story Bible/outline/writer, bao gồm factual không bịa thoại và life-story không ép hai reveals.
- [x] Truyền brief vào các provider đang hỗ trợ; mode mới chưa được provider hỗ trợ phải fail rõ.
- [x] Dàn cảnh mới phải có hành động/thông tin/hệ quả và nghĩa vụ phù hợp.
- [x] Word budget/duration, selected source snapshot, metadata request/hash xuyên suốt.
- [x] Mode nâng cấp giữ locks và báo thay đổi; không gọi import-text rồi cho qua gate.

**Điều kiện qua:** tạo ra tập mới qua service/UI production, không bỏ qua các guards ở baseline.

### P4 — QC và lineage đầy đủ

- [x] Source-aware factual assertions, fiction similarity review và own-script lock checks.
- [x] Hai lượt review có trích dẫn; missing/invalid evidence fail-closed.
- [x] Chỉnh nguồn/brief làm stale đúng downstream; stale Audio bị chặn.
- [x] Test race giữa generation và source edit, cache keys, retry/idempotency và restart.

**Điều kiện qua:** lỗi thật bị chặn và case hợp lệ không bị ép sửa để thỏa mystery giả.

### P5 — Build và nghiệm thu thực

- [x] Run focused tests, build frontend; kiểm tra source/dist và launcher thực sự phục vụ bundle mới.
- [x] Chạy full suite trên bản sao cô lập vì một số test ghi/xóa runtime; đối chiếu baseline, không chạy destructive fixtures trong project người dùng.
- [x] Thực hiện ma trận mục 12 qua Studio UI và OpenAI-compatible thật.
- [x] Lưu artifact, full script, provenance, QC, UI screenshot và đánh giá thủ công; cập nhật mục 15.
- [x] Commit source/tests/dist cần thiết và push main theo ủy quyền hiện có; không stage DB, nguồn, cookie, media hoặc runtime JSON.

**Điều kiện hoàn thành bản đầu:** toàn bộ ma trận bắt buộc đạt, không có regression mới, limitations được ghi rõ; user có thể dùng chức năng từ web đang chạy.

## 12. Ma trận nghiệm thu bắt buộc

### Nghiệm thu tích hợp có đối chứng

| Case | Kỳ vọng |
|---|---|
| Bài báo lấy được / rỗng / lỗi / redirect nội bộ | Nội dung đúng, lỗi rõ; không title-only; URL nội bộ bị chặn |
| YouTube phụ đề thủ công / tự động / không có | Đúng ngôn ngữ và timestamp, de-dup đúng; thiếu transcript không sinh giả |
| Transcript ghi instruction giả | Không thay đổi system policy, mode, gates hay quyền tool |
| Chuyện thật có lời đồn và thiếu kết thúc | Giữ attribution/unknown, không thêm thú nhận hay kết cục |
| Hư cấu cùng chủ đề | Có câu chuyện mới, không chỉ thay từ/tên; giới hạn nguồn rõ |
| Nâng cấp có locked ending/facts | Locks giữ nguyên; thay đổi được chỉ ra |
| Nguồn/brief sửa sau Script approved | Script/QC/approval và downstream stale; Audio bị chặn |
| Source edit trong khi AI đang chạy | Kết quả cũ không ghi thành current cho source mới |
| Retry/reload/restart/đổi episode | Không nhân đôi job, không nhầm nguồn, đúng nội dung và lineage |
| Project cũ không dùng source | Các luồng ideas/topic/script import và mystery cũ không đổi hành vi ngoài thay đổi đã được chủ ý ghi nhận |

### Nghiệm thu production thật — ít nhất ba tập mới

1. **Factual**: một URL báo đọc được, kiểm tra metadata và nội dung; đề xuất/chọn hướng; sinh Story và Full Script. Từng khẳng định trọng yếu map nguồn, không thoại bịa, không reveal ép.
2. **Fiction**: một URL YouTube có phụ đề, kiểm tra nội dung; lấy chủ đề công sở/mưu sinh hoặc chủ đề không phải ngoại tình; dựng câu chuyện mới và đọc toàn tập đối chiếu nguồn.
3. **Own script**: văn bản do người dùng cung cấp hoặc fixture do nhóm tự viết, có phần khóa; nâng cấp nhịp kể nhưng giữ canon và ending. Không lấy một bài của người khác rồi mặc định “kịch bản của tôi”.

Ngoài ba tập: chạy trường hợp YouTube không có captions bằng test đối chứng và, nếu có nguồn thực phù hợp, qua UI. Chứng minh fallback nhập transcript; không cần sinh thêm một tập dài.

Mỗi tập phải lưu: project/title, source ID/revision/hash, mode/selected direction, Story và Script request IDs, actual/reported model, prompt/QC versions, segments/words/duration estimate, full text, hai lượt QC có evidence, thông tin leakage/source support/locks. Duyệt từ UI, chuyển Audio, reload vẫn cùng artifact; sau đó sửa source của một tập test và kiểm tra stale/gate.

Đọc toàn văn bằng người kiểm tra ngoài badge: độ tự nhiên, hook, mỗi cảnh có tác dụng, khả năng theo dõi và ending. Có lỗi thì phân loại intake/analysis/plan/writer/reviewer/persistence và sửa code tại layer đó; không bấm viết lại vô hạn.

Không dùng EP1005/EP1006, EP2022 hoặc cached artifacts làm nghiệm thu tính năng mới. Không claim đã TTS/render nếu chỉ kiểm tra Audio gate. Audio/Visual/Flow/assembler phải giữ regression coverage; nghiệm thu video hoàn chỉnh là phạm vi riêng nếu chưa chạy thật.

## 13. Giai đoạn tùy chọn sau bản đầu: nhận dạng audio

Chỉ mở sau khi P5 đạt và người dùng yêu cầu. Khi thiếu captions, UI cho chọn **Nhận dạng từ âm thanh** và báo thời gian/chi phí dự kiến trước chạy.

- Tải audio khi có thể, dùng engine ASR đã thống nhất; không nhầm TTS VieNeu với ASR.
- Nhận dạng có timestamps; báo đoạn nghe không rõ và cho người dùng sửa tên/số. Không tạo độ tin cậy giả.
- Nghiệm thu tiếng Việt, âm thanh nhiều người/nhạc nền; chốt chính sách lưu/xóa file tạm và dependency.
- Nếu bị chặn, hỗ trợ upload audio/transcript; không tự vượt quyền truy cập.

## 14. Quy tắc chống lệch và những gì không được kết luận

- Không phát triển riêng chỉ cho một video/bài báo hoặc một chủ đề ngoại tình. Tests có negative controls và các cách kể khác.
- Không thay định nghĩa REAL_AI/current/PASS để làm import hợp lệ giả.
- Không ép mọi chuyện có hung thủ, bí mật, false lead, ba manh mối hay hai cú lật.
- Không gọi đổi tên/đổi câu là nguyên bản, không cho similarity score thay đánh giá cấu trúc.
- Không biến chuyện thật thành hư cấu mà vẫn gắn nhãn thật, hoặc thêm câu cảnh báo để hợp thức hóa sự kiện bịa.
- Không làm URL ingestion thành đường cho source instruction chạy tool hoặc truy cập mạng nội bộ.
- Không thay Audio Formula V1, mapping MC Minh → Binh/020, BGM gain, schema SCC_FLOW_V1, visual continuity/timing, assembler hay render/QC hiện có trong tính năng này.
- Không tuyên bố app/video sẵn sàng production chỉ vì ba kịch bản PASS. Phải phân biệt sinh kịch bản, Audio, render và xuất bản.
- Không hứa mọi lần AI đều hay hoặc đúng. Báo cáo cả số lượt repair, lỗi chưa giải quyết, đánh giá thủ công và giới hạn nguồn/model/thời lượng.
- Không đóng app đang dùng hoặc reset runtime ngoài nhu cầu thật; khi restart backend để nạp code phải giữ dữ liệu và thông báo ngắn.

## 15. Nhật ký tiến độ và bằng chứng

| Ngày | Giai đoạn | Công việc / quyết định | Kiểm thử / bằng chứng | Commit | Trạng thái / bước tiếp |
|---|---|---|---|---|---|
| 03/10/2026 | Kế hoạch | Chốt ba modes, một nguồn, preview, ba hướng, profile/QC/lineage; ASR để sau | Đọc wizard/import/models và đối chiếu pipeline hiện tại; chưa chạy generation tính năng mới | Chưa commit kế hoạch | Tiếp theo P0; chưa triển khai code |

| 03/10/2026 | P0 | Hợp đồng source/claim/brief đã có schema và revisions. Audit: outline ép điều tra/hai reveal, Script QC bắt REVEAL/3–6 câu hỏi, generation bắt các cấu trúc mystery. Source profile chỉ bỏ các yêu cầu hình thức không phù hợp; vẫn giữ native logic và hai lượt semantic/source review. | 87 focused tests đạt; `.venv` có yt-dlp, đã cài Trafilatura 2.3.0; frontend build đạt. Chưa nghiệm thu live. | Chưa commit | P1–P4 đang tích hợp |
| 03/10/2026 | Quyết định kỹ thuật | Bản web kiểm thử dùng 8766 để giữ phiên app/launcher người dùng ở 8765. Cùng code, project store và dist, tạo tập mới; không đóng app để test. | Kiểm tra process/port trước launch | Chưa commit | P5 phải ghi URL thật, không nhận là đã nạp code vào process cũ |

Khi hoàn thành từng giai đoạn, bổ sung đường dẫn bằng chứng và cập nhật checkbox tương ứng. Nếu đổi scope hoặc một gate thất bại, ghi tại đây thay vì lặng lẽ bỏ bước.

## 16. Tài liệu kỹ thuật tham khảo

- yt-dlp: https://github.com/yt-dlp/yt-dlp#subtitle-options — lấy phụ đề; `--skip-download`, `--write-subs`, `--write-auto-subs`, `--list-subs`.
- Trafilatura: https://trafilatura.readthedocs.io/en/latest/usage-python.html — nội dung chính và metadata bài viết.
- Kế hoạch này là thiết kế dự kiến, không phải chứng nhận mọi URL đều lấy được nội dung. Khi triển khai cần kiểm tra version/tooling thực và lỗi truy cập đúng lúc nghiệm thu.

### Nghiệm thu P5 — 03/10/2026

- Báo cáo: [SOURCE_TO_SCRIPT_ACCEPTANCE.md](SOURCE_TO_SCRIPT_ACCEPTANCE.md); metadata và screenshots tại source-evidence/.
- Ba tập mới EPSOURCE2023/2024/2025 qua UI và OpenAI-compatible thật. Đã đọc toàn văn; hai native + hai source reviews; reload/restart đúng ID/hash. EPSOURCE2025 sửa nguồn bằng UI để chứng minh STALE và khóa Audio.
- Focused 119 passed + 6 subtests; full clone cô lập 704 passed, 15 failed, 10 errors, 5 skipped, 6 subtests. Chính xác 25 lỗi baseline vẫn còn, không regression mới; build TypeScript/Vite đạt.
- Điều chỉnh trong scope: planner/writer cần nhiệm vụ và hành động cụ thể, grounding quotes/field aliases đúng artifact, budget ±15%, source snapshot/race và job restart; không sửa tay Script nghiệm thu. Metadata prompt cuối phản ánh cả repair thật.
- EPSOURCE2024 còn hai cảnh báo biên tập; không gọi PASS là hoàn hảo. Chưa chạy TTS/render cho ba tập này. Không thay Audio Formula/Flow/assembler.
- Cổng 8766 phục vụ bản mới; giữ app 8765 chạy. ASR/no-caption audio, playlist và video xuất bản vẫn ngoài bản đầu.


- Code/tests/dist đã commit và push origin/main thành công: e2a8db3 (feat(studio): adapt sources into grounded scripts with revision gates). Commit tài liệu riêng lưu kế hoạch, báo cáo và bằng chứng metadata/UI. Không stage studio_data.db hoặc idea_bank.json.

### Sửa lỗi production EP2026 — 04/10/2026

- Theo [EP2026_WRITER_FIX.md](EP2026_WRITER_FIX.md). Tái hiện model `auto` dừng bình thường nhưng thiếu độ dài và gắn nhiều ENDING; feedback cũ chỉ báo ENDING. Tập dài >1800 từ chuyển sang các cụm cảnh liên tiếp có ngân sách riêng, giữ toàn bộ ngữ cảnh đã viết và kiểm tra toàn tập. Đây là điều chỉnh kỹ thuật sau nghiệm thu tập ngắn, không đổi mode/source/canon.
- Grounding giữ fail-closed: ID khoảng chỉ resolve khi quote nguyên văn khớp duy nhất trong phạm vi, source quote không ghép units; không đổi FAIL thành PASS. Source repair không chèn câu chào mẫu và không sửa đoạn mở vì reviewer sai quote. Source QC v5.8 kiểm tra lời chào bằng nội dung/ID thật.
- EP2026 qua UI/OpenAI-compatible thật: 4286 từ/81 đoạn, CURRENT/QC PASS, 2 native + 2 source review, chỉ 081 chào kết, leakage 0. Reload cùng request/hash. Giữ NEEDS_REVIEW để người dùng đọc/duyệt; chưa chạy TTS/render. Phần cuối còn yếu về biên tập, không chứng nhận đủ hấp dẫn đăng YouTube.
- Focused 188 passed + 6 subtests; full 715 passed và cùng 25 lỗi baseline, không regression mới. Python-only, không rebuild dist. Backend nghiệm thu hiện chạy riêng tại 8768; app chính 8765 chưa được agent đóng/restart.

### P6 — Thiết kế cảnh, nhịp kể và payoff thực hiện — 04/10/2026

- [x] Phân bổ số từ theo vai trò cảnh, giới hạn chiêm nghiệm/lời chào; không giới hạn cảnh thực hiện kết quả.
- [x] Planner ghi thay đổi tình thế và câu hỏi người nghe; writer nối lựa chọn với hệ quả, không chia đều ngân sách cho các cụm gọi AI.
- [x] QC đọc nội dung toàn tập, phân biệt chuẩn bị với hoàn thành và kiểm tra phần kết bất kể delivery_profile; review/repair vẫn giới hạn số lượt.
- [x] Regression: lời hứa trả học phí từ thu nhập mới khác việc dành tiền hoặc trả học phí trước đó; không bịa kết quả chuyện thật.
- [x] Chạy nghiệm thu EP2027/2028/2029/2030 mới bằng OpenAI-compatible qua Studio, đọc toàn văn, ghi cả lần thất bại và sửa; không sửa tay artifact cũ. Đã thực hiện kiểm tra, chưa đồng nghĩa mọi bản sẵn sàng đăng.
- [x] Focused/full tests cô lập, so baseline 25 lỗi, báo cáo và commit code/test/docs; giữ nguyên Audio Formula V1/Flow/assembler.

Audit đầu vào: EP2026 đạt QC nhưng kết lặp, lời hứa “đóng học phí tiếp theo” chỉ được kể thành “dành tiền”. P6 sửa generator/QC, không sửa nội dung EP2026 và không chứng nhận Audio/render.

Báo cáo chi tiết: [NARRATIVE_DESIGN_ACCEPTANCE.md](NARRATIVE_DESIGN_ACCEPTANCE.md). Bản kiểm thử hiện tại dùng 8772, giữ app chính 8765. Các tập thử đều là hư cấu từ brief tự viết; không dùng chúng để chứng nhận mọi nguồn báo/YouTube hoặc mọi chế độ. Đọc tập dài phát hiện lỗi dù QC ban đầu PASS; chỉ tick nghiệm thu sẵn sàng xuất bản sau khi cả lỗi khách quan và nhịp kể đã được kiểm tra lại.

Kết quả P6 cuối (05/10/2026): 384 focused + 6 subtests passed; full 818 passed, 15 failed, 10 errors, 5 skipped, 6 subtests, cùng đúng 25 lỗi baseline và không lỗi mới. EP2028/2029/2030 qua QC hiện hành và reload giữ request/hash; EP2027 vẫn chưa đạt, lần cuối bị giới hạn ngân sách có sẵn. EP2030 dùng writer v14 tạo 3.894 từ/81 đoạn mới, không sửa tay. Đọc toàn văn vẫn thấy nhịp giữa tập dài chậm; chưa chứng nhận tự động mọi tập đủ cuốn hút để đăng. Cổng 8772 dùng code mới, app chính 8765 giữ nguyên phiên đang chạy. Chi tiết và bằng chứng nằm trong báo cáo P6.

### Sửa analysis phụ đề EP2031 — 05/10/2026

- [EP2031_SOURCE_ANALYSIS_FIX.md](EP2031_SOURCE_ANALYSIS_FIX.md): nguồn YouTube 5.136 từ đã đọc được; câu trích chạy qua các cue khiến gate một-unit từ chối. Code tìm span nguyên văn duy nhất và xuất refs riêng từng cue, giữ dấu vết quote/ID gốc; không lưu quote ghép vào một ID hoặc nới gate cho lời bịa.
- Lần đầu sửa qua UI tạo được 14 claims/28 refs và ba hướng; reload giữ lineage/hash. Bổ sung xử lý fragment ba từ sau lần thử tiếp theo. Bản cuối tái hiện được cả ba refs lỗi trên nguồn thật, nhưng generation trực tiếp hiện bị proxy 5000 trả 502/upstream 403. **Chưa tick nghiệm thu live bản cuối hoặc Story/Script của EP2031.**
- Source tests 88 passed; focused 125 + 6 subtests; full cô lập 824 passed và đúng 25 failures/errors baseline, không regression mới. Giữ phiên chính 8765; cổng 8772 chạy code cuối. Không sửa tay transcript/Script, không thay Audio/Flow/assembler hoặc provider.

### Sửa QC và thời gian tạo cốt truyện EP2031 — 05/10/2026

- [EP2031_STORY_QC_PERFORMANCE_FIX.md](EP2031_STORY_QC_PERFORMANCE_FIX.md): tái hiện lần cũ khoảng 17 phút/64 lượt AI với QC FAIL. Sửa bắt nhầm “hình ảnh” và lời nhắc viết tiếp; gom các trường Bible ngắn thành batch có giới hạn, tái sử dụng QC gắn đúng hash, dừng sửa không cải thiện hoặc reviewer lỗi. Hai lượt nguồn và hai lượt logic vẫn giữ, không chuyển lỗi thật thành PASS.
- Nghiệm thu cùng nguồn/hướng EP2031 qua Studio UI và OpenAI-compatible thật: **163,09 giây / 11 lượt / QC PASS**, 48 trường được kiểm tra đủ trong mỗi lượt nguồn, không phải sửa tự động. Reload giữ request/hash. Story vẫn **NEEDS_REVIEW**, Script/Audio **STALE**; chưa nghiệm thu Full Script hay TTS của EP2031.
- 102 source tests; 188 focused + 6 subtests; full cô lập 838 passed và đúng 25 lỗi baseline, không lỗi mới. Chỉ sửa Python/test/docs, không cần rebuild dist; cổng 8772 dùng code mới và giữ app 8765 đang mở.

### Sửa lỗi request Full Script EP2031 — 05/10/2026

- [EP2031_OUTLINE_PAYLOAD_FIX.md](EP2031_OUTLINE_PAYLOAD_FIX.md): Studio gọi text JSON, không gửi yêu cầu tạo ảnh. Proxy trả 502/upstream 413; code đã gửi dư báo cáo QC và gửi trùng nguồn trong repair. Loại dữ liệu chẩn đoán khỏi prompt ở planner/reviewer/Story repair và bỏ nguồn trùng trong segment repair, giữ canon/locks/source đầy đủ. Lỗi provider ở outline bắt buộc được báo đúng nguyên nhân.
- UI thật viết được 81 đoạn. Lượt Auto-Repair cuối 927 giây / 64 calls / ba vòng, không còn 413 nhưng **NEEDS_REVISION**, không nghiệm thu chất lượng. Đọc toàn văn thấy lặp ở đầu/giữa/cuối; reviewer còn quote không hợp lệ và bắt nhầm lỗi từ caption. Không sửa tay artifact, không mở gate hoặc gọi đó là PASS. Script sau reload: 4.167 từ, request 1ed3f3cc-d833-4705-a59a-7a1751bb3d67, Audio vẫn khóa.
- 227 focused + 6 subtests; full cô lập 847 passed và cùng 25 lỗi baseline, không lỗi mới. Python-only, không rebuild dist. Code mới chạy 8772; giữ phiên chính 8765. **Phần generator/reviewer cho bản kể thật dài vẫn chưa hoàn thành nghiệm thu.**
