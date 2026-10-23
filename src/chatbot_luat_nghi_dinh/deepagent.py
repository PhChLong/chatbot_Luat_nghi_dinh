import os

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from .prompts import *

load_dotenv()

type MessageType = HumanMessage | SystemMessage
class Agent:
    def __init__(self, model_name:str = "gemma4:31b") -> None:
        self.llm: ChatOllama = ChatOllama(
            model=model_name,
            base_url="https://ollama.com",
            temperature=0.1,
            client_kwargs={
                "headers": {
                    "Authorization": f"Bearer {os.environ['OLLAMA_API_KEY']}",
                },
            },
        )
        self.history:list[MessageType] = [
            SystemMessage(
                content= "bạn là giáo viên dạy toán cho học sinh tiểu học, hãy giảng thật từ từ và dễ hiểu"
            ),
        ]

    def invoke(self, question:str) -> None:
        self.history.append(
            HumanMessage(content=question)
        )
        response : AIMessage = self.llm.invoke(self.history)
        print(response.content)