import os, csv
from uuid import uuid4
from datetime import datetime
import gradio as gr
from dotenv import load_dotenv

# ─────────────────────────────────────────
# 환경 변수
# ─────────────────────────────────────────
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL_ID = os.getenv("MODEL_ID", "ft:gpt-4o-mini-2024-07-18:personal:eliva-abstract:CRZmoXCj")
USE_DUMMY_DEFAULT = os.getenv("USE_DUMMY", "false").lower() in ("1", "true", "yes")

# ─────────────────────────────────────────
# SYSTEM_PERSONA / SYSTEM_TOOL_SOP 불러오기
# ─────────────────────────────────────────
SYSTEM_PERSONA = ""
if os.path.exists("system_persona.txt"):
    with open("system_persona.txt", "r", encoding="utf-8") as f:
        SYSTEM_PERSONA = f.read().strip()

SYSTEM_TOOL_SOP = ""
if os.path.exists("system_sop.txt"):
    with open("system_sop.txt", "r", encoding="utf-8") as f:
        SYSTEM_TOOL_SOP = f.read().strip()

# ─────────────────────────────────────────
# Tool 정의 (select_strategy) ← Responses API 표준 구조
# ─────────────────────────────────────────
tools = [
    {
        "type": "function",
        "name": "select_strategy",
        "description": (
            "Analyze the user's message in Korean to understand intent and concerns. "
            "Generate 5–12 concise Korean persuasive strategy candidates (each 2–6 words, no emojis or numbering), "
            "and choose one as `chosen_strategy`. "
            "Return all three fields: `analysis`, `strategy_candidates`, and `chosen_strategy`."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": "A Korean sentence analyzing the user's intent and concerns."
                },
                "strategy_candidates": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "A list of 5–12 concise Korean strategy candidates (each 2–6 words, no emojis or numbering)."
                },
                "chosen_strategy": {
                    "type": "string",
                    "description": "The name of the selected final strategy (in Korean)."
                }
            },
            "required": ["analysis", "strategy_candidates", "chosen_strategy"]
        },
    }
]

# ─────────────────────────────────────────
# 스타일
# ─────────────────────────────────────────
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');
body, div, p, textarea, input, button {
    font-family: 'Noto Sans KR', sans-serif !important;
    color: black !important;
    font-size: 14px !important;
}
.message { max-width: 85% !important; color: black !important; font-size: 14px !important; animation: none !important; transition: none !important; }
.message.user { margin-left:auto; background:#F0F0F0!important; border:1px solid #E0E0E0!important; border-radius:18px 18px 4px 18px!important; position:relative; max-width:40%!important; min-width:160px; }
.message.bot  { margin-right:auto; background:#E3F2FD!important; border:1px solid #BBDEFB!important; border-radius:18px 18px 18px 4px!important; position:relative; }
.message.user::after { content:""; position:absolute; right:-8px; top:14px; border-width:8px; border-style:solid; border-color:transparent transparent transparent #F0F0F0; }
.message.bot::after  { content:""; position:absolute; left:-8px; top:14px; border-width:8px; border-style:solid; border-color:transparent #E3F2FD transparent transparent; }
.message.bot::before { content:"Eliva"; position:absolute; top:-22px; left:5px; font-size:13px; font-weight:600; color:black!important; opacity:0.9; }
#chatbot-wrapper { position: relative; }
@media (max-width:720px){ .message.user{max-width:60%!important;} .message.bot{max-width:90%!important;} }
"""

# ─────────────────────────────────────────
# 히스토리 정제(Responses API 호환): role/content 외 키 제거 + content를 문자열화
# ─────────────────────────────────────────
def _coerce_text(content):
    """content가 str이 아니어도 안전하게 텍스트로 변환"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                if "text" in c and isinstance(c["text"], str):
                    parts.append(c["text"])
                elif "content" in c and isinstance(c["content"], str):
                    parts.append(c["content"])
                else:
                    parts.append(str(c))
            else:
                parts.append(str(c))
        return "\n".join(parts)
    if isinstance(content, dict):
        if "text" in content and isinstance(content["text"], str):
            return content["text"]
        return str(content)
    return str(content)

def _sanitize_history(history_messages):
    """각 항목에서 role/content만 남기고 나머지 키 제거 + content를 문자열화"""
    sanitized = []
    for m in history_messages or []:
        role = m.get("role", "user")
        content = _coerce_text(m.get("content", ""))
        sanitized.append({"role": role, "content": content})
    return sanitized

# ─────────────────────────────────────────
# 더미 / 실제 응답
# ─────────────────────────────────────────
def mock_reply(user_text: str, cond: str) -> str:
    if (cond or "").upper() == "A":
        pool = [
            "좋은 질문이에요 😊 DUNO는 지속 가능한 이동을 지향합니다.",
            "배터리 보증은 8년 또는 16만 km예요. 오랜 시간 안심하고 타실 수 있어요.",
            "당신의 일상에 어울리는 편안함, 그게 DUNO의 가치예요 🌿",
        ]
    else:
        pool = [
            "배터리 보증은 8년 또는 16만 km입니다. 내구성 테스트 데이터도 확보되어 있습니다.",
            "DUNO는 효율/안정 중심 설계이며, 충방전 관리로 성능 저하를 억제합니다.",
            "질문 감사합니다. 관련 수치와 근거를 기준으로 설명드릴게요.",
        ]
    return pool[hash(user_text) % len(pool)]

def live_reply(history_messages: list[dict], user_text: str) -> str:
    if not OPENAI_API_KEY:
        return "[오류] OPENAI_API_KEY가 설정되지 않았습니다. 관리자에게 문의해 주세요."
    if not MODEL_ID:
        return "[오류] MODEL_ID가 설정되지 않았습니다. 관리자에게 문의해 주세요."

    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    # 1) system + sop
    messages = []
    if SYSTEM_PERSONA:
        messages.append({"role": "system", "content": SYSTEM_PERSONA})
    else:
        messages.append({"role": "system", "content": "Answer only in Korean (5–250 words). Follow Eliva persona and ELSIO DUNO policy."})
    if SYSTEM_TOOL_SOP:
        messages.append({"role": "system", "content": SYSTEM_TOOL_SOP})

    # 2) 과거 히스토리 정제
    messages += _sanitize_history(history_messages)

    # 3) 사용자 입력
    messages.append({"role": "user", "content": _coerce_text(user_text)})

    try:
        # ── 1차 호출: 필요 시 툴 호출 발생
        resp = client.responses.create(
            model=MODEL_ID,
            input=messages,
            tools=tools,
            tool_choice="auto",
        )

        # 응답 내 tool call 감지
        tool_calls = []
        for item in getattr(resp, "output", []) or []:
            if getattr(item, "type", "") == "tool_call":
                # Responses API는 평탄한 구조 사용
                name = getattr(item, "name", "")
                arguments = getattr(item, "arguments", "")
                call_id = getattr(item, "id", "")
                if name and call_id:
                    tool_calls.append({"id": call_id, "name": name, "arguments": arguments})

        # tool call이 없으면 직접 텍스트 응답 반환
        if not tool_calls:
            output_text = getattr(resp, "output_text", None)
            if output_text:
                return output_text
            # 디버깅용
            print(f"[DEBUG] 1차 응답에 tool_call도 output_text도 없음. resp.output: {getattr(resp, 'output', None)}")
            return "[오류] 모델 응답이 비어 있습니다."

        # ── 툴 결과 만들어서(여기선 모의 OK) tool 메시지를 붙여 2차 호출
        # 실제로 툴을 실행하려면 여기서 arguments를 파싱해 처리한 뒤 결과를 content에 넣으면 됩니다.
        
        # 먼저 assistant의 tool_call을 히스토리에 추가
        # FIXED: Responses API requires empty content field for tool calls
        messages.append({
            "role": "assistant",
            "content": "",  # This was missing - Responses API requires this
            "tool_calls": [{
                "id": tc["id"],
                "type": "function",
                "name": tc["name"],
                "arguments": tc["arguments"]
            } for tc in tool_calls]
        })
        
        # 그 다음 tool 응답 추가
        for tc in tool_calls:
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": "OK",  # 우리의 툴 SFT가 'OK'만 기대하므로 그대로 사용
            })

        # 2차 호출: 최종 답변 생성
        resp2 = client.responses.create(
            model=MODEL_ID,
            input=messages,
        )
        
        # 디버깅용 (나중에 제거 가능)
        output_text = resp2.output_text or ""
        if not output_text:
            print(f"[DEBUG] 2차 응답 비어있음. resp2.output: {getattr(resp2, 'output', None)}")
            print(f"[DEBUG] Messages sent to 2nd call: {messages}")
        
        return output_text or "[오류] 최종 응답이 비어 있습니다."

    except Exception as e:
        print(f"[ERROR] live_reply 예외 발생: {e}")
        return f"[오류 발생] {e}"

# ─────────────────────────────────────────
# 로깅
# ─────────────────────────────────────────
def ensure_logs(): os.makedirs("logs", exist_ok=True)

def save_turn(sid, pid, cond, role, text):
    ensure_logs()
    path = f"logs/{sid}_chatlogs.csv"
    write_header = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["timestamp", "session_id", "participant_id", "condition", "role", "message"])
        w.writerow([datetime.now().isoformat(), sid, pid, cond, role, text])

def save_full(sid, pid, cond, history_messages: list[dict]):
    ensure_logs()
    path = f"logs/{sid}_full_conversation.csv"
    write_header = not os.path.exists(path)
    transcript = "\n".join(f"{'User' if m['role']=='user' else 'Eliva'}: {m['content']}" for m in history_messages)
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["timestamp", "session_id", "participant_id", "condition", "conversation"])
        w.writerow([datetime.now().isoformat(), sid, pid, cond, transcript])

# ─────────────────────────────────────────
# 초기 로드 (빈 히스토리 + 모드 결정)
# ─────────────────────────────────────────
def on_load(request: gr.Request):
    pid = (request.query_params.get("pid") or "").strip()
    cond = (request.query_params.get("cond") or "").strip()
    mode_param = (request.query_params.get("mode") or "").strip().lower()
    if mode_param in ("live", "dummy"):
        use_dummy = (mode_param == "dummy")
    else:
        use_dummy = USE_DUMMY_DEFAULT

    sid = datetime.now().strftime("%Y%m%d_%H%M%S") + "-" + uuid4().hex[:6]
    header = []
    if pid or cond:
        header.append(f"**ResponseID:** {pid or '-'}  |  **Condition:** {cond or '-'}")
    header.append(f"**Mode:** {'DUMMY' if use_dummy else 'LIVE'}")
    header_md = "  |  ".join(header)

    history = []  # 초기 인사 제거
    return gr.update(value=header_md), history, pid, cond, sid, use_dummy

# ─────────────────────────────────────────
# 응답 + 배경 숨김
# ─────────────────────────────────────────
def respond(user_text, history: list[dict], pid, cond, sid, use_dummy):
    if not user_text:
        return history, pid, cond, sid, use_dummy

    # 사용자 메시지 추가 + 저장
    history = history + [{"role": "user", "content": user_text}]
    save_turn(sid, pid or "NA", cond or "NA", "user", user_text)

    # 답변 생성
    answer = mock_reply(user_text, cond) if use_dummy else live_reply(history, user_text)

    # 어시스턴트 메시지 추가 + 저장
    history = history + [{"role": "assistant", "content": answer}]
    save_turn(sid, pid or "NA", cond or "NA", "assistant", answer)
    save_full(sid, pid or "NA", cond or "NA", history)
    return history, pid, cond, sid, use_dummy

def respond_and_hide_bg(user_text, history, pid, cond, sid, use_dummy):
    history, pid, cond, sid, use_dummy = respond(user_text, history, pid, cond, sid, use_dummy)
    return history, pid, cond, sid, use_dummy, gr.update(visible=False)

# ─────────────────────────────────────────
# Gradio UI
# ─────────────────────────────────────────
with gr.Blocks(css=CSS, theme=gr.themes.Soft()) as demo:
    gr.Markdown("## 🔵 Eliva")
    header_md = gr.Markdown("", elem_id="headerbar")

    # Chatbot (Gradio 버전 호환)
    try:
        chatbot = gr.Chatbot(label="", height=520, type="messages", elem_id="chatbot")
    except TypeError:
        chatbot = gr.Chatbot(label="", height=520, elem_id="chatbot")

    # 채팅박스 안의 배경 오버레이
    with gr.Group(elem_id="chatbot-wrapper"):
        empty_bg = gr.HTML(
            """
            <div id="chatbot-bg" style="
                position: absolute;
                top: 120px; left: 0; right: 0;
                text-align: center;
                z-index: 0; pointer-events: none;
                color: #333333; font-family: 'Noto Sans KR', sans-serif;">
                <div style="width: 80px; height: 80px;
                    background: radial-gradient(circle at center, #1E88E5 40%, #E3F2FD 100%);
                    border-radius: 50%; margin: 0 auto 25px auto;">
                </div>
                <div style="font-size: 22px; font-weight: 700;">
                    Eliva와 대화를 시작하세요!
                </div>
            </div>
            """,
        )

    pid_s = gr.State("")
    cond_s = gr.State("")
    session_s = gr.State("")
    use_dummy_s = gr.State(USE_DUMMY_DEFAULT)

    txt = gr.Textbox(
        placeholder="Eliva에게 메시지를 입력하세요... (Enter로 입력)",
        show_label=False,
        scale=9,
    )

    # 초기 로드
    demo.load(on_load, None, [header_md, chatbot, pid_s, cond_s, session_s, use_dummy_s])

    # 첫 입력 → 응답 + 배경 숨김
    txt.submit(
        fn=respond_and_hide_bg,
        inputs=[txt, chatbot, pid_s, cond_s, session_s, use_dummy_s],
        outputs=[chatbot, pid_s, cond_s, session_s, use_dummy_s, empty_bg],
    )

    # 전송 후 입력창 비우기
    def clear_box(): return gr.update(value="")
    txt.submit(clear_box, None, [txt])

if __name__ == "__main__":
    # 공개 링크 필요시 share=True
    demo.launch(server_name="0.0.0.0", server_port=7860, share=True)