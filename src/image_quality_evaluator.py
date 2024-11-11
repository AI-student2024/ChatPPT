import os
from openai import OpenAI
from logger import LOG

class ImageQualityEvaluator:
    def __init__(self, prompt_file="prompts/image_quality_evaluator.txt", model="gpt-4o"):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            LOG.error("API key not found in environment variables. Please set 'OPENAI_API_KEY'.")
            raise ValueError("Missing OpenAI API key")
        self.client = OpenAI(api_key=self.api_key)
        self.system_prompt = self.load_system_prompt(prompt_file)
        self.model = model

    def load_system_prompt(self, prompt_file):
        try:
            with open(prompt_file, "r", encoding="utf-8") as file:
                return file.read().strip()
        except FileNotFoundError:
            LOG.error(f"Prompt file '{prompt_file}' not found.")
            raise

    def analyze_image_with_openai(self, image_url):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe the content of this image."},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    }
                ],
                max_tokens=300,
                timeout=10
            )

            # 检查 choices 结构是否符合预期
            if response.choices and response.choices[0].message:
                description = response.choices[0].message.content
                LOG.debug(f"Image description generated: {description}")
                return description
            else:
                LOG.error("Unexpected response structure: 'choices' does not contain 'message'.")
                return None

        except Exception as e:
            LOG.error(f"Failed to generate image description with OpenAI API: {e}")
            return None

    def evaluate_image_quality_with_openai(self, slide_text, image_url):
        image_description = self.analyze_image_with_openai(image_url)

        if not image_description:
            LOG.warning("No image description available; returning low similarity score.")
            return 0.0

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"Compare the slide text and image description provided below and respond ONLY with a similarity score between 0 and 1.\n\nSlide Text: {slide_text}\n\nImage Description: {image_description}\n\nSimilarity Score:"
                            }
                        ]
                    }
                ],
                max_tokens=10,  # 限制输出长度，确保只返回数值
                timeout=10
            )

            if response.choices and response.choices[0].message:
                score_text = response.choices[0].message.content.strip()
                score = float(score_text)
                LOG.debug(f"Similarity score for slide text and image: {score}")
                return score
            else:
                LOG.error("Unexpected response structure or empty response.")
                return 0.0

        except ValueError as e:
            LOG.error(f"Could not convert similarity score to float: {e}")
            return 0.0
        except Exception as e:
            LOG.error(f"Failed to evaluate similarity with OpenAI API: {e}")
            return 0.0

def main():
    """
    主函数，用于测试 ImageQualityEvaluator 类的功能。
    """
    evaluator = ImageQualityEvaluator()

    # 测试数据
    slide_text = "This slide discusses the effects of climate change on global temperatures and ecosystems."
    # image_url = "https://cdn.britannica.com/47/246247-050-F1021DE9/AI-text-to-image-photo-robot-with-computer.jpg"
    image_url = "https://www.worldatlas.com/r/w1200/upload/fc/db/26/thinkstockphotos-464822073.jpg"

    LOG.info("开始测试图像描述生成")
    image_description = evaluator.analyze_image_with_openai(image_url)
    LOG.info(f"生成的图像描述: {image_description}")

    LOG.info("开始测试幻灯片内容与图像内容的匹配度评估")
    similarity_score = evaluator.evaluate_image_quality_with_openai(slide_text, image_url)
    
    # 更直观的输出结果
    LOG.info("匹配度评估结果：")
    LOG.info(f"Slide Text: {slide_text}")
    LOG.info(f"Image Description: {image_description}")
    LOG.info(f"Similarity Score: {similarity_score}")

if __name__ == "__main__":
    main()
