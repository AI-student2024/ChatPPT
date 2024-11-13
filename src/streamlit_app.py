import os
import asyncio
import streamlit as st

# 从同一目录下的其他模块导入
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

# 实例化 Config，加载配置文件
config = Config()
chatbot = ChatBot(config.chatbot_prompt)
content_formatter = ContentFormatter(config.content_formatter_prompt)
content_assistant = ContentAssistant(config.content_assistant_prompt)
image_advisor = ImageAdvisor(config.image_advisor_prompt)

# 加载 PowerPoint 模板，并获取可用布局
ppt_template = load_template(config.ppt_template)
layout_manager = LayoutManager(get_layout_mapping(ppt_template))

# 异步生成幻灯片内容的函数
async def generate_contents(message, history):
    try:
        texts = []

        # 获取文本输入
        text_input = message.get("text")
        if text_input:
            texts.append(text_input)

        # 处理上传的文件
        for uploaded_file in message.get("files", []):
            LOG.debug(f"[上传文件]: {uploaded_file}")
            file_ext = os.path.splitext(uploaded_file.name)[1].lower()
            if file_ext in ('.wav', '.flac', '.mp3'):
                audio_text = await asr(uploaded_file)
                texts.append(audio_text)
            elif file_ext in ('.docx', '.doc'):
                raw_content = generate_markdown_from_docx(uploaded_file)
                markdown_content = content_formatter.format(raw_content)
                return content_assistant.adjust_single_picture(markdown_content)
            else:
                LOG.debug(f"[格式不支持]: {uploaded_file}")

        # 合并文本和转录结果
        user_requirement = "需求如下:\n" + "\n".join(texts)
        LOG.info(user_requirement)

        # 调用生成-反思循环
        slides_content = await chatbot.chat_with_reflection(user_requirement)
        return slides_content
    except Exception as e:
        LOG.error(f"[内容生成错误]: {e}")
        raise Exception("网络问题，请重试:)")

# Streamlit 兼容异步支持的包装函数
def async_generate_contents(*args, **kwargs):
    return asyncio.run(generate_contents(*args, **kwargs))

# 配图生成函数
def handle_image_generate(history):
    try:
        # 检查 history 是否为空
        if not history:
            LOG.warning("历史记录为空，无法生成配图")
            raise ValueError("历史记录为空，无法生成配图")

        # 获取最新的内容
        latest_entry = history[-1]
        slides_content = latest_entry.get("content")

        if not slides_content:
            LOG.warning("最新条目没有内容，无法生成配图")
            raise ValueError("最新条目没有内容，无法生成配图")

        # 生成配图
        content_with_images, image_pair = image_advisor.generate_images(slides_content)

        # 创建新的消息
        new_message = {"role": "assistant", "content": content_with_images}
        history.append(new_message)

        return history

    except IndexError as e:
        LOG.error(f"[配图生成错误]: {e}")
        raise Exception("【提示】未找到合适配图，请重试！")

    except ValueError as e:
        LOG.error(f"[配图生成错误]: {e}")
        raise Exception("【提示】未找到合适配图，请重试！")

    except Exception as e:
        LOG.error(f"[配图生成错误]: {e}")
        raise Exception("【提示】未找到合适配图，请重试！")

# 生成 PowerPoint 的函数
def handle_generate(history):
    try:
        slides_content = history[-1]["content"]
        powerpoint_data, presentation_title = parse_input_text(slides_content, layout_manager)
        output_pptx = f"outputs/{presentation_title}.pptx"

        generate_presentation(powerpoint_data, config.ppt_template, output_pptx)
        return output_pptx
    except Exception as e:
        LOG.error(f"[PPT 生成错误]: {e}")
        raise Exception("【提示】请先输入你的主题内容或上传文件")

# 创建 Streamlit 页面
st.title("ChatPPT")

# 创建聊天记录容器
history = []
chat_container = st.container()

# 用户输入区域
user_input = st.text_area("输入你的主题内容或上传音频文件", "")
file_uploader = st.file_uploader("上传文件", type=['wav', 'flac', 'mp3', 'docx', 'doc'])

# 提交按钮
if st.button('提交'):
    message = {"text": user_input, "files": [file_uploader] if file_uploader else []}
    response = async_generate_contents(message, history)
    history.append({"role": "assistant", "content": response})
    chat_container.write(response)

# 配图按钮
if st.button('一键为 PowerPoint 配图'):
    updated_history = handle_image_generate(history)
    chat_container.write(updated_history[-1]['content'])

# 生成 PPT 按钮
if st.button('一键生成 PowerPoint'):
    pptx_path = handle_generate(history)
    with open(pptx_path, "rb") as file:
        st.download_button(
            label="下载 PPT",
            data=file,
            file_name=os.path.basename(pptx_path),
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )