"""LangGraph workflow assembly for Flamo autonomous agent."""

import logging
from langgraph.graph import StateGraph, START, END
from app.agents.supervisor import supervisor_agent
from app.workflows.nodes import (
    supervisor_node,
    planner_node,
    executor_node,
    tools_node,
    verifier_node,
    recovery_node,
    finalize_node,
)
from app.workflows.state import FlamoAgentState

logger = logging.getLogger("flamo.workflows.graph")


def executor_condition(state: FlamoAgentState) -> str:
    """Determine whether executor requested tool calls or finished its turn."""
    messages = state.get("messages", [])
    tool_results = state.get("tool_results", [])
    # Allow tool execution up to max 14 tool calls across reasoning & recovery
    if messages and len(tool_results) < 14:
        last_message = messages[-1]
        tool_calls = getattr(last_message, "tool_calls", None)
        if tool_calls:
            return "tools"
    return "supervisor"


def create_flamo_graph():
    """Build and compile the complete Flamo orchestration graph."""
    builder = StateGraph(FlamoAgentState)

    # 1. Register workflow nodes
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("planner", planner_node)
    builder.add_node("executor", executor_node)
    builder.add_node("tools", tools_node)
    builder.add_node("verifier", verifier_node)
    builder.add_node("recovery", recovery_node)
    builder.add_node("finalize", finalize_node)

    # 2. START -> supervisor
    builder.add_edge(START, "supervisor")

    # 3. Supervisor routing conditional edge
    builder.add_conditional_edges(
        "supervisor",
        supervisor_agent.route,
        {
            "planner": "planner",
            "executor": "executor",
            "verifier": "verifier",
            "recovery": "recovery",
            "finalize": "finalize",
        },
    )

    # 4. Planner -> Supervisor
    builder.add_edge("planner", "supervisor")

    # 5. Executor -> Tools (if tool call) OR Supervisor (if finished)
    builder.add_conditional_edges(
        "executor",
        executor_condition,
        {
            "tools": "tools",
            "supervisor": "supervisor",
        },
    )

    # 6. Tools loop back to Executor to observe results
    builder.add_edge("tools", "executor")

    # 7. Verifier -> Supervisor
    builder.add_edge("verifier", "supervisor")

    # 8. Recovery -> Supervisor
    builder.add_edge("recovery", "supervisor")

    # 9. Finalize -> END
    builder.add_edge("finalize", END)

    # Compile the graph
    return builder.compile()


# Global compiled workflow instance
flamo_graph = create_flamo_graph()
