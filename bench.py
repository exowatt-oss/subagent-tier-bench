#!/usr/bin/env python3
"""subagent-tier-bench: does a 3-tier agent team keep quality while cutting cost?

Standard library only, Python 3.9+. Commands:

  list                                   tasks, arms, suites
  plan     --suite smoke|core|full       ordered run list for a suite
  prompt   --task T --arm A              the exact first message for a run's root agent
  setup    --task T --arm A [--rep N]    create a fresh run directory + prompt file
  score    --run ID | --dir D --task T   grade a workspace with the hidden tests
  cost     --run ID | --dir D --arm A   price compatible JSONL sessions in a workspace, by tier
  finish   --run ID --status S           score + cost + append to results.jsonl
  judge-pack   --run ID                  blind code-review prompt for a finished run
  judge-record --run ID --json '{...}'   store the reviewer's scores
  report                                 aggregate results.jsonl into results.md
  selftest [--task T] [--write]          check fixtures; measure the starter baseline

Runs live under --root (default $STB_ROOT or ~/stb-runs), outside this repo, so the
agents under test never see hidden tests.
"""

from __future__ import annotations

import argparse
import ast
import datetime as _dt
import hashlib
import json
import math
import os
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent
TASKS_DIR = REPO / "tasks"
DEFAULT_ROOT = Path(os.environ.get("STB_ROOT", str(Path.home() / "stb-runs")))
RUN_TIME_LIMIT_MIN = 90

# --------------------------------------------------------------------------------------
# Model IDs, aliases, regexes and illustrative USD/million-token rates live in models.json.
# The legacy arm names below are stable experiment identifiers, not provider requirements.
# --------------------------------------------------------------------------------------

def load_models(path: Path) -> dict:
    data = json.loads(path.read_text())
    models = data["models"]
    for alias, model in models.items():
        if not all(k in model for k in ("label", "phi", "version", "price")):
            raise ValueError("incomplete model configuration for %s" % alias)
        re.compile(model["version"])
        if not all(k in model["price"] for k in ("input", "output", "cacheRead", "cacheWrite")):
            raise ValueError("incomplete rates for %s" % alias)
    return models


MODELS = {}  # Loaded by main() from --config or STB_CONFIG.

# Arms: tiers top-down as (model family, effort). Tier 0 is the root (L0).
ARMS = {
    "solo-luna": {
        "tiers": [("luna", "max")],
        "about": "One economy agent, no subagents. Cheap control: is any team needed at all?",
    },
    "solo-opus": {
        "tiers": [("opus", "xhigh")],
        "about": "One strong agent, no subagents. Control: does delegation help at all?",
    },
    "flat-opus": {
        "tiers": [("opus", "xhigh"), ("opus", "high")],
        "about": "Strong orchestrator -> strong workers. The expensive baseline.",
    },
    "flat-sonnet": {
        "tiers": [("opus", "xhigh"), ("sonnet", "xhigh")],
        "about": "Strong orchestrator -> balanced workers. Is the middle tier alone enough?",
    },
    "flat-luna": {
        "tiers": [("opus", "xhigh"), ("luna", "max")],
        "about": "Strong orchestrator -> economy workers. The cheap 2-tier baseline.",
    },
    "h-opus-sonnet-luna": {
        "tiers": [("opus", "xhigh"), ("sonnet", "xhigh"), ("luna", "max")],
        "about": "3-tier: strong root -> balanced leads -> economy workers.",
    },
    "h-opus-opus-luna": {
        "tiers": [("opus", "xhigh"), ("opus", "high"), ("luna", "max")],
        "about": "3-tier: strong root -> strong leads -> economy workers.",
    },
    "h-fable-sonnet-luna": {
        "tiers": [("fable", "xhigh"), ("sonnet", "xhigh"), ("luna", "max")],
        "about": "3-tier: premium root -> balanced leads -> economy workers.",
    },
    "h-fable-opus-luna": {
        "tiers": [("fable", "xhigh"), ("opus", "high"), ("luna", "max")],
        "about": "3-tier: premium root -> strong leads -> economy workers.",
    },
}

CORE_ARMS = ["solo-luna", "solo-opus", "flat-opus", "flat-luna",
             "h-opus-sonnet-luna", "h-opus-opus-luna", "h-fable-sonnet-luna"]
EXTRA_ARMS = ["flat-sonnet", "h-fable-opus-luna"]
BASELINE_ARM = "flat-opus"

SUITES = {
    # name: (tasks or None for all, arms, reps)
    "smoke": (["t1-ledger"], CORE_ARMS, 1),
    "core": (None, CORE_ARMS, 1),
    "full": (None, CORE_ARMS, 2),
    "extended": (None, CORE_ARMS + EXTRA_ARMS, 2),
}

TIER_NAMES = ["L0", "L1", "L2"]

# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------


def die(msg: str, code: int = 2) -> None:
    print("error: " + msg, file=sys.stderr)
    sys.exit(code)


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(value) -> float | None:
    """Session timestamps are ISO strings or epoch milliseconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value / 1000.0 if value > 1e11 else float(value)
    try:
        text = str(value).replace("Z", "+00:00")
        return _dt.datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def load_task(task_id: str) -> dict:
    tdir = TASKS_DIR / task_id
    meta_file = tdir / "task.json"
    if not meta_file.is_file():
        die("unknown task %r (have: %s)" % (task_id, ", ".join(task_ids())))
    meta = json.loads(meta_file.read_text())
    meta["_dir"] = tdir
    return meta


def task_ids() -> list:
    if not TASKS_DIR.is_dir():
        return []
    return sorted(p.name for p in TASKS_DIR.iterdir() if (p / "task.json").is_file())


def arm_or_die(arm: str) -> dict:
    if arm not in ARMS:
        die("unknown arm %r (have: %s)" % (arm, ", ".join(ARMS)))
    return ARMS[arm]


def root_dir(args) -> Path:
    return Path(getattr(args, "root", None) or DEFAULT_ROOT).expanduser().resolve()


def meta_dir(root: Path, run_id: str) -> Path:
    return root / "_meta" / run_id


def load_run(root: Path, run_id: str) -> dict:
    f = meta_dir(root, run_id) / "meta.json"
    if not f.is_file():
        die("unknown run %r under %s" % (run_id, root))
    return json.loads(f.read_text())


def tree_hash(path: Path) -> str:
    h = hashlib.sha256()
    if not path.exists():
        return "missing"
    for f in sorted(p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        h.update(str(f.relative_to(path)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()


# --------------------------------------------------------------------------------------
# Prompt composition (the arm's team policy + the task brief)
# --------------------------------------------------------------------------------------

COMMON_RULES = """\
Ground rules (all arms):
- Nobody will answer questions while you work. Do not ask; decide, and keep going.
- Work only inside this directory. No git commits, branches, pushes or worktrees
  (`git status` / `git diff` are fine). Do not install packages; nothing needs the network.
- Do not modify anything under `tests/`; it is restored before grading.
- The run is stopped after {limit} minutes of wall-clock time and graded as it stands.
- When you are done, reply with a summary of at most 10 lines.
"""

SPAWN_HELP = """\
Start a child with your harness's delegation adapter: model `{phi}` ({label}),
effort `{effort}`. Keep the same checkout and ensure each child session is recorded.
Use the configured adapter consistently at every depth; do not mix sessionless tools.
"""


def spawn_help(tier) -> str:
    fam, effort = tier
    m = MODELS[fam]
    return SPAWN_HELP.format(label=m["label"], effort=effort, phi=m["phi"])


def tier_label(tier) -> str:
    fam, effort = tier
    return "%s at %s effort" % (MODELS[fam]["label"], effort)


def time_limit(task: dict) -> int:
    return int(task.get("time_limit_min", RUN_TIME_LIMIT_MIN))


def policy_text(arm_id: str, limit_min: int = RUN_TIME_LIMIT_MIN) -> str:
    arm = arm_or_die(arm_id)
    tiers = arm["tiers"]
    rules = COMMON_RULES.format(limit=limit_min)
    head = "# How you work (benchmark arm `%s`)\n\n" % arm_id
    if len(tiers) == 1:
        return head + (
            "You are %s and you work alone. Do not start subagents, delegate tasks, or create "
            "other threads or agents of any kind. Do all of the work yourself.\n\n" % tier_label(tiers[0])
        ) + rules

    if len(tiers) == 2:
        return head + (
            "You are the orchestrator (L0, %s). Your team: workers (L1) = %s.\n\n"
            % (tier_label(tiers[0]), tier_label(tiers[1]))
        ) + spawn_help(tiers[1]) + """
Your rules:
1. You plan, split the work, delegate, review, integrate and verify. You do not write product
   code yourself, except one up-front shared contract/interface file if it helps, and small
   integration fixes of at most 20 changed lines per file after workers report back.
2. Workers see none of your context. Every brief is self-contained: goal, the files the worker
   owns, interfaces to honour, exact verification commands, and this line: "You are a worker.
   Do not start subagents. Do not edit tests/. No git mutations."
3. Workers running at the same time get disjoint files. Everyone works in this one checkout.
4. Use as many workers and fix-up rounds as you judge best, within these rules. If a part comes
   back incomplete, start a new worker with what is done and what still fails.

""" + rules

    # three tiers
    lead_policy = (
        "<<TEAM-POLICY>>\n"
        "You are an L1 lead in a three-tier team. Above you: the L0 orchestrator. Below you: L2 "
        "workers = %s.\n" % tier_label(tiers[2])
        + spawn_help(tiers[2])
        + "- Split your workstream into worker tasks, each with one clear deliverable (roughly 150\n"
          "  changed lines or less) and files disjoint from any worker running at the same time.\n"
          "  Start one L2 worker per task with the model and effort above.\n"
          "- Workers see none of your context. Each brief is self-contained: goal, the files it owns,\n"
          "  interfaces to honour, exact verification commands, and this line: \"You are an L2 worker.\n"
          "  Do not start subagents. Do not edit tests/. No git mutations.\"\n"
          "- You review worker output, run the tests, and send fix-ups as new worker tasks (with what\n"
          "  failed). You may hand-edit only small glue fixes (at most 20 changed lines per file).\n"
          "  You never write the bulk of the implementation yourself.\n"
          "- Stay inside your workstream's files unless your brief says otherwise. No git mutations,\n"
          "  no worktrees, do not edit tests/.\n"
          "- Finish with a short report: what is done, test status, open issues.\n"
          "<</TEAM-POLICY>>\n"
    )
    return head + (
        "You are the orchestrator (L0, %s). Your team has two tiers below you:\n"
        "- L1 leads = %s. Only you start leads: one per workstream, 2 to 4 at a time.\n"
        "- L2 workers = %s. Only leads start workers.\n\n"
        % (tier_label(tiers[0]), tier_label(tiers[1]), tier_label(tiers[2]))
    ) + "To start a lead:\n" + spawn_help(tiers[1]) + """
Your rules:
1. You plan the split into workstreams, optionally write one up-front shared contract/interface
   file, start the leads, review what they report, integrate and verify. You write no product
   code yourself beyond that contract and integration fixes of at most 20 changed lines per file.
2. Leads see none of your context. Every lead brief is self-contained (goal, files the
   workstream owns, interfaces, verification commands) and ends with the TEAM-POLICY block
   below, copied verbatim, markers included.
3. If a workstream comes back incomplete, start a new lead for the remainder with what is done
   and what still fails. Do not finish it yourself.

""" + lead_policy + "\n" + rules


def compose_prompt(task_id: str, arm_id: str) -> str:
    task = load_task(task_id)
    brief = (task["_dir"] / "brief.md").read_text().strip()
    return policy_text(arm_id, time_limit(task)).rstrip() + "\n\n---\n\n" + brief + "\n"


# --------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------

RUNNER = r'''
import importlib.util, json, sys, traceback, unittest
root, path = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)
out = {"tests": {}, "import_error": None}
try:
    spec = importlib.util.spec_from_file_location("stb_hidden_" + str(abs(hash(path))), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    suite = unittest.defaultTestLoader.loadTestsFromModule(mod)
except BaseException:
    out["import_error"] = traceback.format_exc()[-2000:]
    print("@@STB@@" + json.dumps(out))
    sys.exit(0)

class R(unittest.TestResult):
    def _key(self, t):
        return "%s.%s" % (type(t).__name__, getattr(t, "_testMethodName", str(t)))
    def addSuccess(self, t):
        out["tests"].setdefault(self._key(t), "pass")
    def addFailure(self, t, e):
        out["tests"][self._key(t)] = "fail"
    def addError(self, t, e):
        out["tests"][self._key(t)] = "error"
    def addSkip(self, t, r):
        out["tests"][self._key(t)] = "skip"
    def addExpectedFailure(self, t, e):
        out["tests"][self._key(t)] = "fail"
    def addUnexpectedSuccess(self, t):
        out["tests"][self._key(t)] = "fail"
    def addSubTest(self, t, s, e):
        if e is not None:
            out["tests"][self._key(t)] = "fail"

suite.run(R())
print("@@STB@@" + json.dumps(out))
'''


def count_test_methods(path: Path) -> int:
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return 0
    n = 0
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test"):
                    n += 1
    return n


def run_test_files(root: Path, files: list, python: str, timeout: int) -> dict:
    runner = root / "_stb_runner.py"
    runner.write_text(RUNNER)
    results = {}
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["TZ"] = "UTC"
    env["LC_ALL"] = "C.UTF-8" if sys.platform != "darwin" else "en_US.UTF-8"
    for f in files:
        expected = count_test_methods(f)
        rec = {"file": f.name, "expected": expected, "passed": 0, "total": expected, "status": "ok", "detail": None}
        try:
            proc = subprocess.run([python, str(runner), str(root), str(f)], cwd=str(root), env=env,
                                  capture_output=True, text=True, timeout=timeout)
            line = next((l for l in proc.stdout.splitlines()[::-1] if l.startswith("@@STB@@")), None)
            if line is None:
                rec["status"] = "crash"
                rec["detail"] = (proc.stderr or proc.stdout)[-1500:]
            else:
                data = json.loads(line[len("@@STB@@"):])
                if data.get("import_error"):
                    rec["status"] = "import_error"
                    rec["detail"] = data["import_error"]
                else:
                    tests = data["tests"]
                    rec["passed"] = sum(1 for v in tests.values() if v == "pass")
                    rec["total"] = max(expected, len(tests))
                    rec["failed"] = sorted(k for k, v in tests.items() if v != "pass")
        except subprocess.TimeoutExpired:
            rec["status"] = "timeout"
            rec["detail"] = "file exceeded %ss" % timeout
        results[f.name] = rec
    runner.unlink()
    return results


def summarize(results: dict, workstreams: list) -> dict:
    passed = sum(r["passed"] for r in results.values())
    total = sum(r["total"] for r in results.values())
    by_ws = {}
    for name, r in results.items():
        ws = "other"
        for w in workstreams:
            if name.startswith("test_%s_" % w) or name == "test_%s.py" % w:
                ws = w
                break
        b = by_ws.setdefault(ws, {"passed": 0, "total": 0})
        b["passed"] += r["passed"]
        b["total"] += r["total"]
    problems = {n: {"status": r["status"], "detail": (r.get("detail") or "")[:600]}
                for n, r in results.items() if r["status"] != "ok"}
    return {"passed": passed, "total": total, "rate": (passed / total) if total else 0.0,
            "by_workstream": by_ws, "problems": problems,
            "failed_tests": {n: r.get("failed", []) for n, r in results.items() if r.get("failed")}}


def score_workspace(workspace: Path, task_id: str, python: str) -> dict:
    task = load_task(task_id)
    tdir = task["_dir"]
    timeout = int(task.get("hidden_file_timeout_s", 120))
    workstreams = task.get("workstreams", [])
    t0 = time.time()
    tests_modified = tree_hash(workspace / "tests") != tree_hash(tdir / "starter" / "tests")
    with tempfile.TemporaryDirectory(prefix="stb-score-") as tmp:
        root = Path(tmp) / "ws"
        shutil.copytree(str(workspace), str(root), symlinks=True,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "node_modules", ".venv",
                                                      "tests_hidden"))
        if (root / "tests").exists():
            shutil.rmtree(str(root / "tests"))
        shutil.copytree(str(tdir / "starter" / "tests"), str(root / "tests"))
        shutil.copytree(str(tdir / "hidden"), str(root / "tests_hidden"))
        hidden_files = sorted((root / "tests_hidden").glob("test_*.py"))
        visible_files = sorted((root / "tests").glob("test_*.py"))
        hidden = summarize(run_test_files(root, hidden_files, python, timeout), workstreams)
        visible = summarize(run_test_files(root, visible_files, python, timeout), [])
    return {"task": task_id, "workspace": str(workspace), "scored_at": now_iso(),
            "python": python, "duration_s": round(time.time() - t0, 1),
            "tests_modified": tests_modified, "hidden": hidden, "visible": visible}


# --------------------------------------------------------------------------------------
# Cost (phi session files)
# --------------------------------------------------------------------------------------


def session_roots(extra: list) -> list:
    roots = [Path(p).expanduser() for p in extra]
    env_sd = os.environ.get("PI_CODING_AGENT_SESSION_DIR", "").strip()
    if env_sd:
        roots.append(Path(env_sd).expanduser())
    env_ad = os.environ.get("PI_CODING_AGENT_DIR", "").strip()
    if env_ad:
        roots.append(Path(env_ad).expanduser() / "sessions")
    roots.append(Path.home() / ".pi" / "agent" / "sessions")
    seen, out = set(), []
    for r in roots:
        r = r.resolve()
        if r not in seen and r.is_dir():
            seen.add(r)
            out.append(r)
    return out


def phi_slug(path: Path) -> str:
    text = str(path)
    text = re.sub(r"^[/\\]", "", text)
    return "--" + re.sub(r"[/\\:]", "-", text)


def within(child: str, parent: str) -> bool:
    child = os.path.realpath(child)
    parent = os.path.realpath(parent)
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


def find_sessions(workspace: Path, roots: list, since: float | None) -> list:
    """Session files whose header cwd is the workspace or inside it."""
    real = Path(os.path.realpath(str(workspace)))
    prefix = phi_slug(real)
    found = []
    for r in roots:
        candidates = []
        for d in r.iterdir():
            if d.is_dir() and d.name.startswith(prefix):
                candidates.extend(d.glob("*.jsonl"))
        # explicit roots may hold session files directly
        candidates.extend(r.glob("*.jsonl"))
        for f in candidates:
            try:
                with open(f, "r") as fh:
                    header = json.loads(fh.readline())
            except (OSError, ValueError):
                continue
            if header.get("type") != "session":
                continue
            if not within(header.get("cwd", ""), str(real)):
                continue
            started = parse_ts(header.get("timestamp"))
            if since is not None and started is not None and started < since - 120:
                continue
            found.append(f)
    return sorted(set(found))


def family_of(model: str) -> str | None:
    for alias, spec in MODELS.items():
        if re.search(spec["version"], model or "", re.I):
            return alias
    return None


def price_message(fam: str | None, model: str, usage: dict) -> float | None:
    """List price for the exact model version the bench expects; None -> use reported cost."""
    if fam is None or fam not in MODELS:
        return None
    if not re.search(MODELS[fam]["version"], model or "", re.I):
        return None
    rates = MODELS[fam]["price"]
    inp = usage.get("input", 0) or 0
    cr = usage.get("cacheRead", 0) or 0
    cw = usage.get("cacheWrite", 0) or 0
    cw1h = usage.get("cacheWrite1h", 0) or 0
    total_in = inp + cr + cw
    for tier in rates.get("tiers", []):
        if total_in > tier["inputTokensAbove"]:
            rates = tier
    out = usage.get("output", 0) or 0
    return (rates["input"] * inp + rates["output"] * out + rates["cacheRead"] * cr
            + rates["cacheWrite"] * (cw - cw1h) + rates["input"] * 2 * cw1h) / 1e6


def read_session(path: Path) -> dict:
    s = {"file": str(path), "started": None, "ended": None, "models": {}, "efforts": [],
         "messages": 0, "tokens": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
         "cost_list": 0.0, "cost_reported": 0.0, "unpriced_messages": 0, "tool_turns": 0}
    effort = None
    with open(path, "r") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            t = rec.get("type")
            if t == "session":
                s["started"] = parse_ts(rec.get("timestamp"))
                s["cwd"] = rec.get("cwd")
                s["id"] = rec.get("id")
                continue
            if t == "thinking_level_change":
                effort = rec.get("thinkingLevel")
                if effort and effort not in s["efforts"]:
                    s["efforts"].append(effort)
                continue
            if t == "model_change":
                continue
            msg = rec.get("message") if t == "message" else None
            if not msg or msg.get("role") != "assistant" or not msg.get("usage"):
                continue
            u = msg["usage"]
            model = msg.get("model") or msg.get("responseModel") or ""
            fam = family_of(model)
            s["messages"] += 1
            if msg.get("stopReason") == "toolUse":
                s["tool_turns"] += 1
            for k in s["tokens"]:
                s["tokens"][k] += u.get(k, 0) or 0
            mk = "%s/%s" % (msg.get("provider", "?"), model)
            s["models"][mk] = s["models"].get(mk, 0) + 1
            c = price_message(fam, model, u)
            reported = (u.get("cost") or {}).get("total", 0) or 0
            s["cost_reported"] += reported
            if c is None:
                s["unpriced_messages"] += 1
                c = reported
            s["cost_list"] += c
            ts = parse_ts(rec.get("timestamp")) or parse_ts(msg.get("timestamp"))
            if ts is not None:
                s["ended"] = max(s["ended"] or ts, ts)
    top_model = max(s["models"], key=s["models"].get) if s["models"] else ""
    s["model"] = top_model
    s["family"] = family_of(top_model)
    s["effort"] = s["efforts"][-1] if s["efforts"] else None
    return s


def attribute_tiers(sessions: list, arm_id: str | None) -> None:
    """Tag each session with L0/L1/L2 by (model family, effort) against the arm's tiers.

    The earliest session is the root. Sessions that fit no tier are "off-policy"."""
    if not sessions:
        return
    sessions.sort(key=lambda s: s["started"] or 0)
    if not arm_id:
        for s in sessions:
            s["tier"] = "?"
        return
    tiers = ARMS[arm_id]["tiers"]
    root_fam, root_eff = tiers[0]
    roots = [s for s in sessions if s["family"] == root_fam and s["effort"] in (None, root_eff)] \
        or [s for s in sessions if s["family"] == root_fam]
    root = roots[0] if roots else None
    for s in sessions:
        if s is root:
            s["tier"] = "L0"
            if s["effort"] and s["effort"] != root_eff:
                s["tier_note"] = "root effort %s, expected %s" % (s["effort"], root_eff)
            continue
        match = None
        for level in range(1, len(tiers)):
            fam, eff = tiers[level]
            if s["family"] == fam and (s["effort"] is None or s["effort"] == eff):
                match = level
                break
        if match is None:
            # right family, wrong effort -> still the tier, but flagged
            for level in range(1, len(tiers)):
                if s["family"] == tiers[level][0]:
                    match = level
                    s["tier_note"] = "effort %s, expected %s" % (s["effort"], tiers[level][1])
                    break
        if match is not None:
            s["tier"] = TIER_NAMES[match]
        elif s["tool_turns"] == 0 and s["messages"] <= 3:
            s["tier"] = "helper"  # harness side-calls (titles, summaries): priced, not flagged
        else:
            s["tier"] = "off-policy"


def cost_workspace(workspace: Path, arm_id: str | None, since: float | None, extra_roots: list) -> dict:
    files = find_sessions(workspace, session_roots(extra_roots), since)
    sessions = [read_session(f) for f in files]
    sessions = [s for s in sessions if s["messages"] > 0]
    attribute_tiers(sessions, arm_id)
    by_tier, by_family = {}, {}
    for s in sessions:
        for key, bucket in ((s["tier"], by_tier), (s["family"] or "unknown", by_family)):
            b = bucket.setdefault(key, {"sessions": 0, "cost": 0.0, "input": 0, "output": 0,
                                        "cacheRead": 0, "cacheWrite": 0})
            b["sessions"] += 1
            b["cost"] += s["cost_list"]
            for k in ("input", "output", "cacheRead", "cacheWrite"):
                b[k] += s["tokens"][k]
    starts = [s["started"] for s in sessions if s["started"]]
    ends = [s["ended"] for s in sessions if s["ended"]]
    span = (max(ends) - min(starts)) if starts and ends else None
    return {
        "workspace": str(workspace), "arm": arm_id, "computed_at": now_iso(),
        "session_files": len(files), "sessions": [
            {k: s.get(k) for k in ("file", "tier", "tier_note", "model", "family", "effort", "messages",
                                   "tokens", "cost_list", "cost_reported", "unpriced_messages",
                                   "started", "ended")} for s in sessions],
        "total_cost": sum(s["cost_list"] for s in sessions),
        "reported_cost": sum(s["cost_reported"] for s in sessions),
        "by_tier": by_tier, "by_family": by_family,
        "off_policy_sessions": sum(1 for s in sessions if s["tier"] == "off-policy"),
        "session_span_s": round(span, 1) if span is not None else None,
    }


# --------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------


def cmd_list(args) -> None:
    print("tasks:")
    for t in task_ids():
        m = load_task(t)
        print("  %-14s %-18s %s" % (t, m.get("shape", ""), m.get("title", "")))
    print("\narms (tiers top-down):")
    for a, spec in ARMS.items():
        chain = " -> ".join("%s:%s" % (MODELS[f]["phi"], e) for f, e in spec["tiers"])
        tag = "core" if a in CORE_ARMS else "extra"
        print("  %-20s [%s] %s" % (a, tag, chain))
    print("\nsuites:")
    for s, (tasks, arms, reps) in SUITES.items():
        n = len(tasks or task_ids()) * len(arms) * reps
        print("  %-9s %d runs (%s tasks x %d arms x %d reps)" % (s, n, len(tasks or task_ids()), len(arms), reps))


def plan_runs(suite: str, arms_override=None, reps_override=None, tasks_override=None) -> list:
    tasks, arms, reps = SUITES[suite]
    tasks = tasks_override or tasks or task_ids()
    arms = arms_override or arms
    reps = reps_override or reps
    rng = random.Random("stb-" + suite)
    runs = []
    for rep in range(1, reps + 1):
        block = [(t, a, rep) for t in tasks for a in arms]
        rng.shuffle(block)
        runs.extend(block)
    return runs


def cmd_plan(args) -> None:
    arms = args.arms.split(",") if args.arms else None
    for a in arms or []:
        arm_or_die(a)
    tasks = args.tasks.split(",") if args.tasks else None
    runs = plan_runs(args.suite, arms, args.reps, tasks)
    for i, (t, a, r) in enumerate(runs, 1):
        print("%3d  %-12s %-20s rep %d" % (i, t, a, r))


def cmd_prompt(args) -> None:
    arm_or_die(args.arm)
    sys.stdout.write(compose_prompt(args.task, args.arm))


def cmd_setup(args) -> None:
    root = root_dir(args)
    arm = arm_or_die(args.arm)
    task = load_task(args.task)
    run_id = "%s__%s__r%d__%s" % (args.task, args.arm, args.rep, uuid.uuid4().hex[:6])
    run_dir = root / "runs" / run_id
    mdir = meta_dir(root, run_id)
    mdir.mkdir(parents=True)
    shutil.copytree(str(task["_dir"] / "starter"), str(run_dir))
    subprocess.run(["git", "init", "-q"], cwd=str(run_dir), check=False)
    subprocess.run(["git", "add", "-A"], cwd=str(run_dir), check=False)
    subprocess.run(["git", "-c", "user.name=stb", "-c", "user.email=stb@localhost", "commit", "-qm",
                    "starter"], cwd=str(run_dir), check=False)
    prompt = compose_prompt(args.task, args.arm)
    (mdir / "prompt.md").write_text(prompt)
    fam, effort = arm["tiers"][0]
    meta = {"run_id": run_id, "task": args.task, "arm": args.arm, "rep": args.rep,
            "run_dir": str(run_dir), "created_at": now_iso(), "created_ts": time.time(),
            "root_model": MODELS[fam]["phi"], "root_model_label": MODELS[fam]["label"],
            "root_effort": effort, "harness": args.harness, "time_limit_min": time_limit(task)}
    (mdir / "meta.json").write_text(json.dumps(meta, indent=2))
    out = dict(meta)
    out["prompt_file"] = str(mdir / "prompt.md")
    print(json.dumps(out, indent=2))


def cmd_score(args) -> None:
    root = root_dir(args)
    if args.run:
        meta = load_run(root, args.run)
        ws, task = Path(meta["run_dir"]), meta["task"]
    else:
        if not (args.dir and args.task):
            die("score needs --run, or --dir and --task")
        ws, task = Path(args.dir).expanduser().resolve(), args.task
    result = score_workspace(ws, task, args.python)
    if args.run:
        (meta_dir(root, args.run) / "score.json").write_text(json.dumps(result, indent=2))
    h, v = result["hidden"], result["visible"]
    print("hidden  %d/%d = %.1f%%" % (h["passed"], h["total"], 100 * h["rate"]))
    for ws_name, b in sorted(h["by_workstream"].items()):
        print("  %-10s %d/%d" % (ws_name, b["passed"], b["total"]))
    print("visible %d/%d = %.1f%%" % (v["passed"], v["total"], 100 * v["rate"]))
    if result["tests_modified"]:
        print("note: tests/ was modified in the workspace (pristine copy used for grading)")
    for name, p in h["problems"].items():
        print("problem %s: %s" % (name, p["status"]))
    if args.verbose:
        for name, failed in h["failed_tests"].items():
            print("  %s: %s" % (name, ", ".join(failed)))


def cmd_cost(args) -> None:
    root = root_dir(args)
    if args.run:
        meta = load_run(root, args.run)
        ws, arm, since = Path(meta["run_dir"]), meta["arm"], meta.get("created_ts")
    else:
        if not args.dir:
            die("cost needs --run or --dir")
        ws, arm, since = Path(args.dir).expanduser().resolve(), args.arm, None
        if arm:
            arm_or_die(arm)
    result = cost_workspace(ws, arm, since, args.sessions or [])
    if args.run:
        (meta_dir(root, args.run) / "cost.json").write_text(json.dumps(result, indent=2))
    print("sessions %d, configured-price cost $%.2f (provider-reported $%.2f)"
          % (len(result["sessions"]), result["total_cost"], result["reported_cost"]))
    for tier, b in sorted(result["by_tier"].items()):
        print("  %-10s %3d sessions  $%8.2f  in %9d  out %8d  cache r/w %d/%d"
              % (tier, b["sessions"], b["cost"], b["input"], b["output"], b["cacheRead"], b["cacheWrite"]))
    for s in result["sessions"]:
        if s.get("tier_note") or s["tier"] == "off-policy":
            print("  ! %s %s %s: %s" % (s["tier"], s["model"], s["effort"], s.get("tier_note") or ""))


def cmd_finish(args) -> None:
    root = root_dir(args)
    meta = load_run(root, args.run)
    ws = Path(meta["run_dir"])
    mdir = meta_dir(root, args.run)
    score = score_workspace(ws, meta["task"], args.python)
    (mdir / "score.json").write_text(json.dumps(score, indent=2))
    cost = cost_workspace(ws, meta["arm"], meta.get("created_ts"), args.sessions or [])
    (mdir / "cost.json").write_text(json.dumps(cost, indent=2))
    task = load_task(meta["task"])
    base = task.get("starter_hidden_pass")
    rate = score["hidden"]["rate"]
    gain = None
    if base is not None and base < 1:
        gain = (rate - base) / (1 - base)
    wall = args.wall_s if args.wall_s is not None else cost.get("session_span_s")
    row = {
        "run_id": meta["run_id"], "task": meta["task"], "arm": meta["arm"], "rep": meta["rep"],
        "status": args.status, "harness": meta.get("harness"), "finished_at": now_iso(),
        "wall_s": wall, "hidden_passed": score["hidden"]["passed"], "hidden_total": score["hidden"]["total"],
        "hidden_rate": rate, "norm_gain": gain, "visible_rate": score["visible"]["rate"],
        "by_workstream": score["hidden"]["by_workstream"], "tests_modified": score["tests_modified"],
        "cost": cost["total_cost"], "cost_reported": cost["reported_cost"],
        "cost_by_tier": {k: round(v["cost"], 4) for k, v in cost["by_tier"].items()},
        "sessions_by_tier": {k: v["sessions"] for k, v in cost["by_tier"].items()},
        "output_tokens_by_tier": {k: v["output"] for k, v in cost["by_tier"].items()},
        "off_policy_sessions": cost["off_policy_sessions"], "note": args.note or "",
    }
    jf = mdir / "judge.json"
    if jf.exists():
        jd = json.loads(jf.read_text())
        row["judge"] = {k: jd.get(k) for k in JUDGE_KEYS}
    results = root / "results.jsonl"
    rows = []
    if results.exists():
        rows = [json.loads(l) for l in results.read_text().splitlines() if l.strip()]
        rows = [r for r in rows if r["run_id"] != row["run_id"]]
    rows.append(row)
    results.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(json.dumps({k: row[k] for k in ("run_id", "status", "hidden_rate", "cost", "wall_s",
                                          "sessions_by_tier", "off_policy_sessions")}, indent=2))
    total = sum(r["cost"] for r in rows)
    print("cumulative bench spend: $%.2f over %d runs" % (total, len(rows)))


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def _sd(xs):
    xs = [x for x in xs if x is not None]
    return statistics.stdev(xs) if len(xs) > 1 else None


def _fmt_pct(x):
    return "-" if x is None else "%.1f" % (100 * x)


def _fmt_usd(x):
    return "-" if x is None else "$%.2f" % x


JUDGE_RUBRIC = """\
You are a senior engineer doing a blind code review of one solution to the task below. Hidden
unit tests already grade behaviour, so do not re-derive test results. Judge the code itself:
the change shown as a unified diff against the starter project.

Score each criterion from 1 (poor) to 10 (excellent):
- design: sensible decomposition, clear data model, no needless complexity.
- consistency: one coherent codebase rather than pieces stitched together (shared helpers
  reused, one error-handling style, one naming style, no duplicated logic across modules).
- robustness: edge cases and failure paths handled beyond what the brief's examples show.
- readability: names, structure and comments a maintainer can follow.
- fit: respects the existing code, public API and conventions the task required.
- overall: your holistic judgement (not an average).

Reply with exactly one line of JSON and nothing else:
{"design": n, "consistency": n, "robustness": n, "readability": n, "fit": n, "overall": n, "notes": "<= 40 words"}
"""

JUDGE_KEYS = ("design", "consistency", "robustness", "readability", "fit", "overall")


def cmd_judge_pack(args) -> None:
    root = root_dir(args)
    meta = load_run(root, args.run)
    task = load_task(meta["task"])
    ws = Path(meta["run_dir"])
    with tempfile.TemporaryDirectory(prefix="stb-judge-") as tmp:
        a = Path(tmp) / "a"
        b = Path(tmp) / "b"
        ign = shutil.ignore_patterns(".git", "__pycache__", "tests", "tests_hidden", "*.pyc")
        shutil.copytree(str(task["_dir"] / "starter"), str(a), ignore=ign)
        shutil.copytree(str(ws), str(b), ignore=ign)
        proc = subprocess.run(["git", "diff", "--no-index", "--no-color", "-U3", "a", "b"],
                              cwd=tmp, capture_output=True, text=True)
        diff = proc.stdout
    brief = (task["_dir"] / "brief.md").read_text().strip()
    text = (JUDGE_RUBRIC + "\n## Task brief\n\n" + brief +
            "\n\n## The change (diff from starter to solution; tests/ excluded)\n\n```diff\n" + diff + "```\n")
    out = meta_dir(root, args.run) / "judge.md"
    out.write_text(text)
    print(json.dumps({"run_id": args.run, "judge_prompt_file": str(out),
                      "diff_lines": diff.count("\n"), "judge_model": MODELS["opus"]["phi"],
                      "judge_effort": "high"}, indent=2))


def cmd_judge_record(args) -> None:
    root = root_dir(args)
    load_run(root, args.run)
    raw = Path(args.file).read_text() if args.file else args.json
    if not raw:
        die("judge-record needs --json or --file")
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        die("no JSON object found in the judge reply")
    data = json.loads(match.group(0))
    for k in JUDGE_KEYS:
        if not isinstance(data.get(k), (int, float)) or not 1 <= data[k] <= 10:
            die("judge reply needs %s as a number from 1 to 10" % k)
    (meta_dir(root, args.run) / "judge.json").write_text(json.dumps(data, indent=2))
    results = root / "results.jsonl"
    if results.exists():
        rows = [json.loads(l) for l in results.read_text().splitlines() if l.strip()]
        for r in rows:
            if r["run_id"] == args.run:
                r["judge"] = {k: data[k] for k in JUDGE_KEYS}
        results.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print("recorded judge scores for %s: overall %s" % (args.run, data["overall"]))


def cmd_report(args) -> None:
    root = root_dir(args)
    results = root / "results.jsonl"
    if not results.exists():
        die("no results yet at %s" % results)
    rows = [json.loads(l) for l in results.read_text().splitlines() if l.strip()]
    graded = [r for r in rows if r["status"] in ("ok", "timeout")]
    tasks = sorted({r["task"] for r in graded})
    arms = [a for a in ARMS if any(r["arm"] == a for r in graded)]
    lines = ["# subagent-tier-bench results", "",
             "Generated %s from %d graded runs (%d rows total; infra/error rows excluded). "
             "Quality = hidden-test pass rate (%%). Cost = configured price recomputed from tokens."
             % (now_iso(), len(graded), len(rows)), ""]

    # per-arm summary, averaged per task first so tasks weigh equally
    def arm_stats(arm):
        per_task_q, per_task_c, per_task_w = [], [], []
        for t in tasks:
            rs = [r for r in graded if r["arm"] == arm and r["task"] == t]
            if not rs:
                continue
            per_task_q.append(_mean([r["hidden_rate"] for r in rs]))
            per_task_c.append(_mean([r["cost"] for r in rs]))
            per_task_w.append(_mean([r["wall_s"] for r in rs]))
        rs = [r for r in graded if r["arm"] == arm]
        tier_cost = {}
        for r in rs:
            for k, v in r["cost_by_tier"].items():
                tier_cost[k] = tier_cost.get(k, 0) + v
        tot = sum(tier_cost.values()) or 1
        sess = {}
        for r in rs:
            for k, v in r["sessions_by_tier"].items():
                sess[k] = sess.get(k, 0) + v
        return {
            "runs": len(rs), "tasks": len(per_task_q), "q": _mean(per_task_q),
            "q_sd": _sd([r["hidden_rate"] for r in rs]), "cost": _mean(per_task_c),
            "wall": _mean(per_task_w),
            "tier_share": {k: v / tot for k, v in tier_cost.items()},
            "sess": {k: v / len(rs) for k, v in sess.items()} if rs else {},
            "timeouts": sum(1 for r in rs if r["status"] == "timeout"),
            "offp": sum(r["off_policy_sessions"] for r in rs),
            "complete": len(per_task_q) == len(tasks),
            "judge": _mean([r["judge"]["overall"] for r in rs if r.get("judge")]),
            "judge_consistency": _mean([r["judge"]["consistency"] for r in rs if r.get("judge")]),
            "judged": sum(1 for r in rs if r.get("judge")),
        }

    stats = {a: arm_stats(a) for a in arms}
    base = stats.get(BASELINE_ARM)
    lines += ["## Arms (tasks weighted equally)", "",
              "| arm | runs | quality %% | sd | review /10 (consistency) | mean cost | cost vs %s | wall min | cost share L0/L1/L2 | agents/run L0/L1/L2 | off-policy | timeouts |" % BASELINE_ARM,
              "|---|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---:|"]
    for a in arms:
        s = stats[a]
        rel = "-" if not base or not base["cost"] or s["cost"] is None else "%.2fx" % (s["cost"] / base["cost"])
        share = "/".join("%.0f%%" % (100 * s["tier_share"].get(t, 0)) for t in TIER_NAMES[:len(ARMS[a]["tiers"])])
        sess = "/".join("%.1f" % s["sess"].get(t, 0) for t in TIER_NAMES[:len(ARMS[a]["tiers"])])
        review = "-" if s["judge"] is None else "%.1f (%.1f)%s" % (
            s["judge"], s["judge_consistency"], "" if s["judged"] == s["runs"] else " n=%d" % s["judged"])
        lines.append("| %s%s | %d | %s | %s | %s | %s | %s | %s | %s | %s | %d | %d |" % (
            a, "" if s["complete"] else " (partial)", s["runs"], _fmt_pct(s["q"]),
            _fmt_pct(s["q_sd"]), review, _fmt_usd(s["cost"]), rel,
            "-" if s["wall"] is None else "%.0f" % (s["wall"] / 60), share, sess, s["offp"], s["timeouts"]))
    lines.append("")

    # per task matrix
    lines += ["## Quality % and cost per task", "", "| arm | " + " | ".join(tasks) + " |",
              "|---|" + "---:|" * len(tasks)]
    for a in arms:
        cells = []
        for t in tasks:
            rs = [r for r in graded if r["arm"] == a and r["task"] == t]
            if not rs:
                cells.append("-")
                continue
            cells.append("%s / %s" % (_fmt_pct(_mean([r["hidden_rate"] for r in rs])),
                                      _fmt_usd(_mean([r["cost"] for r in rs]))))
        lines.append("| %s | %s |" % (a, " | ".join(cells)))
    lines.append("")

    # pareto frontier
    pts = [(a, stats[a]["cost"], stats[a]["q"]) for a in arms
           if stats[a]["complete"] and stats[a]["cost"] is not None and stats[a]["q"] is not None]
    frontier = [a for a, c, q in pts
                if not any((c2 <= c and q2 >= q) and (c2 < c or q2 > q) for _, c2, q2 in pts)]
    lines += ["## Cost-quality frontier", "",
              "Arms no other arm beats on both cost and quality: " + (", ".join(frontier) or "-"), ""]

    # verdicts
    lines += ["## Verdict per hierarchical arm", "",
              "Rule: WIN if quality is within 3 points of `%s` at no more than half its cost; "
              "CHEAPER-BUT-WORSE if it saves at least half the cost but loses more than 3 points; "
              "NO-SAVINGS if it costs more than 0.8x; otherwise MIXED." % BASELINE_ARM, ""]
    for a in arms:
        if not a.startswith("h-"):
            continue
        s = stats[a]
        if not base or base["cost"] is None or s["cost"] is None or not s["complete"] or not base["complete"]:
            lines.append("- `%s`: not enough data (needs every task for it and `%s`)" % (a, BASELINE_ARM))
            continue
        dq = 100 * (s["q"] - base["q"])
        ratio = s["cost"] / base["cost"] if base["cost"] else float("inf")
        if ratio > 0.8:
            v = "NO-SAVINGS"
        elif dq >= -3 and ratio <= 0.5:
            v = "WIN"
        elif ratio <= 0.5:
            v = "CHEAPER-BUT-WORSE"
        else:
            v = "MIXED"
        lines.append("- `%s`: **%s** (quality %+.1f pts, cost %.2fx of %s)" % (a, v, dq, ratio, BASELINE_ARM))
    lines.append("")

    # workstream breakdown
    wss = sorted({w for r in graded for w in r.get("by_workstream", {})})
    if wss:
        lines += ["## Quality % by workstream (all tasks pooled)", "",
                  "| arm | " + " | ".join(wss) + " |", "|---|" + "---:|" * len(wss)]
        for a in arms:
            cells = []
            for w in wss:
                p = sum(r["by_workstream"].get(w, {}).get("passed", 0) for r in graded if r["arm"] == a)
                t = sum(r["by_workstream"].get(w, {}).get("total", 0) for r in graded if r["arm"] == a)
                cells.append(_fmt_pct(p / t) if t else "-")
            lines.append("| %s | %s |" % (a, " | ".join(cells)))
        lines.append("")

    flagged = [r for r in rows if r["status"] not in ("ok", "timeout") or r["tests_modified"] or r["off_policy_sessions"]]
    if flagged:
        lines += ["## Flags", ""]
        for r in flagged:
            bits = []
            if r["status"] not in ("ok", "timeout"):
                bits.append("status " + r["status"])
            if r["tests_modified"]:
                bits.append("edited tests/")
            if r["off_policy_sessions"]:
                bits.append("%d off-policy sessions" % r["off_policy_sessions"])
            lines.append("- %s: %s %s" % (r["run_id"], ", ".join(bits), r.get("note", "")))
        lines.append("")
    lines.append("Total bench spend (all rows): $%.2f" % sum(r["cost"] for r in rows))
    out = root / "results.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nwrote %s" % out)


def cmd_selftest(args) -> None:
    ids = [args.task] if args.task else task_ids()
    if not ids:
        die("no tasks found under %s" % TASKS_DIR)
    ok = True
    for t in ids:
        task = load_task(t)
        tdir = task["_dir"]
        problems = []
        for rel in ("brief.md", "starter/tests/__init__.py", "hidden"):
            if not (tdir / rel).exists():
                problems.append("missing " + rel)
        hidden = sorted((tdir / "hidden").glob("test_*.py"))
        visible = sorted((tdir / "starter" / "tests").glob("test_*.py"))
        nh = sum(count_test_methods(f) for f in hidden)
        nv = sum(count_test_methods(f) for f in visible)
        for f in hidden:
            if not any(f.name.startswith("test_%s_" % w) for w in task.get("workstreams", [])):
                problems.append("hidden file %s matches no workstream" % f.name)
        res = score_workspace(tdir / "starter", t, args.python)
        base = res["hidden"]["rate"]
        print("%-12s hidden %3d tests in %d files, visible %3d; starter hidden pass %.1f%%, visible %.1f%%, %.1fs"
              % (t, nh, len(hidden), nv, 100 * base, 100 * res["visible"]["rate"], res["duration_s"]))
        for name, p in res["hidden"]["problems"].items():
            if p["status"] == "timeout":
                problems.append("starter hidden file %s timed out" % name)
        if problems:
            ok = False
            for p in problems:
                print("  ! " + p)
        if args.write:
            meta_file = tdir / "task.json"
            meta = json.loads(meta_file.read_text())
            meta["starter_hidden_pass"] = round(base, 4)
            meta["hidden_tests"] = nh
            meta["visible_tests"] = nv
            meta_file.write_text(json.dumps(meta, indent=2) + "\n")
    print("model check: configured ids used by arms ->",
          ", ".join(sorted({MODELS[f]["phi"] for a in ARMS.values() for f, _ in a["tiers"]})))
    sys.exit(0 if ok else 1)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", help="runs root (default $STB_ROOT or ~/stb-runs)")
    p.add_argument("--config", default=os.environ.get("STB_CONFIG", str(REPO / "models.json")),
                   help="model aliases and prices JSON (default: ./models.json or $STB_CONFIG)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list").set_defaults(fn=cmd_list)

    sp = sub.add_parser("plan")
    sp.add_argument("--suite", choices=list(SUITES), default="core")
    sp.add_argument("--arms", help="comma-separated arm override")
    sp.add_argument("--tasks", help="comma-separated task override")
    sp.add_argument("--reps", type=int)
    sp.set_defaults(fn=cmd_plan)

    sp = sub.add_parser("prompt")
    sp.add_argument("--task", required=True)
    sp.add_argument("--arm", required=True)
    sp.set_defaults(fn=cmd_prompt)

    sp = sub.add_parser("setup")
    sp.add_argument("--task", required=True)
    sp.add_argument("--arm", required=True)
    sp.add_argument("--rep", type=int, default=1)
    sp.add_argument("--harness", default="generic", help="adapter label (generic, phi, p3, ...)")
    sp.set_defaults(fn=cmd_setup)

    for name, fn in (("score", cmd_score), ("cost", cmd_cost)):
        sp = sub.add_parser(name)
        sp.add_argument("--run")
        sp.add_argument("--dir")
        sp.add_argument("--task")
        sp.add_argument("--arm")
        sp.add_argument("--python", default=sys.executable)
        sp.add_argument("--sessions", action="append", help="extra phi sessions root (repeatable)")
        sp.add_argument("-v", "--verbose", action="store_true")
        sp.set_defaults(fn=fn)

    sp = sub.add_parser("finish")
    sp.add_argument("--run", required=True)
    sp.add_argument("--status", required=True, choices=["ok", "timeout", "error", "infra"])
    sp.add_argument("--wall-s", type=float, dest="wall_s")
    sp.add_argument("--note")
    sp.add_argument("--python", default=sys.executable)
    sp.add_argument("--sessions", action="append")
    sp.set_defaults(fn=cmd_finish)

    sub.add_parser("report").set_defaults(fn=cmd_report)

    sp = sub.add_parser("judge-pack")
    sp.add_argument("--run", required=True)
    sp.set_defaults(fn=cmd_judge_pack)

    sp = sub.add_parser("judge-record")
    sp.add_argument("--run", required=True)
    sp.add_argument("--json", help="the judge's JSON reply")
    sp.add_argument("--file", help="file holding the judge's reply")
    sp.set_defaults(fn=cmd_judge_record)

    sp = sub.add_parser("selftest")
    sp.add_argument("--task")
    sp.add_argument("--write", action="store_true", help="store starter baseline + counts in task.json")
    sp.add_argument("--python", default=sys.executable)
    sp.set_defaults(fn=cmd_selftest)

    args = p.parse_args(argv)
    global MODELS
    MODELS = load_models(Path(args.config).expanduser())
    args.fn(args)


if __name__ == "__main__":
    main()
