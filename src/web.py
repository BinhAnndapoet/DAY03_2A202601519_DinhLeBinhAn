import sys
import os
from pathlib import Path
import streamlit as st

# Đảm bảo import được các module từ thư mục src/
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Import các hàm core từ dự án của bạn
from app import run_react_agent, run_baseline_chatbot, serialize_observation
from providers import get_llm_provider
from tools import AVAILABLE_TOOLS, TOOL_SPECS

# ==========================================
# GIAO DIỆN STREAMLIT
# ==========================================
st.set_page_config(page_title="VinUni AI Agent Demo", page_icon="🤖", layout="wide")

st.title("🤖 Chatbot Web UI")
st.markdown("Giao diện kiểm thử trực quan cho bài Lab 3. Bạn có thể chọn chế độ hoạt động ở thanh bên trái.")

# --- Cấu hình Sidebar ---
with st.sidebar:
    st.header("⚙️ Cài đặt")
    mode = st.radio("Chế độ hoạt động:", ["ReAct Agent", "Chatbot Baseline"])
    
    # Lấy LLM Provider hiện tại từ .env hoặc biến môi trường
    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    st.info(f"**Provider:** {provider.__class__.__name__}\n\n**Model:** {model_name}")

    st.markdown("---")
    if st.button("🗑️ Xóa lịch sử chat"):
        st.session_state.messages = []
        st.rerun()

# --- Quản lý Trạng thái Chat ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        # Nếu có trace log của Agent, hiển thị trong expander
        if "trace" in msg and msg["trace"]:
            with st.expander("🔍 Xem chi tiết quá trình suy luận (ReAct Trace)"):
                for step in msg["trace"]:
                    st.markdown(f"**Iteration {step.iteration}**")
                    if step.thought:
                        st.write(f"💭 **Thought:** {step.thought}")
                    if step.action:
                        args = ", ".join(str(a) for a in step.action.arguments)
                        st.write(f"🛠️ **Action:** `{step.action.tool_name}[{args}]`")
                    if step.observation is not None:
                        st.code(serialize_observation(step.observation), language="json")
                    if step.final_answer:
                        st.write(f"🏁 **Final Answer:** {step.final_answer}")
                    st.divider()

# --- Xử lý Input từ người dùng ---
if prompt := st.chat_input("Nhập câu hỏi của bạn (VD: Kiểm tra đơn ORD-2001)..."):
    # Lưu và hiển thị câu hỏi của user
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Hiển thị phản hồi của Assistant
    with st.chat_message("assistant"):
        with st.spinner("Đang xử lý..."):
            if mode == "ReAct Agent":
                # Chạy Agent với auto-confirm cho các Tool có side-effect trên web demo
                result = run_react_agent(
                    user_query=prompt,
                    provider=provider,
                    tools=AVAILABLE_TOOLS,
                    tool_specs=TOOL_SPECS,
                    confirmation_handler=lambda action: True # Tự động xác nhận (Auto-confirm)
                )
                
                final_text = result.final_answer
                st.markdown(final_text)
                
                # Hiển thị trace trực tiếp cho lần chạy này
                with st.expander("🔍 Xem chi tiết quá trình suy luận (ReAct Trace)"):
                    for step in result.trace:
                        st.markdown(f"**Iteration {step.iteration}**")
                        if step.thought:
                            st.write(f"💭 **Thought:** {step.thought}")
                        if step.action:
                            args = ", ".join(str(a) for a in step.action.arguments)
                            st.write(f"🛠️ **Action:** `{step.action.tool_name}[{args}]`")
                        if step.observation is not None:
                            st.code(serialize_observation(step.observation), language="json")
                        if step.final_answer:
                            st.write(f"🏁 **Final Answer:** {step.final_answer}")
                        st.divider()
                    st.caption(f"Lý do dừng: `{result.stop_reason}`")
                
                # Lưu vào lịch sử
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": final_text,
                    "trace": result.trace
                })
                
            else:
                # Chạy Chatbot Baseline
                response = run_baseline_chatbot(prompt, provider)
                st.markdown(response)
                # Lưu vào lịch sử
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": response
                })