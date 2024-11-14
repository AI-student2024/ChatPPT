import streamlit as st
import os
import re
import asyncio
from io import BytesIO
from pptx import Presentation
from config import Config
from chatbot import ChatBot
from content_formatter import ContentFormatter
from content_assistant import ContentAssistant
from image_advisor import ImageAdvisor
from input_parser import parse_input_text
from ppt_generator import generate_presentation
from template_manager import load_template, get_layout_mapping
from layout_manager import LayoutManager
from logger import LOG
from openai_whisper import asr
from docx_parser import generate_markdown_from_docx

# 配置初始化
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "ChatPPT"

config = Config()
chatbot = ChatBot(config.chatbot_prompt)
content_formatter = ContentFormatter(config.content_formatter_prompt)
content_assistant = ContentAssistant(config.content_assistant_prompt)
image_advisor = ImageAdvisor(config.image_advisor_prompt)
ppt_template = load_template(config.ppt_template)
layout_manager = LayoutManager(get_layout_mapping(ppt_template))

# 初始化输出文件夹
os.makedirs("outputs", exist_ok=True)

# 初始化 session_state 中的变量
if "history" not in st.session_state:
    st.session_state.history = []
if "slides_content" not in st.session_state:
    st.session_state.slides_content = None
if "content_with_images" not in st.session_state:
    st.session_state.content_with_images = None
if "presentation_title" not in st.session_state:
    st.session_state.presentation_title = "Untitled_Presentation"

# 异步生成内容函数
async def generate_contents(message):
    try:
        texts = []
        if message.get("text"):
            texts.append(message["text"])

        for uploaded_file in message.get("files", []):
            LOG.debug(f"[处理文件]: {uploaded_file['name']}")
            file_ext = os.path.splitext(uploaded_file['name'])[1].lower()
            if file_ext in ('.wav', '.flac', '.mp3'):
                audio_text = await asr(uploaded_file['file'])
                texts.append(audio_text)
            elif file_ext in ('.docx', '.doc'):
                raw_content = generate_markdown_from_docx(uploaded_file['file'])
                markdown_content = content_formatter.format(raw_content)
                formatted_content = content_assistant.adjust_single_picture(markdown_content)
                texts.append(formatted_content)

        user_requirement = "需求如下:\n" + "\n".join(texts)
        LOG.info(f"用户需求: {user_requirement}")

        slides_content = await chatbot.chat_with_reflection(user_requirement)
        st.session_state.slides_content = slides_content

        # 在预设的内容展示框中显示生成的内容
        st.session_state.display_content = slides_content
        return slides_content
    except Exception as e:
        LOG.error(f"[内容生成错误]: {e}")
        st.error("生成内容时出错，请重试。")
        return None

# 配图生成
def handle_image_generate():
    try:
        slides_content = st.session_state.slides_content
        if not slides_content:
            st.error("请先生成内容。")
            return

        content_with_images, _ = image_advisor.generate_images(slides_content)
        st.session_state.content_with_images = content_with_images

        # 在预设的内容展示框中显示生成的配图内容
        st.session_state.display_content = content_with_images
    except Exception as e:
        LOG.error(f"[配图生成错误]: {e}")
        st.error("配图生成出错，请重试。")

# PowerPoint 生成并预览
def handle_generate():
    try:
        slides_content = st.session_state.content_with_images or st.session_state.slides_content
        if not slides_content:
            st.error("请先生成内容再生成PowerPoint。")
            return

        powerpoint_data, presentation_title = parse_input_text(slides_content, layout_manager)
        st.session_state.presentation_title = re.sub(r'[\\/*?:"<>|]', "", presentation_title or "Untitled_Presentation")
        output_pptx = f"outputs/{st.session_state.presentation_title}.pptx"

        generate_presentation(powerpoint_data, config.ppt_template, output_pptx)
        st.success("PowerPoint生成成功！")

        # 在预设的内容展示框中显示预览内容
        st.session_state.display_content = f"PowerPoint 预览文件已生成：{st.session_state.presentation_title}.pptx"
        
        # 提供下载功能
        with open(output_pptx, "rb") as ppt_file:
            st.download_button("下载 PowerPoint", ppt_file, file_name=f"{st.session_state.presentation_title}.pptx")
    except Exception as e:
        LOG.error(f"[PPT生成错误]: {e}")
        st.error("生成 PPT 时出错。请检查输入内容并重试。")

# 页面样式和布局
st.markdown(
    """
    <style>
    .main { background: linear-gradient(135deg, #fdfcfb, #e2d1c3); color: #333333; font-family: Arial, sans-serif; }
    .title { font-size: 32px; font-weight: bold; color: #333333; text-align: center; margin-bottom: 10px; }
    .subtitle { font-size: 18px; color: #666666; text-align: center; margin-bottom: 30px; }
    .stButton button {
        background-color: #1e88e5;
        color: white;
        font-size: 18px;
        padding: 10px 20px;
        border-radius: 5px;
        display: inline-flex;
        align-items: center;
    }
    .stButton button:hover {
        background-color: #1565c0;
    }
    .stFileUploader div {
        color: #333333;
        font-size: 16px;
    }
    /* 内容展示框样式，宽度设为100%以适应页面宽度 */
    .content-box {
        width: 100%;
        max-width: 1000px;  /* 限制内容宽度，保持美观 */
        margin: 0 auto;  /* 居中显示 */
        padding: 10px;
        border: 1px solid #e6e6e6;
        background-color: #f9f9f9;
        border-radius: 5px;
        margin-top: 20px;
        overflow-wrap: break-word;
        word-wrap: break-word;
        word-break: break-word;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# 标题和欢迎语
st.markdown("<div class='title'>ChatPPT</div>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>欢迎使用ChatPPT，请选择一个功能开始您的智能文档之旅。</div>", unsafe_allow_html=True)

# 用户输入和文件上传区域
st.text_area("请输入主题内容", key="user_input")
uploaded_files = st.file_uploader("拖拽文件到此处或点击上传（每个文件最大200MB）", accept_multiple_files=True)

# 模块化内容区域
st.markdown("<div style='text-align: center; margin-top: 20px;'>", unsafe_allow_html=True)
col1, col2, col3 = st.columns([1, 1, 1])

# 绑定按钮功能
with col1:
    if st.button("📑 生成内容"):
        with st.spinner("正在生成内容..."):
            asyncio.run(generate_contents({"text": st.session_state.user_input, "files": [{"name": f.name, "file": f} for f in uploaded_files]}))

with col2:
    if st.button("🖼️ 生成配图"):
        with st.spinner("正在生成配图..."):
            handle_image_generate()

with col3:
    if st.button("📄 生成PPT"):
        with st.spinner("正在生成PPT..."):
            handle_generate()

st.markdown("</div>", unsafe_allow_html=True)

# 在按钮下方显示内容展示框，宽度为页面宽度
if "display_content" in st.session_state and st.session_state.display_content:
    st.markdown("<div class='content-box'>", unsafe_allow_html=True)
    st.write(st.session_state.display_content)
    st.markdown("</div>", unsafe_allow_html=True)
