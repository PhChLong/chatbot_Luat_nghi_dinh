from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

qwen = ChatOllama(
    model="qwen3.5:4b",
    temperature= 0.1,
)
response = qwen.invoke("Giải thích Rag trong 3 câu")
print(response.content)