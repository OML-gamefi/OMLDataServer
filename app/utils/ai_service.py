from openai import AsyncOpenAI
import asyncio
from typing import Optional, List, Union, Dict, Any
from pydantic import BaseModel
from app.config import settings

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None

class ChatResponse(BaseModel):
    content: str
    role: str

class AIService:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.AI_API_KEY,
            base_url=settings.AI_BASE_URL
        )
        self.model = settings.AI_MODEL

    async def chat_completion(
        self,
        chat_request: ChatRequest,
    ) -> ChatResponse:
        """
        调用AI进行对话
        :param chat_request: 对话请求
        :return: AI响应
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[msg.dict() for msg in chat_request.messages],
                temperature=chat_request.temperature,
                max_tokens=chat_request.max_tokens,
            )
            return ChatResponse(
                content=response.choices[0].message.content,
                role=response.choices[0].message.role
            )
        except Exception as e:
            print(f"AI调用出错: {str(e)}")
            raise e

# 创建单例实例
ai_service = AIService()

async def test_chat():
    messages = [
        ChatMessage(role="system", content="你是一个助手"),
        ChatMessage(role="user", content="你好，请介绍一下你自己")
    ]
    chat_request = ChatRequest(messages=messages)
    try:
        response = await ai_service.chat_completion(chat_request)
        print("AI回复：")
        print(response.content)
    except Exception as e:
        print(f"测试过程中出错: {str(e)}")

if __name__ == "__main__":
    # 运行测试对话
    asyncio.run(test_chat())
