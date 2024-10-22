import json
import os

class Config:
    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self.load_config()
    
    def load_config(self):
        # 检查 config 文件是否存在
        if not os.path.exists(self.config_file):
            raise FileNotFoundError(f"Config file '{self.config_file}' not found.")

        with open(self.config_file, 'r') as f:
            config = json.load(f)
            
            # 加载 ChatPPT 运行模式（默认文本模态）
            self.input_mode = config.get('input_mode', "text")
            
            # 加载所有模板类型及其映射
            self.templatetypes = config.get('templatetypes', {})

    def get_template_info(self, template_type="standard"):
        """
        获取指定模板类型的模板信息。
        :param template_type: 模板类型（如 'standard', 'master', 'extra'）
        :return: 模板名称和布局映射
        """
        if template_type in self.templatetypes:
            template_info = self.templatetypes[template_type]
            ppt_template = template_info.get('ppt_template', '')
            layout_mapping = template_info.get('layout_mapping', {})
            return ppt_template, layout_mapping
        else:
            raise ValueError(f"Template type '{template_type}' not found in config.")
