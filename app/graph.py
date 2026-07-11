"""
AID Demo – LangGraph Pipeline
START → briefing → rules → layout → mep → evaluation → report → END
"""

from langgraph.graph import StateGraph, START, END
from app.state import PlanningState
from app.agents.briefing      import briefing_agent
from app.agents.rules         import rule_agent
from app.agents.topology      import topology_agent
from app.agents.strategy      import layout_strategy_agent
from app.agents.layout        import layout_agent
from app.agents.erschliessung import erschliessungs_agent
from app.agents.mep           import mep_agent
from app.agents.evaluation    import evaluation_agent
from app.agents.analyse       import analyse_agent
from app.agents.report        import report_agent

builder = StateGraph(PlanningState)

builder.add_node("briefing",      briefing_agent)
builder.add_node("rules",         rule_agent)
builder.add_node("topology",      topology_agent)
builder.add_node("strategy",      layout_strategy_agent)
builder.add_node("layout",        layout_agent)
builder.add_node("erschliessung", erschliessungs_agent)
builder.add_node("mep",           mep_agent)
builder.add_node("evaluation",    evaluation_agent)
builder.add_node("analyse",       analyse_agent)
builder.add_node("report",        report_agent)

builder.add_edge(START,            "briefing")
builder.add_edge("briefing",       "rules")
builder.add_edge("rules",          "topology")
builder.add_edge("topology",       "strategy")
builder.add_edge("strategy",       "layout")
builder.add_edge("layout",         "erschliessung")
builder.add_edge("erschliessung",  "mep")
builder.add_edge("mep",        "evaluation")
builder.add_conditional_edges(
    "evaluation",
    lambda state: "layout" if state.get("needs_layout_refinement") else "analyse",
    {"layout": "layout", "analyse": "analyse"},
)
builder.add_edge("analyse",    "report")
builder.add_edge("report",     END)

graph = builder.compile()
