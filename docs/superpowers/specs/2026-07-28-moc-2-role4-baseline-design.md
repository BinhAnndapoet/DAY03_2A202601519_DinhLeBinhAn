# Thiết kế Mốc 2 Role 4 — Tích hợp Chatbot Baseline

## 1. Mục tiêu

Hoàn thành nhiệm vụ Role 4 ở Mốc 2:

- Đồng bộ dữ liệu và prompt mới của Role 1–3.
- Nối `run_baseline_chatbot()` vào luồng chạy chính.
- Chạy Chatbot Baseline trên 5 test case đầu tiên.
- Bảo đảm baseline chỉ gọi LLM, không gọi tool.
- Chạy thử bằng OpenAI sau khi kiểm thử offline thành công.

## 2. Hiện trạng sau khi đồng bộ

`main` đã được fast-forward tới commit `fc12564`. Các role khác đã thay đổi:

- `config/test_cases.json` từ một list 5 phần tử thành object chứa `test_cases` với 20 case.
- Trường câu hỏi đổi từ `question` thành `user_input`.
- `src/tools.py` đã bỏ `get_weather` và `search_flights`, thay bằng tool cho đơn hàng/đổi trả.
- `src/prompts.py` đã có `CHATBOT_BASELINE_PROMPT` cho nghiệp vụ mới.

`src/app.py` vẫn dùng interface cũ nên hiện không khởi động được:

1. Import `get_weather` và `search_flights` gây `ImportError`.
2. Loader trả toàn bộ object JSON nhưng code truy cập `tests[2]`.
3. Code đọc trường `question`, trong khi test case mới dùng `user_input`.

## 3. Phạm vi thay đổi

### Trong phạm vi

- Sửa `src/app.py`.
- Thêm unit test cho phần tích hợp Role 4.
- Chạy đúng 5 test case đầu tiên.
- Chạy smoke test bằng Mock Provider.
- Chạy demo thật bằng OpenAI sau khi test offline đạt.

### Ngoài phạm vi

- Không triển khai tool của Role 2.
- Không sửa prompt của Role 3.
- Không sửa dữ liệu hoặc expected outcome của Role 1.
- Không triển khai ReAct loop của Mốc 3.
- Không sửa guardrails của Role 3.

## 4. Thiết kế thành phần

### `load_test_cases()`

- Đọc `config/test_cases.json` theo đường dẫn tuyệt đối từ project root.
- Yêu cầu top-level là object có trường `test_cases`.
- Yêu cầu `test_cases` là list.
- Yêu cầu mỗi case được chọn có `user_input` không rỗng.
- Trả về list test case đã chuẩn hóa.
- Báo `ValueError` rõ ràng nếu contract dữ liệu bị vi phạm.

### `run_baseline_chatbot(user_query, provider)`

- Nhận câu hỏi và provider đã khởi tạo.
- Gọi đúng một lần:

```python
provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
```

- Không import hoặc gọi bất kỳ tool nào.
- In câu hỏi, prompt và phản hồi để phục vụ demo.
- Trả response để unit test có thể kiểm chứng.

### `run_baseline_suite(test_cases, provider, limit=5)`

- Chọn `test_cases[:limit]`.
- Mặc định chạy 5 case đầu.
- In ID, tiêu đề và số thứ tự từng case.
- Gọi `run_baseline_chatbot()` đúng một lần cho mỗi case.
- Trả danh sách kết quả để kiểm thử và dùng cho báo cáo sau này.

### Luồng `main`

1. Khởi tạo provider từ `.env`.
2. Tải 20 test case.
3. Thông báo tổng số case và số case được chọn.
4. Chạy baseline suite trên 5 case đầu.
5. Không gọi `run_react_agent()` trong Mốc 2.

Phần ReAct cũ về thời tiết bị loại khỏi `app.py` vì vừa không tương thích với tool mới vừa nằm ngoài phạm vi Mốc 2. ReAct sẽ được triển khai lại ở Mốc 3.

## 5. Xử lý lỗi

- JSON sai cú pháp: giữ lỗi parse gốc để chỉ đúng file và dòng.
- Thiếu `test_cases`: báo contract dữ liệu không hợp lệ.
- `test_cases` không phải list: báo kiểu dữ liệu thực tế.
- Case thiếu `user_input`: báo ID hoặc vị trí case bị lỗi.
- Provider trả chuỗi lỗi: baseline vẫn ghi nhận chuỗi đó như một kết quả để không làm dừng toàn bộ suite.
- Provider ném exception ngoài adapter: không nuốt lỗi ở `app.py`; test hoặc terminal phải thấy stack trace.

## 6. Chiến lược kiểm thử

Unit test dùng `unittest` và Fake Provider, không gọi mạng:

1. Loader đọc được 20 test case hiện tại.
2. Năm case đầu đều có `user_input`.
3. `run_baseline_chatbot()` gọi provider đúng một lần với system prompt đúng.
4. Baseline trả lại response từ provider.
5. Suite chỉ chạy 5 case đầu và giữ đúng thứ tự.
6. Baseline không truy cập `AVAILABLE_TOOLS`.

Kiểm tra tích hợp:

```powershell
$env:LLM_PROVIDER = "mock"
.\.venv\Scripts\python.exe src\app.py
```

Kiểm tra thật:

```powershell
$env:LLM_PROVIDER = "openai"
.\.venv\Scripts\python.exe src\app.py
```

Lần chạy thật sử dụng 5 API call, tương ứng 5 test case đã được người dùng chọn.

## 7. Tiêu chí hoàn thành

- `python -m unittest discover -v` pass.
- `python -m compileall -q src` pass.
- Mock smoke test exit code `0`.
- Chương trình hiển thị đúng 20 case đã tải và chạy đúng 5 case đầu.
- Không còn import tool thời tiết/chuyến bay.
- Không có tool nào được gọi trong baseline.
- OpenAI demo hoàn thành 5 case hoặc trả lỗi provider rõ ràng mà không làm lộ API key.
- `.env` không được commit.

## 8. Phạm vi Git

- Nhánh: `moc-2-role4-baseline`
- Base: `main`
- File triển khai dự kiến: `src/app.py`
- File test dự kiến: `tests/test_app.py`
- Không chỉnh sửa file thuộc Role 1–3.
