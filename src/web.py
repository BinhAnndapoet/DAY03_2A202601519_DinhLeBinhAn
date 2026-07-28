import sys
import os
from pathlib import Path
import streamlit as st

# --- SETUP ĐƯỜNG DẪN ---
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from app import run_react_agent, run_baseline_chatbot, serialize_observation
from providers import get_llm_provider
from tools import AVAILABLE_TOOLS, TOOL_SPECS

# ==========================================
# CẤU HÌNH TRANG & CSS TÙY CHỈNH
# ==========================================
st.set_page_config(
    page_title="VinUni AI Agent", 
    page_icon="✨", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Nhúng Custom CSS để làm đẹp giao diện
st.markdown("""
<style>
    /* Ẩn menu mặc định của Streamlit cho gọn */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Làm đẹp tiêu đề chính với Gradient */
    .main-title {
        font-size: 2.5rem;
        font-weight: 800;
        background: -webkit-linear-gradient(45deg, #0072ff, #00c6ff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
        padding-bottom: 0;
    }
    .sub-title {
        color: #6c757d;
        font-size: 1.1rem;
        font-weight: 400;
        margin-top: 5px;
        margin-bottom: 30px;
    }
    
    /* Style cho box thông tin model */
    .info-box {
        background-color: #f1f8ff;
        border-left: 4px solid #0366d6;
        padding: 10px 15px;
        border-radius: 5px;
        margin-bottom: 15px;
        font-size: 0.9rem;
    }
    
    /* Làm đẹp trace log */
    .trace-step {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 10px;
    }
    .trace-thought { color: #856404; font-style: italic; }
    .trace-action { color: #004085; font-weight: 600; }
    .trace-final { color: #155724; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# HÀM HIỂN THỊ TRACE LOG ĐẸP MẮT
# ==========================================
def render_trace_ui(trace_steps, stop_reason):
    """Render quá trình suy luận của Agent với UI gọn gàng"""
    with st.expander("🔍 Nhấn để xem luồng suy luận của AI (ReAct Trace)", expanded=False):
        for step in trace_steps:
            st.markdown(f"<div class='trace-step'>", unsafe_allow_html=True)
            st.markdown(f"**Vòng lặp (Iteration) {step.iteration}**")
            
            if step.thought:
                st.markdown(f"<div class='trace-thought'>🤔 <b>Thought:</b> {step.thought}</div>", unsafe_allow_html=True)
            
            if step.action:
                args = ", ".join(f"`{a}`" for a in step.action.arguments)
                st.markdown(f"<div class='trace-action'>🛠️ <b>Action:</b> {step.action.tool_name} [{args}]</div>", unsafe_allow_html=True)
            
            if step.observation is not None:
                st.markdown("👁️ **Observation:**")
                st.code(serialize_observation(step.observation), language="json")
                
            if step.final_answer:
                st.markdown(f"<div class='trace-final'>🏁 <b>Final Answer:</b> {step.final_answer}</div>", unsafe_allow_html=True)
                
            st.markdown("</div>", unsafe_allow_html=True)
        
        st.info(f"**Lý do kết thúc:** `{stop_reason}`", icon="ℹ️")

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/c/ca/VinUni_Logo.svg/512px-VinUni_Logo.svg.png", width=150)
    st.markdown("### ⚙️ Bảng Điều Khiển")
    
    # Chọn chế độ với icon
    mode = st.radio(
        "Lựa chọn hệ thống AI:",
        ["🧠 ReAct Agent (Khuyên dùng)", "💬 Chatbot Baseline"],
        help="ReAct Agent có khả năng gọi Tools để lấy dữ liệu thực tế."
    )
    
    st.markdown("---")
    
    # Hiển thị thông tin Provider đẹp mắt
    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    st.markdown(f"""
    <div class='info-box'>
        <b>🔌 Provider:</b> {provider.__class__.__name__}<br>
        <b>🤖 Model:</b> {model_name}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    
    # Nút xóa lịch sử với type primary
    if st.button("🗑️ Làm mới cuộc trò chuyện", type="primary", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ==========================================
# MAIN INTERFACE
# ==========================================
st.markdown("<h1 class='main-title'>AI Agent: Quản lý Đổi/Trả Hàng</h1>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>Hệ thống demo so sánh giữa Chatbot thông thường và ReAct Agent có khả năng sử dụng công cụ.</div>", unsafe_allow_html=True)

# Khởi tạo session state cho lịch sử chat
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "👋 Chào bạn! Mình có thể giúp gì cho bạn với các đơn hàng và chính sách đổi trả hôm nay?"}
    ]

# Hiển thị lịch sử chat
for msg in st.session_state.messages:
    # Gán avatar cho từng role
    avatar = "🧑‍💻" if msg["role"] == "user" else "✨"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        # Nếu có log ReAct, gọi hàm render UI
        if msg.get("trace"):
            render_trace_ui(msg["trace"], msg.get("stop_reason", "completed"))

# ==========================================
# CHAT INPUT & XỬ LÝ LOGIC
# ==========================================
if prompt := st.chat_input("Nhập câu hỏi (Ví dụ: Đơn ORD-2001 đã giao chưa?)..."):
    
    # Hiển thị ngay câu hỏi của user
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(prompt)

    # Hiển thị box đang xử lý (Status)
    with st.chat_message("assistant", avatar="✨"):
        if "ReAct" in mode:
            with st.status("🤖 Agent đang suy nghĩ và tra cứu dữ liệu...", expanded=True) as status:
                st.write("Đang khởi động ReAct Loop...")
                
                # Chạy Agent (Tự động bypass Confirmation trên UI)
                result = run_react_agent(
                    user_query=prompt,
                    provider=provider,
                    tools=AVAILABLE_TOOLS,
                    tool_specs=TOOL_SPECS,
                    confirmation_handler=lambda action: True
                )
                status.update(label="✅ Đã hoàn tất xử lý!", state="complete", expanded=False)
            
            # In câu trả lời cuối cùng
            st.markdown(result.final_answer)
            # Render trace
            render_trace_ui(result.trace, result.stop_reason)
            
            # Lưu lịch sử
            st.session_state.messages.append({
                "role": "assistant", 
                "content": result.final_answer,
                "trace": result.trace,
                "stop_reason": result.stop_reason
            })
            
        else:
            with st.spinner("💬 Chatbot đang gõ..."):
                response = run_baseline_chatbot(prompt, provider)
            
            st.markdown(response)
            st.session_state.messages.append({
                "role": "assistant", 
                "content": response
            })