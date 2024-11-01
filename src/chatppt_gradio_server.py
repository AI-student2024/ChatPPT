import gradio as gr
import os
from pathlib import Path
from input_parser import parse_input_text
from ppt_generator import generate_presentation
from template_manager import load_template, print_layouts
from layout_manager import LayoutManager
from config import Config
from logger import LOG
from openai import OpenAI

# 初始化 OpenAI API 密钥
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    LOG.error("未找到 OpenAI API 密钥，请检查环境变量。")
    raise ValueError("OpenAI API 密钥未在环境变量中找到")

client = OpenAI(api_key=api_key)

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 提示词文件路径
PROMPTS_DIR = BASE_DIR / "prompts"
FORMATTER_FILE_PATH = PROMPTS_DIR / "formatter.txt"

# 输出文件夹路径
OUTPUTS_DIR = BASE_DIR / "outputs"

# 创建输出文件夹（如果不存在）
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# 存储图文内容的列表
content_history = []

def load_system_prompt():
    LOG.info(f"加载系统提示词文件：{FORMATTER_FILE_PATH}")
    if not FORMATTER_FILE_PATH.exists():
        LOG.error(f"未找到系统提示词文件：{FORMATTER_FILE_PATH}")
        raise FileNotFoundError(f"文件未找到: {FORMATTER_FILE_PATH}")
    with FORMATTER_FILE_PATH.open("r", encoding="utf-8") as file:
        return file.read()

def model_generate_markdown(user_input):
    LOG.info("调用大模型生成 Markdown 格式的内容...")
    system_prompt = load_system_prompt()
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]
    )
    markdown_text = completion.choices[0].message.content
    LOG.info("成功生成 Markdown 内容")
    return markdown_text

def add_content_to_history(user_input, images):
    # 将用户输入的文本和图片保存到全局内容历史列表
    if user_input:
        content_history.append({"text": user_input, "images": []})
    if images:
        image_paths = [img for img in images] if isinstance(images, list) else [images]
        content_history.append({"text": "", "images": image_paths})
    LOG.info(f"内容已保存到历史记录中，共有 {len(content_history)} 条内容。")

def generate_md_file():
    LOG.info("开始生成 Markdown 文件...")
    markdown_text = ""

    # 遍历历史记录，生成 Markdown 内容
    for entry in content_history:
        if entry["text"]:
            markdown_text += f"{entry['text']}\n\n"
        if entry["images"]:
            for i, img_path in enumerate(entry["images"]):
                img_tag = f"![图片{i + 1}]({img_path})"
                markdown_text += f"{img_tag}\n\n"

    # 保存 Markdown 文件
    output_md_path = OUTPUTS_DIR / "chatppt_content.md"
    with output_md_path.open("w", encoding="utf-8") as md_file:
        md_file.write(markdown_text)
    LOG.info(f"Markdown 文件已保存到：{output_md_path}")
    return str(output_md_path)  # 将 Path 转换为字符串

def generate_pptx_from_md(md_path):
    LOG.info("开始将 Markdown 内容转换为 PPTX 文件...")
    config = Config()
    prs = load_template(config.ppt_template)
    print_layouts(prs)
    layout_manager = LayoutManager(config.layout_mapping)

    with Path(md_path).open("r", encoding="utf-8") as md_file:
        markdown_text = md_file.read()

    powerpoint_data, presentation_title = parse_input_text(markdown_text, layout_manager)

    if not presentation_title:
        presentation_title = "默认演示文稿"
        LOG.warning("演示文稿标题为空，已设置为默认名称。")

    output_pptx_path = OUTPUTS_DIR / f"{presentation_title}.pptx"
    generate_presentation(powerpoint_data, config.ppt_template, output_pptx_path)
    LOG.info(f"PPTX 文件已保存到：{output_pptx_path}")
    return str(output_pptx_path)  # 将 Path 转换为字符串

def handle_text_input(message, chat_history):
    # 将用户输入的文本保存到历史记录中
    add_content_to_history(message, [])
    # 更新聊天历史
    chat_history.append({"role": "user", "content": message})
    # bot_response = "内容已保存。您可以继续输入下一段内容和图片，或者点击“生成 PPTX 文件”按钮以生成文件。"
    
    # 直接调用 GPT-4o-mini 生成回复
    try:
        bot_response = model_generate_markdown(message)
    except Exception as e:
        LOG.error(f"生成回复时出错: {e}")
        bot_response = "抱歉，我在生成回复时遇到问题，请稍后再试。"

    # 将模型回复保存到历史记录中
    add_content_to_history(bot_response, [])
   
    # 更新聊天历史
    chat_history.append({"role": "assistant", "content": bot_response})
    return "", chat_history

def handle_image_upload(images, chat_history):
    # 将图片路径保存到历史记录中
    if images:
        add_content_to_history("", images)
        # 更新聊天历史
        for i, img_path in enumerate(images):
            chat_history.append({"role": "user", "content": f"上传了图片 {i + 1}: {os.path.basename(img_path)}"})
    bot_response = "图片已保存。您可以继续输入内容，或者点击“生成 PPTX 文件”按钮以生成文件。"
    chat_history.append({"role": "assistant", "content": bot_response})
    return chat_history

def generate_files():
    # 生成 Markdown 文件
    md_file_path = generate_md_file()

    # 基于 Markdown 文件生成 PPTX 文件
    pptx_file_path = generate_pptx_from_md(md_file_path)

    return md_file_path, pptx_file_path

# 设置 Gradio 界面
with gr.Blocks() as demo:
    gr.Markdown("<h2 style='text-align: center;'>ChatPPT 生成器</h2>")

    chatbot = gr.Chatbot(
        placeholder="<strong>你的ppt助手</strong><br><br>给我内容，一键生成pptx！",
        height=800,
        type="messages"  # 确保格式为 messages 类型
    )
    msg = gr.Textbox(label="输入您的内容", placeholder="请输入您的内容")
    image_input = gr.File(label="上传图片", file_count="multiple", type="filepath")  # 允许多张图片上传
    generate_pptx_button = gr.Button("生成 PPTX 文件", variant="primary")

    md_file = gr.File(label="下载 Markdown 文件")
    pptx_file = gr.File(label="下载 PPTX 文件")

    # 连接文本输入框与聊天历史更新
    msg.submit(handle_text_input, [msg, chatbot], [msg, chatbot])

    # 连接图片上传到聊天历史更新
    image_input.upload(handle_image_upload, [image_input, chatbot], [chatbot])

    # 连接“生成 PPTX”按钮与文件生成函数
    generate_pptx_button.click(generate_files, [], [md_file, pptx_file])

if __name__ == "__main__":
    LOG.info("启动 ChatPPT 生成器服务器...")
    demo.launch(server_port=7860)
