from deepagents import create_deep_agent
from langchain_ollama import ChatOllama

qwen = ChatOllama(
    model="qwen3.5:4b",
    temperature=0.1,
)

agent = create_deep_agent(
    model= qwen,
    tools = [],
    system_prompt= (
        ""
    )
)
