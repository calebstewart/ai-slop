#!/usr/bin/env python3
"""End-to-end tests for skills/worktree/bin/wt.

Every test gets its own sandbox: a bare "origin", a clone of it as the project
root, a private WT_HOME (so the registry is fresh), fake `short` and `gh`
executables, and `sleep` processes standing in for Claude sessions. wt is always
run as a subprocess, exactly as a session or the editor would run it.

    python3 tests/test_wt.py            # or: python3 -m unittest tests.test_wt
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

WT = Path(__file__).resolve().parent.parent / "skills" / "worktree" / "bin" / "wt"

SETUP = """\
#!/bin/sh
set -eu
echo "setup $WT_NAME slot=$WT_SLOT warm=$WT_SLOT_WARM cwd=$PWD" >> "$RECORDS"
echo "TEST_ENV_NUMBER=$WT_SLOT" >> "$WT_ENV_OUT"
echo "PORT=$((10000 + WT_SLOT * 100))" >> "$WT_ENV_OUT"
"""

TEARDOWN = """\
#!/bin/sh
set -eu
echo "teardown name=$WT_NAME slot=$WT_SLOT mode=$WT_TEARDOWN_MODE dry=$WT_DRY_RUN env=${TEST_ENV_NUMBER:-} cwd=$PWD" >> "$RECORDS"
if [ "$WT_DRY_RUN" = 1 ]; then echo "would $WT_TEARDOWN_MODE slot $WT_SLOT"; fi
"""


class Sandbox(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp(prefix="wt-test-")))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.records = self.tmp / "records.log"
        self.records.touch()
        gitconfig = self.tmp / "gitconfig"
        gitconfig.write_text(
            "[user]\n\tname = Test\n\temail = test@example.com\n"
            "[init]\n\tdefaultBranch = main\n[advice]\n\tdetachedHead = false\n"
        )
        self.env = {
            k: v for k, v in os.environ.items() if not k.startswith(("WT_", "CLAUDE", "GIT_"))
        }
        self.env.update(
            HOME=str(self.tmp / "home"),
            WT_HOME=str(self.tmp / "wt-home"),
            CLAUDE_CONFIG_DIR=str(self.tmp / "claude"),
            GIT_CONFIG_GLOBAL=str(gitconfig),
            GIT_CONFIG_NOSYSTEM="1",
            PATH=f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}",
            WT_SHORT=str(self.bin / "short"),
            WT_GH=str(self.bin / "gh"),
            RECORDS=str(self.records),
            STORIES=str(self.tmp / "stories"),
            PRS=str(self.tmp / "prs"),
        )
        (self.tmp / "stories").mkdir()
        (self.tmp / "prs").mkdir()
        self.script(self.bin / "short", """\
            #!/bin/sh
            # short story ID -q -f FORMAT  -> "type<TAB>title" from $STORIES/ID
            f="$STORIES/$2"
            if [ ! -f "$f" ]; then echo "Story not found" >&2; exit 1; fi
            printf '\\033[2K\\033[1G'; cat "$f"
        """)
        self.script(self.bin / "gh", """\
            #!/bin/sh
            # gh pr view BRANCH --json ...  -> $PRS/<branch with / as __>.json
            f="$PRS/$(echo "$3" | sed 's#/#__#g').json"
            if [ ! -f "$f" ]; then echo "no pull requests found for branch \\"$3\\"" >&2; exit 1; fi
            cat "$f"
        """)

        self.origin = self.tmp / "origin.git"
        self.root = self.tmp / "proj"
        self.git(self.tmp, "init", "--quiet", "--bare", str(self.origin))
        self.git(self.tmp, "clone", "--quiet", str(self.origin), str(self.root))
        (self.root / "README").write_text("hello\n")
        self.git(self.root, "add", "README")
        self.git(self.root, "commit", "--quiet", "-m", "init")
        self.git(self.root, "push", "--quiet", "origin", "main")
        self.git(self.root, "remote", "set-head", "origin", "main")
        with open(self.root / ".git" / "info" / "exclude", "a") as fh:
            fh.write("/.claude/\n")
        self.hooks = self.root / ".claude" / "worktree"
        self.hooks.mkdir(parents=True)

    # -- helpers --------------------------------------------------------- #

    def git(self, cwd, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(cwd), *args], env=self.env, check=True, capture_output=True, text=True
        ).stdout

    def script(self, path: Path, body: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body))
        path.chmod(0o755)

    def hook(self, name: str, body: str) -> None:
        self.script(self.hooks / name, body)

    def config(self, text: str) -> None:
        (self.hooks / "config.toml").write_text(textwrap.dedent(text))

    def session(self) -> dict:
        proc = subprocess.Popen(["sleep", "600"])
        self.addCleanup(lambda: (proc.kill(), proc.wait()))
        return {"id": str(uuid.uuid4()), "pid": proc.pid, "proc": proc}

    def end(self, session: dict) -> None:
        session["proc"].kill()
        session["proc"].wait()

    def wt(self, *args: str, session: dict | None = None, cwd=None, check: bool | int = True,
           env: dict | None = None) -> subprocess.CompletedProcess:
        full_env = dict(self.env)
        if session:
            full_env.update(WT_SESSION_ID=session["id"], WT_PID=str(session["pid"]))
        if env:
            full_env.update(env)
        proc = subprocess.run(
            [sys.executable, str(WT), *args], cwd=cwd or self.root, env=full_env,
            capture_output=True, text=True, timeout=120,
        )
        want = 0 if check is True else check
        if check is not False and proc.returncode != want:
            self.fail(f"wt {' '.join(args)} exited {proc.returncode}, wanted {want}\n"
                      f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
        return proc

    def wtj(self, *args: str, **kw):
        return json.loads(self.wt(*args, "--json", **kw).stdout)

    def records_lines(self) -> list[str]:
        return self.records.read_text().splitlines()

    def sql(self, statement: str, *params):
        """Run one statement against the registry and return all rows (empty if no registry yet)."""
        path = Path(self.env["WT_HOME"]) / "registry.sqlite"
        if not path.exists():
            return []
        db = sqlite3.connect(path, timeout=30)
        try:
            with db:
                return db.execute(statement, params).fetchall()
        finally:
            db.close()

    def tree_path(self, name: str) -> Path:
        return self.root / ".claude" / "worktrees" / name


class NamingTests(Sandbox):
    def test_free_text_creates_typed_branch_and_name(self):
        info = self.wtj("new", "Fix the flaky dashboard spec")
        self.assertEqual(info["name"], "fix-the-flaky-dashboard-spec")
        self.assertEqual(info["branch"], "feature/fix-the-flaky-dashboard-spec")
        self.assertTrue(self.tree_path(info["name"]).is_dir())
        self.assertTrue(info["created_branch"])
        # --no-track: the new branch must not push to main by accident
        upstream = subprocess.run(
            ["git", "-C", info["path"], "rev-parse", "--abbrev-ref", "@{u}"],
            env=self.env, capture_output=True, text=True,
        )
        self.assertNotEqual(upstream.returncode, 0)

    def test_type_prefixed_text_is_a_branch_name(self):
        info = self.wtj("new", "bug/odd-thing")
        self.assertEqual((info["branch"], info["name"]), ("bug/odd-thing", "odd-thing"))

    def test_existing_local_branch(self):
        self.git(self.root, "branch", "chore/tidy-up")
        info = self.wtj("new", "chore/tidy-up")
        self.assertEqual((info["branch"], info["name"]), ("chore/tidy-up", "tidy-up"))
        self.assertFalse(info["created_branch"])

    def test_story_with_remote_branch_uses_it(self):
        self.git(self.root, "push", "--quiet", "origin", "main:refs/heads/bug/sc-4242-broken-thing")
        info = self.wtj("new", "sc-4242")
        self.assertEqual(info["branch"], "bug/sc-4242-broken-thing")
        self.assertEqual(info["name"], "sc-4242-broken-thing")
        self.assertEqual(info["story"], "sc-4242")
        upstream = self.git(info["path"], "rev-parse", "--abbrev-ref", "@{u}").strip()
        self.assertEqual(upstream, "origin/bug/sc-4242-broken-thing")

    def test_bare_story_number_and_story_inside_text(self):
        self.git(self.root, "branch", "feature/sc-5151-thing")
        self.assertEqual(self.wtj("new", "5151")["branch"], "feature/sc-5151-thing")
        self.git(self.root, "branch", "feature/sc-6161-other")
        self.assertEqual(self.wtj("new", "work on sc-6161 please")["branch"], "feature/sc-6161-other")

    def test_story_without_branch_is_looked_up(self):
        (self.tmp / "stories" / "777").write_text("chore\tTag render_data metrics with the pipeline name")
        info = self.wtj("new", "sc-777")
        self.assertEqual(info["branch"], "chore/sc-777-tag-render-data-metrics-with-the-pipeline-name")
        self.assertEqual(info["name"], "sc-777-tag-render-data-metrics-with-the-pipeline-name")

    def test_unknown_story_fails_cleanly(self):
        proc = self.wt("new", "sc-999", check=1)
        self.assertIn("could not look up story sc-999", proc.stderr)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM trees"), [(0,)])
        self.assertFalse((self.root / ".claude" / "worktrees").exists())

    def test_ambiguous_story_lists_branches(self):
        self.git(self.root, "branch", "feature/sc-31-a")
        self.git(self.root, "branch", "bug/sc-31-b")
        proc = self.wt("new", "sc-31", check=1)
        self.assertIn("bug/sc-31-b", proc.stderr)
        self.assertIn("feature/sc-31-a", proc.stderr)

    def test_story_id_prefix_is_not_a_match(self):
        # sc-31 must not match sc-310's branch
        self.git(self.root, "branch", "feature/sc-310-other")
        (self.tmp / "stories" / "31").write_text("feature\tThe real one")
        self.assertEqual(self.wtj("new", "sc-31")["branch"], "feature/sc-31-the-real-one")

    def test_branch_checked_out_elsewhere_is_refused(self):
        self.wtj("new", "bug/odd-thing")
        proc = self.wt("new", "bug/odd-thing", check=1)
        self.assertIn("already checked out", proc.stderr)
        self.assertIn("wt claim odd-thing", proc.stderr)


class SetupAndEnvTests(Sandbox):
    def setUp(self):
        super().setUp()
        self.hook("setup", SETUP)
        self.hook("teardown", TEARDOWN)

    def test_setup_env_is_stored_and_delivered(self):
        info = self.wtj("new", "alpha")
        self.assertEqual(info["state"], "ready")
        self.assertEqual(info["env"]["TEST_ENV_NUMBER"], str(info["slot"]))
        self.assertEqual(info["env"]["WT_NAME"], "alpha")
        self.assertIn(f"setup alpha slot=1 warm=0 cwd={info['path']}", self.records_lines())

        out = self.wt("env", "alpha").stdout
        self.assertIn("export TEST_ENV_NUMBER=1", out)

        ran = self.wt("exec", "alpha", "--", "sh", "-c", 'echo "$PWD $TEST_ENV_NUMBER $PORT"').stdout
        self.assertEqual(ran.strip(), f"{info['path']} 1 10100")

    def test_exec_infers_tree_from_session_and_cwd(self):
        s = self.session()
        info = self.wtj("new", "alpha", session=s)
        ran = self.wt("exec", "--", "sh", "-c", "echo $WT_NAME", session=s).stdout
        self.assertEqual(ran.strip(), "alpha")
        ran = self.wt("exec", "--", "sh", "-c", "echo $WT_NAME", cwd=info["path"]).stdout
        self.assertEqual(ran.strip(), "alpha")
        self.wt("exec", "--", "true", check=2)  # no session, cwd is root: nothing to infer

    def test_slot_min_is_respected(self):
        self.config("slot_min = 2\n")
        self.assertEqual(self.wtj("new", "alpha")["slot"], 2)
        self.assertEqual(self.wtj("new", "beta")["slot"], 3)

    def test_failed_setup_marks_broken_and_can_be_rerun(self):
        self.hook("setup", "#!/bin/sh\necho boom; exit 3\n")
        proc = self.wt("new", "alpha", check=1)
        self.assertIn("setup exited 3", proc.stderr)
        self.assertIn("boom", proc.stderr)
        self.assertEqual(self.wtj("list")["trees"][0]["state"], "broken")
        kinds = {a["kind"] for a in self.wtj("status")["anomalies"]}
        self.assertIn("BROKEN", kinds)
        self.hook("setup", SETUP)
        self.assertEqual(self.wtj("setup", "alpha")["state"], "ready")

    def test_bad_env_output_is_a_setup_failure(self):
        self.hook("setup", '#!/bin/sh\necho "not a pair" >> "$WT_ENV_OUT"\n')
        proc = self.wt("new", "alpha", check=1)
        self.assertIn("not KEY=VALUE", proc.stderr)

    def test_reserved_env_names_are_rejected(self):
        self.hook("setup", '#!/bin/sh\necho "WT_SLOT=99" >> "$WT_ENV_OUT"\n')
        self.assertIn("reserved", self.wt("new", "alpha", check=1).stderr)

    def test_non_executable_hook_is_reported(self):
        (self.hooks / "setup").chmod(0o644)
        self.assertIn("chmod +x", self.wt("new", "alpha", check=1).stderr)

    def test_interrupted_setup_is_stuck(self):
        self.hook("setup", "#!/bin/sh\nsleep 30\n")
        proc = subprocess.Popen([sys.executable, str(WT), "new", "alpha"], cwd=self.root, env=self.env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        deadline = time.time() + 30
        while time.time() < deadline:
            if self.sql("SELECT name FROM trees WHERE state = 'setting_up'") and self.tree_path("alpha").is_dir():
                break
            time.sleep(0.1)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):  # already gone; darwin reports EPERM
            pass
        proc.wait()
        kinds = {a["kind"]: a for a in self.wtj("status")["anomalies"]}
        self.assertIn("STUCK", kinds)
        self.hook("setup", SETUP)
        self.assertEqual(self.wtj("setup", "alpha")["state"], "ready")

    def test_concurrent_new_gets_distinct_slots(self):
        names = [f"tree-{i}" for i in range(8)]
        with ThreadPoolExecutor(len(names)) as pool:
            results = list(pool.map(lambda n: self.wt("new", n, "--json", check=False), names))
        for proc in results:
            self.assertEqual(proc.returncode, 0, proc.stderr)
        slots = sorted(json.loads(p.stdout)["slot"] for p in results)
        self.assertEqual(slots, list(range(1, 9)))


class ClaimTests(Sandbox):
    def test_take_over_rules(self):
        a, b = self.session(), self.session()
        self.wtj("new", "alpha", session=a)

        # A is alive: B cannot have it, not even with --take-over.
        out = json.loads(self.wt("claim", "alpha", "--json", session=b, check=3).stdout)
        self.assertEqual(out["holder"]["session"], a["id"])
        self.wt("claim", "alpha", "--take-over", session=b, check=3)

        # A ends: B needs to confirm.
        self.end(a)
        self.assertEqual(self.wtj("list")["trees"][0]["holder"]["state"], "ended")
        self.wt("claim", "alpha", session=b, check=4)
        info = self.wtj("claim", "alpha", "--take-over", session=b)
        self.assertEqual(info["holder"]["session"], b["id"])
        self.assertTrue(info["holder"]["mine"])

    def test_resumed_session_reclaims_without_prompt(self):
        a = self.session()
        self.wtj("new", "alpha", session=a)
        self.end(a)
        resumed = {**self.session(), "id": a["id"]}
        info = self.wtj("claim", "alpha", session=resumed)
        self.assertEqual(info["holder"]["pid"], resumed["pid"])

    def test_reused_pid_is_not_a_live_holder(self):
        a, b = self.session(), self.session()
        self.wtj("new", "alpha", session=a)
        self.sql("UPDATE trees SET claim_start = 'some other process'")
        self.wt("claim", "alpha", session=b, check=4)

    def test_one_tree_per_session(self):
        s = self.session()
        self.wtj("new", "alpha", session=s)
        info = self.wtj("new", "beta", session=s)
        self.assertEqual(info["holder"]["session"], s["id"])
        trees = {t["name"]: t["holder"]["state"] for t in self.wtj("list")["trees"]}
        self.assertEqual(trees, {"alpha": "none", "beta": "live"})
        self.assertEqual(self.wtj("claim", "alpha", session=s)["released"], ["beta"])

    def test_release(self):
        a, b = self.session(), self.session()
        self.wtj("new", "alpha", session=a)
        self.wt("release", "alpha", session=b, check=3)
        self.wt("release", "alpha", session=a)
        self.assertEqual(self.wtj("list")["trees"][0]["holder"]["state"], "none")

    def test_claim_needs_identity(self):
        self.wtj("new", "alpha")
        self.assertIn("no session identity", self.wt("claim", "alpha", check=1).stderr)

    def test_list_shows_session_label(self):
        s = self.session()
        sessions = self.tmp / "claude" / "sessions"
        sessions.mkdir(parents=True)
        (sessions / f"{s['pid']}.json").write_text(json.dumps({"sessionId": s["id"], "name": "proj-a1"}))
        self.wtj("new", "alpha", session=s)
        out = self.wt("list").stdout
        self.assertIn("proj-a1 (live)", out)


class RemovalTests(Sandbox):
    def setUp(self):
        super().setUp()
        self.hook("setup", SETUP)
        self.hook("teardown", TEARDOWN)

    def test_dry_run_changes_nothing(self):
        self.wtj("new", "alpha")
        out = self.wtj("rm", "alpha")
        self.assertFalse(out["applied"])
        self.assertIn("would destroy slot 1", out["plan"]["teardown"]["output"])
        self.assertTrue(self.tree_path("alpha").is_dir())
        self.assertEqual(len(self.wtj("list")["trees"]), 1)

    def test_rm_runs_teardown_with_stored_env_and_removes(self):
        info = self.wtj("new", "alpha")
        self.hook("teardown", TEARDOWN + 'echo "dropped slot $WT_SLOT"\n')
        out = self.wtj("rm", "alpha", "--yes")
        self.assertTrue(out["applied"])
        self.assertEqual(out["result"]["teardown"]["rc"], 0)
        self.assertIn("dropped slot 1", out["result"]["teardown"]["output"])
        self.assertFalse(Path(info["path"]).exists())
        self.assertEqual(self.wtj("list")["trees"], [])
        self.assertIn(f"teardown name=alpha slot=1 mode=destroy dry=0 env=1 cwd={info['path']}",
                      self.records_lines())
        # the branch had no commits of its own, but deletion is opt-in
        self.assertIn("feature/alpha", self.git(self.root, "branch", "--list", "feature/alpha"))

    def test_warm_pool(self):
        self.config("warm_slots = 1\n")
        self.wtj("new", "alpha")
        self.wtj("new", "beta")
        self.assertEqual(self.wtj("rm", "alpha", "--yes")["result"]["mode"], "release")
        self.assertEqual(self.wtj("rm", "beta", "--yes")["result"]["mode"], "destroy")
        self.assertEqual(self.wtj("slots")["warm"], [1])
        info = self.wtj("new", "gamma")
        self.assertEqual((info["slot"], info["slot_warm"]), (1, True))
        self.assertIn("setup gamma slot=1 warm=1", " ".join(self.records_lines()))
        self.assertEqual(self.wtj("slots")["warm"], [])
        self.assertEqual(self.wtj("rm", "gamma", "--yes", "--destroy")["result"]["mode"], "destroy")

    def test_dirty_and_unpushed_work_blocks(self):
        info = self.wtj("new", "alpha")
        (Path(info["path"]) / "scratch.txt").write_text("wip\n")
        out = json.loads(self.wt("rm", "alpha", "--yes", "--json", check=5).stdout)
        self.assertIn("1 uncommitted change(s)", out["plan"]["blocked"])
        self.git(info["path"], "add", "scratch.txt")
        self.git(info["path"], "commit", "--quiet", "-m", "wip")
        out = json.loads(self.wt("rm", "alpha", "--yes", "--json", check=5).stdout)
        self.assertIn("1 commit(s) not pushed to origin", out["plan"]["blocked"])
        self.assertTrue(Path(info["path"]).is_dir())
        self.git(info["path"], "push", "--quiet", "-u", "origin", "feature/alpha")
        self.assertTrue(self.wtj("rm", "alpha", "--yes")["applied"])

    def test_force_removes_dirty_tree(self):
        info = self.wtj("new", "alpha")
        (Path(info["path"]) / "scratch.txt").write_text("wip\n")
        self.assertTrue(self.wtj("rm", "alpha", "--yes", "--force")["applied"])
        self.assertFalse(Path(info["path"]).exists())

    def test_unsure_teardown_refuses(self):
        self.wtj("new", "alpha")
        self.hook("teardown", "#!/bin/sh\necho 'database unreachable, cannot tell'; exit 1\n")
        out = json.loads(self.wt("rm", "alpha", "--yes", "--json", check=5).stdout)
        self.assertIn("database unreachable", out["plan"]["teardown"]["output"])
        self.assertTrue(self.tree_path("alpha").is_dir())
        self.assertEqual(self.wtj("list")["trees"][0]["state"], "ready")

    def test_failing_real_teardown_keeps_row(self):
        self.wtj("new", "alpha")
        self.hook("teardown", '#!/bin/sh\n[ "$WT_DRY_RUN" = 1 ] && exit 0; echo nope; exit 2\n')
        self.wt("rm", "alpha", "--yes", check=5)
        tree = self.wtj("list")["trees"][0]
        self.assertEqual(tree["state"], "broken")
        self.assertTrue(tree["exists"])
        self.hook("teardown", TEARDOWN)
        self.assertTrue(self.wtj("rm", "alpha", "--yes")["applied"])

    def test_orphaned_tree_is_reported_and_removable(self):
        info = self.wtj("new", "alpha")
        shutil.rmtree(info["path"])
        kinds = [a["kind"] for a in self.wtj("status")["anomalies"]]
        self.assertIn("ORPHANED", kinds)
        self.assertTrue(self.wtj("rm", "alpha", "--yes")["applied"])
        self.assertIn(f"teardown name=alpha slot=1 mode=destroy dry=0 env=1 cwd={self.root}",
                      self.records_lines())
        self.assertNotIn("alpha", self.git(self.root, "worktree", "list"))

    def test_held_by_live_session_is_not_removed(self):
        a, b = self.session(), self.session()
        self.wtj("new", "alpha", session=a)
        self.wt("rm", "alpha", "--yes", session=b, check=3)
        self.assertTrue(self.wtj("rm", "alpha", "--yes", session=a)["applied"])

    def test_merged_pr_allows_removal_and_deletes_branch(self):
        info = self.wtj("new", "alpha")
        (Path(info["path"]) / "f.txt").write_text("x\n")
        self.git(info["path"], "add", "f.txt")
        self.git(info["path"], "commit", "--quiet", "-m", "feature")
        head = self.git(info["path"], "rev-parse", "HEAD").strip()
        (self.tmp / "prs" / "feature__alpha.json").write_text(json.dumps(
            {"number": 12, "state": "MERGED", "url": "https://example.test/pr/12", "headRefOid": head}))
        out = self.wtj("rm", "alpha", "--yes")
        self.assertEqual(out["result"]["branch_result"], "deleted")
        self.assertEqual(self.git(self.root, "branch", "--list", "feature/alpha"), "")

    def test_merged_pr_with_newer_local_commits_still_blocks(self):
        info = self.wtj("new", "alpha")
        (self.tmp / "prs" / "feature__alpha.json").write_text(json.dumps(
            {"number": 12, "state": "MERGED", "url": "u", "headRefOid": "0" * 40}))
        (Path(info["path"]) / "f.txt").write_text("x\n")
        self.git(info["path"], "add", "f.txt")
        self.git(info["path"], "commit", "--quiet", "-m", "after merge")
        out = json.loads(self.wt("rm", "alpha", "--yes", "--json", check=5).stdout)
        self.assertTrue(any("not pushed" in b for b in out["plan"]["blocked"]))

    def test_cleanup_stale(self):
        a, b, live = self.session(), self.session(), self.session()
        self.wtj("new", "alpha", session=a)
        dirty = self.wtj("new", "beta", session=b)
        self.wtj("new", "gamma", session=live)
        self.wtj("new", "delta")  # never claimed
        (Path(dirty["path"]) / "wip.txt").write_text("wip\n")
        self.end(a)
        self.end(b)

        plan = self.wtj("cleanup", "--stale")
        self.assertEqual(sorted(p["name"] for p in plan["plans"]), ["alpha", "beta"])
        self.assertFalse(plan["applied"])

        done = self.wtj("cleanup", "--stale", "--yes")
        self.assertEqual([r["name"] for r in done["removed"]], ["alpha"])
        names = sorted(t["name"] for t in self.wtj("list")["trees"])
        self.assertEqual(names, ["beta", "delta", "gamma"])

        done = self.wtj("cleanup", "--stale", "--include-unclaimed", "--yes")
        self.assertEqual([r["name"] for r in done["removed"]], ["delta"])


class RegistryTests(Sandbox):
    def test_unregistered_unmanaged_and_adopt(self):
        trees = self.root / ".claude" / "worktrees"
        self.git(self.root, "worktree", "add", "--quiet", "-b", "loose", str(trees / "loose"))
        self.git(self.root, "worktree", "add", "--quiet", "-b", "agent-x", str(trees / "agent-x"))
        anomalies = self.wtj("status")["anomalies"]
        self.assertEqual([(a["kind"], a["subject"]) for a in anomalies], [("UNREGISTERED", "loose")])
        self.assertEqual(self.wtj("list")["unmanaged"], ["agent-x"])

        self.hook("setup", SETUP)
        info = self.wtj("adopt", str(trees / "loose"), "--slot", "7", "--warm")
        self.assertEqual((info["name"], info["slot"], info["branch"]), ("loose", 7, "loose"))
        self.assertIn("setup loose slot=7 warm=1", " ".join(self.records_lines()))
        self.assertEqual(self.wtj("status")["anomalies"], [])

    def test_inventory_finds_leaks(self):
        self.hook("teardown", TEARDOWN)
        self.hook("inventory", "#!/bin/sh\necho 1; echo 7\n")
        self.wtj("new", "alpha")
        anomalies = self.wtj("status")["anomalies"]
        self.assertEqual([(a["kind"], a["subject"]) for a in anomalies], [("LEAKED", "slot 7")])
        self.assertFalse(self.wtj("slots", "purge", "7")["applied"])
        self.assertTrue(self.wtj("slots", "purge", "7", "--yes")["applied"])
        self.assertIn("teardown name= slot=7 mode=destroy dry=0", " ".join(self.records_lines()))
        self.wt("slots", "purge", "1", check=1)  # in use by alpha

    def test_failing_inventory_is_unknown_not_clean(self):
        self.hook("inventory", "#!/bin/sh\necho 'auth failed'; exit 1\n")
        kinds = [a["kind"] for a in self.wtj("status")["anomalies"]]
        self.assertEqual(kinds, ["UNKNOWN"])

    def test_janitor(self):
        a = self.session()
        self.wtj("new", "alpha", session=a)
        self.assertEqual(self.wt("janitor").stdout, "")
        self.end(a)
        out = self.wt("janitor").stdout
        self.assertIn("1 tree(s) held by ended sessions: alpha", out)
        hook = subprocess.run([sys.executable, str(WT), "janitor", "--hook"], cwd=self.root, env=self.env,
                              input=json.dumps({"session_id": a["id"]}), capture_output=True, text=True)
        self.assertIn("this session holds tree alpha", hook.stdout)
        self.assertEqual(self.wt("janitor", cwd=self.tmp).stdout, "")  # not a repo: silent

    def test_suggested_fixes_run_as_printed(self):
        self.hook("teardown", TEARDOWN)
        info = self.wtj("new", "alpha")
        shutil.rmtree(info["path"])

        def orphan_fix() -> str:
            return next(a["fix"] for a in self.wtj("status")["anomalies"] if a["kind"] == "ORPHANED")

        # Not on PATH: the full path, which is what a skill or hook has to run.
        self.assertEqual(orphan_fix(), f"{WT} rm alpha --yes")
        # On PATH as this same file: the short form.
        (self.bin / "wt").symlink_to(WT)
        fix = orphan_fix()
        self.assertEqual(fix, "wt rm alpha --yes")
        subprocess.run(shlex.split(fix), cwd=self.root, env=self.env, check=True, capture_output=True)
        self.assertEqual(self.wtj("list")["trees"], [])

    def test_init_creates_stubs_and_local_excludes(self):
        shutil.rmtree(self.hooks.parent)
        self.git(self.root, "rm", "--quiet", "--cached", "-r", "--ignore-unmatch", ".claude")
        exclude = self.root / ".git" / "info" / "exclude"
        exclude.write_text("")
        out = self.wtj("init", "--local")
        self.assertEqual(len(out["created"]), 3)
        self.assertTrue(os.access(self.hooks / "setup", os.X_OK))
        self.assertIn("/.claude/worktree/", exclude.read_text())
        self.assertIn("/.claude/worktrees/", exclude.read_text())
        self.assertEqual(self.git(self.root, "status", "--porcelain"), "")
        # the stubs work as they are
        info = self.wtj("new", "alpha")
        self.assertEqual(info["state"], "ready")
        self.assertIn("would destroy the resources of slot 1", self.wtj("rm", "alpha")["plan"]["teardown"]["output"])
        # a second init keeps what is there and does not duplicate excludes
        again = self.wtj("init", "--local")
        self.assertEqual((again["created"], again["excluded"]), ([], []))

    def test_new_ignores_the_trees_directory(self):
        exclude = self.root / ".git" / "info" / "exclude"
        exclude.write_text("/.claude/worktree/\n")
        self.wtj("new", "alpha")
        self.assertIn("/.claude/worktrees/", exclude.read_text())
        self.assertEqual(self.git(self.root, "status", "--porcelain"), "")

    def test_common_options_before_or_after_the_command(self):
        self.wtj("new", "alpha")
        elsewhere = {"cwd": self.tmp}
        before = self.wt("-C", str(self.root), "--json", "list", **elsewhere).stdout
        after = self.wt("list", "-C", str(self.root), "--json", **elsewhere).stdout
        self.assertEqual(json.loads(before), json.loads(after))
        ran = self.wt("-C", str(self.root), "exec", "alpha", "--", "sh", "-c", "echo $WT_SLOT", **elsewhere)
        self.assertEqual(ran.stdout.strip(), "1")
        ran = self.wt("exec", "alpha", "-C", str(self.root), "--", "sh", "-c", "echo $WT_SLOT", **elsewhere)
        self.assertEqual(ran.stdout.strip(), "1")
        ran = self.wt("exec", "-C", str(self.root), "--", "sh", "-c", "echo $WT_NAME",
                      cwd=self.tree_path("alpha"))
        self.assertEqual(ran.stdout.strip(), "alpha")
        self.wt("exec", "alpha", "beta", "--", "true", check=2)

    def test_project_is_shared_by_all_worktrees(self):
        info = self.wtj("new", "alpha")
        from_tree = self.wtj("list", cwd=info["path"])
        self.assertEqual(from_tree["root"], str(self.root))
        self.assertEqual([t["name"] for t in from_tree["trees"]], ["alpha"])

    def test_list_all_projects(self):
        self.wtj("new", "alpha")
        other = self.tmp / "other"
        self.git(self.tmp, "init", "--quiet", str(other))
        (other / "f").write_text("x")
        self.git(other, "add", "f")
        self.git(other, "commit", "--quiet", "-m", "x")
        self.wtj("new", "beta", cwd=other)
        projects = self.wtj("list", "--all-projects")
        self.assertEqual(sorted(p["project"] for p in projects), ["other", "proj"])

    def test_config_is_validated(self):
        self.config("slot_mn = 2\n")
        self.assertIn("unknown setting", self.wt("list", check=1).stderr)
        self.config("slot_min = 'two'\n")
        self.assertIn("must be a int", self.wt("list", check=1).stderr)

    def test_event_log(self):
        self.wtj("new", "alpha")
        kinds = [e["kind"] for e in self.wtj("log", "alpha")]
        self.assertEqual(kinds, ["created", "setup_ok"])


if __name__ == "__main__":
    unittest.main()
