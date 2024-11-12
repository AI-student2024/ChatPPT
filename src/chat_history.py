from langchain_core.chat_history import (
    BaseChatMessageHistory,
    InMemoryChatMessageHistory,
)

# 用于存储会话历史的字典
store = {}

def get_session_history(session_id: str) -> BaseChatMessageHistory:
    """
    获取指定会话ID的聊天历史。如果该会话ID不存在，则创建一个新的聊天历史实例。
    
    参数:
        session_id (str): 会话的唯一标识符
    
    返回:
        BaseChatMessageHistory: 对应会话的聊天历史对象
    """
    if session_id not in store:
        # 如果会话ID不存在于存储中，创建一个新的内存聊天历史实例
        store[session_id] = InMemoryChatMessageHistory()
    return store[session_id]

def clear_session_history(session_id: str):
    """
    清空指定会话ID的聊天历史，但保留最后一条消息。
    
    参数:
        session_id (str): 会话的唯一标识符
    """
    if session_id in store:
        history = store[session_id]
        if history.messages:
            # 保存最后一条消息并重置历史
            last_message = history.messages[-1]
            store[session_id] = InMemoryChatMessageHistory()
            store[session_id].messages.append(last_message)
