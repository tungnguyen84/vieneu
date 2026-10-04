# EP2026: sửa luồng viết dài từ nguồn tham khảo

Ngày kiểm tra: 04/10/2026. Baseline code: `ed603f1f9d39c24b32013ef1aa59bf3267a6b85a`.
Theo [SOURCE_TO_SCRIPT_PLAN.md](SOURCE_TO_SCRIPT_PLAN.md). Không sửa tay nội dung Script, nguồn hoặc Story Bible để nghiệm thu.

## Nguyên nhân đã tái hiện

- UI gọi đúng backend/AI. Ba jobs EP2026 thất bại ở validator của `write_adapted_script`, không phải lỗi nút, cache trình duyệt hay thiếu yt-dlp.
- OpenAI-compatible `auto` trả bình thường (`finish_reason=stop`) nhưng chỉ 1263/1756 từ cho mục tiêu 4050 từ. Model gắn cả đoạn chiêm nghiệm và lời chào là ENDING. Kiểm tra ENDING chạy trước rồi ném lỗi, che mất thiếu độ dài trong feedback retry.
- Chỉ sửa nhãn không giải quyết thiếu nội dung: lượt tái hiện tiếp theo vẫn trả 1404/845 từ. Vì vậy tập dài cần giới hạn công việc theo các cụm cảnh liên tiếp đã được planner kiểm tra.
- Reviewer đôi khi trả ID dạng khoảng (`062–064`) hoặc ID nguồn sai. Chỉ sửa ID khi quote nguyên văn khớp duy nhất trong phạm vi cho phép; quote ghép/diễn giải/mơ hồ tiếp tục bị từ chối.
- Transcript người dùng dán có timestamps và câu ngắt giữa source units. Review cần quote ngắn nằm trong một unit, nhiều units cần nhiều refs; không được nối lại rồi gọi đó là quote nguyên văn.
- Bộ sửa cũ nhận câu chào mẫu “quý vị đã lắng nghe”, không nhận lời kết “các bạn đã theo dõi”. Nó chèn thêm câu chào mẫu sau lời kết đã có, gây lặp lời chào. Kiểm tra source hiện dùng cùng nhận dạng nội dung với writer và giữ đúng ID đoạn lỗi.
- Lỗi format/transport của reviewer từng bị đưa vào sửa văn bản đoạn 001. Source repair nay chỉ chạy lại QC cho lỗi này, không sửa phần mở để chữa lỗi trích dẫn.

## Thay đổi code

| File | Thay đổi |
|---|---|
| `apps/script_factory/adaptation.py` | Chuẩn hóa nhãn không đổi text; tổng hợp lỗi ENDING/độ dài; tập >1800 từ viết các cụm cảnh với ngân sách riêng, toàn bộ nội dung trước làm ngữ cảnh; kiểm tra kết toàn tập; grounding source mode; prompt quote theo unit; kiểm tra lời chào sau repair. |
| `apps/script_factory/semantic_review.py` | ID khoảng source chỉ resolve bằng một quote nguyên văn duy nhất trong khoảng hợp lệ; giữ reported ID; feedback cho finding bị từ chối. Native lookup không đổi. |
| `apps/script_factory/script_qc.py` | Source QC `script-qc-v5.8-source-closing`; kiểm tra lời chào bằng nội dung và ID thật; source targeted repair chỉ chuẩn hóa nhãn, không chèn/xóa lời kể theo mẫu broadcast cũ. |
| `apps/script_factory/segment_rewriter.py` | Source repair sửa đúng đoạn chào lặp; bỏ sửa văn bản do lỗi reviewer; chống thêm lời chào sớm theo regex source. |
| `tests/test_source_adaptation.py` | Đối chứng nhãn ENDING, thiếu nội dung, chào sớm, batch thất bại, continuity/lineage/tokens, quote-ID sai và phạm vi, giữ lời kết tự nhiên, thiếu kết không chèn template, đúng đoạn repair và reviewer error không sửa prose. |

Không đổi frontend/dist, Audio Formula V1, voice 020, BGM, Visual/Flow hay assembler.

## Nghiệm thu thật

EP2026, Script title “Khoản tiền cuối tháng”, FICTION_FROM_THEME, nguồn v1, mục tiêu 1500s/4050 từ.
Story request: `acbe8792-2f78-4b4b-b31c-e11542307dd7`.
Provider: OpenAI-compatible cấu hình thật trong app, requested model `auto`; proxy không báo được model thật nên metadata ghi “proxy auto — chưa xác định”.

Lượt UI viết mới `9ab8fddfb517407c80f2efe3c128adf1`: 5 cụm cảnh, bản ban đầu 4147 từ/80 đoạn, một ENDING cuối. Native QC bắt lặp diễn biến; các lượt sửa/QC chạy thật, giữ fail-closed khi chứng cứ review không hợp lệ. Không nhận bản chỉ hết lỗi JSON là kịch bản đạt.

Lượt UI cuối trên backend đã nạp code ở **http://127.0.0.1:8768/** hoàn thành trong 141s: review bắt DUPLICATE_SIGNOFF tại 080, AI sửa đúng 1/1 đoạn, rồi chạy lại toàn bộ QC. Kết quả **4286 từ / 81 đoạn / 1587.41s ước tính**, trong ±15% mục tiêu 1500s. Một lời chào và một ENDING tại 081; leakage 0; native review RUN 2 passes và source review RUN 2 passes, không lỗi chặn. Script CURRENT, QC PASS, có thể duyệt. Request cuối `0a546b3b-a656-4b95-9118-3f56905ba889`; hash `636c419f428cd29c2ad0d9bf0e53e51ef51604aa23a10b5131995eee9572a39c`.

Reload trang và mở lại Kịch bản: cùng request ID/hash/QC PASS, không lấy lại bản cũ. [Metadata](source-evidence/EP2026-writer-live.json), [ảnh UI sau reload](source-evidence/EP2026-writer-fix.png). Để Script NEEDS_REVIEW cho người dùng đọc và duyệt; Audio vẫn khóa vì chưa duyệt, không phải STALE. Không nghiệm thu TTS/render trong bản sửa lỗi tạo Script này.

Đã đọc toàn văn bản viết dài và các đoạn được sửa ở bản cuối. Cốt truyện đi theo brief đã chọn, có lựa chọn và hệ quả, nhưng phần cuối còn nhiều nhận xét/tóm lược kế hoạch tài chính. Vì vậy **chưa kết luận bản này có độ hấp dẫn đủ để đăng YouTube** chỉ vì QC PASS. Revision round tích lũy 7 gồm các lượt chẩn đoán qua những phiên bản code đang sửa; phiên cuối chỉ cần một lượt sửa nội dung 080. Không có cam kết mọi lần sinh AI đều đạt ngay.

## Kiểm thử

Focused (8 files): **188 passed + 6 subtests**. Full suite chạy trong clone cô lập bằng `.venv` thật để không cho fixtures thay dữ liệu production: **715 passed, 15 failed, 10 errors, 5 skipped, 6 subtests**, 293.13s. Đối chiếu chính xác tên/class/status của 25 lỗi với baseline: **không lỗi mới hoặc lỗi biến mất**. Kết quả/danh sách lưu ở [EP2026-writer-test-results.json](source-evidence/EP2026-writer-test-results.json). Các lỗi cũ gồm thiếu media pilot, FlowKit và origin remote của clone local; không tuyên bố full suite xanh.

## Kiểm tra thủ công

1. Mở bản backend đã nạp code mới, chọn EP2026 → Kịch bản; kiểm tra title/request ID/QC.
2. Tạo một tập mới từ nguồn tham khảo, chọn mục tiêu dài và một hướng đã duyệt. Tiến trình phải viết các cụm cảnh, không chào kết giữa tập.
3. Nếu AI thiếu độ dài, feedback phải có số từ thực tế và ngân sách; không công bố partial script thành current.
4. QC phải báo đúng đoạn khi có lời chào lặp hoặc lỗi nội dung. Lỗi review phải giữ khóa duyệt/Audio.
5. Reload giữ cùng artifact/request/hash. Đọc toàn văn trước duyệt; PASS không thay thế đánh giá sức hấp dẫn và không phải chứng nhận video sẵn sàng đăng.
