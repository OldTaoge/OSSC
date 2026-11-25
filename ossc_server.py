#!/usr/bin/env python3
import argparse
import json
import sqlite3
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse


def now_ts():
    return int(time.time())


DEFAULT_HEARTBEAT_TIMEOUT = 45


PANEL_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OSSC Panel</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d9dee7;
      --text: #172033;
      --muted: #667085;
      --accent: #1b6b5f;
      --accent-2: #b43d2d;
      --code: #101828;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 24px;
      background: #ffffff;
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 2;
    }
    h1 { font-size: 20px; margin: 0; }
    h2 { font-size: 15px; margin: 0 0 12px; }
    main {
      display: grid;
      grid-template-columns: minmax(280px, 0.95fr) minmax(420px, 1.35fr);
      gap: 16px;
      padding: 16px 24px 28px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-width: 0;
    }
    .stack { display: grid; gap: 16px; align-content: start; }
    .toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    button {
      border: 1px solid #b8c1cf;
      border-radius: 6px;
      background: #ffffff;
      color: var(--text);
      min-height: 34px;
      padding: 7px 11px;
      cursor: pointer;
      font-weight: 600;
    }
    button.primary {
      background: var(--accent);
      border-color: var(--accent);
      color: #ffffff;
    }
    button:disabled { opacity: 0.55; cursor: wait; }
    input, textarea, select {
      width: 100%;
      border: 1px solid #c7ced9;
      border-radius: 6px;
      padding: 8px 9px;
      background: #ffffff;
      color: var(--text);
      font: inherit;
    }
    textarea {
      min-height: 120px;
      resize: vertical;
      font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
      font-size: 12px;
      line-height: 1.45;
    }
    label { display: grid; gap: 5px; color: var(--muted); font-size: 12px; font-weight: 600; }
    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
    .form { display: grid; gap: 10px; }
    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }
    th, td {
      border-bottom: 1px solid #edf0f4;
      padding: 8px 7px;
      text-align: left;
      vertical-align: top;
      overflow-wrap: anywhere;
    }
    th {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 700;
      background: #eef4f3;
      color: var(--accent);
    }
    .pill.offline { background: #f7ecea; color: var(--accent-2); }
    .muted { color: var(--muted); }
    .mono {
      font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
      font-size: 12px;
    }
    pre {
      margin: 0;
      max-height: 210px;
      overflow: auto;
      white-space: pre-wrap;
      background: #111827;
      color: #f9fafb;
      border-radius: 6px;
      padding: 10px;
      font-size: 12px;
    }
    details { border-top: 1px solid #edf0f4; padding-top: 8px; }
    summary { cursor: pointer; font-weight: 700; }
    .status { min-height: 20px; font-weight: 700; }
    .status.error { color: var(--accent-2); }
    .status.ok { color: var(--accent); }
    @media (max-width: 920px) {
      main { grid-template-columns: 1fr; padding: 12px; }
      header { padding: 14px 12px; align-items: flex-start; }
      .grid-2, .grid-3 { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>OSSC Panel</h1>
      <div class="muted">Client heartbeat, command tasks, and observation results</div>
    </div>
    <div class="toolbar">
      <button id="refreshBtn">Refresh</button>
      <button id="autoBtn" class="primary">Auto refresh on</button>
    </div>
  </header>
  <main>
    <div class="stack">
      <section>
        <h2>Clients</h2>
        <div id="clientSummary" class="muted">Loading...</div>
        <table>
          <thead><tr><th style="width: 22%">Client</th><th style="width: 18%">State</th><th>Address / Reported</th><th style="width: 18%">Manage</th></tr></thead>
          <tbody id="clientsBody"></tbody>
        </table>
      </section>
      <section>
        <h2>Client Management</h2>
        <form id="clientForm" class="form">
          <div class="grid-2">
            <label>Client ID<input name="id" placeholder="client-a"></label>
            <label>Name<input name="name" placeholder="Client A"></label>
          </div>
          <label>IP / Domain for probes<input name="address" placeholder="192.168.1.20 or node-a.example.com"></label>
          <label>Meta JSON<textarea name="meta" style="min-height: 80px;">{}</textarea></label>
          <div class="toolbar">
            <button class="primary" type="submit">Save Client</button>
            <button id="clearClientBtn" type="button">Clear</button>
          </div>
        </form>
        <div class="muted">Agents are auto-discovered when they register or send heartbeats.</div>
      </section>
      <section>
        <h2>Create Command Task</h2>
        <form id="commandForm" class="form">
          <div class="grid-2">
            <label>Name<input name="name" value="ping-check"></label>
            <label>Interval seconds<input name="interval" type="number" min="0" value="60"></label>
          </div>
          <label>Observer IDs<input name="observers" placeholder="client-a, client-c"></label>
          <label>Target hosts<input name="targets" placeholder="192.168.1.20, node-a.example.com"></label>
          <div class="grid-3">
            <label>Mode<select name="mode"><option>foreground</option><option>background</option><option>stop</option></select></label>
            <label>Timeout<input name="timeout" type="number" min="1" value="20"></label>
            <label>Shell<select name="shell"><option value="false">false</option><option value="true">true</option></select></label>
          </div>
          <label>Command<input name="command" value='["ping","-n","4","{target}"]'></label>
          <button class="primary" type="submit">Create Command Task</button>
        </form>
      </section>
      <section>
        <h2>Create Combo Task</h2>
        <form id="comboForm" class="form">
          <div class="grid-2">
            <label>Name<input name="name" value="iperf3-combo"></label>
            <label>Interval seconds<input name="interval" type="number" min="0" value="300"></label>
          </div>
          <label>Observer IDs<input name="observers" placeholder="client-a"></label>
          <label>Target client IDs<input name="targets" placeholder="client-b"></label>
          <label>Steps JSON<textarea name="steps"></textarea></label>
          <button class="primary" type="submit">Create Combo Task</button>
        </form>
      </section>
      <section>
        <h2>Service Management</h2>
        <form id="serviceForm" class="form">
          <div class="grid-2">
            <label>Client IDs<input name="clients" placeholder="client-a, client-b"></label>
            <label>Interval seconds<input name="interval" type="number" min="0" value="0"></label>
          </div>
          <div class="grid-2">
            <label>Service name<input name="service" placeholder="nginx.service"></label>
            <label>Action
              <select name="action">
                <option value="status">status</option>
                <option value="is-active">is-active</option>
                <option value="start">start</option>
                <option value="stop">stop</option>
                <option value="restart">restart</option>
                <option value="reload">reload</option>
              </select>
            </label>
          </div>
          <button class="primary" type="submit">Run systemctl</button>
        </form>
      </section>
    </div>
    <div class="stack">
      <section>
        <h2>Tasks</h2>
        <table>
          <thead><tr><th style="width: 9%">ID</th><th>Name</th><th style="width: 18%">Type</th><th style="width: 16%">Interval</th><th>Targets</th></tr></thead>
          <tbody id="tasksBody"></tbody>
        </table>
      </section>
      <section>
        <h2>Results</h2>
        <table>
          <thead><tr><th style="width: 10%">Run</th><th style="width: 16%">Client</th><th style="width: 14%">Status</th><th>Output</th></tr></thead>
          <tbody id="resultsBody"></tbody>
        </table>
      </section>
      <section>
        <h2>Request Status</h2>
        <div id="status" class="status muted">Ready</div>
      </section>
    </div>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    let autoRefresh = true;
    const defaultSteps = [
      {
        role: "target",
        delay_seconds: 0,
        mode: "background",
        process_key: "iperf3-{target_client_id}-5201",
        command: ["iperf3", "-s", "-p", "5201"]
      },
      {
        role: "observer",
        delay_seconds: 2,
        mode: "foreground",
        command: ["iperf3", "-c", "{target}", "-p", "5201", "-t", "10", "-J"],
        timeout: 25
      },
      {
        role: "target",
        delay_seconds: 14,
        mode: "stop",
        process_key: "iperf3-{target_client_id}-5201"
      }
    ];
    $("comboForm").steps.value = JSON.stringify(defaultSteps, null, 2);

    function setStatus(message, isError = false) {
      $("status").textContent = message;
      $("status").className = "status " + (isError ? "error" : "ok");
    }

    function parseCsv(value) {
      return value.split(",").map((item) => item.trim()).filter(Boolean);
    }

    function parseCommand(value) {
      const trimmed = value.trim();
      if (trimmed.startsWith("[") || trimmed.startsWith("{")) return JSON.parse(trimmed);
      return trimmed;
    }

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: { "Content-Type": "application/json", "Accept": "application/json" },
        ...options
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || data.error || response.statusText);
      return data;
    }

    function renderClients(clients) {
      const online = clients.filter((client) => client.online).length;
      $("clientSummary").textContent = `${online}/${clients.length} online`;
      $("clientsBody").innerHTML = clients.map((client) => {
        const meta = client.meta || {};
        const metaText = Object.entries(meta).slice(0, 4).map(([k, v]) => `${k}: ${v}`).join(" | ");
        const encoded = encodeURIComponent(JSON.stringify(client));
        return `<tr>
          <td><strong>${escapeHtml(client.id)}</strong><div class="muted">${escapeHtml(client.name)}</div></td>
          <td><span class="pill ${client.online ? "" : "offline"}">${client.online ? "online" : "offline"}</span><div class="muted">${client.seconds_since_seen}s ago</div></td>
          <td>
            <div>${escapeHtml(client.address || "(not configured)")}</div>
            <div class="muted mono">reported: ${escapeHtml(client.host || "")}</div>
            <div class="muted mono">${escapeHtml(metaText)}</div>
          </td>
          <td>
            <button type="button" data-client-edit="${encoded}">Edit</button>
            <button type="button" data-client-delete="${escapeHtml(client.id)}">Delete</button>
          </td>
        </tr>`;
      }).join("");
    }

    function renderTasks(tasks) {
      $("tasksBody").innerHTML = tasks.map((task) => {
        return `<tr>
          <td class="mono">${task.id}</td>
          <td><strong>${escapeHtml(task.name)}</strong><div class="muted mono">${escapeHtml((task.observer_ids || []).join(", "))}</div></td>
          <td>${escapeHtml(task.type)}<div class="muted">${task.enabled ? "enabled" : "disabled"}</div></td>
          <td>${task.interval_seconds}s</td>
          <td class="mono">${escapeHtml((task.target_hosts || []).join(", "))}</td>
        </tr>`;
      }).join("");
    }

    function renderResults(results) {
      $("resultsBody").innerHTML = results.map((result) => {
        const stdout = result.stdout || "";
        const stderr = result.stderr || "";
        const statusClass = result.status === "done" ? "" : "offline";
        return `<tr>
          <td class="mono">#${result.id}<div class="muted">task ${result.task_id}</div></td>
          <td>${escapeHtml(result.observer_id)}<div class="muted mono">${escapeHtml(result.target || "")}</div></td>
          <td><span class="pill ${statusClass}">${escapeHtml(result.status)}</span><div class="muted">exit ${result.exit_code ?? ""}</div></td>
          <td>
            <details>
              <summary>${escapeHtml(result.task_name || "")}</summary>
              <pre>${escapeHtml(stdout || stderr || "(no output)")}</pre>
            </details>
          </td>
        </tr>`;
      }).join("");
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    async function refreshAll() {
      const [clients, tasks, results] = await Promise.all([
        api("/api/clients"),
        api("/api/tasks"),
        api("/api/results?limit=50")
      ]);
      renderClients(clients.clients || []);
      renderTasks(tasks.tasks || []);
      renderResults(results.results || []);
      setStatus(`Refreshed ${new Date().toLocaleTimeString()}`);
    }

    $("commandForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const fields = form.elements;
      const payload = {
        name: fields.name.value.trim() || "command-task",
        type: "command",
        observer_ids: parseCsv(fields.observers.value),
        target_hosts: parseCsv(fields.targets.value),
        interval_seconds: Number(fields.interval.value || 0),
        params: {
          mode: fields.mode.value,
          command: parseCommand(fields.command.value),
          timeout: Number(fields.timeout.value || 60),
          shell: fields.shell.value === "true"
        }
      };
      try {
        await api("/api/tasks", { method: "POST", body: JSON.stringify(payload) });
        setStatus("Command task created");
        await refreshAll();
      } catch (error) {
        setStatus(error.message, true);
      }
    });

    $("comboForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const fields = form.elements;
      const payload = {
        name: fields.name.value.trim() || "combo-task",
        type: "command_combo",
        observer_ids: parseCsv(fields.observers.value),
        target_client_ids: parseCsv(fields.targets.value),
        interval_seconds: Number(fields.interval.value || 0),
        params: { steps: JSON.parse(fields.steps.value) }
      };
      try {
        await api("/api/tasks", { method: "POST", body: JSON.stringify(payload) });
        setStatus("Combo task created");
        await refreshAll();
      } catch (error) {
        setStatus(error.message, true);
      }
    });

    $("clientForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const fields = event.currentTarget.elements;
      const id = fields.id.value.trim();
      if (!id) {
        setStatus("Client ID is required", true);
        return;
      }
      let meta = {};
      try {
        meta = JSON.parse(fields.meta.value || "{}");
      } catch (error) {
        setStatus("Meta JSON is invalid", true);
        return;
      }
      const payload = {
        id,
        name: fields.name.value.trim() || id,
        address: fields.address.value.trim(),
        meta
      };
      try {
        await api(`/api/clients/${encodeURIComponent(id)}`, {
          method: "PUT",
          body: JSON.stringify(payload)
        });
        setStatus(`Client ${id} saved`);
        await refreshAll();
      } catch (error) {
        setStatus(error.message, true);
      }
    });

    $("clearClientBtn").addEventListener("click", () => {
      const fields = $("clientForm").elements;
      fields.id.value = "";
      fields.name.value = "";
      fields.address.value = "";
      fields.meta.value = "{}";
      fields.id.disabled = false;
    });

    $("clientsBody").addEventListener("click", async (event) => {
      const editValue = event.target.getAttribute("data-client-edit");
      const deleteId = event.target.getAttribute("data-client-delete");
      if (editValue) {
        const client = JSON.parse(decodeURIComponent(editValue));
        const fields = $("clientForm").elements;
        fields.id.value = client.id || "";
        fields.id.disabled = true;
        fields.name.value = client.name || "";
        fields.address.value = client.address || "";
        fields.meta.value = JSON.stringify(client.meta || {}, null, 2);
      }
      if (deleteId) {
        try {
          await api(`/api/clients/${encodeURIComponent(deleteId)}`, { method: "DELETE" });
          setStatus(`Client ${deleteId} deleted`);
          await refreshAll();
        } catch (error) {
          setStatus(error.message, true);
        }
      }
    });

    $("serviceForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const fields = form.elements;
      const clients = parseCsv(fields.clients.value);
      const service = fields.service.value.trim();
      const action = fields.action.value;
      if (!clients.length) {
        setStatus("At least one client id is required", true);
        return;
      }
      if (!service) {
        setStatus("Service name is required", true);
        return;
      }
      const payload = {
        name: `systemctl-${action}-${service}`,
        type: "command",
        observer_ids: [],
        target_hosts: [],
        interval_seconds: Number(fields.interval.value || 0),
        params: {
          mode: "foreground",
          command: ["systemctl", action, service, "--no-pager"],
          timeout: action === "status" ? 15 : 60
        }
      };
      try {
        for (const client of clients) {
          await api("/api/tasks", {
            method: "POST",
            body: JSON.stringify({
              ...payload,
              name: `${payload.name}-${client}`,
              observer_ids: [client],
              target_hosts: [client]
            })
          });
        }
        setStatus(`Created ${clients.length} systemctl ${action} task(s)`);
        await refreshAll();
      } catch (error) {
        setStatus(error.message, true);
      }
    });

    $("refreshBtn").addEventListener("click", () => refreshAll().catch((error) => setStatus(error.message, true)));
    $("autoBtn").addEventListener("click", () => {
      autoRefresh = !autoRefresh;
      $("autoBtn").textContent = autoRefresh ? "Auto refresh on" : "Auto refresh off";
      $("autoBtn").className = autoRefresh ? "primary" : "";
    });

    setInterval(() => {
      if (autoRefresh) refreshAll().catch((error) => setStatus(error.message, true));
    }, 5000);
    refreshAll().catch((error) => setStatus(error.message, true));
  </script>
</body>
</html>
"""


def json_dumps(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class Store:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()

    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_db(self):
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS clients (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    host TEXT,
                    address TEXT,
                    last_seen INTEGER NOT NULL,
                    meta_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    interval_seconds INTEGER NOT NULL DEFAULT 0,
                    next_run_at INTEGER,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    params_json TEXT NOT NULL DEFAULT '{}',
                    created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS task_observers (
                    task_id INTEGER NOT NULL,
                    client_id TEXT NOT NULL,
                    PRIMARY KEY (task_id, client_id),
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS task_targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    target TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS task_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    observer_id TEXT NOT NULL,
                    target TEXT NOT NULL,
                    run_type TEXT,
                    params_json TEXT NOT NULL DEFAULT '{}',
                    group_key TEXT,
                    step_order INTEGER NOT NULL DEFAULT 0,
                    not_before INTEGER,
                    status TEXT NOT NULL,
                    assigned_at INTEGER NOT NULL,
                    started_at INTEGER,
                    finished_at INTEGER,
                    exit_code INTEGER,
                    stdout TEXT,
                    stderr TEXT,
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_task_runs_observer_status
                    ON task_runs(observer_id, status);
                CREATE INDEX IF NOT EXISTS idx_task_runs_task
                    ON task_runs(task_id);
                """
            )
            self.ensure_task_run_columns(conn)
            self.ensure_client_columns(conn)

    def ensure_task_run_columns(self, conn):
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(task_runs)")}
        migrations = {
            "run_type": "ALTER TABLE task_runs ADD COLUMN run_type TEXT",
            "params_json": "ALTER TABLE task_runs ADD COLUMN params_json TEXT NOT NULL DEFAULT '{}'",
            "group_key": "ALTER TABLE task_runs ADD COLUMN group_key TEXT",
            "step_order": "ALTER TABLE task_runs ADD COLUMN step_order INTEGER NOT NULL DEFAULT 0",
            "not_before": "ALTER TABLE task_runs ADD COLUMN not_before INTEGER",
        }
        for column, sql in migrations.items():
            if column not in columns:
                conn.execute(sql)

    def ensure_client_columns(self, conn):
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(clients)")}
        if "address" not in columns:
            conn.execute("ALTER TABLE clients ADD COLUMN address TEXT")
            conn.execute("UPDATE clients SET address=host WHERE address IS NULL")

    def register_client(self, client_id, name, host, meta):
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO clients(id, name, host, address, last_seen, meta_json)
                VALUES (?, ?, ?, NULL, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    host=excluded.host,
                    last_seen=excluded.last_seen,
                    meta_json=excluded.meta_json
                """,
                (client_id, name, host, now_ts(), json.dumps(meta or {})),
            )

    def save_client(self, client_id, name, address, meta):
        with self.connect() as conn:
            row = conn.execute("SELECT host FROM clients WHERE id=?", (client_id,)).fetchone()
            reported_host = row["host"] if row else None
            conn.execute(
                """
                INSERT INTO clients(id, name, host, address, last_seen, meta_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    address=excluded.address,
                    meta_json=excluded.meta_json
                """,
                (
                    client_id,
                    name or client_id,
                    reported_host,
                    address,
                    now_ts(),
                    json.dumps(meta or {}, ensure_ascii=False),
                ),
            )

    def delete_client(self, client_id):
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
            return cur.rowcount

    def heartbeat_client(self, client_id, host, meta):
        with self.connect() as conn:
            row = conn.execute("SELECT meta_json FROM clients WHERE id=?", (client_id,)).fetchone()
            if not row:
                conn.execute(
                    """
                    INSERT INTO clients(id, name, host, address, last_seen, meta_json)
                    VALUES (?, ?, ?, NULL, ?, ?)
                    """,
                    (client_id, client_id, host, now_ts(), json.dumps(meta or {}, ensure_ascii=False)),
                )
                return

            current_meta = json.loads(row["meta_json"] or "{}")
            current_meta.update(meta or {})
            conn.execute(
                """
                UPDATE clients
                SET host=COALESCE(?, host), last_seen=?, meta_json=?
                WHERE id=?
                """,
                (host, now_ts(), json.dumps(current_meta, ensure_ascii=False), client_id),
            )

    def list_clients(self, heartbeat_timeout=DEFAULT_HEARTBEAT_TIMEOUT):
        current = now_ts()
        with self.connect() as conn:
            clients = []
            for row in conn.execute("SELECT * FROM clients ORDER BY id"):
                item = dict(row)
                item["meta"] = json.loads(item.pop("meta_json") or "{}")
                item["seconds_since_seen"] = max(0, current - int(item["last_seen"]))
                item["heartbeat_timeout"] = heartbeat_timeout
                item["online"] = item["seconds_since_seen"] <= heartbeat_timeout
                clients.append(item)
            return clients

    def create_task(self, payload):
        task_type = payload.get("type")
        if task_type not in {"command", "command_combo"}:
            raise ValueError("type must be one of: command, command_combo")

        observer_ids = payload.get("observer_ids") or []
        target_hosts = self.normalize_target_hosts(payload)
        if not observer_ids:
            raise ValueError("observer_ids is required")
        if not target_hosts:
            raise ValueError("target_hosts or target_clients is required")
        if task_type == "command_combo":
            if not all(isinstance(target, dict) for target in target_hosts):
                raise ValueError("command_combo requires target_clients or target_client_ids")
            if not (payload.get("params") or {}).get("steps"):
                raise ValueError("command_combo requires params.steps")
        if task_type == "command" and not (payload.get("params") or {}).get("command"):
            raise ValueError("command requires params.command")

        interval_seconds = int(payload.get("interval_seconds", 0))
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be >= 0")

        params = payload.get("params") or {}
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO tasks(name, type, interval_seconds, next_run_at, enabled, params_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("name") or f"{task_type}-{now_ts()}",
                    task_type,
                    interval_seconds,
                    now_ts(),
                    1 if payload.get("enabled", True) else 0,
                    json.dumps(params, ensure_ascii=False),
                    now_ts(),
                ),
            )
            task_id = cur.lastrowid
            conn.executemany(
                "INSERT INTO task_observers(task_id, client_id) VALUES (?, ?)",
                [(task_id, str(client_id)) for client_id in observer_ids],
            )
            conn.executemany(
                "INSERT INTO task_targets(task_id, target) VALUES (?, ?)",
                [(task_id, self.encode_target(target)) for target in target_hosts],
            )
        return self.get_task(task_id)

    def encode_target(self, target):
        if isinstance(target, dict):
            return json.dumps(target, ensure_ascii=False, separators=(",", ":"))
        return str(target)

    def get_task(self, task_id):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                return None
            task = dict(row)
            task["params"] = json.loads(task.pop("params_json") or "{}")
            task["observer_ids"] = [
                item["client_id"]
                for item in conn.execute("SELECT client_id FROM task_observers WHERE task_id=? ORDER BY client_id", (task_id,))
            ]
            task["target_hosts"] = [
                item["target"]
                for item in conn.execute("SELECT target FROM task_targets WHERE task_id=? ORDER BY id", (task_id,))
            ]
            return task

    def list_tasks(self):
        with self.connect() as conn:
            ids = [row["id"] for row in conn.execute("SELECT id FROM tasks ORDER BY id DESC")]
        return [self.get_task(task_id) for task_id in ids]

    def normalize_target_hosts(self, payload):
        if payload.get("target_hosts"):
            return [str(target) for target in payload.get("target_hosts")]
        targets = []
        for item in payload.get("target_clients") or []:
            if isinstance(item, dict):
                target_id = str(item.get("id") or item.get("client_id"))
                host = item.get("address") or item.get("host") or self.get_client_host(target_id)
                targets.append({"id": target_id, "host": host})
            else:
                target_id = str(item)
                targets.append({"id": target_id, "host": self.get_client_host(target_id)})
        for target_id in payload.get("target_client_ids") or []:
            target_id = str(target_id)
            targets.append({"id": target_id, "host": self.get_client_host(target_id)})
        return targets

    def get_client_host(self, client_id):
        with self.connect() as conn:
            row = conn.execute("SELECT address FROM clients WHERE id=?", (client_id,)).fetchone()
        if not row:
            raise ValueError(f"target client not found: {client_id}")
        if not row["address"]:
            raise ValueError(f"target client address is not configured: {client_id}")
        return row["address"]

    def schedule_due_runs(self):
        due = now_ts()
        with self.connect() as conn:
            tasks = list(
                conn.execute(
                    """
                    SELECT t.* FROM tasks t
                    WHERE t.enabled=1 AND t.next_run_at IS NOT NULL AND t.next_run_at<=?
                    ORDER BY t.next_run_at, t.id
                    """,
                    (due,),
                )
            )
            for task in tasks:
                targets = list(conn.execute("SELECT target FROM task_targets WHERE task_id=? ORDER BY id", (task["id"],)))
                observers = [
                    row["client_id"]
                    for row in conn.execute("SELECT client_id FROM task_observers WHERE task_id=? ORDER BY client_id", (task["id"],))
                ]
                for observer_id in observers:
                    if task["type"] == "command_combo":
                        self.insert_command_combo_runs(conn, task, observer_id, targets, due)
                    else:
                        for target in targets:
                            target_context = self.decode_target_context(target["target"])
                            run_params = self.render_command_params(
                                json.loads(task["params_json"] or "{}"),
                                observer_id,
                                target_context,
                            )
                            self.insert_run(
                                conn,
                                task_id=task["id"],
                                observer_id=observer_id,
                                target=target_context["host"],
                                run_type="command",
                                params_json=json.dumps(run_params, ensure_ascii=False),
                                assigned_at=due,
                            )

                if task["interval_seconds"] > 0:
                    next_run = max(due + task["interval_seconds"], int(task["next_run_at"]) + task["interval_seconds"])
                else:
                    next_run = None
                    conn.execute("UPDATE tasks SET enabled=0 WHERE id=?", (task["id"],))
                conn.execute("UPDATE tasks SET next_run_at=? WHERE id=?", (next_run, task["id"]))

    def insert_run(
        self,
        conn,
        task_id,
        observer_id,
        target,
        run_type,
        params_json,
        assigned_at,
        group_key=None,
        step_order=0,
        not_before=None,
    ):
        conn.execute(
            """
            INSERT INTO task_runs(
                task_id, observer_id, target, run_type, params_json, group_key,
                step_order, not_before, status, assigned_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                task_id,
                observer_id,
                target,
                run_type,
                params_json,
                group_key,
                step_order,
                not_before,
                assigned_at,
            ),
        )

    def decode_target_context(self, raw_target):
        if raw_target.startswith("{"):
            target = json.loads(raw_target)
            return {
                "id": str(target.get("id") or target.get("client_id") or target.get("host")),
                "host": str(target.get("host")),
            }
        return {"id": raw_target, "host": raw_target}

    def render_value(self, value, observer_id, target_context):
        replacements = {
            "observer_id": str(observer_id),
            "target": str(target_context["host"]),
            "target_host": str(target_context["host"]),
            "target_client_id": str(target_context["id"]),
        }
        if isinstance(value, str):
            return value.format(**replacements)
        if isinstance(value, list):
            return [self.render_value(item, observer_id, target_context) for item in value]
        if isinstance(value, dict):
            return {key: self.render_value(item, observer_id, target_context) for key, item in value.items()}
        return value

    def render_command_params(self, params, observer_id, target_context):
        return self.render_value(params, observer_id, target_context)

    def insert_command_combo_runs(self, conn, task, observer_id, targets, due):
        params = json.loads(task["params_json"] or "{}")
        steps = params.get("steps") or []
        for index, target in enumerate(targets):
            target_context = self.decode_target_context(target["target"])
            target_client_id = target_context["id"]
            group_key = f"{task['id']}:{due}:{observer_id}:{target_client_id}:{index}"
            for step_index, step in enumerate(steps, start=1):
                step_role = step.get("role", "observer")
                if step_role == "target":
                    assignee = target_context["id"]
                elif step_role == "observer":
                    assignee = observer_id
                else:
                    raise ValueError("combo step role must be observer or target")

                delay = int(step.get("delay_seconds", 0))
                step_params = {
                    key: value
                    for key, value in step.items()
                    if key not in {"role", "delay_seconds"}
                }
                step_params = self.render_command_params(step_params, observer_id, target_context)
                self.insert_run(
                    conn,
                    task_id=task["id"],
                    observer_id=assignee,
                    target=target_context["host"],
                    run_type="command",
                    params_json=json.dumps(step_params, ensure_ascii=False),
                    assigned_at=due,
                    group_key=group_key,
                    step_order=step_index,
                    not_before=due + delay,
                )

    def pull_runs(self, observer_id, limit):
        self.schedule_due_runs()
        with self.connect() as conn:
            rows = list(
                conn.execute(
                    """
                    SELECT
                        r.id AS run_id, r.target, r.run_type, r.params_json AS run_params_json,
                        r.group_key, r.step_order, t.id AS task_id, t.name, t.type, t.params_json
                    FROM task_runs r
                    JOIN tasks t ON t.id=r.task_id
                    WHERE r.observer_id=?
                        AND r.status='pending'
                        AND (r.not_before IS NULL OR r.not_before<=?)
                    ORDER BY r.assigned_at, r.group_key, r.step_order, r.id
                    LIMIT ?
                    """,
                    (observer_id, now_ts(), limit),
                )
            )
            run_ids = [row["run_id"] for row in rows]
            if run_ids:
                conn.executemany("UPDATE task_runs SET status='leased' WHERE id=?", [(run_id,) for run_id in run_ids])
            result = []
            for row in rows:
                item = dict(row)
                item["run_type"] = item["run_type"] or item["type"]
                run_params_json = item.pop("run_params_json") or item.pop("params_json") or "{}"
                item.pop("params_json", None)
                item["params"] = json.loads(run_params_json)
                result.append(item)
            return result

    def save_result(self, observer_id, payload):
        run_id = int(payload["run_id"])
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id FROM task_runs WHERE id=? AND observer_id=?",
                (run_id, observer_id),
            ).fetchone()
            if not row:
                raise ValueError("run_id not found for this observer")
            conn.execute(
                """
                UPDATE task_runs SET
                    status=?,
                    started_at=?,
                    finished_at=?,
                    exit_code=?,
                    stdout=?,
                    stderr=?,
                    metrics_json=?
                WHERE id=? AND observer_id=?
                """,
                (
                    payload.get("status", "done"),
                    payload.get("started_at"),
                    payload.get("finished_at"),
                    payload.get("exit_code"),
                    payload.get("stdout", ""),
                    payload.get("stderr", ""),
                    json.dumps(payload.get("metrics") or {}, ensure_ascii=False),
                    run_id,
                    observer_id,
                ),
            )

    def list_results(self, query):
        params = []
        where = []
        if query.get("task_id"):
            where.append("r.task_id=?")
            params.append(int(query["task_id"][0]))
        if query.get("observer_id"):
            where.append("r.observer_id=?")
            params.append(query["observer_id"][0])
        sql_where = "WHERE " + " AND ".join(where) if where else ""
        limit = min(int((query.get("limit") or ["100"])[0]), 1000)
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT r.*, t.name AS task_name, t.type AS task_type
                FROM task_runs r
                JOIN tasks t ON t.id=r.task_id
                {sql_where}
                ORDER BY r.id DESC
                LIMIT ?
                """,
                params,
            )
            result = []
            for row in rows:
                item = dict(row)
                item["metrics"] = json.loads(item.pop("metrics_json") or "{}")
                result.append(item)
            return result


class Handler(BaseHTTPRequestHandler):
    server_version = "OSSCPrototype/0.1"

    def send_json(self, status, data):
        body = json_dumps(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, status, html):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    @property
    def store(self):
        return self.server.store

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)

            if path == "/" or path == "/panel":
                self.send_html(200, PANEL_HTML)
            elif path == "/api/clients":
                heartbeat_timeout = int((query.get("heartbeat_timeout") or [str(DEFAULT_HEARTBEAT_TIMEOUT)])[0])
                self.send_json(200, {"clients": self.store.list_clients(heartbeat_timeout)})
            elif path == "/api/tasks":
                self.send_json(200, {"tasks": self.store.list_tasks()})
            elif path.startswith("/api/agents/") and path.endswith("/tasks"):
                parts = path.split("/")
                client_id = parts[3]
                limit = int((query.get("limit") or ["5"])[0])
                self.send_json(200, {"tasks": self.store.pull_runs(client_id, limit)})
            elif path == "/api/results":
                self.send_json(200, {"results": self.store.list_results(query)})
            else:
                self.send_json(404, {"error": "not_found", "path": path})
        except Exception as exc:
            traceback.print_exc()
            self.send_json(500, {"error": "server_error", "message": str(exc)})

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            payload = self.read_json()

            if path == "/api/clients/register":
                client_id = str(payload["id"])
                name = str(payload.get("name") or client_id)
                host = payload.get("host") or self.client_address[0]
                meta = payload.get("meta") or {}
                self.store.register_client(client_id, name, host, meta)
                self.send_json(200, {"ok": True, "client_id": client_id})
            elif path == "/api/clients/heartbeat":
                client_id = str(payload["id"])
                host = payload.get("host") or self.client_address[0]
                meta = payload.get("meta") or {}
                self.store.heartbeat_client(client_id, host, meta)
                self.send_json(200, {"ok": True, "client_id": client_id, "server_time": now_ts()})
            elif path == "/api/tasks":
                task = self.store.create_task(payload)
                self.send_json(201, {"ok": True, "task": task})
            elif path.startswith("/api/agents/") and path.endswith("/results"):
                parts = path.split("/")
                client_id = parts[3]
                self.store.save_result(client_id, payload)
                self.send_json(200, {"ok": True})
            else:
                self.send_json(404, {"error": "not_found", "path": path})
        except KeyError as exc:
            self.send_json(400, {"error": "bad_request", "message": f"missing field: {exc}"})
        except ValueError as exc:
            self.send_json(400, {"error": "bad_request", "message": str(exc)})
        except Exception as exc:
            traceback.print_exc()
            self.send_json(500, {"error": "server_error", "message": str(exc)})

    def do_PUT(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            payload = self.read_json()

            if path.startswith("/api/clients/"):
                client_id = unquote(path.split("/", 3)[3])
                payload_id = str(payload.get("id") or client_id)
                if payload_id != client_id:
                    raise ValueError("client id in path and body must match")
                name = str(payload.get("name") or client_id)
                address = payload.get("address") or payload.get("host") or None
                meta = payload.get("meta") or {}
                self.store.save_client(client_id, name, address, meta)
                self.send_json(200, {"ok": True, "client_id": client_id})
            else:
                self.send_json(404, {"error": "not_found", "path": path})
        except ValueError as exc:
            self.send_json(400, {"error": "bad_request", "message": str(exc)})
        except Exception as exc:
            traceback.print_exc()
            self.send_json(500, {"error": "server_error", "message": str(exc)})

    def do_DELETE(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"

            if path.startswith("/api/clients/"):
                client_id = unquote(path.split("/", 3)[3])
                deleted = self.store.delete_client(client_id)
                self.send_json(200, {"ok": True, "client_id": client_id, "deleted": deleted})
            else:
                self.send_json(404, {"error": "not_found", "path": path})
        except Exception as exc:
            traceback.print_exc()
            self.send_json(500, {"error": "server_error", "message": str(exc)})

    def log_message(self, fmt, *args):
        print("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), fmt % args))


def main():
    parser = argparse.ArgumentParser(description="OSSC temporary Python server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default="ossc.sqlite3")
    args = parser.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.store = Store(args.db)
    print(f"OSSC server listening on http://{args.host}:{args.port}, db={args.db}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
