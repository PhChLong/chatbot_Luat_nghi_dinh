import os

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

load_dotenv()

type MessageType = HumanMessage | SystemMessage


#@ Gộp content của AIMessage (str hoặc list các khối) thành 1 chuỗi text
def content_to_text(content: str | list[str | dict]) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    block: str | dict
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif block.get("type") == "text":  #?: bỏ qua các khối không phải text (thinking, tool_use...)
            parts.append(str(block.get("text", "")))
    return "".join(parts)


class Agent:
    def __init__(
        self,
        system_prompt: str | None = None,
        model_name: str = "gemma4:31b",
        temperature: float = 0.1,
    ) -> None:
        self.system_prompt: str | None = system_prompt
        self.llm: ChatOllama = ChatOllama(
            model=model_name,
            base_url="https://ollama.com",
            temperature=temperature,
            client_kwargs={
                "headers": {"Authorization": f"Bearer {os.environ['OLLAMA_API_KEY']}"},
            },
        )

    #@ Gửi system prompt (nếu có) cùng câu hỏi tới model và trả về text
    def invoke(self, question: str) -> str:
        messages: list[MessageType] = []
        if self.system_prompt is not None:
            messages.append(SystemMessage(content=self.system_prompt))
        messages.append(HumanMessage(content=question))
        response: AIMessage = self.llm.invoke(messages)
        return content_to_text(response.content)