# EP2031: trích dẫn phụ đề bị chia đoạn — 05/10/2026

Baseline: `e8c676dbaf48511ba9c4041003da0dcb965df19f`.

## Nguyên nhân đã xác minh

Transcript YouTube đã lấy được bằng yt-dlp-vtt: 5.136 từ, 301 cue, nguồn đã xác nhận revision 1. Lỗi xảy ra ở `analyze_source`, trước bước tạo ba hướng; không phải lỗi tải transcript hoặc cache kịch bản.

Hai câu AI trích nằm qua U0007/U0008 và U0010/U0011. Validator chỉ tìm trong unit AI gửi, nên từ chối dù câu có thật trong nguồn liên tiếp. Hàm sửa ID cho quote nguyên văn đã tồn tại nhưng chưa được gọi tại bước analysis và chưa hỗ trợ câu qua ranh giới cue. Feedback cũ chỉ lặp ref sai, không đưa đoạn gốc gần đó cho AI sửa.

Lần thử tiếp theo còn phát hiện quote ba từ ở U0017: có thật nhưng bị yêu cầu tối thiểu bốn từ chặn. Bản sửa cuối xử lý cả hai tình huống tại code, không sửa transcript hoặc kịch bản.

## Thay đổi

- `apps/script_factory/adaptation.py`: gọi canonicalizer trước validation analysis; sửa ID khi quote nguyên văn khớp duy nhất; tìm span tối thiểu qua tối đa ba unit liền nhau rồi xuất refs riêng với nguyên văn từng unit. Lưu `original_quote`, `reported_unit_id`, `source_span_unit_ids` để đối chiếu.
- Quote ba từ chỉ được mở rộng sang nguyên văn cue khi anchor đủ 12 ký tự, khớp duy nhất và ID AI đã gửi đúng. Quote hai từ, câu bịa, vị trí nhập nhằng hoặc các đoạn không liền nhau vẫn bị chặn. Validator công khai vẫn yêu cầu bốn từ; không tự sửa claim, verdict hoặc nguồn.
- Prompt yêu cầu quote 4–12 từ riêng từng cue. Retry có ref sai và các unit gốc gần đó, vẫn giới hạn một lần thử lại. Analysis mới ghi `source-analysis-v2-caption-spans`.
- `tests/test_source_adaptation.py`: thêm sáu cases về sentence span, ID sai, fragment ngắn và negative controls. Không thay Audio Formula V1, Flow, assembler hoặc dist; thay đổi Python nên không rebuild frontend.

## Kiểm thử thật và giới hạn nghiệm thu

Đã bấm **Đề xuất ba hướng khai thác** qua Studio `http://127.0.0.1:8772/`, trên chính nguồn EP2031, mode FACTUAL_RETELLING, topic “Góc khuất nghề sale bất động sản”, 25 phút, OpenAI-compatible được cấu hình trong app.

Lần sửa đầu hoàn tất trong 39 giây: 14 claims ATTRIBUTED_CLAIM, 28 refs, tất cả qua validator nguyên văn, ba hướng hiện trên UI và còn sau reload. Analysis request `321a2132-6b1c-471d-ac03-39f80816b217`; directions request `ede882ef-dd61-467c-9697-6c758e0e7834`, parent đúng analysis. Model báo `proxy auto — chưa xác định`; không gán tên model phía sau proxy. Hash nguồn vẫn `c8b49e6f0ed6990475c8168b67e1dd32f03f7acf7eab0d93a374938eaf1c2fa2`.

Sau đó phát hiện fragment ba từ và bổ sung xử lý cuối. Tái hiện cả ba refs quan sát được bằng code cuối trên units thật đều qua validator. Tuy nhiên hai lần thử UI với code cuối đều dừng trước validation vì dịch vụ AI trả:

```text
OpenAI-Compatible (auto) HTTP 502
/backend-anon/conversation failed: status=403
type=server_error, code=upstream_error
```

Vì thế **chưa nghiệm thu thành công một generation trực tiếp trên bản code cuối**, dù lỗi trích dẫn đã có regression và đối chiếu nguồn thật. Không nhận kết quả cũ là generation mới; không đổi provider, tự nâng budget, sửa trạng thái job hay giả PASS. Các directions hợp lệ từ lần thành công vẫn được giữ. Chưa chọn hướng, chưa tạo Story/Full Script/Audio trong lượt audit này.

## Kiểm thử tự động

- Source adaptation: **88 passed**.
- Focused source/story/lineage ở checkout riêng: **125 passed + 6 subtests**.
- Full suite checkout riêng: **824 passed, 15 failed, 10 errors, 5 skipped, 6 subtests**. Tập hợp 25 failures/errors giống baseline e8c676d, không có lỗi mới. Không chạy full suite trong project store production.
- Kiểm tra diff không có lỗi whitespace. Frontend không đổi.
- Bằng chứng: [EP2031-caption-span.json](narrative-evidence/EP2031-caption-span.json), [caption-span-tests.json](narrative-evidence/caption-span-tests.json), [UI và lỗi proxy](narrative-evidence/EP2031-provider-block.png).

## Tiếp tục kiểm tra

1. Dùng bản web mới ở cổng 8772; phiên app chính 8765 được giữ nguyên, chưa hot reload code Python vào launcher cũ.
2. Kiểm tra dịch vụ OpenAI-compatible cổng 5000, vì upstream đang từ chối 403; chưa xác định đây là lỗi session, quyền hay chặn phía dịch vụ. Không khẳng định chỉ đăng nhập lại sẽ giải quyết.
3. Khi dịch vụ hồi phục, mở EP2031 → Nguồn tham khảo → nguồn đã xác nhận → Đề xuất ba hướng. Kiểm tra request mới, prompt version v2, refs và parent/hash, rồi reload.
4. Chọn hướng người dùng muốn mới tiếp tục Story/Script; chất lượng kịch bản cần QC và đọc toàn văn riêng. Sửa analysis không chứng nhận mọi kịch bản tự động hấp dẫn để xuất bản.
