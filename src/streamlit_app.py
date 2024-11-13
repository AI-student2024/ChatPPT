import streamlit as st
import os
import re
import asyncio
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
from openai_whisper import asr, transcribe
from docx_parser import generate_markdown_from_docx

# 环境变量设置
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_PROJECT"] = "ChatPPT"

# 初始化配置和组件
config = Config()
chatbot = ChatBot(config.chatbot_prompt)
content_formatter = ContentFormatter(config.content_formatter_prompt)
content_assistant = ContentAssistant(config.content_assistant_prompt)
image_advisor = ImageAdvisor(config.image_advisor_prompt)

ppt_template = load_template(config.ppt_template)
layout_manager = LayoutManager(get_layout_mapping(ppt_template))

os.makedirs("outputs", exist_ok=True)

if "history" not in st.session_state:
    st.session_state.history = []

async def generate_contents(message, history):
    try:
        texts = []
        text_input = message.get("text")
        if text_input:
            texts.append(text_input)

        for uploaded_file in message.get("files", []):
            LOG.debug(f"[处理文件]: {uploaded_file['name']}")
            file_ext = os.path.splitext(uploaded_file['name'])[1].lower()
            if file_ext in ('.wav', '.flac', '.mp3'):
                audio_text = await asr(uploaded_file['file'])
                texts.append(audio_text)
            elif file_ext in ('.docx', '.doc'):
                raw_content = generate_markdown_from_docx(uploaded_file['file'])
                markdown_content = content_formatter.format(raw_content)
                return content_assistant.adjust_single_picture(markdown_content)

        user_requirement = "需求如下:\n" + "\n".join(texts)
        LOG.info(f"用户需求: {user_requirement}")

        slides_content = await chatbot.chat_with_reflection(user_requirement)
        LOG.debug(f"生成的幻灯片内容: {slides_content}")

        # 立即存储 slides_content
        if slides_content:
            st.session_state.history.append({"role": "assistant", "content": slides_content})
            LOG.debug(f"History after generating content: {st.session_state.history}")
        
        return slides_content
    except Exception as e:
        LOG.error(f"[内容生成错误]: {e}")
        st.error("生成内容时出错，请重试。")
        return None

# 配图
def handle_image_generate():
    try:
        slides_content = st.session_state.history[-1]["content"]
        LOG.debug(f"幻灯片内容（配图前）: {slides_content}")
        
        content_with_images, _ = image_advisor.generate_images(slides_content)
        LOG.debug(f"配图后的内容: {content_with_images}")

        # 更新 history 中的内容
        st.session_state.history.append({"role": "assistant", "content": content_with_images})
        st.write("生成配图后的内容:", content_with_images)
    except Exception as e:
        LOG.error(f"[配图生成错误]: {e}")
        st.error("配图生成出错，请重试。")

# PowerPoint generation handler
def handle_generate():
    try:
        if not st.session_state.history:
            LOG.error("No content in session history to generate PowerPoint.")
            st.error("请先生成内容再生成PowerPoint。")
            return
        
        # 确认 slides_content 的内容格式
        slides_content = st.session_state.history[-1]["content"]
        LOG.debug(f"Slides content before parsing: {slides_content}")

        # 调用解析函数
        powerpoint_data, presentation_title = parse_input_text(slides_content, layout_manager)
        LOG.debug(f"Parsed powerpoint_data: {powerpoint_data}")
        LOG.debug(f"Parsed presentation_title: {presentation_title}")

        # 验证是否生成了内容
        if not powerpoint_data or not powerpoint_data.slides:
            LOG.error("内容为空，无法生成有效的 PowerPoint 文件")
            st.error("内容解析错误，请检查输入数据。")
            return

        # 保存文件
        presentation_title = presentation_title or "Untitled_Presentation"
        presentation_title = re.sub(r'[\\/*?:"<>|]', "", presentation_title)
        output_pptx = f"outputs/{presentation_title}.pptx"

        generate_presentation(powerpoint_data, config.ppt_template, output_pptx)
        st.success("PowerPoint生成成功！点击下载:")
        with open(output_pptx, "rb") as ppt_file:
            st.download_button(label="Download PowerPoint", data=ppt_file, file_name=f"{presentation_title}.pptx")
    except Exception as e:
        LOG.error(f"[PPT生成错误]: {e}")
        st.error("生成 PPT 时出错。请检查输入内容并重试。")

# Streamlit界面设置
st.title("ChatPPT")
st.markdown("## AI-Powered PPT Generation")

user_input = st.text_area("输入主题内容或上传音频文件")
if user_input:
    st.session_state.history.append({"role": "user", "content": user_input})

uploaded_files = st.file_uploader("上传文件", accept_multiple_files=True)
files_data = [{"name": f.name, "file": f} for f in uploaded_files] if uploaded_files else []

if st.button("生成内容"):
    with st.spinner("正在生成内容..."):
        slides_content = asyncio.run(generate_contents({"text": user_input, "files": files_data}, st.session_state.history))
        if slides_content:
            st.write("生成的内容:", slides_content)

if st.button("为PowerPoint生成配图"):
    handle_image_generate()

if st.button("生成PowerPoint"):
    handle_generate()
