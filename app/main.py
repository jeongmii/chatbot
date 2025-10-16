from __future__ import annotations
import asyncio
import json
import math
import time
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.responses import HTMLResponse, Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import SessionLocal, engine
from .models import Base, ChatSession, Message
from .openai_client import create_chat_completion

from sqlalchemy.orm import Session
from sqlalchemy import select, func

settings = get_settings()

app = FastAPI(title="Toss-like Chat UI with ChatGPT")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB init
Base.metadata.create_all(bind=engine)


# NOTE: We mount static later to avoid intercepting WebSocket/API routes


# Dependency
async def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def _ensure_session(db: Session, *, session_id: Optional[str], participant_id: Optional[str], study_id: Optional[str], system_prompt: Optional[str], model: Optional[str], user_agent: Optional[str], ip_address: Optional[str], source: Optional[str], meta_json: Optional[str]) -> ChatSession:
    if session_id:
        chat_session = db.get(ChatSession, session_id)
        if chat_session:
            # update metadata if provided
            changed = False
            if participant_id and chat_session.participant_id != participant_id:
                chat_session.participant_id = participant_id; changed = True
            if study_id and chat_session.study_id != study_id:
                chat_session.study_id = study_id; changed = True
            if system_prompt and chat_session.system_prompt != system_prompt:
                chat_session.system_prompt = system_prompt; changed = True
            if model and chat_session.model != model:
                chat_session.model = model; changed = True
            if user_agent and chat_session.user_agent != user_agent:
                chat_session.user_agent = user_agent; changed = True
            if ip_address and chat_session.ip_address != ip_address:
                chat_session.ip_address = ip_address; changed = True
            if source and chat_session.source != source:
                chat_session.source = source; changed = True
            if meta_json and chat_session.meta_json != meta_json:
                chat_session.meta_json = meta_json; changed = True
            if changed:
                db.add(chat_session)
                db.commit()
                db.refresh(chat_session)
            return chat_session

    # create new session
    chat_session = ChatSession(
        participant_id=participant_id,
        study_id=study_id,
        system_prompt=system_prompt,
        model=model or settings.openai_model,
        user_agent=user_agent,
        ip_address=ip_address,
        source=source,
        meta_json=meta_json,
    )
    db.add(chat_session)
    db.commit()
    db.refresh(chat_session)
    return chat_session


async def _get_next_sequence(db: Session, session_id: str) -> int:
    max_seq = db.execute(select(func.max(Message.sequence)).where(Message.session_id == session_id)).scalar()
    if max_seq is None:
        return 1
    return int(max_seq) + 1


async def _load_history(db: Session, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
    stmt = select(Message).where(Message.session_id == session_id).order_by(Message.created_at.asc(), Message.sequence.asc())
    rows = db.execute(stmt).scalars().all()
    history = [
        {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat() if hasattr(m.created_at, "isoformat") else None}
        for m in rows[-limit:]
    ]
    return history


def _chunk_text(text: str, size: int = 24) -> List[str]:
    if size <= 0:
        return [text]
    return [text[i:i+size] for i in range(0, len(text), size)]


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"ok": True}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("frontend/index.html")


def _parse_iso8601(dt_str: Optional[str]):
    if not dt_str:
        return None
    from datetime import datetime
    try:
        # Support both with and without timezone suffix
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None


@app.get("/export/sessions")
async def export_sessions(
    db: Session = Depends(get_db),
    study_id: Optional[str] = Query(default=None),
    pid: Optional[str] = Query(default=None, alias="participant_id"),
    since: Optional[str] = Query(default=None, description="ISO8601 start datetime"),
    until: Optional[str] = Query(default=None, description="ISO8601 end datetime"),
):
    from io import StringIO
    import csv
    from sqlalchemy import and_

    stmt = select(ChatSession)
    where_clauses = []
    if study_id:
        where_clauses.append(ChatSession.study_id == study_id)
    if pid:
        where_clauses.append(ChatSession.participant_id == pid)
    dt_since = _parse_iso8601(since)
    dt_until = _parse_iso8601(until)
    if dt_since is not None:
        where_clauses.append(ChatSession.created_at >= dt_since)
    if dt_until is not None:
        where_clauses.append(ChatSession.created_at <= dt_until)
    if where_clauses:
        stmt = stmt.where(and_(*where_clauses))
    stmt = stmt.order_by(ChatSession.created_at.asc())

    rows = db.execute(stmt).scalars().all()
    sio = StringIO()
    writer = csv.writer(sio)
    writer.writerow([
        "id",
        "created_at",
        "updated_at",
        "participant_id",
        "study_id",
        "source",
        "system_prompt",
        "model",
        "user_agent",
        "ip_address",
        "meta_json",
    ])
    for r in rows:
        writer.writerow([
            r.id,
            r.created_at,
            r.updated_at,
            r.participant_id,
            r.study_id,
            r.source,
            r.system_prompt,
            r.model,
            r.user_agent,
            r.ip_address,
            r.meta_json,
        ])
    return Response(content=sio.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=sessions.csv"})


@app.get("/export/messages")
async def export_messages(
    db: Session = Depends(get_db),
    session_id: Optional[str] = Query(default=None),
    study_id: Optional[str] = Query(default=None),
    pid: Optional[str] = Query(default=None, alias="participant_id"),
    since: Optional[str] = Query(default=None, description="ISO8601 start datetime"),
    until: Optional[str] = Query(default=None, description="ISO8601 end datetime"),
):
    from io import StringIO
    import csv
    from sqlalchemy import and_

    # Base query
    stmt = select(Message)
    joined_sessions = False

    # Filters
    if session_id:
        stmt = stmt.where(Message.session_id == session_id)
    if study_id or pid:
        stmt = stmt.join(ChatSession, Message.session_id == ChatSession.id)
        joined_sessions = True
        if study_id:
            stmt = stmt.where(ChatSession.study_id == study_id)
        if pid:
            stmt = stmt.where(ChatSession.participant_id == pid)

    dt_since = _parse_iso8601(since)
    dt_until = _parse_iso8601(until)
    if dt_since is not None:
        stmt = stmt.where(Message.created_at >= dt_since)
    if dt_until is not None:
        stmt = stmt.where(Message.created_at <= dt_until)

    stmt = stmt.order_by(Message.created_at.asc(), Message.sequence.asc())

    rows = db.execute(stmt).scalars().all()
    sio = StringIO()
    writer = csv.writer(sio)
    writer.writerow([
        "id",
        "created_at",
        "session_id",
        "sequence",
        "role",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "latency_ms",
        "content",
    ])
    for m in rows:
        writer.writerow([
            m.id,
            m.created_at,
            m.session_id,
            m.sequence,
            m.role,
            m.model,
            m.prompt_tokens,
            m.completion_tokens,
            m.total_tokens,
            m.latency_ms,
            m.content,
        ])
    return Response(content=sio.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=messages.csv"})


@app.websocket("/ws/chat")
async def ws_chat(
    websocket: WebSocket,
    db: Session = Depends(get_db),
):
    await websocket.accept()
    try:
        qp = websocket.query_params
        participant_id = qp.get("pid")
        session_id = qp.get("sid")
        study_id = qp.get("study_id")
        source = qp.get("source", "qualtrics_iframe")
        model = qp.get("model")
        system_prompt = qp.get("sys")
        meta = qp.get("meta")  # optional JSON string
        user_agent = websocket.headers.get("user-agent")
        ip_address = websocket.client.host if websocket.client else None

        chat_session = await _ensure_session(
            db,
            session_id=session_id,
            participant_id=participant_id,
            study_id=study_id,
            system_prompt=system_prompt,
            model=model,
            user_agent=user_agent,
            ip_address=ip_address,
            source=source,
            meta_json=meta,
        )

        # notify client of session
        await websocket.send_json({
            "type": "session_info",
            "session_id": chat_session.id,
            "participant_id": chat_session.participant_id,
            "study_id": chat_session.study_id,
            "model": chat_session.model,
        })

        # send history
        history = await _load_history(db, chat_session.id, limit=100)
        if history:
            await websocket.send_json({"type": "history", "messages": history})

        # main loop
        while True:
            incoming = await websocket.receive_json()
            t = incoming.get("type")

            if t == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if t == "user_message":
                content = (incoming.get("content") or "").strip()
                if not content:
                    await websocket.send_json({"type": "error", "message": "Empty message"})
                    continue

                # persist user message
                seq = await _get_next_sequence(db, chat_session.id)
                user_msg = Message(
                    session_id=chat_session.id,
                    role="user",
                    content=content,
                    sequence=seq,
                    model=None,
                )
                db.add(user_msg)
                db.commit()
                db.refresh(user_msg)

                # build conversation for OpenAI
                messages: List[Dict[str, str]] = []
                if chat_session.system_prompt:
                    messages.append({"role": "system", "content": chat_session.system_prompt})
                # include full history (could be optimized)
                prior = await _load_history(db, chat_session.id, limit=100)
                for m in prior:
                    if m["role"] in ("system", "user", "assistant"):
                        messages.append({"role": m["role"], "content": m["content"]})
                messages.append({"role": "user", "content": content})

                # call OpenAI (sync under the hood, using executor)
                start_ns = time.perf_counter_ns()
                try:
                    completion = await create_chat_completion(messages, model=chat_session.model)
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": f"OpenAI error: {e}"})
                    continue
                latency_ms = int((time.perf_counter_ns() - start_ns) / 1_000_000)

                assistant_text = completion.choices[0].message.content or ""
                usage = getattr(completion, "usage", None)
                prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
                completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
                total_tokens = getattr(usage, "total_tokens", None) if usage else None
                finish_reason = completion.choices[0].finish_reason

                # stream to client in small chunks for smooth UI
                for chunk in _chunk_text(assistant_text, size=24):
                    await websocket.send_json({"type": "assistant_delta", "delta": chunk})
                    await asyncio.sleep(0.01)
                await websocket.send_json({
                    "type": "assistant_complete",
                    "finish_reason": finish_reason,
                    "usage": {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    },
                    "latency_ms": latency_ms,
                })

                # persist assistant message
                seq = await _get_next_sequence(db, chat_session.id)
                asst_msg = Message(
                    session_id=chat_session.id,
                    role="assistant",
                    content=assistant_text,
                    sequence=seq,
                    model=chat_session.model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    latency_ms=latency_ms,
                )
                db.add(asst_msg)
                db.commit()

            else:
                await websocket.send_json({"type": "error", "message": f"Unknown message type: {t}"})

    except WebSocketDisconnect:
        return


# Serve frontend (mounted last to avoid intercepting API/WS routes)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
