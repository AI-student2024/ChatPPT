import gradio as gr
import os
import asyncio

from gradio.data_classes import FileData
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
            file_ext = os.path.splitext(uploaded_file)[1].lower()
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
        raise gr.Error("网络问题，请重试:)")

# Gradio 兼容异步支持的包装函数
def async_generate_contents(*args, **kwargs):
    return asyncio.run(generate_contents(*args, **kwargs))

# 配图生成函数
def handle_image_generate(history):
    try:
        slides_content = history[-1]["content"]
        content_with_images, image_pair = image_advisor.generate_images(slides_content)

        new_message = {"role": "assistant", "content": content_with_images}
        history.append(new_message)

        return history
    except Exception as e:
        LOG.error(f"[配图生成错误]: {e}")
        raise gr.Error("【提示】未找到合适配图，请重试！")

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
        raise gr.Error("【提示】请先输入你的主题内容或上传文件")

# 创建 Gradio 界面
with gr.Blocks(
    title="ChatPPT",
    css="""
    body { animation: fadeIn 2s; }
    @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
    """
) as demo:

    gr.Markdown("## ChatPPT")

    # 创建聊天机器人界面
    contents_chatbot = gr.Chatbot(
        placeholder="<strong>AI 一键生成 PPT</strong><br><br>输入你的主题内容或上传音频文件",
        height=800,
        type="messages",
    )

    # 定义 ChatBot 和生成内容的接口
    gr.ChatInterface(
        fn=async_generate_contents,
        chatbot=contents_chatbot,
        type="messages",
        multimodal=True
    )

    image_generate_btn = gr.Button("一键为 PowerPoint 配图")

    image_generate_btn.click(
        fn=handle_image_generate,
        inputs=contents_chatbot,
        outputs=contents_chatbot,
    )

    generate_btn = gr.Button("一键生成 PowerPoint")

    generate_btn.click(
        fn=handle_generate,
        inputs=contents_chatbot,
        outputs=gr.File()
    )

# 主程序入口
if __name__ == "__main__":
    demo.queue().launch(
        share=False,
        server_name="0.0.0.0",
    )
