# src/chatbot.py

import asyncio
from abc import ABC
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.runnables.history import RunnableWithMessageHistory
from typing import Annotated
from typing_extensions import TypedDict

from logger import LOG
from chat_history import get_session_history, clear_session_history

MAX_ROUNDS = 3  # 测试时设置为3轮

class State(TypedDict):
    messages: Annotated[list, add_messages]
    round: int  # 添加轮次数

class ChatBot(ABC):
    def __init__(self, prompt_file="./prompts/chatbot.txt", session_id=None):
        self.prompt_file = prompt_file
        self.session_id = session_id if session_id else "default_session_id"
        self.prompt = self.load_prompt()  
        self.create_chatbot()  

    def load_prompt(self):
        try:
            with open(self.prompt_file, "r", encoding="utf-8") as file:
                return file.read().strip()
        except FileNotFoundError:
            raise FileNotFoundError(f"找不到提示文件 {self.prompt_file}!")

    def create_chatbot(self):
        # 创建聊天提示模板
        system_prompt = ChatPromptTemplate.from_messages([
            ("system", self.prompt),
            MessagesPlaceholder(variable_name="messages"),
        ])

        # 初始化聊天模型
        self.chatbot = system_prompt | ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.5,
            max_tokens=4096
        )

        # 添加消息历史功能
        self.chatbot_with_history = RunnableWithMessageHistory(self.chatbot, get_session_history)

        # 配置反思提示模板，适应 PPT 内容反馈
        self.reflection_prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are a presentation expert reviewing the user's PowerPoint content. Assess the clarity, logical flow, visual impact, and overall effectiveness of the slides."
                " Provide detailed feedback, including suggestions for improving the structure, enhancing key points, refining language, and optimizing visuals to better engage the audience."
                " Tailor your recommendations to ensure that the presentation effectively communicates the intended message and maintains audience interest.",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ])

        # 初始化反思模型
        self.reflect = self.reflection_prompt | ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.2,
            max_tokens=4096,
        )

    async def generation_node(self, state: State) -> State:
        result = await self.chatbot.ainvoke(state['messages']) 
        LOG.debug(f"第 {state['round']} 轮生成内容: {result.content[:100]}")
        state['messages'] = [result]
        return state

    async def reflection_node(self, state: State) -> State:
        LOG.debug(f"调用反思节点，当前轮次: {state['round']}")
        cls_map = {"ai": HumanMessage, "human": HumanMessage}
        translated = [state['messages'][0]] + [
            cls_map[msg.type](content=msg.content) for msg in state['messages'][1:]
        ]
        res = await self.reflect.ainvoke(translated)
        LOG.debug(f"第 {state['round']} 轮反思内容: {res.content[:100]}")
        state['messages'] = [HumanMessage(content=res.content)]
        state['round'] += 1  # 反思完成后增加轮次
        return state

    def should_continue(self, state: State):
        if state["round"] > MAX_ROUNDS:
            LOG.debug("达到最大轮数，终止反思循环")
            return END
        return "reflect"

    async def chat_with_reflection(self, user_input, session_id=None):
        if session_id is None:
            session_id = self.session_id

        LOG.debug(f"用户初始输入: {user_input}")

        builder = StateGraph(State)
        builder.add_node("writer", self.generation_node)  
        builder.add_node("reflect", self.reflection_node)  
        builder.add_edge(START, "writer")  
        builder.add_conditional_edges("writer", self.should_continue)  
        builder.add_edge("reflect", "writer")  
        memory = MemorySaver()
        graph = builder.compile(checkpointer=memory)  

        # 初始化输入，设置round为1
        inputs = {"messages": [HumanMessage(content=user_input)], "round": 1} 
        config = {"configurable": {"thread_id": session_id}}  

        LOG.debug("开始执行生成-反思过程")
        final_content = ""  # 存储最终生成内容
        async for event in graph.astream(inputs, config=config):
            if 'writer' in event:
                final_content = event['writer']['messages'][0].content
            elif 'reflect' in event:
                final_content = event['reflect']['messages'][0].content
                
            # 每轮次后清除历史记录，只保留当前轮次的内容
            clear_session_history(session_id)

        # 在反思循环结束后，执行最后一次内容生成
        LOG.debug("反思结束，生成最终内容")
        final_event = await self.generation_node(inputs)
        final_content = final_event["messages"][0].content
        LOG.debug(f"[ChatBot 最终生成输出] {final_content}") 


        # 将最终生成的版本存入ChatHistory
        get_session_history(session_id).add_message(HumanMessage(content=final_content))
        return final_content

    def chat_with_history(self, user_input, session_id=None):
        """
        处理用户输入，生成包含聊天历史的回复。

        参数:
            user_input (str): 用户输入的消息
            session_id (str, optional): 会话的唯一标识符

        返回:
            str: AI 生成的回复
        """
        if session_id is None:
            session_id = self.session_id

        response = self.chatbot_with_history.invoke(
            [HumanMessage(content=user_input)],  
            {"configurable": {"session_id": session_id}},  
        )

        LOG.debug(f"[ChatBot] {response.content}")
        return response.content  

if __name__ == "__main__":
    bot = ChatBot()
    user_input = "介绍宇宙黑洞"
    asyncio.run(bot.chat_with_reflection(user_input))
