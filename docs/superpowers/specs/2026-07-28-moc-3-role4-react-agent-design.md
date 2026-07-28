# Thiết kế Mốc 3 Role 4 — ReAct Agent V1 + V2

> Cập nhật sau tích hợp (2026-07-28): contract đã merge của Role 3 dùng
> arguments phân tách bằng dấu phẩy, nên parser thực tế hỗ trợ cả dạng đó và
> JSON-quoted mà không dùng `eval`. `src/app.py` giữ nguyên
> `prompts.MAX_ITERATIONS = 3` nhưng cưỡng chế runtime budget tối thiểu 6 lượt
> để TC04 có thể chạy bốn tool. Trace thực thi được xuất tại
> `docs/moc3_role4_trace.md`.

## 1. Mục tiêu

Chuẩn bị kiến trúc tích hợp cho nhiệm vụ Role 4 ở Mốc 3 của đề tài
“Trợ lý Tra cứu Đơn hàng và Xử lý Đổi trả”:

- Kéo và kiểm tra contract mới nhất của Role 1, 2 và 3.
- Giữ nguyên Chatbot Baseline đã hoàn thành ở Mốc 2.
- Lắp vòng lặp ReAct theo chuỗi quyết định công khai ngắn gọn
  `Thought -> Action -> Observation`.
- Chạy tool thật từ registry thay vì hardcode từng tên tool.
- Có recovery cho output sai định dạng, tool lạ và sai tham số.
- Có phanh chống action lặp, giới hạn vòng lặp và safe fallback.
- Bảo vệ tool làm thay đổi trạng thái bằng điều kiện nghiệp vụ và xác nhận
  từ người dùng.
- Trả trace có cấu trúc để Role 5 đưa vào `docs/trace_eval.md`.

Thiết kế bao gồm cả Agent V1 chạy được đường chuẩn và Agent V2 chịu lỗi.

## 2. Phạm vi

### Trong phạm vi Role 4

- Sửa `src/app.py`.
- Mở rộng `tests/test_app.py` và tạo thêm file test tập trung nếu cần.
- Thêm tài liệu design và implementation plan.
- Tích hợp các API công khai do Role 1–3 cung cấp.
- Chạy unit, integration và provider smoke test.

### Ngoài phạm vi Role 4

- Không cài logic dữ liệu nghiệp vụ trong `src/tools.py`.
- Không tự sửa system prompt thay Role 3 trong `src/prompts.py`.
- Không thay đổi bộ dữ liệu hoặc expected outcome của Role 1 trong
  `config/test_cases.json`.
- Không sửa báo cáo đánh giá của Role 5 trong `docs/trace_eval.md`.
- Không triển khai Hybrid Router của Mốc 4.
- Không chuyển sang native tool calling riêng của OpenAI hoặc OpenRouter.

Nếu contract của file thuộc Role khác không tương thích, Role 4 dừng ở bước
preflight và báo chính xác mismatch để đúng người phụ trách sửa.

## 3. Hiện trạng và các mismatch phải xử lý trước khi tích hợp

Mốc 2 đã được merge qua PR #6. `src/app.py` hiện nạp 20 test case và chạy
5 case đầu bằng Baseline mà không gọi tool.

Các thành phần Mốc 3 chưa sẵn sàng:

1. Bảy hàm trong `src/tools.py` vẫn chứa `pass`.
2. `AVAILABLE_TOOLS` dùng các tên:
   - `lookup_order`
   - `lookup_orders_by_email`
   - `check_return_eligibility`
   - `check_inventory`
   - `initiate_return_request`
   - `initiate_exchange_request`
   - `get_return_policy`
3. `REACT_SYSTEM_PROMPT` và allowlist trong `guardrails.py` còn dùng các tên
   cũ như `get_order_status` và `create_return_request`.
4. `config/test_cases.json` mô tả mutation dưới tên `initiate_return` và
   `initiate_exchange`, chưa trùng với registry.
5. `MAX_ITERATIONS = 3` không đủ cho TC04, vì đường chuẩn cần bốn tool call
   và thêm ít nhất một lần gọi LLM để sinh Final Answer.
6. Output guardrail hiện vừa yêu cầu prefix `Final Answer:` vừa coi chính
   prefix đó là dấu hiệu rò rỉ system prompt, nên một final answer hợp lệ
   vẫn có thể bị chặn.

Role 4 không bắt đầu implementation cho đến khi các merge gate ở phần tiếp
theo đều đạt.

## 4. Quyết định kiến trúc

### Phương án được chọn: registry-driven text ReAct loop

`src/app.py` đọc `AVAILABLE_TOOLS` và `TOOL_SPECS`, parse output text theo
contract chung, kiểm tra action rồi gọi callable tương ứng.

Lý do chọn:

- Hoạt động với adapter provider hiện tại.
- Không phụ thuộc tính năng function calling riêng của một hãng.
- Không cần chuỗi `if/elif` theo từng tool.
- Tool mới chỉ cần được đăng ký đúng contract.
- Dễ inject fake registry và scripted provider khi test.

### Phương án không chọn

- Dispatcher hardcode: nhanh lúc đầu nhưng dễ lệch tên và tham số.
- Native function calling: có cấu trúc tốt nhưng buộc sửa `providers.py`,
  tạo khác biệt giữa OpenAI/OpenRouter và vượt phạm vi Role 4.

## 5. Merge gates với Role 1–3

Trước khi viết vòng lặp, Role 4 chạy preflight contract test.

### Gate A — Tool implementation của Role 2

- Không còn hàm registry nào trả `None` do `pass`.
- Tất cả tool trả `dict` hoặc `list` có thể serialize bằng JSON.
- Lỗi nghiệp vụ được trả dưới dạng dữ liệu có trường `error`.
- Exception ngoài dự kiến vẫn có thể xảy ra, nhưng app sẽ chuyển exception
  đó thành Error Observation an toàn.
- `AVAILABLE_TOOLS` và `TOOL_SPECS` có cùng tập key.

### Gate B — Tên tool canonical

Tên canonical cho Mốc 3 là tập key trong `AVAILABLE_TOOLS`:

```text
lookup_order
lookup_orders_by_email
check_return_eligibility
check_inventory
initiate_return_request
initiate_exchange_request
get_return_policy
```

Role 1 và Role 3 phải dùng chính xác các tên này trong test expectation và
prompt. Alias không được giải quyết âm thầm trong `src/app.py`, vì alias có
thể che giấu contract sai.

### Gate C — Prompt và output guardrail của Role 3

- Prompt liệt kê đủ bảy tên tool canonical cùng đúng thứ tự tham số.
- Intermediate output chấp nhận đúng hai dòng `Thought` và `Action`.
- `Thought` chỉ là một câu tóm tắt quyết định có thể công khai, không yêu
  cầu hoặc lưu chain-of-thought nội bộ dài.
- Arguments trong Action là các JSON value hợp lệ.
- Final output dùng duy nhất prefix `Final Answer:`.
- Intermediate guardrail chấp nhận các tool trong `AVAILABLE_TOOLS`.
- Final guardrail không tự chặn prefix `Final Answer:`.
- `MAX_ITERATIONS` được đặt thành `6`, được hiểu là tối đa sáu lần gọi LLM
  cho một yêu cầu. Budget này cho phép bốn tool call, một Final Answer và
  một lượt recovery.

### Gate D — Bộ test của Role 1

- Có ít nhất một case read-only đơn giản.
- Có một case multi-step bốn tool.
- Có case order không tồn tại.
- Có case thiếu thông tin hoặc gây lặp.
- Expected tool call dùng đúng tên canonical.

## 6. Output contract giữa model và application

### Intermediate decision

Model trả đúng hai dòng:

```text
Thought: Cần tra cứu đơn hàng đã được cung cấp.
Action: lookup_order["ORD-2001"]
```

Phần bên trong dấu `[]` là danh sách JSON value. Ví dụ nhiều tham số:

```text
Thought: Sản phẩm đủ điều kiện; cần kiểm tra tồn kho biến thể đích.
Action: check_inventory["Áo thun basic", "L", "Trắng"]
```

Application không dùng `eval`. Nó ghép payload thành JSON array rồi dùng
`json.loads`.

### Final decision

```text
Final Answer: Đơn ORD-2001 đã được giao ngày 2026-07-23.
```

Không được trộn Action và Final Answer trong cùng phản hồi. Observation chỉ
do application tạo; model không được tự sinh Observation.

## 7. Các đơn vị trong `src/app.py`

### `AgentAction`

Value object gồm:

- `thought`: tóm tắt quyết định công khai.
- `tool_name`: tên tool canonical.
- `arguments`: danh sách giá trị đã parse từ JSON.
- `raw_output`: output gốc phục vụ trace và chẩn đoán.

### `AgentTraceStep`

Một bước trace gồm:

- `iteration`
- `thought`
- `action`
- `arguments`
- `observation`
- `error_code`

Trace không chứa system prompt, API key hoặc stack trace.

### `AgentRunResult`

Kết quả của một lượt Agent gồm:

- `final_answer`
- `stop_reason`
- `iterations`
- `tool_calls`
- `trace`
- `guardrail_violations`

Các stop reason hợp lệ:

```text
final_answer
input_blocked
output_blocked
max_iterations
repeated_action
confirmation_denied
contract_error
```

### `parse_agent_output(model_output)`

- Parse Final Answer trước.
- Nếu không phải Final Answer, parse đúng cặp Thought/Action.
- Dùng `json.loads` cho arguments.
- Từ chối output trộn format, thiếu Thought, thiếu Action hoặc JSON lỗi.
- Trả lỗi có mã thay vì ném lỗi parse ra ngoài loop.

### `execute_tool_action(action, state, confirmation_handler)`

- Kiểm tra tên tool bằng `AVAILABLE_TOOLS`.
- Dùng signature của callable để kiểm tra số lượng tham số.
- Kiểm tra fingerprint action đã chạy.
- Kiểm tra điều kiện của write tool.
- Xin xác nhận trước write tool.
- Gọi tool và serialize kết quả bằng
  `json.dumps(..., ensure_ascii=False, default=str)`.
- Chuyển exception ngoài dự kiến thành Observation có mã
  `TOOL_EXCEPTION`, không lộ traceback cho model.

### `run_react_agent(user_query, provider, ...)`

- Validate input trước khi gọi LLM.
- Quản lý transcript, state, iteration budget và trace.
- Gọi provider, parse decision và validate intermediate/final output.
- Append đúng một Observation cho mỗi Action hợp lệ hoặc lỗi có thể
  recovery.
- Dừng tại Final Answer hợp lệ hoặc safe fallback.

### `run_react_suite(test_cases, provider, limit=5, ...)`

- Chạy đúng năm case đầu để nhất quán với Baseline.
- Trả danh sách `AgentRunResult`.
- In header theo case để Role 5 dễ tách trace.

## 8. State và bảo vệ tool có side effect

State lưu action fingerprint theo cặp:

```text
(tool_name, canonical_json_arguments)
```

State đồng thời lập chỉ mục các Observation đã xác thực:

```text
orders[order_id].items[item_id] -> product, color và dữ liệu item
eligibility[(order_id, item_id)] -> eligible, refund_method, reason_code
inventory[(product, size, color)] -> stock
```

Chỉ dữ liệu trả về từ tool thật mới được ghi vào các chỉ mục này. Giá trị
model tự nhắc lại trong Thought hoặc Action không được xem là bằng chứng.

Nếu model lặp action:

1. Application không gọi tool lần nữa.
2. Lần lặp đầu tạo Observation `REPEATED_ACTION` để model có một cơ hội
   chuyển sang Final Answer hoặc chiến lược khác.
3. Nếu model tiếp tục đưa lại cùng action, loop dừng với
   `stop_reason = repeated_action`.

Điều kiện write tool:

- `initiate_return_request` cần một Observation eligibility thành công cho
  đúng `order_id` và `item_id`; `refund_method` trong Action phải trùng
  phương thức mà eligibility cho phép.
- `initiate_exchange_request` cần eligibility thành công cho đúng
  `order_id`/`item_id`. Application lấy tên sản phẩm và màu hiện tại từ
  Observation `lookup_order`, sau đó yêu cầu Observation inventory có
  `stock > 0` cho đúng `(product, new_size, new_color)`.
- Write tool luôn cần `confirmation_handler(action) is True`.

Handler mặc định từ chối. CLI handler hỏi `[y/N]`; test inject handler xác
định để không phụ thuộc input terminal.

## 9. Data flow

```text
User input
  -> Input Guardrail
  -> Transcript ban đầu
  -> LLM decision
      -> Parse error có thể sửa
          -> Error Observation
          -> Append transcript
          -> LLM decision tiếp theo
      -> Action
          -> Intermediate Guardrail
          -> Registry/signature/precondition/repetition checks
          -> Confirmation nếu là write tool
          -> Tool thật
          -> JSON Observation
          -> Append transcript
          -> LLM decision tiếp theo
      -> Final Answer
          -> Final Output Guardrail
          -> AgentRunResult
  -> Safe Fallback nếu hết budget hoặc vi phạm không thể phục hồi
```

Transcript gửi vào provider gồm Question, các quyết định công khai, Action
và Observation. System prompt vẫn được truyền riêng qua tham số
`system_prompt`.

## 10. Error handling và recovery

| Tình huống | Hành vi |
|---|---|
| Input bị guardrail chặn | Không gọi LLM/tool; trả fallback |
| Output trộn Action và Final Answer | Error Observation một lần |
| Arguments không phải JSON | `MALFORMED_ARGUMENTS` và ví dụ format đúng |
| Tool không tồn tại | `UNKNOWN_TOOL` và danh sách tool hợp lệ |
| Sai số tham số | `INVALID_ARGUMENTS` và required args từ spec |
| Tool trả dữ liệu có `error` | Append nguyên dữ liệu lỗi an toàn |
| Tool ném exception | `TOOL_EXCEPTION`; không lộ traceback |
| Action lặp | Không gọi tool; recovery một lần rồi fallback |
| Thiếu precondition write | `PRECONDITION_FAILED`; không gọi tool |
| Người dùng từ chối xác nhận | Dừng `confirmation_denied` |
| Final output bị chặn | Safe fallback `output_blocked` |
| Hết sáu lần gọi LLM | Safe fallback `max_iterations` |

Safe fallback phải lịch sự, không khẳng định giao dịch đã thành công và đề
nghị người dùng kiểm tra lại thông tin hoặc liên hệ nhân viên hỗ trợ.

## 11. Observability

Console trace có dạng:

```text
🧠 REACT CASE 1/5: TC01
Step 1
Thought: Cần tra cứu mã đơn.
Action: lookup_order["ORD-2001"]
Observation: {"status": "delivered", "delivery_date": "2026-07-23"}

Step 2
Final Answer: Đơn ORD-2001 đã được giao ngày 2026-07-23.
Stop reason: final_answer
```

Chỉ public decision summary được in. System prompt, API key, traceback và
chain-of-thought nội bộ không được ghi log.

## 12. Luồng `main()`

Ở Mốc 3, `main()`:

1. Khởi tạo provider.
2. Nạp 20 test case.
3. Chạy ReAct suite trên năm case đầu.
4. Dùng confirmation handler tương tác cho write tool khi terminal hỗ trợ
   tương tác; nếu không thì mặc định từ chối.
5. In trace và stop reason.

Các hàm Baseline Mốc 2 vẫn được giữ nguyên để Role 5 có thể chạy so sánh.
Hybrid routing giữa Baseline và ReAct chưa được thêm trong Mốc 3.

## 13. Chiến lược kiểm thử

### Contract preflight

- `AVAILABLE_TOOLS` và `TOOL_SPECS` có cùng key.
- Prompt chứa đủ tên canonical.
- Intermediate guardrail chấp nhận Action của từng tool.
- Final guardrail chấp nhận Final Answer hợp lệ.
- `MAX_ITERATIONS == 6`.
- Read-only tool smoke fixture không trả `None`; mutation tool được kiểm tra
  trên datastore/fixture cô lập để không tạo giao dịch thật.

### Parser

- Parse Action một tham số.
- Parse Action nhiều tham số Unicode.
- Parse Final Answer.
- Từ chối malformed JSON.
- Từ chối mixed output.

### Executor

- Gọi đúng callable với đúng thứ tự args.
- Chặn unknown tool.
- Chặn sai số args.
- Chuyển exception thành Error Observation.
- Serialize dict/list Unicode.

### Loop và recovery

Dùng scripted fake provider, không gọi API:

- Action -> Observation -> Final Answer.
- Observation xuất hiện trong prompt kế tiếp.
- Unknown tool được sửa trong budget.
- Malformed args được sửa trong budget.
- Action lặp không gọi tool lần hai.
- Hết iteration trả safe fallback.
- Input/output guardrail chặn đúng điểm.

### Side effects

- Return bị chặn nếu chưa eligibility.
- Exchange bị chặn nếu chưa eligibility.
- Exchange bị chặn khi stock bằng 0.
- Write bị chặn khi confirmation handler từ chối.
- Write được gọi đúng một lần khi đủ precondition và xác nhận.

### Regression và integration

- Toàn bộ test Baseline Mốc 2 vẫn pass.
- TC01 đại diện read-only happy path.
- TC04 đại diện đường bốn tool có side effect.
- TC17 đại diện NOT_FOUND, chống bịa.
- TC18 đại diện thiếu thông tin/chống loop.
- Mock smoke test không cần mạng.
- OpenAI smoke test chạy sau cùng, giới hạn năm case và không log secret.

## 14. Chiến lược Git trong thời gian chờ các Role khác

- Design và plan nằm trên nhánh `moc-3-role4-planning` bắt đầu từ
  `origin/main` sau PR #6.
- Không viết implementation trên nhánh planning.
- Khi Role 1–3 merge xong Mốc 3, Role 4 fetch/pull `main`, chạy contract
  preflight rồi tạo nhánh `moc-3-role4-react-agent` từ `main` mới nhất.
- Nếu gate thất bại, báo mismatch cho đúng Role; không thêm alias hoặc sửa
  file của họ để lách lỗi.
- Chỉ sau khi gate đạt mới triển khai theo implementation plan.

## 15. Tiêu chí hoàn thành

Mốc 3 Role 4 hoàn thành khi:

1. Baseline Mốc 2 không regress.
2. Agent chạy được Action -> Observation -> Final Answer.
3. Observation thực xuất hiện trong transcript của lượt LLM kế tiếp.
4. Không tool nào được gọi bằng tên ngoài registry.
5. Parse/tool error không làm crash app.
6. Action lặp và hết budget đều dừng bằng safe fallback.
7. Write tool không chạy nếu thiếu precondition hoặc xác nhận.
8. Trace đủ rõ để Role 5 đưa vào báo cáo mà không lộ secret/suy luận nội bộ.
9. Các case TC01, TC04, TC17 và TC18 đạt hành vi kỳ vọng sau khi contract
   của Role 1–3 đã được đồng bộ.
