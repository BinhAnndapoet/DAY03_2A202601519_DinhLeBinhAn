import os

# Đường dẫn file
file_path = "docs/hybrid_flowchart.mermaid"

# Đảm bảo thư mục tồn tại
os.makedirs(os.path.dirname(file_path), exist_ok=True)

# Nội dung file Mermaid
mermaid_content = """flowchart TD
    %% Định nghĩa các node
    Start([👤 User Input])
    Router{🔀 Intent Router / Classifier}
    
    %% Đường Chatbot Baseline
    Chatbot[💬 Chatbot Baseline]
    LLM_Simple[🧠 LLM Sinh câu trả lời tự nhiên]
    
    %% Đường ReAct Agent
    Agent[🤖 ReAct Agent Loop]
    Thought[🤔 Thought: Suy luận & Lập kế hoạch]
    Action[🛠️ Action: Gọi công cụ (Tool)]
    Observation[👁️ Observation: Kết quả từ Tool]
    
    %% Output
    End([✅ Final Response])

    %% Luồng chính
    Start --> Router
    
    %% Nhánh Đơn giản
    Router -- "Câu hỏi đơn giản\n(Chào hỏi, hỏi đáp lý thuyết)" --> Chatbot
    Chatbot --> LLM_Simple
    LLM_Simple --> End
    
    %% Nhánh Phức tạp
    Router -- "Câu hỏi phức tạp\n(Cần tra cứu đơn, tồn kho, đổi trả)" --> Agent
    
    subgraph "Vòng lặp ReAct (Max Iterations = 6)"
        Agent --> Thought
        Thought --> Action
        Action --> Observation
        Observation -- "Chưa đủ dữ liệu" --> Thought
    end
    
    Observation -- "Đã đủ thông tin / Chạm giới hạn lặp" --> End
    
    %% Trang trí CSS
    classDef router fill:#f9f2f4,stroke:#d39e00,stroke-width:2px,color:#333
    classDef chatbot fill:#e1f5fe,stroke:#0288d1,stroke-width:2px
    classDef agent fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px
    classDef output fill:#e8f5e9,stroke:#388e3c,stroke-width:2px
    
    class Router router
    class Chatbot,LLM_Simple chatbot
    class Agent,Thought,Action,Observation agent
    class End output
"""

# Ghi ra file
with open(file_path, "w", encoding="utf-8") as f:
    f.write(mermaid_content)

print(f"Created {file_path}")