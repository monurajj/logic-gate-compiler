"""
Auto-commit watcher: commits (and optionally pushes) changes automatically.

    python3 tools/autocommit.py            # check every 30 s, commit + push
    python3 tools/autocommit.py --no-push  # commit locally only
    python3 tools/autocommit.py --interval 60

It waits until the files have stopped changing for one interval before
committing, so half-finished edits are not committed in the middle of typing.
Files listed in .gitignore are never committed. Press Ctrl+C to stop.
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git(*args):
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).rstrip()   # keep leading spaces: status codes use them


def busy():
    """True while a merge / rebase / cherry-pick is in progress."""
    gitdir = os.path.join(REPO, ".git")
    return any(os.path.exists(os.path.join(gitdir, n))
               for n in ("MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD"))


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def push():
    code, out = git("push")
    if code == 0:
        return log("pushed to GitHub")
    # Usually a teammate pushed first: bring their commits in, then retry.
    code, out = git("pull", "--rebase")
    if code != 0:
        git("rebase", "--abort")
        return log("push failed: your changes conflict with a teammate's. "
                   "Run 'git pull' and fix the conflict by hand (your commit is safe locally).")
    code, out = git("push")
    log("pulled teammates' changes and pushed to GitHub" if code == 0
        else f"push failed (will retry after the next commit): {out.splitlines()[-1] if out else ''}")


def commit_message(status):
    files = [line[3:].split(" -> ")[-1].strip('"') for line in status.splitlines()]
    shown = ", ".join(files[:4]) + (f" (+{len(files) - 4} more)" if len(files) > 4 else "")
    return f"Auto-commit: update {shown}"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--interval", type=int, default=30, help="seconds between checks (default 30)")
    p.add_argument("--no-push", action="store_true", help="commit locally, do not push to GitHub")
    args = p.parse_args()

    log(f"Watching {REPO} every {args.interval}s ({'commit only' if args.no_push else 'commit + push'}). Ctrl+C to stop.")
    previous = None
    while True:
        try:
            code, status = git("status", "--porcelain")
            if code != 0:
                log(f"git status failed: {status}")
            elif not status:
                previous = None
            elif busy():
                log("merge/rebase in progress - skipping")
            elif status != previous:
                previous = status          # changes still happening; wait one more interval
            else:
                git("add", "-A")
                msg = commit_message(status)
                code, out = git("commit", "-m", msg)
                if code == 0:
                    log(msg)
                    if not args.no_push:
                        push()
                else:
                    log(f"commit failed: {out}")
                previous = None
            time.sleep(args.interval)
        except KeyboardInterrupt:
            log("stopped.")
            return 0


if __name__ == "__main__":
    sys.exit(main())
