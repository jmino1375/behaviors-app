import asyncio
import json
import os
import re
from typing import Literal

import anthropic
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

app = FastAPI()

# ── State ──────────────────────────────────────────────────────────────────
behaviors: dict[str, list[str]] = {"above": [], "below": []}
categories: dict[str, list] = {"above": [], "below": []}
clients: list[WebSocket] = []


# ── WebSocket broadcast ────────────────────────────────────────────────────
async def broadcast(msg: dict):
    dead = []
    for ws in clients:
        try:
            await ws.send_text(json.dumps(msg))
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.remove(ws)


# ── WebSocket endpoint ─────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.append(ws)
    # Send current state to new client
    await ws.send_text(json.dumps({
        "type": "state",
        "behaviors": behaviors,
        "categories": categories,
    }))
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "submit":
                kind = msg.get("kind")  # "above" or "below"
                text = (msg.get("text") or "").strip()[:500]
                if kind in ("above", "below") and text:
                    behaviors[kind].append(text)
                    await broadcast({"type": "new_behavior", "kind": kind, "text": text})
    except WebSocketDisconnect:
        clients.remove(ws)


# ── Categorize endpoint ────────────────────────────────────────────────────
@app.post("/categorize")
async def categorize_behaviors():
    above_list = "\n".join(f"{i+1}. {b}" for i, b in enumerate(behaviors["above"])) or "(ninguno)"
    below_list = "\n".join(f"{i+1}. {b}" for i, b in enumerate(behaviors["below"])) or "(ninguno)"

    prompt = f"""Analiza los siguientes comportamientos y agrúpalos en categorías temáticas comunes. Responde ÚNICAMENTE con JSON válido.

COMPORTAMIENTOS SOBRE LA LÍNEA:
{above_list}

COMPORTAMIENTOS BAJO LA LÍNEA:
{below_list}

Responde con este formato JSON exacto:
{{
  "above": [
    {{ "category": "Nombre de categoría", "items": ["comportamiento 1", "comportamiento 2"] }}
  ],
  "below": [
    {{ "category": "Nombre de categoría", "items": ["comportamiento 1", "comportamiento 2"] }}
  ]
}}

Reglas:
- Agrupa comportamientos similares o relacionados bajo una misma categoría
- Los nombres de categoría deben ser descriptivos y en español
- Cada comportamiento debe aparecer en exactamente una categoría
- Si no hay comportamientos en un tipo, devuelve array vacío"""

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text.strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return {"error": "No JSON found in response"}

    global categories
    categories = json.loads(match.group())
    await broadcast({"type": "categories_updated", "categories": categories})
    return {"success": True, "categories": categories}


# ── Static files ───────────────────────────────────────────────────────────
app.mount("/", StaticFiles(directory="public", html=True), name="static")


# ── Run ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 3000))
    uvicorn.run(app, host="0.0.0.0", port=port)
