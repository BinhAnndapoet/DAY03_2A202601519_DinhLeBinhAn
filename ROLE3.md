# Tóm tắt: Prompt Engineering & Guardrails cho AI Customer Support Assistant
 
**Đề tài:** Trợ lý tra cứu đơn hàng và xử lý đổi/trả
**Phạm vi:** Mốc 2 (Prompt + Tool Spec) → Mốc 3 (Guardrails)
 
---
 
## 1. Kiến trúc tổng quan
 
```
User Input
    │
    ▼
[InputGuardrail]  ──block──▶ Từ chối, không gửi cho LLM
    │ allow
    ▼
[LLM: REACT_SYSTEM_PROMPT]  →  Thought: ... / Action: tool[args]
    │
    ▼
[OutputGuardrail, is_final_answer=False]  ──block──▶ Yêu cầu LLM sinh lại
    │ allow
    ▼
[Tool Registry] → gọi tool thật → Observation
    │
    ▼ (lặp lại tối đa MAX_ITERATIONS=3, do orchestrator đếm — KHÔNG để LLM tự đếm)
    │
[LLM] → Final Answer: ...
    │
    ▼
[OutputGuardrail, is_final_answer=True]  ──block──▶ Câu trả lời an toàn mặc định
    │ allow
    ▼
Trả lời người dùng
```
 
---
 
## 2. Prompts (`prompts.py`)
 
### `CHATBOT_BASELINE_PROMPT`
Dùng khi chưa có tool — chatbot trả lời thuần dựa trên kiến thức có sẵn, không tự bịa dữ liệu đơn hàng/chính sách.
 
### `REACT_SYSTEM_PROMPT`
Prompt chính cho Agent, theo mô hình **ReAct** (Reasoning + Acting):
 
| Thành phần | Nội dung |
|---|---|
| **Format bắt buộc** | Mỗi bước trung gian: `Thought: <lý do, ≤20 từ>` → `Action: tool[args]`. Không được trộn Action với Final Answer trong cùng 1 phản hồi. |
| **7 tool khai báo** | `lookup_order`, `lookup_orders_by_email`, `get_return_policy`, `check_return_eligibility`, `check_inventory`, `initiate_return_request`, `initiate_exchange_request` |
| **Quy tắc nghiệp vụ** | `initiate_return_request` / `initiate_exchange_request` chỉ được gọi sau khi `check_return_eligibility` (và `check_inventory` với đổi hàng) đã pass **trong cùng phiên**, và người dùng đã xác nhận. |
| **Xử lý lỗi tool** | Có hướng dẫn riêng cho từng loại lỗi: not found, email trả nhiều đơn, timeout, dữ liệu thiếu trường, kết quả không đủ điều kiện... — không được tự suy diễn khi thiếu dữ liệu. |
| **Giới hạn vòng lặp** | `MAX_ITERATIONS = 3` — prompt ghi rõ đây là giới hạn do **orchestrator bên ngoài enforce**, LLM không tự đếm. |
 
**Điểm thiết kế quan trọng:** tách rõ *baseline prompt* (không tool) và *ReAct prompt* (có tool) để dễ so sánh hành vi, và toàn bộ prompt bằng tiếng Việt có dấu để nhất quán với ngôn ngữ người dùng.
 
---
 
## 3. Tool Registry (`tools.py`)
 
7 hàm tool, mỗi hàm có docstring chuẩn hoá (Args/Returns/Notes) để dùng làm nguồn sinh tool schema. Phân loại theo `TOOL_SPECS`:
 
- **Read-only (5 tool):** `lookup_order`, `lookup_orders_by_email`, `check_return_eligibility`, `check_inventory`, `get_return_policy`
- **State-changing, cần xác nhận (2 tool):** `initiate_return_request`, `initiate_exchange_request`
> Mốc 2 chỉ chuẩn hoá interface (tên, tham số, kiểu trả về). Logic nghiệp vụ thật sẽ cài đặt ở Mốc 3.
 
---
 
## 4. Guardrails (`guardrails.py`)
 
Module độc lập, không phụ thuộc LLM, chặn/làm sạch cả **input** lẫn **output**.
 
### 4.1 Input Guardrail
| Rule | Hành động |
|---|---|
| Prompt injection (VD "bỏ qua hướng dẫn ở trên...") | **BLOCK** |
| Từ khoá jailbreak (sudo mode, override safety...) | **BLOCK** |
| CCCD/CMND, số thẻ ngân hàng | **BLOCK** (không tool nào cần đến) |
| Số điện thoại | **SANITIZE** (che, vì không tool nào cần SĐT) |
| **Email** | **Giữ nguyên, không che** — vì `lookup_orders_by_email` cần giá trị thật để hoạt động |
| Input rỗng / quá dài | **BLOCK** |
| Ký tự ẩn (zero-width) né filter | Tự động chuẩn hoá (NFKC) trước khi kiểm tra |
 
### 4.2 Output Guardrail
| Rule | Hành động |
|---|---|
| Sai format `Thought:`/`Action:`/`Final Answer:` | **BLOCK** |
| Gọi tool không nằm trong `ALLOWED_TOOLS` (bịa tool) | **BLOCK** |
| `Thought:` dài hơn 20 từ | **BLOCK** (nghi lộ chain-of-thought) |
| Trộn Action và Final Answer cùng lúc | **BLOCK** |
| `Thought:` lộ ra trong Final Answer | **BLOCK** |
| Rò rỉ system prompt / cấu trúc nội bộ | **BLOCK**, trả về câu trả lời an toàn mặc định |
| Observation "tiêm" chỉ dẫn không an toàn (indirect injection) | **BLOCK** |
| PII của khách khác lỡ xuất hiện trong output | **SANITIZE** (che) |
| Dấu hiệu suy đoán không dựa trên tool (hallucination) | **WARN** (không block, chỉ log để review — tránh false positive) |
 
---

## 5. Giới hạn hiện tại (cần biết trước khi lên production)
 
- **`TOXIC_KEYWORDS` đang để trống.** Danh sách từ khoá tự viết tay không đủ tin cậy — cần tích hợp moderation API thật trước khi go-live. (Chưa thêm)

- **Guardrails không enforce thứ tự nghiệp vụ** (VD phải gọi `check_return_eligibility` trước `initiate_return_request`) — đây là state-machine logic, nên nằm ở **orchestrator/tool wrapper**, không phải ở content guardrail này.
---
 
## 6. File liên quan
 
| File | Nội dung |
|---|---|
| `prompts.py` | `CHATBOT_BASELINE_PROMPT`, `REACT_SYSTEM_PROMPT`, `MAX_ITERATIONS`, `TIMEOUT_SECONDS` |
| `tools.py` | 7 hàm tool (stub) + `TOOL_SPECS` + `AVAILABLE_TOOLS` |
| `guardrails.py` | `InputGuardrail`, `OutputGuardrail`, `GuardrailConfig`, hàm tiện ích `validate_input()` / `validate_output()` |