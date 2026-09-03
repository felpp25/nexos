"""Launcher do NEXOS.

    python run.py          -> sobe o servidor local e abre a janela desktop
    python run.py --web    -> apenas o servidor (abra http://127.0.0.1:8770)
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time

import uvicorn

from app.config import settings

TITLE = "NEXOS"


def _free_port(host: str, port: int) -> int:
    for candidate in range(port, port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex((host, candidate)) != 0:
                return candidate
    raise RuntimeError("Nenhuma porta livre encontrada.")


def _wait_until_up(host: str, port: int, timeout: float = 40.0) -> bool:
    """Espera a porta aceitar conexao (evita proxies do sistema)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False



def _close_splash() -> None:
    """Fecha a splash screen do executavel (existe so no build do PyInstaller)."""
    try:
        import pyi_splash  # type: ignore[import-not-found]

        pyi_splash.close()
    except Exception:  # noqa: BLE001 - fora do executavel o modulo nao existe
        pass


def _ensure_streams() -> None:
    """pythonw.exe roda sem stdout/stderr: redireciona para data/nexos.log.

    Sem isso o primeiro print (ou log do uvicorn) quebra o processo com
    AttributeError em None.write.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_path = settings.data_dir / "nexos.log"
    try:
        stream = open(log_path, "a", encoding="utf-8", buffering=1)
    except OSError:
        import os

        stream = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def _tune_window(title: str, timeout: float = 15.0) -> None:
    """Barra de titulo escura + janela ajustada a area util do monitor.

    Roda em thread separada porque a janela so existe depois de webview.start().
    Trabalha em pixels fisicos (mesmo espaco do Win32), evitando conta de DPI.
    """
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                    ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]

    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi

    deadline = time.time() + timeout
    hwnd = 0
    while time.time() < deadline and not hwnd:
        hwnd = user32.FindWindowW(None, title)
        if not hwnd:
            time.sleep(0.3)
    if not hwnd:
        return

    # 1) barra de titulo escura
    value = ctypes.c_int(1)
    for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (novo, antigo)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), ctypes.c_uint(attribute),
            ctypes.byref(value), ctypes.sizeof(value),
        )

    # 2) cabe na area util (desconta a barra de tarefas) e centraliza
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    monitor = user32.MonitorFromWindow(wintypes.HWND(hwnd), 2)  # NEAREST
    win = RECT()
    if user32.GetMonitorInfoW(monitor, ctypes.byref(info)) and user32.GetWindowRect(
        wintypes.HWND(hwnd), ctypes.byref(win)
    ):
        work_w = info.rcWork.right - info.rcWork.left
        work_h = info.rcWork.bottom - info.rcWork.top
        target_w = min(win.right - win.left, work_w - 40)
        target_h = min(win.bottom - win.top, work_h - 40)
        x = info.rcWork.left + (work_w - target_w) // 2
        y = info.rcWork.top + (work_h - target_h) // 2
        user32.SetWindowPos(hwnd, 0, x, y, target_w, target_h, 0x0004)  # SWP_NOZORDER
    else:
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0020)


def _window_size(default: tuple[int, int] = (1460, 940)) -> tuple[int, int]:
    """Tamanho da janela limitado a area util da tela (considera DPI e taskbar)."""
    width, height = default
    if sys.platform != "win32":
        return width, height
    try:
        import ctypes
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        user32 = ctypes.windll.user32
        rect = RECT()
        if not user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            return width, height
        try:
            scale = user32.GetDpiForSystem() / 96.0
        except AttributeError:
            scale = 1.0
        scale = scale or 1.0
        avail_w = int((rect.right - rect.left) / scale) - 40
        avail_h = int((rect.bottom - rect.top) / scale) - 40
        width = max(1000, min(width, avail_w))
        height = max(620, min(height, avail_h))
    except Exception:  # noqa: BLE001 - qualquer falha volta ao padrao
        return default
    return width, height


def main() -> int:
    _ensure_streams()
    parser = argparse.ArgumentParser(description="NEXOS")
    parser.add_argument("--web", action="store_true", help="nao abrir a janela desktop")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--reload", action="store_true", help="hot reload (dev)")
    args = parser.parse_args()

    host = args.host
    port = _free_port(host, args.port)
    url = f"http://{host}:{port}"

    if args.reload:
        uvicorn.run("app.main:app", host=host, port=port, reload=True)
        return 0

    from app.main import app as fastapi_app  # import direto: o PyInstaller rastreia melhor

    config = uvicorn.Config(fastapi_app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    if not _wait_until_up(host, port):
        print("Falha ao subir o servidor.", file=sys.stderr)
        return 1

    print(f"{TITLE} rodando em {url}")

    if args.web:
        try:
            while thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        return 0

    _close_splash()

    try:
        import webview
    except ImportError:
        print("pywebview nao instalado; abra no navegador:", url)
        try:
            while thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        return 0

    threading.Thread(target=_tune_window, args=(TITLE,), daemon=True).start()

    width, height = _window_size()

    webview.create_window(
        TITLE,
        url,
        width=width,
        height=height,
        min_size=(1080, 660),
        background_color="#0f1012",
        text_select=True,
    )
    webview.start()
    server.should_exit = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
