#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "fastapi>=0.115.0",
#   "uvicorn>=0.30.0",
#   "httpx>=0.27.0",
# ]
# ///

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

HOST = os.environ.get("TESTRUN_UI_HOST", "0.0.0.0")
PORT = int(os.environ.get("TESTRUN_UI_PORT", "9988"))
DEFAULT_TARGET_DMS_URL = "http://localhost:8002"

SCRIPT_DIR = Path(__file__).resolve().parent
UPLOAD_SCRIPT = SCRIPT_DIR / "upload_testrun.sh"
UPLOADS_DIR = SCRIPT_DIR / "uploads"
DOCUMENT_TYPES_JSON = SCRIPT_DIR / "document_types.json"
RUN_LOCK = asyncio.Lock()


@dataclass
class RunResult:
    scenario_key: str
    scenario_label: str
    limit: int | None
    all_files: bool
    command: str
    exit_code: int
    ok: bool
    output: str
    payload: str
    timestamp: str


class RunRequest(BaseModel):
    limit: int | None = Field(default=10, ge=1)
    all_files: bool = False


class SelectedFile(BaseModel):
    id: str
    filename: str


class RunSelectedRequest(BaseModel):
    selected_files: list[SelectedFile] = Field(..., min_length=1)


app = FastAPI(title="Testrun UI")


HTML_PAGE = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Testrun UI</title>
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
    <style>
      :root {{
        --bg: #f5f2ea;
        --panel: #fffaf0;
        --ink: #1f1a16;
        --muted: #6b6259;
        --line: #d8cdbf;
        --accent: #b2492e;
        --accent-2: #234f41;
        --warn: #8a2d1d;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(178, 73, 46, 0.18), transparent 30%),
          radial-gradient(circle at top right, rgba(35, 79, 65, 0.16), transparent 28%),
          linear-gradient(180deg, #f8f3ea 0%, var(--bg) 100%);
      }}
      .shell {{
        max-width: 1200px;
        margin: 0 auto;
        padding: 32px 20px 56px;
      }}
      .hero {{
        padding: 28px;
        border: 1px solid var(--line);
        border-radius: 24px;
        background: rgba(255, 250, 240, 0.88);
        backdrop-filter: blur(6px);
        box-shadow: 0 20px 60px rgba(66, 45, 27, 0.08);
      }}
      h1 {{
        margin: 0 0 8px;
        font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
        font-size: clamp(1.8rem, 4vw, 3rem);
        letter-spacing: -0.04em;
      }}
      .sub {{
        margin: 0;
        color: var(--muted);
        max-width: 70ch;
      }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 18px;
        margin-top: 24px;
      }}
      .card {{
        border: 1px solid var(--line);
        border-radius: 18px;
        background: var(--panel);
        padding: 18px;
      }}
      .field {{
        display: grid;
        gap: 8px;
        margin-bottom: 16px;
      }}
      label {{
        font-size: 0.95rem;
        font-weight: 700;
      }}
      input[type="text"], input[type="number"], textarea {{
        width: 100%;
        border: 1px solid #c7b8a5;
        border-radius: 12px;
        padding: 12px 14px;
        background: #fffefb;
        color: var(--ink);
        font: inherit;
      }}
      textarea {{
        min-height: 220px;
        resize: vertical;
        font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
        font-size: 0.92rem;
      }}
      .scenario-buttons {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-bottom: 16px;
      }}
      .scenario-buttons button, .run-btn {{
        appearance: none;
        border: 1px solid var(--ink);
        border-radius: 999px;
        padding: 10px 16px;
        background: transparent;
        color: var(--ink);
        cursor: pointer;
        font: inherit;
        transition: transform 120ms ease, background 120ms ease, color 120ms ease;
      }}
      .scenario-buttons button.active {{
        background: var(--ink);
        color: #fff7ef;
      }}
      .scenario-buttons button:hover, .run-btn:hover {{
        transform: translateY(-1px);
      }}
      .run-btn {{
        background: var(--accent);
        color: #fff7ef;
        border-color: var(--accent);
        width: 100%;
        font-weight: 700;
      }}
      .toggle {{
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 16px;
      }}
      .meta {{
        font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
        font-size: 0.9rem;
        color: var(--muted);
      }}
      .status {{
        padding: 12px 14px;
        border-radius: 14px;
        background: rgba(35, 79, 65, 0.08);
        color: var(--accent-2);
        font-weight: 700;
      }}
      .status.error {{
        background: rgba(138, 45, 29, 0.10);
        color: var(--warn);
      }}
      .history {{
        margin-top: 24px;
        display: grid;
        gap: 14px;
      }}
      details {{
        border: 1px solid var(--line);
        border-radius: 18px;
        background: rgba(255, 250, 240, 0.82);
        overflow: hidden;
      }}
      summary {{
        list-style: none;
        cursor: pointer;
        padding: 18px 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
      }}
      summary::-webkit-details-marker {{ display: none; }}
      .scenario-title {{
        font-weight: 800;
      }}
      .scenario-meta {{
        color: var(--muted);
        font-size: 0.92rem;
      }}
      .details-body {{
        padding: 0 20px 20px;
        display: grid;
        gap: 18px;
      }}
      .run-card {{
        border-top: 1px solid var(--line);
        padding-top: 18px;
        display: grid;
        gap: 10px;
      }}
      .pill {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        border-radius: 999px;
        padding: 6px 10px;
        background: rgba(35, 79, 65, 0.10);
        color: var(--accent-2);
        width: fit-content;
        font-size: 0.86rem;
        font-weight: 700;
      }}
      .pill.fail {{
        background: rgba(138, 45, 29, 0.10);
        color: var(--warn);
      }}
      .empty {{
        color: var(--muted);
        font-style: italic;
      }}
      .dialog-overlay {{
        position: fixed;
        inset: 0;
        z-index: 1000;
        background: rgba(31, 26, 22, 0.5);
        backdrop-filter: blur(4px);
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 24px;
      }}
      .dialog {{
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 24px;
        box-shadow: 0 30px 80px rgba(66, 45, 27, 0.2);
        width: 100%;
        max-width: 960px;
        max-height: 90vh;
        display: flex;
        flex-direction: column;
        overflow: hidden;
      }}
      .dialog-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 20px 24px;
        border-bottom: 1px solid var(--line);
        flex-shrink: 0;
      }}
      .dialog-header h2 {{ margin: 0; font-size: 1.2rem; }}
      .dialog-close {{
        appearance: none;
        border: none;
        background: none;
        font-size: 1.4rem;
        cursor: pointer;
        color: var(--muted);
        padding: 4px 8px;
        border-radius: 8px;
      }}
      .dialog-close:hover {{ background: rgba(0,0,0,0.06); }}
      .file-toolbar {{
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 14px 24px;
        border-bottom: 1px solid var(--line);
        flex-wrap: wrap;
        flex-shrink: 0;
      }}
      .file-toolbar button {{
        appearance: none;
        border: 1px solid var(--line);
        border-radius: 999px;
        padding: 6px 12px;
        background: transparent;
        color: var(--ink);
        cursor: pointer;
        font: inherit;
        font-size: 0.88rem;
      }}
      .file-toolbar button:hover {{ background: rgba(0,0,0,0.04); }}
      .file-toolbar .count {{
        margin-left: auto;
        font-size: 0.88rem;
        color: var(--muted);
        font-weight: 700;
      }}
      .file-list {{
        flex: 1;
        overflow-y: auto;
        min-height: 0;
      }}
      .file-row {{
        display: flex;
        align-items: flex-start;
        gap: 10px;
        padding: 10px 24px;
        font-size: 0.9rem;
        border-bottom: 1px solid rgba(0,0,0,0.04);
        cursor: pointer;
      }}
      .file-row:last-child {{ border-bottom: none; }}
      .file-row:nth-child(even) {{ background: rgba(0,0,0,0.015); }}
      .file-row:hover {{ background: rgba(178, 73, 46, 0.06); }}
      .file-row input[type="checkbox"] {{ flex-shrink: 0; margin-top: 2px; }}
      .file-row .fname {{
        flex: 1;
        word-break: break-all;
        font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
        font-size: 0.82rem;
        line-height: 1.4;
      }}
      .dialog-footer {{
        display: flex;
        gap: 10px;
        padding: 16px 24px;
        border-top: 1px solid var(--line);
        flex-shrink: 0;
      }}
      .run-selected-btn {{
        appearance: none;
        border: 1px solid var(--accent-2);
        border-radius: 999px;
        padding: 10px 20px;
        background: var(--accent-2);
        color: #fff7ef;
        cursor: pointer;
        font: inherit;
        font-weight: 700;
        flex: 1;
        transition: transform 120ms ease;
      }}
      .run-selected-btn:hover {{ transform: translateY(-1px); }}
      .cancel-btn {{
        appearance: none;
        border: 1px solid var(--line);
        border-radius: 999px;
        padding: 10px 20px;
        background: transparent;
        color: var(--ink);
        cursor: pointer;
        font: inherit;
      }}
      .cancel-btn:hover {{ background: rgba(0,0,0,0.04); }}
      @media (max-width: 700px) {{
        .shell {{ padding: 20px 14px 32px; }}
        .hero {{ padding: 20px; border-radius: 20px; }}
        summary {{ flex-direction: column; align-items: flex-start; }}
      }}
    </style>
  </head>
  <body>
    <div class="shell" x-data="testrunApp()">
      <section class="hero">
        <h1>Testrun Control</h1>
        <p class="sub">
          Runs <code>upload_testrun.sh</code> on this machine, always with <code>--yes</code>,
          and keeps per-scenario results in this browser's local storage.
        </p>

        <div class="grid">
          <section class="card">
            <div class="field">
              <button class="run-btn" type="button" style="background:var(--accent-2);border-color:var(--accent-2)"
                @click="listFiles()" :disabled="fileListLoading || running">
                <span x-show="!fileListLoading">List Files</span>
                <span x-show="fileListLoading">Loading...</span>
              </button>
            </div>

            <template x-if="fileListError">
              <div class="status error" x-text="fileListError"></div>
            </template>

            <div class="toggle">
              <input id="all-files" type="checkbox" x-model="form.all_files">
              <label for="all-files">All files</label>
            </div>

            <div class="field">
              <label for="limit">Custom limit</label>
              <input id="limit" type="number" min="1" step="1" x-model.number="form.limit" :disabled="form.all_files">
            </div>

            <button class="run-btn" type="button" @click="runScenario()" :disabled="running">
              <span x-show="!running">Run testrun</span>
              <span x-show="running">Running...</span>
            </button>
          </section>

          <section class="card">
            <div class="meta">Backend</div>
            <p class="meta">Uploads: <code>scripts/uploads/</code></p>
            <p class="meta">Target DMS: {DEFAULT_TARGET_DMS_URL}</p>
            <p class="meta">Server origin: <span x-text="window.location.origin"></span></p>
            <div class="status" :class="{{ error: status.type === 'error' }}" x-text="status.message"></div>
          </section>
        </div>
      </section>

      <template x-if="showFileDialog">
        <div class="dialog-overlay" @click.self="showFileDialog = false">
          <div class="dialog">
            <div class="dialog-header">
              <h2 x-text="`${{fileList.length}} files in uploads/`"></h2>
              <button class="dialog-close" @click="showFileDialog = false">&times;</button>
            </div>
            <div class="file-toolbar">
              <button type="button" @click="fileList.forEach(f => f.selected = true)">Select All</button>
              <button type="button" @click="fileList.forEach(f => f.selected = false)">Deselect All</button>
              <span class="count" x-text="`${{fileList.filter(f => f.selected).length}} / ${{fileList.length}} selected`"></span>
            </div>
            <div class="file-list">
              <template x-for="file in fileList" :key="file.id">
                <label class="file-row">
                  <input type="checkbox" x-model="file.selected">
                  <span class="fname" x-text="file.filename"></span>
                </label>
              </template>
            </div>
            <div class="dialog-footer">
              <button class="cancel-btn" type="button" @click="showFileDialog = false">Cancel</button>
              <button class="run-selected-btn" type="button"
                @click="runSelected()" :disabled="running || !fileList.filter(f => f.selected).length">
                <span x-show="!running" x-text="`Upload ${{fileList.filter(f => f.selected).length}} selected`"></span>
                <span x-show="running">Uploading...</span>
              </button>
            </div>
          </div>
        </div>
      </template>

      <section class="history">
        <template x-for="scenario in scenarioEntries()" :key="scenario.key">
          <details :open="scenario.open">
            <summary>
              <div>
                <div class="scenario-title" x-text="scenario.label"></div>
                <div class="scenario-meta" x-text="scenarioSummary(scenario)"></div>
              </div>
              <div class="scenario-meta" x-text="scenario.runs.length ? `${{scenario.runs.length}} run(s)` : 'no runs yet'"></div>
            </summary>
            <div class="details-body">
              <template x-if="!scenario.runs.length">
                <div class="empty">No stored result for this scenario yet.</div>
              </template>
              <template x-for="run in scenario.runs" :key="run.timestamp + run.command">
                <article class="run-card">
                  <div class="pill" :class="{{ fail: !run.ok }}">
                    <span x-text="run.ok ? 'success' : 'failed'"></span>
                    <span x-text="`exit ${{run.exit_code}}`"></span>
                  </div>
                  <div class="meta" x-text="`${{formatTimestamp(run.timestamp)}} · ${{run.command}}`"></div>
                  <div class="field">
                    <label>Terminal output</label>
                    <textarea readonly x-text="run.output"></textarea>
                  </div>
                  <div class="field">
                    <label>Payload JSON</label>
                    <textarea readonly x-text="run.payload"></textarea>
                  </div>
                </article>
              </template>
            </div>
          </details>
        </template>
      </section>
    </div>

    <script>
      function testrunApp() {{
        return {{
          storageKey: 'testrun-ui-history-v1',
          form: {{
            limit: 10,
            all_files: false,
          }},
          status: {{
            type: 'info',
            message: 'Ready.',
          }},
          history: {{}},
          running: false,
          fileList: [],
          fileListLoading: false,
          fileListError: '',
          showFileDialog: false,
          init() {{
            this.loadHistory();
          }},
          formScenarioKey() {{
            if (this.form.all_files) return 'all';
            return `limit-${{this.form.limit ?? ''}}`;
          }},
          scenarioEntries() {{
            return Object.entries(this.history)
              .sort((a, b) => a[0].localeCompare(b[0]))
              .map(([key, value]) => ({{
                key,
                label: value.label,
                limit: value.limit,
                all_files: value.all_files,
                runs: value.runs ?? [],
                open: key === this.formScenarioKey(),
              }}));
          }},
          scenarioSummary(scenario) {{
            if (scenario.all_files) return 'uses all files';
            return `limit=${{scenario.limit}}`;
          }},
          loadHistory() {{
            try {{
              this.history = JSON.parse(localStorage.getItem(this.storageKey) || '{{}}');
            }} catch (_err) {{
              this.history = {{}};
            }}
          }},
          saveHistory() {{
            localStorage.setItem(this.storageKey, JSON.stringify(this.history));
          }},
          formatTimestamp(value) {{
            return new Date(value).toLocaleString();
          }},
          remember(result) {{
            const key = result.scenario_key;
            if (!this.history[key]) {{
              this.history[key] = {{
                label: result.scenario_label,
                limit: result.limit,
                all_files: result.all_files,
                runs: [],
              }};
            }}
            this.history[key].label = result.scenario_label;
            this.history[key].limit = result.limit;
            this.history[key].all_files = result.all_files;
            this.history[key].runs.unshift(result);
            this.saveHistory();
          }},
          async runScenario() {{
            if (this.running) return;
            if (!this.form.all_files && (!this.form.limit || this.form.limit < 1)) {{
              this.status = {{ type: 'error', message: 'Limit must be at least 1 unless "All files" is enabled.' }};
              return;
            }}

            this.running = true;
            this.status = {{ type: 'info', message: 'Running testrun script...' }};

            try {{
              const response = await fetch('/api/run', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                  limit: this.form.all_files ? null : this.form.limit,
                  all_files: this.form.all_files,
                }}),
              }});
              const data = await response.json();
              if (!response.ok) {{
                throw new Error(data.detail || 'Request failed.');
              }}
              this.remember(data);
              this.status = {{
                type: data.ok ? 'info' : 'error',
                message: data.ok
                  ? `Finished ${{data.scenario_label}} at ${{this.formatTimestamp(data.timestamp)}}.`
                  : `Run failed for ${{data.scenario_label}} with exit code ${{data.exit_code}}.`,
              }};
            }} catch (error) {{
              this.status = {{ type: 'error', message: error.message || 'Run failed.' }};
            }} finally {{
              this.running = false;
            }}
          }},
          async listFiles() {{
            this.fileListLoading = true;
            this.fileListError = '';
            this.fileList = [];
            try {{
              const resp = await fetch('/api/files');
              if (!resp.ok) {{
                const err = await resp.json().catch(() => ({{}}));
                throw new Error(err.detail || `HTTP ${{resp.status}}`);
              }}
              this.fileList = (await resp.json()).map(f => ({{...f, selected: true}}));
              this.showFileDialog = true;
            }} catch (e) {{
              this.fileListError = e.message || 'Failed to list files.';
            }} finally {{
              this.fileListLoading = false;
            }}
          }},
          async runSelected() {{
            const selected = this.fileList.filter(f => f.selected);
            if (!selected.length) {{
              this.status = {{ type: 'error', message: 'No files selected.' }};
              return;
            }}
            this.running = true;
            this.status = {{ type: 'info', message: `Uploading ${{selected.length}} selected files...` }};
            try {{
              const resp = await fetch('/api/run-selected', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                  selected_files: selected.map(f => ({{ id: f.id, filename: f.filename }})),
                }}),
              }});
              const data = await resp.json();
              if (!resp.ok) throw new Error(data.detail || 'Request failed.');
              this.remember(data);
              this.showFileDialog = false;
              this.status = {{
                type: data.ok ? 'info' : 'error',
                message: data.ok
                  ? `Uploaded ${{selected.length}} files at ${{this.formatTimestamp(data.timestamp)}}.`
                  : `Upload failed with exit code ${{data.exit_code}}.`,
              }};
            }} catch (e) {{
              this.status = {{ type: 'error', message: e.message || 'Run failed.' }};
            }} finally {{
              this.running = false;
            }}
          }},
        }};
      }}
    </script>
  </body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(HTML_PAGE)


@app.post("/api/run")
async def run_testrun(request: RunRequest) -> dict:
    if not UPLOAD_SCRIPT.exists():
        raise HTTPException(status_code=500, detail=f"Missing script: {UPLOAD_SCRIPT}")

    if not request.all_files and (request.limit is None or request.limit < 1):
        raise HTTPException(status_code=400, detail="Limit must be >= 1 unless all_files is true.")

    limit = None if request.all_files else request.limit

    scenario = "all" if request.all_files else f"limit-{limit}"
    label = "All files" if request.all_files else f"{limit} files"
    timestamp = datetime.now(UTC).isoformat()

    fd, payload_path_raw = tempfile.mkstemp(prefix="testrun-ui-", suffix=".json")
    os.close(fd)
    payload_path = Path(payload_path_raw)

    command = [str(UPLOAD_SCRIPT), "--yes"]
    if limit is not None:
        command.extend(["--limit", str(limit)])
    command.append(str(payload_path))

    env = os.environ.copy()
    env.setdefault("TARGET_DMS_URL", DEFAULT_TARGET_DMS_URL)

    try:
        async with RUN_LOCK:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(SCRIPT_DIR),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await process.communicate()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    output = stdout.decode("utf-8", errors="replace")
    payload = payload_path.read_text(encoding="utf-8") if payload_path.exists() else ""
    payload_path.unlink(missing_ok=True)

    return asdict(
        RunResult(
            scenario_key=scenario,
            scenario_label=label,
            limit=limit,
            all_files=request.all_files,
            command=" ".join(command),
            exit_code=process.returncode,
            ok=process.returncode == 0,
            output=output,
            payload=payload,
            timestamp=timestamp,
        )
    )


@app.get("/api/files")
async def list_local_files() -> list[dict[str, str]]:
    if not UPLOADS_DIR.is_dir():
        raise HTTPException(status_code=500, detail=f"Uploads directory not found: {UPLOADS_DIR}")
    return [
        {"id": (rel := str(p.relative_to(UPLOADS_DIR))), "filename": rel}
        for p in sorted(UPLOADS_DIR.rglob("*"))
        if p.is_file() and p.name != ".gitkeep"
    ]


async def _upload_file(
    client: httpx.AsyncClient,
    target_dms: str,
    new_project: str,
    filename: str,
    local_path: Path,
) -> str:
    """Upload a file to target DMS and return the new file ID."""
    payload = {"type": "document", "filename": filename, "projectId": new_project}
    resp = await client.post(f"{target_dms}/v2/files/generate-upload-url", json=payload)
    resp.raise_for_status()
    upload_data = resp.json()
    upload_url = upload_data["uploadUrl"]
    mime_type = upload_data.get("mimeType", "application/pdf")

    with open(local_path, "rb") as f:
        file_bytes = f.read()
    resp = await client.put(upload_url, content=file_bytes, headers={"Content-Type": mime_type})
    resp.raise_for_status()

    resp = await client.post(f"{target_dms}/v2/files/confirm-upload", json=payload)
    resp.raise_for_status()
    return resp.json()["id"]


@app.post("/api/run-selected")
async def run_selected(request: RunSelectedRequest) -> dict:
    target_dms = os.environ.get("TARGET_DMS_URL", DEFAULT_TARGET_DMS_URL)
    new_project = str(uuid.uuid4())
    file_count = len(request.selected_files)
    timestamp = datetime.now(UTC).isoformat()
    log_lines: list[str] = []

    log_lines.append("=== Selected-file upload ===")
    log_lines.append(f"New project:    {new_project}")
    log_lines.append(f"Files:          {file_count}")
    log_lines.append("")

    new_file_ids: list[str] = []
    exit_code = 0

    async with RUN_LOCK, httpx.AsyncClient(timeout=httpx.Timeout(300, connect=15)) as client:
        for selected_file in request.selected_files:
            local_path = UPLOADS_DIR / selected_file.filename
            if not local_path.is_file():
                log_lines.append(f"SKIP: {selected_file.filename} (not found)")
                continue
            try:
                new_file_id = await _upload_file(
                    client,
                    target_dms,
                    new_project,
                    selected_file.filename,
                    local_path,
                )
                new_file_ids.append(new_file_id)
                log_lines.append(f"UP: {selected_file.filename} -> {new_file_id}")
            except Exception as exc:
                log_lines.append(f"FAIL: {selected_file.filename}: {exc}")
                exit_code = 1

    payload_dict: dict[str, object] = {"project_id": new_project, "file_ids": new_file_ids}
    if DOCUMENT_TYPES_JSON.exists():
        payload_dict["document_types"] = json.loads(DOCUMENT_TYPES_JSON.read_text())

    log_lines.append("")
    log_lines.append(f"=== Done: {len(new_file_ids)}/{file_count} files uploaded ===")
    log_lines.append(f"Project: {new_project}")

    return asdict(
        RunResult(
            scenario_key=f"selected-{file_count}",
            scenario_label=f"{file_count} selected",
            limit=file_count,
            all_files=False,
            command=f"[python] upload {file_count} selected files",
            exit_code=exit_code,
            ok=exit_code == 0,
            output="\n".join(log_lines),
            payload=json.dumps(payload_dict, indent=2),
            timestamp=timestamp,
        )
    )


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="Serve the testrun UI.")
    parser.add_argument("--host", default=HOST, help=f"Bind host (default: {HOST})")
    parser.add_argument("--port", type=int, default=PORT, help=f"Bind port (default: {PORT})")
    args = parser.parse_args(sys.argv[1:])

    uvicorn.run(app, host=args.host, port=args.port)
