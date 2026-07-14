"""
خادم الويب لنظام «بيّن» — يبثّ مجريات المحاكمة لحظةً بلحظة (SSE عبر POST)،
بوعيٍ زمني (تواريخ هجرية/ميلادية تقديرية لكل إجراء)، ويستقبل:
  • case: حقول الدعوى القابلة للتحرير (الوقائع/العقد، القيمة، الأطراف، تاريخ القيد...).
  • overrides: نصوصٌ من المستخدم تستبدل نصوص الوكلاء (key → text) ثم يُعاد التشغيل.

التشغيل:  python -m uvicorn server:app --port 8010  ثم http://127.0.0.1:8010
"""
from __future__ import annotations

import json
import random
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from bayyin import config, nodes, rules, settings, timeline
from bayyin.graph import build_graph
from bayyin.state import Document, DocType, Party

app = FastAPI(title="بيّن — محكمة افتراضية زمنية الوعي")
WEB = Path(__file__).parent / "web"

# قفلٌ يسلسل التشغيلات: الإعدادات تُطبَّق على globals الوحدة (config.apply/MOCK/…)
# فتشغيلان متوازيان يتصارعان (وقد يتسرّب مفتاحُ مستخدمٍ لنداءات آخر). إلى حين عزل
# الإعدادات لكل تشغيل (RunConfig)، يُنفَّذ تشغيلٌ واحدٌ في كل لحظة.
_RUN_LOCK = threading.Lock()

STAGES: dict[str, tuple[str, str]] = {
    "router": ("تصنيف الدعوى", "🧭"),
    "mediation": ("المصالحة والوساطة (قبل القيد)", "🤝"),
    "intake_register": ("قيد الدعوى", "📝"),
    "research": ("البحث القضائي (مبادئ وسوابق)", "🔎"),
    "rejected": ("طلب استيفاء النواقص (قرارٌ إداري)", "📋"),
    "referred": ("عدم اختصاصٍ نوعي — إحالة", "↪️"), "notify_defendant": ("تبليغٌ وتحديد جلسة", "📨"),
    "defendant_plea": ("مذكرة الدفاع", "🛡️"),
    "incidents": ("الجلسة التحضيرية — الفصل في الدفوع", "⚖️"), "incident_ruling": ("حكمٌ بدفعٍ قاطع", "📑"),
    "plaintiff_plea": ("ردّ المدعي", "👤"),
    "hearing_manager": ("جلسة مرافعة", "⚖️"), "expert": ("ندب خبير", "🔬"),
    "close_pleadings": ("حجز للحكم", "🔒"), "judgment": ("النطق بالحكم", "⚖️"),
    "serve_judgment": ("تسليم الحكم", "📜"), "appeal_brief": ("اعتراض استئناف", "✋"),
    "appellee_response": ("ردّ المستأنف ضدّه", "🛡️"), "appeal_hearing": ("جلسة استئناف", "🏛️"),
    "appellate_panel": ("دائرة الاستئناف (تدقيقاً)", "👨‍⚖️"), "reconsideration": ("التماس إعادة النظر", "🔁"),
}
RAIL = ["mediation", "intake_register", "research", "notify_defendant", "defendant_plea", "plaintiff_plea",
        "incidents", "hearing_manager", "expert", "close_pleadings", "judgment", "serve_judgment",
        "appeal_brief", "appellee_response", "appeal_hearing", "appellate_panel", "reconsideration"]


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def build_state(body: dict) -> tuple[dict, str]:
    c = body.get("case") or {}
    filing = c.get("filing_date") or "2026-01-15"
    claim_text = (c.get("claim_text") or
                  "يطالب المدعي المدعى عليه بسداد قيمة المطالبة الناشئة عن العلاقة محل الدعوى رغم مطالبته.")
    claim = Document(doc_type=DocType.CLAIM_SHEET, author_role="مدعي", title="صحيفة الدعوى",
                     body=claim_text, event="قيد الدعوى", key="claim_sheet")
    state: dict = {
        "case_id": c.get("case_id") or "TC-2026-000001",
        "case_type": c.get("case_type") or "تجاري",
        "claim_subject": c.get("claim_subject") or "مطالبة مالية بموجب عقد",
        "claim_value": _f(c.get("claim_value"), 0.0),
        "parties": [Party(role="مدعي", name=c.get("plaintiff") or "المدعي", is_human=True),
                    Party(role="مدعى عليه", name=c.get("defendant") or "المدعى عليه")],
        "document_ledger": [claim],
        "scripted_plaintiff_replies": [c["plaintiff_reply"]] if c.get("plaintiff_reply") else
                                      ["أتمسّك بطلباتي وبما قدّمته من بيّنات."],
        "overrides": body.get("overrides") or {},
        "filing_date": filing, "deadlines": {},
    }
    if c.get("obligation_due_date"):
        state["obligation_due_date"] = c["obligation_due_date"]
    if c.get("appeal_requested"):
        state["appeal_requested"] = True
        if c.get("appeal_brief"):
            state["scripted_appeal_brief"] = c["appeal_brief"]
    if c.get("training"):
        # الثغرة المحقونة تُختار عشوائياً خادمياً (لا تُردَّد للعميل) — فيكون اكتشاف
        # المحامي حقيقياً لا مطابقةً مُقدَّرةً سلفاً.
        from bayyin import exploits
        state["inject_exploit"] = c.get("inject_exploit") or random.choice(sorted(exploits.SUPPORTED))
    if c.get("reconsideration"):
        state["reconsideration_requested"] = True
        state["reconsideration_ground"] = c.get("recon_ground") or "ultra_petita"
    return state, filing


def _cits(items) -> list[dict]:
    return [{"claim": c.claim, "tool": c.source_tool, "ref": c.source_ref,
             "status": getattr(c, "status", ""), "why": getattr(c, "status_reason", "")}
            for c in items]


def events_for(node: str, delta: dict, date: dict | None = None) -> list[dict]:
    evs: list[dict] = []
    if node in STAGES:
        label, icon = STAGES[node]
        evs.append({"type": "stage", "node": node, "label": label, "icon": icon, "date": date})
    for a in delta.get("audit_log", []) or []:
        evs.append({"type": "log", "actor": a.get("actor", ""), "action": a.get("action", ""),
                    "detail": a.get("detail", "") or "", "model": a.get("model", "")})
    if delta.get("research"):
        r = delta["research"]
        evs.append({"type": "research", "principles": r.get("principles", []),
                    "precedents": r.get("precedents", []),
                    "outcome_signal": r.get("outcome_signal", ""),
                    "summary": r.get("summary", "")})
    for doc in delta.get("document_ledger", []) or []:
        evs.append({"type": "document", "kind": doc.doc_type.value, "actor": doc.author_role,
                    "title": doc.title, "body": doc.body, "flag": doc.flag,
                    "node_key": doc.key, "overridden": doc.overridden, "citations": _cits(doc.citations)})
    adj = delta.get("adjudication") or {}
    for key, kind in (("judgment", "الحكم الابتدائي"), ("appeal_judgment", "الحكم النهائي القطعي")):
        r = delta.get(key)
        if r:
            evs.append({"type": "ruling", "kind": kind, "facts": r.facts, "reasons": r.reasons,
                        "operative": r.operative, "appealable": r.appealable, "route": r.appeal_route,
                        "citations": _cits(r.citations), "confidence": getattr(r, "confidence", ""),
                        "direction": getattr(r, "direction", ""), "blocked": getattr(r, "blocked", False),
                        "composition": getattr(r, "composition", ""),
                        "flags": getattr(r, "flags", []), "chain": adj.get("chain", []) if key == "judgment" else []})
    if delta.get("panel_votes"):
        evs.append({"type": "panel", "votes": [{"lens": v["lens"], "vote": v["vote"]} for v in delta["panel_votes"]]})
    if delta.get("reconsideration_outcome"):
        evs.append({"type": "outcome", "text": delta["reconsideration_outcome"]})
    return evs


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.get("/")
def index() -> HTMLResponse:
    # منع التخزين المؤقت كي يصل المستخدم أحدث إصدارٍ دائماً (لا نسخة قديمة من المتصفّح).
    return HTMLResponse((WEB / "index.html").read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-store, must-revalidate"})


@app.get("/api/config")
def get_config() -> dict:
    """الافتراضيات (النماذج والمطالبات) لتعبئة صفحة الإعدادات — لا تبدأ فارغة.
    يشمل أسباب م.200 السبعة ليختار المحامي سببَ التماسه بنفسه (تدريبٌ حقيقي)."""
    d = config.defaults()
    d["recon_grounds"] = rules.ARTICLE_200_GROUNDS
    return d


@app.post("/api/export")
async def export_ruling(request: Request) -> Response:
    """تصدير صكّ الحكم إلى ملفّ Word (DOCX) منسّقٍ بالعربية."""
    body = await request.json()
    from bayyin.export_docx import build_ruling_docx
    data = build_ruling_docx(body)
    cid = "".join(ch for ch in str((body.get("meta") or {}).get("case_id", "case"))
                  if ch.isalnum() or ch in "-_") or "case"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="bayyin-{cid}.docx"'})


@app.post("/api/run")
async def run(request: Request) -> StreamingResponse:
    body = await request.json()
    mock = int(body.get("mock", 1))
    pace = max(0.0, _f(body.get("pace"), 0.5))

    def gen():
        # تسلسل التشغيلات (لا تشغيلين معاً): الإعدادات globals — انظر تعليق _RUN_LOCK.
        if not _RUN_LOCK.acquire(blocking=False):
            yield _sse({"type": "log", "actor": "النظام", "action": "بانتظار الدور",
                        "detail": "محاكاةٌ أخرى جاريةٌ الآن — سيبدأ تشغيلك فور انتهائها.", "model": ""})
            _RUN_LOCK.acquire()
        try:
            config.apply(body.get("config"))   # مفتاح المستخدم + النماذج + المطالبات (مع تصفير الأصل)
            settings.MOCK = bool(mock)
            settings.LLM_CACHE_FRESH = bool(body.get("fresh"))  # «توليد جديد» يتجاهل التخزين
            nodes._llm.cache_clear()
            state, filing = build_state(body)
            clock = filing
            graph = build_graph()
            rail = [{"node": n, "label": STAGES[n][0], "icon": STAGES[n][1]} for n in RAIL]
            yield _sse({"type": "start", "case_id": state["case_id"], "case_type": state["case_type"],
                        "value": state["claim_value"], "mock": bool(mock),
                        "filing": timeline.fmt(timeline.parse(filing)), "rail": rail})
            appeal_days = settings.APPEAL_WINDOW_DAYS
            try:
                cfg = {"configurable": {"thread_id": state["case_id"] + "-" + str(time.monotonic())}}
                for chunk in graph.stream(state, cfg, stream_mode="updates"):
                    for node, delta in chunk.items():
                        clock, d = timeline.advance(clock, node)
                        if delta.get("appeal_window_days"):
                            appeal_days = delta["appeal_window_days"]
                        for ev in events_for(node, delta, d):
                            yield _sse(ev)
                            time.sleep(pace)
                        if node == "serve_judgment":
                            yield _sse({"type": "deadline",
                                        "label": f"مهلة الاعتراض ({appeal_days} يوماً)",
                                        "date": timeline.add_days(clock, appeal_days)})
            except Exception as e:
                yield _sse({"type": "error", "message": f"{type(e).__name__}: {str(e)[:300]}"})
            yield _sse({"type": "done"})
        finally:
            _RUN_LOCK.release()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
