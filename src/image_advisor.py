import re
import requests
import os
from abc import ABC
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from logger import LOG
from image_generator import ImageGenerator  # 导入图像生成器
from image_quality_evaluator import ImageQualityEvaluator  # 导入图像评估器

class ImageAdvisor(ABC):
    """
    聊天机器人基类，提供建议配图的功能。
    """
    def __init__(self, prompt_file="./prompts/image_advisor.txt"):
        self.prompt_file = prompt_file
        self.prompt = self.load_prompt()
        self.create_advisor()
        self.image_generator = ImageGenerator()  # 初始化图像生成实例
        self.image_quality_evaluator = ImageQualityEvaluator()  # 初始化图像评估实例

    def load_prompt(self):
        """
        从文件加载系统提示语。
        """
        try:
            with open(self.prompt_file, "r", encoding="utf-8") as file:
                return file.read().strip()
        except FileNotFoundError:
            LOG.error(f"找不到提示文件 {self.prompt_file}!")
            raise

    def create_advisor(self):
        """
        初始化聊天机器人，包括系统提示和消息历史记录。
        """
        chat_prompt = ChatPromptTemplate.from_messages([
            ("system", self.prompt),  # 系统提示部分
            ("human", "**Content**:\n\n{input}"),  # 消息占位符
        ])
        self.model = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.7,
            max_tokens=4096,
        )
        self.advisor = chat_prompt | self.model

    def generate_images(self, markdown_content, image_directory="tmps", num_images=3):
        """
        生成图片并嵌入到指定的 PowerPoint 内容中。

        参数:
            markdown_content (str): PowerPoint markdown 原始格式
            image_directory (str): 本地保存图片的文件夹名称
            num_images (int): 每个幻灯片搜索的图像数量

        返回:
            content_with_images (str): 嵌入图片后的内容
            image_pair (dict): 每个幻灯片标题对应的图像路径
        """
        response = self.advisor.invoke({
            "input": markdown_content,
        })

        LOG.debug(f"[Advisor 建议配图]\n{response.content}")

        keywords = self.get_keywords(response.content)
        image_pair = {}

        for slide_title, query in keywords.items():
            # 首先尝试从 Bing 检索图像
            images = self.get_bing_images(slide_title, query, num_images, timeout=1, retries=3)
            if images:
                # 评估检索到的图片与内容的匹配度
                best_image = None
                highest_score = 0
                for image in images:
                    score = self.image_quality_evaluator.evaluate_image_quality_with_openai(slide_text=query, image_url=image["url"])
                    LOG.debug(f"评估图像 '{image['url']}' 与 '{query}' 的匹配度得分: {score}")
                    if score > highest_score:
                        best_image = image
                        highest_score = score

                # 判断匹配度是否足够高
                if highest_score >= 0.7:  # 如果评分达到0.7则使用该图像
                    save_directory = f"images/{image_directory}"
                    os.makedirs(save_directory, exist_ok=True)
                    save_path = os.path.join(save_directory, f"{best_image['slide_title']}_1.jpeg")
                    self.save_image(best_image["obj"], save_path)
                    image_pair[best_image["slide_title"]] = save_path
                else:
                    # 使用生成模型生成图像
                    LOG.warning(f"Image matching score too low ({highest_score}). Generating a new image for '{slide_title}'.")
                    generated_image_path = self.image_generator.generate_image(query, output_path=f"images/{image_directory}/{slide_title}_gen.jpg")
                    if generated_image_path:
                        image_pair[slide_title] = generated_image_path
            else:
                # 如果未找到合适图像，直接使用图像生成模型
                LOG.warning(f"No images found for {slide_title}. Using image generator.")
                generated_image_path = self.image_generator.generate_image(query, output_path=f"images/{image_directory}/{slide_title}_gen.jpg")
                if generated_image_path:
                    image_pair[slide_title] = generated_image_path

        content_with_images = self.insert_images(markdown_content, image_pair)
        return content_with_images, image_pair

    def get_keywords(self, advice):
        """
        使用正则表达式提取关键词。

        参数:
            advice (str): 提示文本
        返回:
            keywords (dict): 提取的关键词字典
        """
        pairs = re.findall(r'\[(.+?)\]:\s*(.+)', advice)
        keywords = {key.strip(): value.strip() for key, value in pairs}
        LOG.debug(f"[检索关键词 正则提取结果]{keywords}")
        return keywords

    def get_bing_images(self, slide_title, query, num_images=5, timeout=1, retries=3):
        """
        从 Bing 检索图像，最多重试3次。
        """
        url = f"https://www.bing.com/images/search?q={query}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36"
        }

        LOG.info(f"开始检索图像，关键词: '{query}', 目标数量: {num_images}")

        # 尝试请求并设置重试逻辑
        for attempt in range(retries):
            try:
                response = requests.get(url, headers=headers, timeout=timeout)
                response.raise_for_status()
                break  # 请求成功，跳出重试循环
            except requests.RequestException as e:
                LOG.warning(f"Attempt {attempt + 1}/{retries} failed for query '{query}': {e}")
                if attempt == retries - 1:
                    LOG.error(f"Max retries reached for query '{query}'.")
                    return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        image_elements = soup.select("a.iusc")

        image_links = []
        for img in image_elements:
            m_data = img.get("m")
            if m_data:
                m_json = eval(m_data)
                if "murl" in m_json:
                    image_links.append(m_json["murl"])
                    LOG.debug(f"发现图片链接: {m_json['murl']}")
            if len(image_links) >= num_images:
                break

        image_data = []
        for link in image_links:
            for attempt in range(retries):
                try:
                    LOG.info(f"开始下载图片 '{link}', 尝试 {attempt + 1}/{retries}")
                    img_data = requests.get(link, headers=headers, timeout=timeout)
                    img = Image.open(BytesIO(img_data.content))
                    image_info = {
                        "slide_title": slide_title,
                        "query": query,
                        "width": img.width,
                        "height": img.height,
                        "resolution": img.width * img.height,
                        "obj": img,
                        "url": link  # 添加图片的原始 URL
                    }
                    LOG.info(f"成功下载图片: {link}")
                    image_data.append(image_info)
                    break  # 成功下载图像，跳出重试循环
                except Exception as e:
                    LOG.warning(f"Attempt {attempt + 1}/{retries} failed for image '{link}': {e}")
                    if attempt == retries - 1:
                        LOG.error(f"Max retries reached for image '{link}'. Skipping.")

        # 排序并选择最优的图像
        sorted_images = sorted(image_data, key=lambda x: x["resolution"], reverse=True)
        LOG.info(f"检索到的图像数量: {len(sorted_images)}，按分辨率排序后选择最优的图像")
        
        return sorted_images


    def save_image(self, img, save_path, format="JPEG", quality=85, max_size=1080):
        """
        保存图像到本地并压缩。
        """
        try:
            width, height = img.size
            if max(width, height) > max_size:
                scaling_factor = max_size / max(width, height)
                new_width = int(width * scaling_factor)
                new_height = int(height * scaling_factor)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            if img.mode == "RGBA":
                format = "PNG"
                save_options = {"optimize": True}
            else:
                save_options = {
                    "quality": quality,
                    "optimize": True,
                    "progressive": True
                }

            img.save(save_path, format=format, **save_options)
            LOG.debug(f"Image saved as {save_path} in {format} format with quality {quality}.")
        except Exception as e:
            LOG.error(f"Failed to save image: {e}")

    def insert_images(self, markdown_content, image_pair):
        """
        将图像嵌入到 Markdown 内容中。
        """
        lines = markdown_content.split('\n')
        new_lines = []
        i = 0
        while i < len(lines):
            line = lines[i]
            new_lines.append(line)
            if line.startswith('## '):
                slide_title = line[3:].strip()
                if slide_title in image_pair:
                    image_path = image_pair[slide_title]
                    image_markdown = f'![{slide_title}]({image_path})'
                    new_lines.append(image_markdown)
            i += 1
        new_content = '\n'.join(new_lines)
        return new_content

def main():
    """
    主函数，用于测试 ImageAdvisor 类的功能。
    """
    advisor = ImageAdvisor()

    test_content = """
    ## Slide 1
    This slide discusses climate change and its impacts.
    ## Slide 2
    Renewable energy sources and their benefits.
    """
    content_with_images, image_pair = advisor.generate_images(test_content, image_directory="test_images")

    LOG.info("生成的内容带图片信息：")
    LOG.info(content_with_images)
    LOG.info("生成的图片路径映射：")
    LOG.info(image_pair)

if __name__ == "__main__":
    main()
