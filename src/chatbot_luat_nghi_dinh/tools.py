
from typing import TypedDict, Literal
from langgraph.graph import START, END, StateGraph

class RagState(TypedDict):
    question: str
    question_type: str
    retrieved_docs: list[dict]
    answer:str

def classify_question_type(state: RagState) -> dict:
    question_type = None
    return {"question_type": question_type}

def choose_route(state:RagState):
    return state["question_type"] if state["question_type"] in ["metadata", "document_content", "situation"] else chitchat

def metadata(state: RagState):
    pass

def document_content(state: RagState):
    pass

def situation(state: RagState):
    pass

def chitchat(state: RagState):
    pass


def builder():
    builder = StateGraph(RagState)
    builder.add_node("classify_question_type", classify_question_type)

    builder.add_edge(START, "classify")
    builder.add_conditional_edges("classify", choose_route)