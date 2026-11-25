#!/usr/bin/env python3
import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def now_ts():
    return int(time.time())


def request_json(method, url, payload=None, timeout=15):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, method=method)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def clamp_text(value, max_chars):
    if value is None:
        return ""
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + f"\n...[truncated {len(value) - max_chars} chars]"


def run_command(cmd, timeout, max_output, shell=False):
    started = now_ts()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=shell,
        )
        return {
            "started_at": started,
            "finished_at": now_ts(),
            "exit_code": proc.returncode,
            "stdout": clamp_text(proc.stdout, max_output),
            "stderr": clamp_text(proc.stderr, max_output),
            "status": "done" if proc.returncode == 0 else "failed",
        }
    except FileNotFoundError as exc:
        return {
            "started_at": started,
            "finished_at": now_ts(),
            "exit_code": 127,
            "stdout": "",
            "stderr": str(exc),
            "status": "failed",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "started_at": started,
            "finished_at": now_ts(),
            "exit_code": 124,
            "stdout": clamp_text(exc.stdout or "", max_output),
            "stderr": clamp_text((exc.stderr or "") + "\ncommand timed out", max_output),
            "status": "timeout",
        }


def command_from_params(params):
    raw = params.get("command")
    if not raw:
        raise ValueError("command task requires params.command")
    if isinstance(raw, list):
        cmd = [str(part) for part in raw]
    else:
        cmd = str(raw) if params.get("shell") else str(raw).split()
    timeout = int(params.get("timeout", 60))
    return cmd, timeout, bool(params.get("shell", False))


def extract_metrics(task_type, result):
    metrics = {}
    if result.get("stdout", "").lstrip().startswith("{"):
        try:
            data = json.loads(result["stdout"])
            metrics["json"] = data
        except json.JSONDecodeError:
            pass
    return metrics


class Agent:
    def __init__(self, args):
        self.server = args.server.rstrip("/") + "/"
        self.client_id = args.id
        self.name = args.name or args.id
        self.poll = args.poll
        self.max_output = args.max_output
        self.managed_processes = {}

    def url(self, path):
        return urljoin(self.server, path.lstrip("/"))

    def register(self):
        payload = {
            "id": self.client_id,
            "name": self.name,
            "host": self.local_ip(),
            "meta": {
                "hostname": socket.gethostname(),
                "platform": platform.platform(),
                "python": sys.version.split()[0],
            },
        }
        return request_json("POST", self.url("/api/clients/register"), payload)

    def heartbeat(self, extra=None):
        payload = {
            "id": self.client_id,
            "host": self.local_ip(),
            "meta": {
                "hostname": socket.gethostname(),
                "platform": platform.platform(),
                "python": sys.version.split()[0],
                "last_poll_at": now_ts(),
                "pending_tasks": 0,
            },
        }
        if extra:
            payload["meta"].update(extra)
        return request_json("POST", self.url("/api/clients/heartbeat"), payload)

    def local_ip(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"

    def pull(self):
        return request_json("GET", self.url(f"/api/agents/{self.client_id}/tasks?limit=5")).get("tasks", [])

    def post_result(self, result):
        return request_json("POST", self.url(f"/api/agents/{self.client_id}/results"), result)

    def execute(self, task):
        task_type = task.get("run_type") or task["type"]
        params = task.get("params") or {}
        target = task["target"]

        try:
            if task_type == "command":
                result = self.execute_command(task, params)
            else:
                raise ValueError(f"unsupported task type: {task_type}")

            result["metrics"] = extract_metrics(task_type, result)
        except Exception as exc:
            result = {
                "started_at": now_ts(),
                "finished_at": now_ts(),
                "exit_code": 1,
                "stdout": "",
                "stderr": str(exc),
                "status": "failed",
                "metrics": {},
            }

        result.update(
            {
                "run_id": task["run_id"],
                "task_id": task["task_id"],
                "target": target,
            }
        )
        return result

    def execute_command(self, task, params):
        mode = params.get("mode", "foreground")
        if mode == "foreground":
            cmd, timeout, shell = command_from_params(params)
            printable = cmd if isinstance(cmd, str) else " ".join(cmd)
            print(f"run_id={task['run_id']} mode=foreground cmd={printable}")
            return run_command(cmd, timeout, self.max_output, shell=shell)
        if mode == "background":
            return self.start_background_command(task, params)
        if mode == "stop":
            return self.stop_background_command(params)
        raise ValueError("command mode must be foreground, background, or stop")

    def start_background_command(self, task, params):
        process_key = str(params.get("process_key") or task.get("group_key") or task["run_id"])
        existing = self.managed_processes.get(process_key)
        if existing and existing.poll() is None:
            return {
                "started_at": now_ts(),
                "finished_at": now_ts(),
                "exit_code": 0,
                "stdout": f"process already running: {process_key}",
                "stderr": "",
                "status": "done",
            }

        cmd, _timeout, shell = command_from_params(params)
        started = now_ts()
        printable = cmd if isinstance(cmd, str) else " ".join(cmd)
        print(f"start background process_key={process_key} cmd={printable}")
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=shell)
        time.sleep(0.2)
        if proc.poll() is not None:
            return {
                "started_at": started,
                "finished_at": now_ts(),
                "exit_code": proc.returncode,
                "stdout": "",
                "stderr": f"process exited immediately with code {proc.returncode}",
                "status": "failed",
            }
        self.managed_processes[process_key] = proc
        return {
            "started_at": started,
            "finished_at": now_ts(),
            "exit_code": 0,
            "stdout": f"process started: {process_key}",
            "stderr": "",
            "status": "done",
        }

    def stop_background_command(self, params):
        process_key = str(params.get("process_key"))
        if not process_key:
            raise ValueError("stop mode requires params.process_key")
        started = now_ts()
        proc = self.managed_processes.pop(process_key, None)
        if not proc or proc.poll() is not None:
            return {
                "started_at": started,
                "finished_at": now_ts(),
                "exit_code": 0,
                "stdout": f"process is not running: {process_key}",
                "stderr": "",
                "status": "done",
            }
        print(f"stop background process_key={process_key}")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        return {
            "started_at": started,
            "finished_at": now_ts(),
            "exit_code": 0,
            "stdout": f"process stopped: {process_key}",
            "stderr": "",
            "status": "done",
        }

    def loop(self):
        registered = False
        while True:
            try:
                if not registered:
                    self.register()
                    registered = True
                self.heartbeat()
                tasks = self.pull()
                self.heartbeat({"pending_tasks": len(tasks)})
                for task in tasks:
                    result = self.execute(task)
                    self.post_result(result)
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                registered = False
                print(f"server communication failed: {exc}")
            time.sleep(self.poll)


def main():
    parser = argparse.ArgumentParser(description="OSSC temporary Python client agent")
    parser.add_argument("--server", required=True, help="Server base URL, for example http://192.168.1.10:8080")
    parser.add_argument("--id", required=True, help="Stable client id, for example client-a")
    parser.add_argument("--name", help="Display name")
    parser.add_argument("--poll", type=int, default=10, help="Polling interval in seconds")
    parser.add_argument("--max-output", type=int, default=20000, help="Max stored stdout/stderr chars")
    args = parser.parse_args()

    if args.poll < 1:
        parser.error("--poll must be >= 1")

    print(f"OSSC agent id={args.id} server={args.server} pid={os.getpid()}")
    Agent(args).loop()


if __name__ == "__main__":
    main()
