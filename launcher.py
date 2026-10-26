# -*- coding: utf-8 -*-
"""专升本 · 章节学习 —— 桌面版启动器
- 内嵌 HTTP 服务（读取打包进 exe 的 app 资源，或源码 App 目录）
- pywebview 打开窗口
- 同一 WiFi 下手机可访问 http://<本机IP>:<端口>/index.html
用法：
  python launcher.py             # 常规启动（窗口）
  python launcher.py --serve     # 只起服务不弹窗（调试/手机访问用）
  python launcher.py --selftest  # 起窗口 6 秒后自动关闭（自检用）
"""
import os
import sys
import socket
import json
import base64
import tempfile
import threading
import time
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


_ocr = None


_RAPID_OCR = None


def _prep_img(data):
    """OCR 前图片预处理：放大至长边≥1600 + CLAHE 对比度增强 + 轻度锐化。
    对手写作文（尤其潦草小字）识别率提升明显；失败时返回 None，由调用方回退原图。"""
    try:
        import numpy as np
        import cv2
        arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            return None
        g = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        h, w = g.shape
        scale = max(1.0, 1600.0 / max(h, w))
        if scale > 1.0:
            g = cv2.resize(g, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        g = clahe.apply(g)
        blur = cv2.GaussianBlur(g, (0, 0), 1.5)
        g = cv2.addWeighted(g, 1.3, blur, -0.3, 0)
        fd, p2 = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        cv2.imwrite(p2, g)
        return p2
    except Exception:
        return None


def _ocr_text_rapid(b64img):
    """本地离线 OCR（RapidOCR / PP-OCRv4 onnx，GitHub 开源，14k+ star）：
    对中文、英文及手写作文识别能力强于系统自带 OCR；全离线、免实名、免服务器。
    英文行内空格被引擎替换为下划线，识别后还原。"""
    global _RAPID_OCR
    try:
        if _RAPID_OCR is None:
            from rapidocr_onnxruntime import RapidOCR
            _RAPID_OCR = RapidOCR()
        data = base64.b64decode(b64img)
        fd, p = tempfile.mkstemp(suffix=".png")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        p2 = _prep_img(data)  # 预处理增强，失败回退原图
        try:
            result, _ = _RAPID_OCR(p2 if p2 else p)
            if not result:
                return ""
            lines = [str(r[1]).replace("_", " ") for r in result]
            return "\n".join(lines).strip()
        finally:
            try:
                os.remove(p)
            except Exception:
                pass
            if p2:
                try:
                    os.remove(p2)
                except Exception:
                    pass
    except Exception as e:
        return "__RAPID_ERR__" + str(e)[:200]


def _ocr_text_winrt(b64img):
    """本地 OCR（Windows 自带 Windows.Media.Ocr，零体积、离线、免实名）：
    识别照片里的作文文字；中文系统直接可用，无需下载任何组件。"""
    import asyncio
    import re as _re
    import winrt.windows.media.ocr as ocr
    import winrt.windows.storage as storage
    import winrt.windows.globalization as glo
    import winrt.windows.graphics.imaging as img

    async def _run():
        langs = ocr.OcrEngine.available_recognizer_languages
        names = [str(l.language_tag) for l in langs]
        tag = next((n for n in names if n.lower().startswith("zh")), names[0] if names else None)
        if not tag:
            return "__NO_LANG__"
        eng = ocr.OcrEngine.try_create_from_language(glo.Language(tag))
        if eng is None:
            eng = ocr.OcrEngine.try_create_from_user_profile_languages()
        if eng is None:
            return "__NO_ENGINE__"
        data = base64.b64decode(b64img)
        fd, p = tempfile.mkstemp(suffix=".png")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        try:
            file = await storage.StorageFile.get_file_from_path_async(p)
            stream = await file.open_async(storage.FileAccessMode.READ)
            dec = await img.BitmapDecoder.create_async(stream)
            bmp = await dec.get_software_bitmap_async()
            result = await eng.recognize_async(bmp)
            text = "\n".join(line.text for line in result.lines)
            # 清理 WinRT 中文识别产生的字间空格（中文字符之间的空白删除，英文单词间的保留）
            text = _re.sub(
                r"(?<=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef])\s+(?=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef])",
                "", text,
            )
            return text.strip()
        finally:
            try:
                os.remove(p)
            except Exception:
                pass

    try:
        return asyncio.run(_run())
    except Exception:
        return ""


def _ocr_text(b64img):
    """本地 OCR 总入口：优先 RapidOCR（PP-OCRv4，手写/印刷中英文均强），
    引擎不可用时自动降级系统自带 Windows.Media.Ocr（WinRT，零体积）。"""
    t = _ocr_text_rapid(b64img)
    if t:
        return t
    return _ocr_text_winrt(b64img)


def _ai_score(provider, key, user_prompt):
    """转发到用户配置的 AI API（DeepSeek / 通义千问）做深度作文评分。免服务器：直接调用官方接口。"""
    import urllib.request
    if provider == "deepseek":
        url = "https://api.deepseek.com/chat/completions"
        model = "deepseek-chat"
    else:
        url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        model = "qwen-turbo"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": user_prompt}],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def base_dir():
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, "app")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "App")


def prog_dir():
    """进度备份目录（必须固定，绝不落在 exe 临时解压目录）：
    1) exe：与 专升本章节学习.exe 同目录的 progress（固定、用户可见）
    2) 源码运行：项目根 progress
    3) 均不可写时退回 AppData 专升本章节学习\\progress"""
    if hasattr(sys, "_MEIPASS"):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates = [
            os.path.join(exe_dir, "progress"),
            os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "专升本章节学习", "progress"),
        ]
    else:
        candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "progress"),
            os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "专升本章节学习", "progress"),
        ]
    for c in candidates:
        try:
            os.makedirs(c, exist_ok=True)
            with open(os.path.join(c, ".probe"), "w", encoding="utf-8") as f:
                f.write("1")
            os.remove(os.path.join(c, ".probe"))
            return c
        except Exception:
            continue
    return os.path.join(os.environ.get("TEMP") or ".", "zsb_progress")


def user_data_dir():
    """pywebview 的 WebView2 用户数据目录默认为 %APPDATA%\\pywebview（固定，
    不随 exe 解压临时目录变化），localStorage 天然持久。此函数仅作说明保留。"""
    return None


def find_port():
    """优先固定端口 41731（保证 localStorage 同源不失效），被占用才随机"""
    for p in (41731,):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("0.0.0.0", p))
            s.close()
            return p
        except Exception:
            continue
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("0.0.0.0", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def webview2_ok():
    """检测微软 WebView2 Runtime 是否已安装（注册表 + 文件兜底）"""
    try:
        import winreg
        for hive, path in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"),
        ]:
            try:
                with winreg.OpenKey(hive, path) as k:
                    winreg.QueryValueEx(k, "pv")
                    return True
            except OSError:
                continue
    except Exception:
        pass
    for base in [os.environ.get("ProgramFiles(x86)") or "", os.environ.get("LocalAppData") or "", os.environ.get("ProgramFiles") or ""]:
        p = os.path.join(base, "Microsoft", "EdgeWebView", "Application")
        if os.path.isdir(p) and any(os.path.isdir(os.path.join(p, d)) for d in os.listdir(p)):
            return True
    return False


def _msgbox(title, text):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x40)
    except Exception:
        pass


def ensure_webview2():
    """WebView2 Runtime 缺失时：弹窗引导安装微软官方组件（不需要任何电脑管家/第三方软件）"""
    if webview2_ok():
        return
    _msgbox("缺少运行组件（不是软件坏了）",
            "本软件要用微软官方的 WebView2 组件显示内容，你电脑上还没装这个组件。\n\n"
            "注意：不需要下载任何电脑管家或第三方软件，只用微软官方免费组件即可。\n\n"
            "下一步会自动打开微软官网下载页，下载后双击安装（默认下一步，一两分钟装完），\n"
            "再重新打开本软件就能正常用了。")
    try:
        import webbrowser
        webbrowser.open("https://go.microsoft.com/fwlink/p/?LinkId=2124703")
    except Exception:
        pass
    _msgbox("请安装后重新打开",
            "微软官方 WebView2 下载页已帮你打开。\n\n"
            "如果页面没有自动打开，请手动访问：\nhttps://go.microsoft.com/fwlink/p/?LinkId=2124703\n\n"
            "装完（默认下一步即可）后，关闭并重新打开本软件。")
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    port = find_port()
    root = base_dir()

    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=root, **k)

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            try:
                data = body if isinstance(body, bytes) else body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype + ("; charset=utf-8" if "charset" not in ctype else ""))
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                pass

        def do_GET(self):
            if self.path.startswith("/api/load/"):
                k = self.path[len("/api/load/"):]
                p = os.path.join(prog_dir(), "{}.json".format(k.replace("/", "_")))
                if os.path.isfile(p):
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            self._send(200, f.read())
                        return
                    except Exception:
                        pass
                self._send(200, "null")
                return
            return super().do_GET()

        def do_POST(self):
            if self.path == "/api/save":
                try:
                    n = int(self.headers.get("Content-Length", "0"))
                    body = self.rfile.read(n) if n else b""
                    obj = json.loads(body.decode("utf-8"))
                    k = obj.get("k", "")
                    v = obj.get("v")
                    if k and v is not None:
                        p = os.path.join(prog_dir(), "{}.json".format(k.replace("/", "_")))
                        with open(p, "w", encoding="utf-8") as f:
                            json.dump(v, f, ensure_ascii=False)
                        self._send(200, '{"ok":true}')
                        return
                except Exception:
                    pass
                self._send(200, '{"ok":false}')
                return
            if self.path == "/api/ocr":
                try:
                    n = int(self.headers.get("Content-Length", "0"))
                    body = self.rfile.read(n) if n else b""
                    obj = json.loads(body.decode("utf-8"))
                    txt = _ocr_text(obj.get("img", ""))
                    self._send(200, json.dumps({"ok": True, "text": txt}, ensure_ascii=False))
                except Exception as e:
                    self._send(200, json.dumps({"ok": False, "err": str(e)}, ensure_ascii=False))
                return
            if self.path == "/api/ai":
                try:
                    n = int(self.headers.get("Content-Length", "0"))
                    body = self.rfile.read(n) if n else b""
                    obj = json.loads(body.decode("utf-8"))
                    reply = _ai_score(obj.get("provider", "deepseek"), obj.get("key", ""), obj.get("prompt", ""))
                    self._send(200, json.dumps({"ok": True, "reply": reply}, ensure_ascii=False))
                except Exception as e:
                    self._send(200, json.dumps({"ok": False, "err": str(e)}, ensure_ascii=False))
                return
            self._send(404, '{"ok":false}')

    srv = ThreadingHTTPServer(("0.0.0.0", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    local_url = "http://127.0.0.1:{}/index.html".format(port)
    mobile_url = "http://{}:{}/index.html".format(lan_ip(), port)

    if args.serve:
        print("LOCAL=" + local_url)
        print("MOBILE=" + mobile_url)
        try:
            temp = os.environ.get("TEMP") or os.environ.get("TMP") or os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(temp, "zsb_serve.txt"), "w", encoding="utf-8") as f:
                f.write(local_url + "\n" + mobile_url)
        except Exception:
            pass
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        srv.shutdown()
        return

    # 桌面窗口模式：先确保 WebView2 运行组件存在（不存在则引导装官方组件，不依赖电脑管家）
    ensure_webview2()

    import webview

    class Api:
        def exit(self):
            try:
                for w in webview.windows:
                    w.destroy()
            except Exception:
                pass

    if args.selftest:
        def close_soon():
            for _ in range(20):
                time.sleep(1)
                try:
                    webview.destroy_window()
                    time.sleep(2)
                    os._exit(0)
                except Exception:
                    continue
            os._exit(0)

        threading.Thread(target=close_soon, daemon=True).start()

    webview.create_window(
        "专升本 · 章节学习（按顺序学 · 自动记进度）",
        local_url,
        width=1200,
        height=820,
        min_size=(960, 640),
        js_api=Api(),
    )
    webview.start(private_mode=False)
    srv.shutdown()


if __name__ == "__main__":
    main()
