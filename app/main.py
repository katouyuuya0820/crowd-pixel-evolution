"""HIEC ゲームのサーバー。学生は / 、管理画面は /server（このPCからのみ）、リザルトは /result。"""

from __future__ import annotations

import io
import json
import os
import socket
from pathlib import Path

import qrcode
import qrcode.image.svg
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .state import Game

STATIC = Path(__file__).resolve().parent.parent / "static"
PORT = int(os.environ.get("HIEC_PORT", "8000"))
# 別のPCから管理画面を開きたい時だけ HIEC_ADMIN_OPEN=1 で起動する
ADMIN_OPEN = os.environ.get("HIEC_ADMIN_OPEN") == "1"

app = FastAPI(title="HIEC")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
game = Game()


# ---------- WebSocket ----------
class Hub:
    def __init__(self) -> None:
        self.sockets: set[WebSocket] = set()

    async def send_all(self, msg: dict) -> None:
        text = json.dumps(msg, ensure_ascii=False)
        dead = []
        for ws in self.sockets:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.sockets.discard(ws)


hub = Hub()


async def broadcast(kind: str) -> None:
    """kind: "vote"（票数のみ）/ "gen"（世代が変わった）/ "config"（お題・設定）"""
    await hub.send_all({"type": kind, "summary": game.summary()})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    hub.sockets.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "hello", "summary": game.summary()}, ensure_ascii=False))
        while True:
            await ws.receive_text()  # クライアントからは使わない（接続維持のみ）
    except WebSocketDisconnect:
        pass
    finally:
        hub.sockets.discard(ws)


# ---------- 管理者の判定 ----------
PROXY_HEADERS = ("cf-connecting-ip", "x-forwarded-for", "forwarded")


def is_admin(request: Request) -> bool:
    if ADMIN_OPEN:
        return True
    # トンネル（cloudflared 等）経由のアクセスは送信元が 127.0.0.1 に見えるので、転送ヘッダーで除外する
    if any(h in request.headers for h in PROXY_HEADERS):
        return False
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost")


def require_admin(request: Request) -> None:
    if not is_admin(request):
        raise HTTPException(403, "管理画面はサーバーのPCからのみ使えます")


# ---------- 画面 ----------
@app.get("/")
async def page_client() -> FileResponse:
    return FileResponse(STATIC / "client.html")


@app.get("/server")
async def page_server(request: Request) -> FileResponse:
    require_admin(request)
    return FileResponse(STATIC / "server.html")


@app.get("/result")
async def page_result() -> FileResponse:
    return FileResponse(STATIC / "result.html")


@app.get("/best")
async def page_best() -> FileResponse:
    return FileResponse(STATIC / "best.html")


# ---------- 学生用 API ----------
class VoteIn(BaseModel):
    client_id: str = Field(min_length=1, max_length=64)
    gen: int
    winner: str
    shown: list[str] = Field(min_length=2, max_length=40)


@app.get("/api/set")
async def api_set(client_id: str) -> dict:
    return game.set_for(client_id[:64])


@app.post("/api/vote")
async def api_vote(v: VoteIn) -> dict:
    res = game.vote(v.client_id, v.gen, v.winner, v.shown)
    if res["accepted"]:
        await broadcast("gen" if res["advanced"] else "vote")
    return res


@app.get("/api/summary")
async def api_summary() -> dict:
    return game.summary()


@app.get("/api/best")
async def api_best() -> dict:
    """いまの集団で評価が一番高い個体の遺伝子だけ（お題は返さない）"""
    best = game.pop.ranked()
    return {"gen": game.pop.gen, "genome": best[0]["genome"] if best else None}


@app.get("/api/history")
async def api_history() -> dict:
    return {"summary": game.summary(), "history": game.history,
            "current": game.admin_state()["population"][:4]}


# ---------- 管理用 API ----------
class TopicIn(BaseModel):
    topic: str = Field(max_length=100)


class ThresholdIn(BaseModel):
    threshold: int = Field(ge=1, le=10000)


class ResetIn(BaseModel):
    size: int = Field(default=18, ge=4, le=40)
    threshold: int | None = Field(default=None, ge=1, le=10000)
    res: int = Field(default=16, ge=4, le=64)
    k: int = Field(default=9, ge=2, le=16)
    palette: str = Field(default="color8", pattern="^(color8|gray4|mono2)$")


@app.get("/api/admin/state")
async def api_admin_state(request: Request) -> dict:
    require_admin(request)
    return game.admin_state()


@app.post("/api/admin/topic")
async def api_topic(t: TopicIn, request: Request) -> dict:
    require_admin(request)
    game.set_topic(t.topic)
    await broadcast("config")
    return game.summary()


@app.post("/api/admin/threshold")
async def api_threshold(t: ThresholdIn, request: Request) -> dict:
    require_admin(request)
    game.set_threshold(t.threshold)
    if game.gen_votes >= game.threshold:
        game.advance()
        await broadcast("gen")
    else:
        await broadcast("config")
    return game.summary()


@app.post("/api/admin/advance")
async def api_advance(request: Request) -> dict:
    require_admin(request)
    game.advance()
    await broadcast("gen")
    return game.summary()


@app.post("/api/admin/reset")
async def api_reset(r: ResetIn, request: Request) -> dict:
    require_admin(request)
    game.reset(size=r.size, threshold=r.threshold, res=r.res, k=r.k, palette=r.palette)
    await broadcast("gen")
    return game.summary()


# ---------- 参加用URL・QR ----------
def lan_ips() -> list[str]:
    ips: list[str] = []
    try:  # 既定の経路のIP（実際には送信しない）
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except OSError:
        pass
    return ips


@app.get("/api/admin/join")
async def api_join(request: Request) -> dict:
    require_admin(request)
    return {"urls": [f"http://{ip}:{PORT}/" for ip in lan_ips()]}


@app.get("/api/admin/qr.svg")
async def api_qr(url: str, request: Request) -> Response:
    require_admin(request)
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml")
