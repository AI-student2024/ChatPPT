import os
import requests
from openai import OpenAI
from PIL import Image
from io import BytesIO
from logger import LOG

class ImageGenerator:
    def __init__(self, prompt_file="./prompts/image_generator.txt"):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("请设置 OPENAI_API_KEY 环境变量")
        self.client = OpenAI(api_key=self.api_key)
        self.prompt_file = prompt_file
        self.prompt = self.load_prompt()  # 加载提示词

    def load_prompt(self):
        """
        从文件加载提示词。
        """
        try:
            with open(self.prompt_file, "r", encoding="utf-8") as file:
                return file.read().strip()
        except FileNotFoundError:
            LOG.error(f"找不到提示文件 {self.prompt_file}!")
            raise

    def generate_image(self, user_input, output_path=None):
        """
        使用 OpenAI API 根据提示生成图像并保存。

        参数:
            user_input (str): 用户输入的图像生成文本提示
            output_path (str): 生成图像的保存路径。如果未指定，默认为项目根目录的 images/generator_images 文件夹。

        返回:
            str: 保存的图像的完整路径
        """
        # 设置默认保存路径为项目根目录的 images/generator_images 文件夹
        if output_path is None:
            output_dir = os.path.join(os.getcwd(), "images", "generator_images")
            os.makedirs(output_dir, exist_ok=True)  # 自动创建目录
            output_path = os.path.join(output_dir, "generated_image.jpg")
        else:
            output_path = os.path.abspath(output_path)  # 转换为完整路径

        prompt = f"{self.prompt} {user_input}"  # 将加载的提示词与用户输入组合

        # 添加日志，记录调用 generate_image 方法的具体操作
        LOG.info(f"调用 ImageGenerator 生成图像，关键词：'{user_input}', 保存路径：{output_path}")

        try:
            response = self.client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                n=1,
                size="1024x1024"
            )
            if hasattr(response, "data") and response.data:
                img_url = response.data[0].url
                img_response = requests.get(img_url)
                img_data = img_response.content
                image = Image.open(BytesIO(img_data))
                image.save(output_path)
                LOG.debug(f"成功生成图像，关键词：{user_input}")
                return output_path
            else:
                raise ValueError("无效的响应格式")
        except Exception as e:
            LOG.error(f"生成图像失败: {e}")
            return None

def main():
    """
    主函数，用于测试 ImageGenerator 类的功能。
    """
    generator = ImageGenerator()
    test_input = "a beautiful landscape with mountains and rivers"  # 示例输入
    result = generator.generate_image(test_input)

    if result:
        LOG.info(f"图像成功生成并保存在 {result}")
    else:
        LOG.error("图像生成失败")

if __name__ == "__main__":
    main()
