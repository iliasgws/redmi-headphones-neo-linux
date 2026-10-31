"""Bounded, UI-independent updater for the REDMI Headphones Neo app.

The GTK application should call :func:`update` from its worker thread and
inspect the returned ``UpdateResult``.  This module deliberately keeps all
subprocess output private so credentials and remote error text are never
shown to the UI or written to a log.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from typing import Optional
from urllib.parse import urlsplit


APP_DIR = Path.home() / ".local" / "share" / "neo-popup"
SOURCE_PATH_FILE = APP_DIR / "source-path"
EXPECTED_REPOSITORY = "iliasgws/redmi-headphones-neo-linux"
GIT_TIMEOUT_SECONDS = 25
INSTALL_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class UpdateResult:
    """Result returned by ``update()`` for the GTK thread to display."""

    status: str  # "updated", "current", or "error"
    message: str
    updated: bool = False
    restart_required: bool = False
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.status != "error"


_update_lock = threading.Lock()


class _UpdateFailure(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _run(args, *, cwd=None, timeout=GIT_TIMEOUT_SECONDS, env=None):
    """Run a fixed argv without a shell; discard all output from callers."""
    try:
        return subprocess.run(
            args,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise _UpdateFailure("timeout", "The update took too long and was stopped. Try again.") from exc
    except OSError as exc:
        raise _UpdateFailure("unavailable", "A required local program could not be started.") from exc


def _git(root: Path, *args, timeout=GIT_TIMEOUT_SECONDS):
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    result = _run(("git", "-C", str(root), *args), cwd=root, timeout=timeout, env=env)
    return result


def _source_root() -> Path:
    try:
        configured = SOURCE_PATH_FILE.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise _UpdateFailure(
            "source_path_missing",
            "The source checkout is not configured. Reinstall the app from its checkout first.",
        ) from exc
    if not configured:
        raise _UpdateFailure("source_path_invalid", "The configured source checkout path is empty.")
    if not Path(configured).expanduser().is_absolute():
        raise _UpdateFailure("source_path_invalid", "The configured source checkout path must be absolute.")
    try:
        return Path(configured).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise _UpdateFailure("source_path_invalid", "The configured source checkout is unavailable.") from exc


def _validate_origin(root: Path) -> None:
    result = _git(root, "remote", "get-url", "origin")
    if result.returncode != 0:
        raise _UpdateFailure("origin_missing", "This checkout has no usable origin remote.")
    remote = result.stdout.strip()
    expected_path = "/" + EXPECTED_REPOSITORY
    valid = False
    try:
        if remote.startswith("https://"):
            parsed = urlsplit(remote)
            valid = (
                parsed.scheme == "https"
                and parsed.hostname == "github.com"
                and parsed.port is None
                and parsed.username is None
                and parsed.password is None
                and parsed.query == ""
                and parsed.fragment == ""
                and parsed.path.removesuffix(".git") == expected_path
            )
        elif remote.startswith("ssh://"):
            parsed = urlsplit(remote)
            valid = (
                parsed.scheme == "ssh"
                and parsed.hostname == "github.com"
                and parsed.port is None
                and parsed.username == "git"
                and parsed.password is None
                and parsed.query == ""
                and parsed.fragment == ""
                and parsed.path.removesuffix(".git") == expected_path
            )
        elif remote.startswith("git@"):
            # SCP-style SSH syntax does not parse as a URL; accept only this
            # exact host and repository path, optionally ending in .git.
            valid = remote.removeprefix("git@github.com:").removesuffix(".git") == EXPECTED_REPOSITORY
    except ValueError:
        valid = False
    if not valid:
        raise _UpdateFailure(
            "wrong_origin",
            "The checkout origin is not the expected GitHub repository. Update was stopped.",
        )


def _checkout_state(root: Path):
    top = _git(root, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        raise _UpdateFailure("not_git", "The configured source path is not a Git checkout.")
    try:
        checkout_root = Path(top.stdout.strip()).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise _UpdateFailure("not_git", "The configured source path is not a valid Git checkout.") from exc
    if checkout_root != root:
        raise _UpdateFailure("not_git_root", "The configured source path must be the Git repository root.")

    branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch.returncode != 0 or not branch.stdout.strip():
        raise _UpdateFailure("detached_head", "This checkout is on a detached commit and cannot be updated safely.")

    upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    upstream_name = upstream.stdout.strip() if upstream.returncode == 0 else ""
    if not upstream_name.startswith("origin/") or not upstream_name[len("origin/"):]:
        raise _UpdateFailure("upstream_missing", "The current branch has no upstream branch on origin.")
    upstream_branch = upstream_name[len("origin/"):]

    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none")
    if status.returncode != 0:
        raise _UpdateFailure("status_failed", "Git could not inspect this checkout safely.")
    if status.stdout:
        raise _UpdateFailure("working_tree_dirty", "The checkout has local or untracked changes. Commit or remove them before updating.")

    head = _git(root, "rev-parse", "--verify", "HEAD")
    if head.returncode != 0:
        raise _UpdateFailure("head_unavailable", "Git could not identify the current commit.")

    return head.stdout.strip(), upstream_branch


def _validate_upstream_exists(root: Path, upstream_branch: str) -> None:
    remote_branch = _git(root, "ls-remote", "--exit-code", "--heads", "origin", "refs/heads/" + upstream_branch)
    if remote_branch.returncode != 0:
        raise _UpdateFailure("upstream_unavailable", "The upstream branch could not be confirmed on GitHub. Check network access and retry.")


def _install(root: Path) -> None:
    installer = root / "install.sh"
    if not installer.is_file():
        raise _UpdateFailure("installer_missing", "The checkout does not contain install.sh, so the update was not installed.")
    env = os.environ.copy()
    env["NEO_NO_START"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    result = _run((str(installer),), cwd=root, timeout=INSTALL_TIMEOUT_SECONDS, env=env)
    if result.returncode != 0:
        raise _UpdateFailure("install_failed", "The source updated, but installation failed. Check the app dependencies and try the installer manually.")


def update() -> UpdateResult:
    """Update the configured checkout and install it without launching it.

    Call from a worker thread. This function never touches GTK and never
    returns subprocess output, URLs, credentials, or command text.
    """
    if not _update_lock.acquire(blocking=False):
        return UpdateResult("error", "An update is already running.", error="busy")
    try:
        try:
            root = _source_root()
            if not root.is_dir():
                raise _UpdateFailure("source_path_invalid", "The configured source checkout is not a directory.")
            before_head, upstream_branch = _checkout_state(root)
            _validate_origin(root)
            _validate_upstream_exists(root, upstream_branch)
            pulled = _git(root, "pull", "--ff-only", timeout=GIT_TIMEOUT_SECONDS)
            if pulled.returncode != 0:
                raise _UpdateFailure("pull_failed", "Git could not fast-forward this branch. Check network access and branch history, then retry.")
            after = _git(root, "rev-parse", "--verify", "HEAD")
            if after.returncode != 0:
                raise _UpdateFailure("head_unavailable", "Git could not verify the result of the update.")
            try:
                installed_head = (APP_DIR / "installed-revision").read_text(encoding="utf-8").strip()
            except OSError:
                installed_head = ""
            changed = before_head != after.stdout.strip() or installed_head != after.stdout.strip()
            if changed:
                _install(root)
                return UpdateResult(
                    "updated",
                    "The app was updated and installed. Restart it to load the new version.",
                    updated=True,
                    restart_required=True,
                )
            return UpdateResult("current", "The app is already up to date.")
        except _UpdateFailure as exc:
            return UpdateResult("error", exc.message, error=exc.code)
        except Exception:
            # Do not expose unexpected exception text, which may contain paths
            # or output supplied by Git, the environment, or installer hooks.
            return UpdateResult("error", "The update stopped because of an unexpected local error.", error="unexpected")
    finally:
        _update_lock.release()


_RESTART_HELPER = r"""
import os, sys, time
pid = int(sys.argv[1])
started = sys.argv[2]
script = sys.argv[3]
python = sys.argv[4]
deadline = time.monotonic() + 30
def process_start(pid):
    try:
        with open('/proc/%d/stat' % pid, 'r', encoding='ascii') as f:
            return f.read().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError, ValueError):
        return None
while process_start(pid) == started and time.monotonic() < deadline:
    time.sleep(0.2)
if process_start(pid) == started:
    sys.exit(2)
os.environ.pop('NEO_NO_START', None)
os.execv(python, [python, script])
"""


def _process_start_time(pid: int) -> Optional[str]:
    try:
        with open("/proc/%d/stat" % pid, "r", encoding="ascii") as handle:
            return handle.read().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError, ValueError):
        return None


def restart_after_update(old_pid: Optional[int] = None) -> bool:
    """Schedule the installed app to start after the old process exits.

    This is opt-in: the parent should call it only after a successful update.
    It never terminates a process. ``systemd-run --user`` is preferred; when
    unavailable, a detached child waits for the same PID instance to exit.
    """
    pid = old_pid if old_pid is not None else os.getpid()
    started = _process_start_time(pid)
    script = APP_DIR / "neo_popup.py"
    python = shutil.which("python3") or sys.executable
    if started is None or not script.is_file():
        return False
    command = (python, "-c", _RESTART_HELPER, str(pid), started, str(script), python)
    systemd_run = shutil.which("systemd-run")
    if systemd_run:
        unit = "neo-popup-restart-%d-%d" % (pid, int(time.time()))
        try:
            result = subprocess.run(
                (systemd_run, "--user", "--quiet", "--collect", "--unit=" + unit, "--property=Type=exec", *command),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8,
                check=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
    try:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        return True
    except OSError:
        return False
