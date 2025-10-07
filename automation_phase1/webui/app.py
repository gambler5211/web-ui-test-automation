from __future__ import annotations

import io
import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Callable, Iterable, Optional
from urllib.parse import parse_qs, urlencode

from ..compiler import Compiler


@dataclass
class CompileContext:
    feature_text: str = ""
    scenario_name: str = ""
    base_url: str = ""
    use_llm: bool = False
    llm_model: str = "gpt-4o-mini"
    scenario_json: Optional[str] = None
    provenance_json: Optional[str] = None
    error: Optional[str] = None


class _Response:
    def __init__(self, status: str, headers: list[tuple[str, str]], body: bytes):
        self.status = status
        self.headers = headers
        self.body = body

    @property
    def status_code(self) -> int:
        return int(self.status.split()[0])

    @property
    def data(self) -> bytes:
        return self.body


class _TestClient:
    def __init__(self, app: "MiniApp"):
        self.app = app

    def open(self, path: str, method: str = "GET", data: Optional[dict[str, str]] = None) -> _Response:
        body_bytes = b""
        content_type = "text/plain"
        if method.upper() == "POST" and data is not None:
            body_bytes = urlencode(data, doseq=True).encode("utf-8")
            content_type = "application/x-www-form-urlencoded"

        environ = {
            "REQUEST_METHOD": method.upper(),
            "PATH_INFO": path,
            "SERVER_NAME": "testserver",
            "SERVER_PORT": "80",
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": "http",
            "wsgi.input": io.BytesIO(body_bytes),
            "wsgi.errors": io.StringIO(),
            "wsgi.multithread": False,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
            "CONTENT_LENGTH": str(len(body_bytes)),
            "CONTENT_TYPE": content_type,
            "QUERY_STRING": "",
        }

        captured: dict[str, object] = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> Callable[[bytes], None]:
            captured["status"] = status
            captured["headers"] = headers

            def write(_: bytes) -> None:
                return None

            return write

        body_iter = self.app(environ, start_response)
        body = b"".join(body_iter)
        status = captured.get("status", "500 Internal Server Error")  # type: ignore[arg-type]
        headers = captured.get("headers", [])  # type: ignore[arg-type]
        return _Response(status=status, headers=headers, body=body)

    def get(self, path: str) -> _Response:
        return self.open(path, method="GET")

    def post(self, path: str, data: dict[str, str]) -> _Response:
        return self.open(path, method="POST", data=data)


class MiniApp:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.styles = (base_dir / "static" / "styles.css").read_text(encoding="utf-8")

    def test_client(self) -> _TestClient:
        return _TestClient(self)

    def __call__(self, environ, start_response) -> Iterable[bytes]:  # type: ignore[override]
        path = environ.get("PATH_INFO", "/")
        method = environ.get("REQUEST_METHOD", "GET").upper()

        if path == "/static/styles.css":
            body = self.styles.encode("utf-8")
            start_response("200 OK", [("Content-Type", "text/css; charset=utf-8"), ("Content-Length", str(len(body)))])
            return [body]

        if path != "/":
            body = b"Not Found"
            start_response("404 Not Found", [("Content-Type", "text/plain"), ("Content-Length", str(len(body)))])
            return [body]

        ctx = CompileContext()
        if method == "POST":
            length = int(environ.get("CONTENT_LENGTH") or 0)
            raw = environ.get("wsgi.input").read(length) if length else b""
            form = parse_qs(raw.decode("utf-8"))
            ctx.feature_text = form.get("feature_text", [""])[0]
            ctx.scenario_name = form.get("scenario_name", [""])[0]
            ctx.base_url = form.get("base_url", [""])[0]
            ctx.use_llm = "use_llm" in form
            ctx.llm_model = (form.get("llm_model", [ctx.llm_model])[0] or ctx.llm_model).strip() or ctx.llm_model

            if not ctx.feature_text.strip():
                ctx.error = "Feature text is required."
            else:
                compiler = Compiler(use_llm=ctx.use_llm, model=ctx.llm_model)
                try:
                    result = compiler.compile_text(
                        feature_text=ctx.feature_text,
                        scenario_name=ctx.scenario_name or None,
                        base_url=ctx.base_url or None,
                    )
                    ctx.scenario_json = json.dumps(
                        result.scenario.model_dump(exclude_none=True),
                        indent=2,
                    )
                    ctx.provenance_json = json.dumps(
                        [p.model_dump(exclude_none=True) for p in result.provenance],
                        indent=2,
                    )
                except Exception as exc:  # noqa: BLE001
                    ctx.error = str(exc)

        body_str = _render_page(ctx)
        body = body_str.encode("utf-8")
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))])
        return [body]


def _render_page(ctx: CompileContext) -> str:
    feature_text = escape(ctx.feature_text)
    scenario_name = escape(ctx.scenario_name)
    base_url = escape(ctx.base_url)
    llm_model = escape(ctx.llm_model)
    checkbox_attr = " checked" if ctx.use_llm else ""

    error_html = (
        f'<div class="alert alert-error" role="alert"><strong>Compilation failed:</strong> {escape(ctx.error or "")}</div>'
        if ctx.error
        else ""
    )

    results_html = ""
    if ctx.scenario_json:
        results_html = (
            "<div class=\"results\">"
            "<h2>Scenario JSON</h2>"
            f"<pre><code>{escape(ctx.scenario_json)}</code></pre>"
            "<h2>Provenance</h2>"
            f"<pre><code>{escape(ctx.provenance_json or '')}</code></pre>"
            "</div>"
        )

    return f"""
<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Automation Phase 1 — Web UI</title>
  <link rel=\"stylesheet\" href=\"/static/styles.css\">
</head>
<body>
  <header>
    <h1>Automation Phase 1</h1>
    <p>Compile Gherkin feature files to Playwright-ready scenarios without leaving your browser.</p>
  </header>
  <main>
    <section class=\"card\">
      <form method=\"post\" novalidate>
        <div class=\"field\">
          <label for=\"feature_text\">Gherkin feature</label>
          <textarea id=\"feature_text\" name=\"feature_text\" rows=\"12\" placeholder=\"Paste your .feature content here...\">{feature_text}</textarea>
        </div>
        <div class=\"field-grid\">
          <div class=\"field\">
            <label for=\"scenario_name\">Scenario name</label>
            <input id=\"scenario_name\" name=\"scenario_name\" type=\"text\" value=\"{scenario_name}\" placeholder=\"Defaults to first scenario\">
          </div>
          <div class=\"field\">
            <label for=\"base_url\">Base URL override</label>
            <input id=\"base_url\" name=\"base_url\" type=\"text\" value=\"{base_url}\" placeholder=\"https://example.com\">
          </div>
        </div>
        <fieldset class=\"field-grid\">
          <legend>Compiler options</legend>
          <label class=\"checkbox\">
            <input type=\"checkbox\" name=\"use_llm\"{checkbox_attr}>
            Enable LLM fallback (requires API keys in environment)
          </label>
          <div class=\"field\">
            <label for=\"llm_model\">LLM model</label>
            <input id=\"llm_model\" name=\"llm_model\" type=\"text\" value=\"{llm_model}\">
          </div>
        </fieldset>
        <button type=\"submit\" class=\"primary\">Compile feature</button>
      </form>
      {error_html}
      {results_html}
    </section>
  </main>
  <footer>
    <p>Need the CLI? Run <code>python -m automation_phase1.cli --help</code>.</p>
  </footer>
</body>
</html>
"""


def create_app() -> MiniApp:
    base_dir = Path(__file__).resolve().parent
    return MiniApp(base_dir)


__all__ = ["create_app", "MiniApp"]
