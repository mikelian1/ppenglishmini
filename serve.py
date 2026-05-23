from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error as urlerror
from urllib import parse, request
import ctypes
import json
import mimetypes
import os
import socket
import sys
import webbrowser
import threading


HOST = "127.0.0.1"
PORT = 8000
DEFAULT_MODEL = "deepseek-v4-flash"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
CREDENTIAL_TARGET = "PPEnglish.DeepSeek.ApiKey"
BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"


def read_int_env(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


MAX_SOURCE_LENGTH = read_int_env("TRANSLATE_MAX_SOURCE_LENGTH", 20000)
MAX_BODY_BYTES = read_int_env("TRANSLATE_MAX_BODY_BYTES", 64 * 1024)
DEEPSEEK_TIMEOUT = read_int_env("DEEPSEEK_TIMEOUT", 60)


class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.c_uint32),
        ("dwHighDateTime", ctypes.c_uint32),
    ]


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", ctypes.c_uint32),
        ("Type", ctypes.c_uint32),
        ("TargetName", ctypes.c_wchar_p),
        ("Comment", ctypes.c_wchar_p),
        ("LastWritten", FILETIME),
        ("CredentialBlobSize", ctypes.c_uint32),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", ctypes.c_uint32),
        ("AttributeCount", ctypes.c_uint32),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", ctypes.c_wchar_p),
        ("UserName", ctypes.c_wchar_p),
    ]


PCREDENTIALW = ctypes.POINTER(CREDENTIALW)
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168


def get_advapi32():
    if os.name != "nt":
        raise RuntimeError("Windows Credential Manager 仅支持 Windows。")

    advapi32 = ctypes.WinDLL("Advapi32", use_last_error=True)
    advapi32.CredReadW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.POINTER(PCREDENTIALW),
    ]
    advapi32.CredReadW.restype = ctypes.c_bool
    advapi32.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), ctypes.c_uint32]
    advapi32.CredWriteW.restype = ctypes.c_bool
    advapi32.CredFree.argtypes = [ctypes.c_void_p]
    advapi32.CredFree.restype = None
    return advapi32


def read_env_deepseek_api_key():
    return os.environ.get("DEEPSEEK_API_KEY", "").strip()


def read_deepseek_api_key():
    env_api_key = read_env_deepseek_api_key()
    if env_api_key:
        return env_api_key

    advapi32 = get_advapi32()
    credential_ptr = PCREDENTIALW()

    if not advapi32.CredReadW(
        CREDENTIAL_TARGET,
        CRED_TYPE_GENERIC,
        0,
        ctypes.byref(credential_ptr),
    ):
        error_code = ctypes.get_last_error()
        if error_code == ERROR_NOT_FOUND:
            return ""
        raise ctypes.WinError(error_code)

    try:
        credential = credential_ptr.contents
        if not credential.CredentialBlobSize:
            return ""
        raw = ctypes.string_at(
            credential.CredentialBlob,
            credential.CredentialBlobSize,
        )
        return raw.decode("utf-16-le").strip()
    finally:
        advapi32.CredFree(credential_ptr)


def write_deepseek_api_key(api_key):
    advapi32 = get_advapi32()
    blob = api_key.encode("utf-16-le")
    blob_buffer = ctypes.create_string_buffer(blob)

    credential = CREDENTIALW()
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = CREDENTIAL_TARGET
    credential.CredentialBlobSize = len(blob)
    credential.CredentialBlob = ctypes.cast(
        blob_buffer,
        ctypes.POINTER(ctypes.c_ubyte),
    )
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = "DeepSeek API Key"

    if not advapi32.CredWriteW(ctypes.byref(credential), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def ensure_deepseek_api_key():
    try:
        if read_env_deepseek_api_key():
            print("DeepSeek API Key found in environment variable DEEPSEEK_API_KEY.")
            return 0

        if read_deepseek_api_key():
            print("DeepSeek API Key already exists in Windows Credential Manager.")
            return 0

        print("首次运行需要输入 DeepSeek API Key。")
        print("为避免双击 run.bat 时误以为无法输入，本次输入会显示在窗口中。")
        print("Key 只会保存到 Windows Credential Manager，不会写入 run.bat 或 serve.py。")
        api_key = input("请输入 DeepSeek API Key: ").strip()
        if not api_key:
            print("No API Key entered. Server was not started.")
            return 1

        write_deepseek_api_key(api_key)
        print("DeepSeek API Key saved to Windows Credential Manager.")
        return 0
    except Exception as exc:
        print(f"Credential setup failed: {exc}")
        return 1


def build_prompt(source, source_lang, target_lang, title, paragraph_count):
    context = []
    if title:
        context.append(f"文章标题：{title}")
    if isinstance(paragraph_count, int):
        context.append(f"原文段落数：{paragraph_count}")

    parts = [
        "\n".join(context) if context else "",
        "你是专业英文到中文译者。",
        f"请将下面的 {source_lang} 文本翻译成 {target_lang}。",
        "要求：保留原意，输出自然标准中文，只返回译文，不要解释。",
        "必须保留原文段落数量、段落顺序和段落结构。",
        "译文段落之间必须使用两个换行符分隔，也就是一个空白行。",
        f"译文必须正好包含 {paragraph_count} 个段落。" if paragraph_count else "",
        source,
    ]
    return "\n\n".join(part for part in parts if part)


def parse_deepseek_error(payload, status_code):
    fallback = f"DeepSeek 翻译失败（HTTP {status_code}）。"
    if not isinstance(payload, dict):
        return fallback

    err = payload.get("error")
    if not err:
        return fallback
    if isinstance(err, str):
        return err
    if isinstance(err, dict):
        return err.get("message") or err.get("code") or fallback
    return fallback


def request_deepseek(payload, api_key):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        DEEPSEEK_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with request.urlopen(req, timeout=DEEPSEEK_TIMEOUT) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urlerror.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = None
        raise RuntimeError(parse_deepseek_error(payload, exc.code)) from exc
    except (urlerror.URLError, socket.timeout, TimeoutError) as exc:
        raise RuntimeError("DeepSeek 翻译请求失败或超时，请稍后重试。") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("DeepSeek 返回了无法解析的响应。") from exc


class LocalProxyHandler(BaseHTTPRequestHandler):
    server_version = "PPEnglishLocal/1.0"

    def do_GET(self):
        if self.api_path:
            if self.path_only == "/api/translate":
                self.send_json(405, {"error": "只支持 POST /api/translate。"})
                return
            self.send_json(404, {"error": "接口不存在。"})
            return

        self.serve_static(send_body=True)

    def do_HEAD(self):
        if self.api_path:
            self.send_response(405 if self.path_only == "/api/translate" else 404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        self.serve_static(send_body=False)

    def do_POST(self):
        if self.path_only != "/api/translate":
            if self.api_path:
                self.send_json(404, {"error": "接口不存在。"})
            else:
                self.send_json(405, {"error": "该路径不支持 POST。"})
            return

        self.handle_translate()

    @property
    def path_only(self):
        return parse.urlparse(self.path).path

    @property
    def api_path(self):
        return self.path_only == "/api" or self.path_only.startswith("/api/")

    def log_message(self, format, *args):
        print("%s - - [%s] %s" % (self.address_string(), self.log_date_time_string(), format % args))

    def send_json(self, status_code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self):
        content_length = self.headers.get("Content-Length")
        if not content_length:
            return {}

        try:
            length = int(content_length)
        except ValueError as exc:
            raise ValueError("请求 Content-Length 不正确。") from exc

        if length > MAX_BODY_BYTES:
            raise ValueError("请求内容过大。")

        raw = self.rfile.read(length).decode("utf-8")
        if not raw:
            return {}

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("请求 JSON 格式不正确。") from exc

    def handle_translate(self):
        try:
            body = self.read_json_body()
        except ValueError as exc:
            self.send_json(400, {"error": str(exc) or "读取请求失败。"})
            return

        source = body.get("source", "")
        source = source.strip() if isinstance(source, str) else ""
        source_lang = body.get("sourceLang") or "en"
        target_lang = body.get("targetLang") or "zh-CN"
        title = body.get("title", "")
        title = title.strip() if isinstance(title, str) else ""
        paragraph_count = body.get("paragraphCount")
        paragraph_count = paragraph_count if isinstance(paragraph_count, int) else None

        if not source:
            self.send_json(400, {"error": "缺少要翻译的原文。"})
            return

        if len(source) > MAX_SOURCE_LENGTH:
            self.send_json(
                400,
                {"error": f"文章文本过长，请控制在 {MAX_SOURCE_LENGTH} 字符以内。"},
            )
            return

        try:
            api_key = read_deepseek_api_key()
        except Exception as exc:
            self.send_json(
                500,
                {"error": f"读取 Windows Credential Manager 失败：{exc}"},
            )
            return

        if not api_key:
            self.send_json(
                500,
                {"error": "缺少 DeepSeek API Key，请设置 DEEPSEEK_API_KEY 环境变量，或重新运行 run.bat 并按提示保存到 Windows Credential Manager。"},
            )
            return

        model = os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        prompt = build_prompt(source, source_lang, target_lang, title, paragraph_count)

        try:
            result = request_deepseek(
                {
                    "model": model,
                    "thinking": {"type": "disabled"},
                    "temperature": 0.6,
                    "stream": False,
                    "messages": [{"role": "user", "content": prompt}],
                },
                api_key,
            )
            choices = result.get("choices") or []
            first_choice = choices[0] if choices and isinstance(choices[0], dict) else {}
            message = first_choice.get("message", {})
            message = message if isinstance(message, dict) else {}
            translation = message.get("content", "")
            translation = translation.strip() if isinstance(translation, str) else ""

            if not translation:
                self.send_json(502, {"error": "DeepSeek 没有返回有效译文。"})
                return

            self.send_json(
                200,
                {
                    "provider": model,
                    "translation": translation,
                    "usage": result.get("usage"),
                },
            )
        except RuntimeError as exc:
            self.send_json(502, {"error": str(exc) or "DeepSeek 翻译失败，请稍后重试。"})

    def serve_static(self, send_body):
        if not DIST_DIR.exists():
            self.send_json(500, {"error": "未找到 dist 目录，请先生成或复制静态文件。"})
            return

        file_path = self.resolve_static_path()
        if not file_path:
            file_path = self.resolve_fallback_path()

        if not file_path:
            self.send_error(404, "File not found")
            return

        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {
            "application/javascript",
            "application/json",
        }:
            content_type += "; charset=utf-8"

        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def resolve_static_path(self):
        raw_path = parse.unquote(self.path_only).lstrip("/")
        parts = [part for part in raw_path.split("/") if part]
        if any(part in {".", ".."} for part in parts):
            return None

        candidate = DIST_DIR.joinpath(*parts) if parts else DIST_DIR / "index.html"
        if candidate.is_dir():
            candidate = candidate / "index.html"

        if candidate.is_file() and DIST_DIR in candidate.resolve().parents:
            return candidate
        return None

    def resolve_fallback_path(self):
        path = Path(self.path_only)
        wants_html = "text/html" in self.headers.get("Accept", "") or not path.suffix
        if not wants_html:
            return None

        for filename in ("200.html", "index.html"):
            candidate = DIST_DIR / filename
            if candidate.is_file():
                return candidate
        return None


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--ensure-credential":
        raise SystemExit(ensure_deepseek_api_key())

    httpd = ThreadingHTTPServer((HOST, PORT), LocalProxyHandler)
    print(f"本地服务已启动：http://localhost:{PORT}")
    threading.Timer(
        0.5,
        lambda: webbrowser.open(f"http://localhost:{PORT}")
    ).start()
    print("按 Ctrl+C 停止服务。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
