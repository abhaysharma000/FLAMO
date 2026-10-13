from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from langchain_core.messages import HumanMessage

from app.services.llm import llm
from app.tools.calculator import calculator
from app.workflows.state import AgentState


# --------------------------------
# 1. Give tools to the LLM
# --------------------------------

tools = [calculator]

llm_with_tools = llm.bind_tools(tools)


# --------------------------------
# 2. LLM Node
# --------------------------------

def call_llm(state: AgentState):

    response = llm_with_tools.invoke(state["messages"])

    return {
        "messages": [response]
    }


# --------------------------------
# 3. Tool Node
# --------------------------------

tool_node = ToolNode(tools)


# --------------------------------
# 4. Decide where to go next
# --------------------------------

def should_continue(state: AgentState):

    last_message = state["messages"][-1]

    # If LLM requested a tool
    if last_message.tool_calls:
        return "tools"

    # Otherwise finish
    return END


# --------------------------------
# 5. Create Graph
# --------------------------------

graph_builder = StateGraph(AgentState)


# Add nodes
graph_builder.add_node("llm", call_llm)
graph_builder.add_node("tools", tool_node)


# START → LLM
graph_builder.add_edge(START, "llm")


# LLM → Tools OR END
graph_builder.add_conditional_edges(
    "llm",
    should_continue,
    {
        "tools": "tools",
        END: END
    }
)


# Tools → LLM
graph_builder.add_edge("tools", "llm")


# Compile
agent = graph_builder.compile()