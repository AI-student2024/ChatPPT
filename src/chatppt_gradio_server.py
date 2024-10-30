import gradio as gr
import os
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

def load_system_prompt():
    file_path = os.path.join(os.path.dirname(__file__), "../prompts/formatter.txt")
    LOG.info(f"加载系统提示词文件：{file_path}")
    if not os.path.exists(file_path):
        LOG.error(f"未找到系统提示词文件：{file_path}")
        raise FileNotFoundError(f"文件未找到: {file_path}")
    with open(file_path, "r", encoding="utf-8") as file:
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

def generate_md_file(user_input):
    LOG.info("开始生成 Markdown 文件...")
    markdown_text = model_generate_markdown(user_input)
    output_md = "outputs/chatppt_content.md"
    os.makedirs(os.path.dirname(output_md), exist_ok=True)
    with open(output_md, "w", encoding="utf-8") as md_file:
        md_file.write(markdown_text)
    LOG.info(f"Markdown 文件已保存到：{output_md}")
    return output_md

def generate_pptx_from_md(md_path):
    LOG.info("开始将 Markdown 内容转换为 PPTX 文件...")
    config = Config()
    prs = load_template(config.ppt_template)
    print_layouts(prs)
    layout_manager = LayoutManager(config.layout_mapping)
    
    with open(md_path, "r", encoding="utf-8") as md_file:
        markdown_text = md_file.read()
    
    powerpoint_data, presentation_title = parse_input_text(markdown_text, layout_manager)
    
    if not presentation_title:
        presentation_title = "默认演示文稿"
        LOG.warning("演示文稿标题为空，已设置为默认名称。")

    output_pptx = f"outputs/{presentation_title}.pptx"
    os.makedirs(os.path.dirname(output_pptx), exist_ok=True)
    generate_presentation(powerpoint_data, config.ppt_template, output_pptx)
    LOG.info(f"PPTX 文件已保存到：{output_pptx}")
    return output_pptx

def handle_chat(message, chat_history):
    # 记录用户输入并向用户提供下一步提示
    chat_history.append({"role": "user", "content": message})
    bot_response = "内容已收到。请点击“生成 PPTX 文件”按钮以生成文件。"
    chat_history.append({"role": "assistant", "content": bot_response})
    return "", chat_history

def generate_files(chat_history):
    # 从聊天记录中提取最后的用户输入
    user_input = next(
        (entry["content"] for entry in reversed(chat_history) if entry["role"] == "user"), ""
    )
    
    # 生成 Markdown 文件
    md_file_path = generate_md_file(user_input)
    
    # 基于 Markdown 文件生成 PPTX 文件
    pptx_file_path = generate_pptx_from_md(md_file_path)
    
    return md_file_path, pptx_file_path

# 设置 Gradio 界面
with gr.Blocks() as demo:
    gr.Markdown("<h2 style='text-align: center;'>ChatPPT 生成器</h2>")
    
    # 聊天交互和输入
    chatbot = gr.Chatbot(label="ChatPPT 交互界面", type="messages")
    msg = gr.Textbox(label="输入您的内容", placeholder="请输入您的内容")
    
    # 按钮用于生成文件
    generate_pptx_button = gr.Button("生成 PPTX 文件", variant="primary")
    
    # 文件下载链接
    md_file = gr.File(label="下载 Markdown 文件")
    pptx_file = gr.File(label="下载 PPTX 文件")
    
    # 将文本框提交操作链接到聊天响应
    msg.submit(handle_chat, [msg, chatbot], [msg, chatbot])
    
    # 连接“生成 PPTX”按钮与文件生成函数
    generate_pptx_button.click(generate_files, chatbot, [md_file, pptx_file])

if __name__ == "__main__":
    LOG.info("启动 ChatPPT 生成器服务器...")
    demo.launch(server_port=7860)