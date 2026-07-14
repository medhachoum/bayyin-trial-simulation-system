"""
آلة الحالة الإجرائية الكاملة (LangGraph StateGraph).
الطوبولوجيا هي الإجراء نفسه: لا تُتخطّى خطوة، وكل انتقال محفوظ بـ checkpoint.

المرحلة الابتدائية (مع حلقة مرافعة وخبير):
  router → intake → [مقبولة؟] → notify → defendant_plea → plaintiff_plea
  → hearing_manager → {expert→hearing_manager | defendant_plea | close}
  → judgment → serve
المرحلة الثانية:
  serve → {appeal_brief → appellee_response → appeal_hearing → appellate_panel
           → [التماس؟] | reconsideration | END}
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from . import nodes
from .state import CaseState


def get_checkpointer():
    """Postgres إن وُجد DSN (إنتاج)، وإلا ذاكرة (عرض/تطوير)."""
    import os
    dsn = os.getenv("BAYYIN_PG_DSN")
    if dsn:
        from langgraph.checkpoint.postgres import PostgresSaver
        cp = PostgresSaver.from_conn_string(dsn)
        cp.setup()
        return cp
    from langgraph.checkpoint.memory import MemorySaver
    return MemorySaver()


def build_graph(checkpointer=None):
    if checkpointer is None:
        checkpointer = get_checkpointer()

    g = StateGraph(CaseState)

    # المرحلة الابتدائية
    g.add_node("router", nodes.router_node)
    g.add_node("mediation", nodes.mediation_node)
    g.add_node("intake_register", nodes.intake_register_node)
    g.add_node("rejected", nodes.rejected_node)
    g.add_node("referred", nodes.referred_node)
    g.add_node("research", nodes.research_node)
    g.add_node("notify_defendant", nodes.notify_defendant_node)
    g.add_node("defendant_plea", nodes.defendant_plea_node)
    g.add_node("incidents", nodes.incidents_node)
    g.add_node("incident_ruling", nodes.incident_ruling_node)
    g.add_node("plaintiff_plea", nodes.plaintiff_plea_node)
    g.add_node("hearing_manager", nodes.hearing_manager_node)
    g.add_node("expert", nodes.expert_node)
    g.add_node("close_pleadings", nodes.close_pleadings_node)
    g.add_node("judgment", nodes.judgment_node)
    g.add_node("serve_judgment", nodes.serve_judgment_node)
    # المرحلة الثانية
    g.add_node("appeal_brief", nodes.appeal_brief_node)
    g.add_node("appellee_response", nodes.appellee_response_node)
    g.add_node("appeal_hearing", nodes.appeal_hearing_node)
    g.add_node("appellate_panel", nodes.appellate_panel_node)
    g.add_node("reconsideration", nodes.reconsideration_node)

    g.add_edge(START, "router")
    # المصالحة/الوساطة قبل القيد (م.8 محاكم تجارية) — شرطُ قبولٍ لطيفٍ من الدعاوى.
    g.add_edge("router", "mediation")
    g.add_edge("mediation", "intake_register")
    g.add_conditional_edges("intake_register", nodes.route_after_intake,
                            {"research": "research", "rejected": "rejected", "referred": "referred"})
    g.add_edge("rejected", END)
    g.add_edge("referred", END)
    g.add_edge("research", "notify_defendant")
    g.add_edge("notify_defendant", "defendant_plea")
    # مبدأ المواجهة: يُمكَّن المدعي من الردّ على المذكرة (ودفوعها) قبل الفصل في الدفوع.
    g.add_edge("defendant_plea", "plaintiff_plea")
    g.add_edge("plaintiff_plea", "incidents")
    g.add_conditional_edges("incidents", nodes.route_after_incidents,
                            {"incident_ruling": "incident_ruling", "hearing_manager": "hearing_manager"})
    g.add_edge("incident_ruling", "serve_judgment")
    g.add_conditional_edges("hearing_manager", nodes.route_pleadings,
                            {"expert": "expert", "close_pleadings": "close_pleadings",
                             "defendant_plea": "defendant_plea"})
    g.add_edge("expert", "hearing_manager")
    g.add_edge("close_pleadings", "judgment")
    g.add_edge("judgment", "serve_judgment")
    g.add_conditional_edges("serve_judgment", nodes.route_after_judgment,
                            {"appeal_brief": "appeal_brief",
                             "reconsideration": "reconsideration", "end": END})

    g.add_edge("appeal_brief", "appellee_response")
    g.add_edge("appellee_response", "appeal_hearing")
    g.add_edge("appeal_hearing", "appellate_panel")
    g.add_conditional_edges("appellate_panel", nodes.route_after_appeal,
                            {"reconsideration": "reconsideration", "end": END})
    g.add_edge("reconsideration", END)

    return g.compile(checkpointer=checkpointer)
