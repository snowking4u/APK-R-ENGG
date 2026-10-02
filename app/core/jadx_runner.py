"""JADX tool detection and safe execution (Phase 03).

JADX is the trusted static decompiler used to turn the DEX files of a
decoded APK into readable Java sources. We never assume it is installed
and we NEVER download anything: the user configures it explicitly or it
is already available on the machine.

Detection order (documented and stable):

1. Environment ``JADX_PATH`` - may point to

   * a launcher script/executable (``jadx``, ``jadx.bat``, ``jadx.cmd``),
   * a JADX distribution directory (``.../jadx`` with ``bin/`` + ``lib/``),
   * a ``jadx-cli*.jar`` (launched through ``java -jar``).

   The variable may also contain several ``os.pathsep`` separated
   candidates; the first usable one wins.
2. Bundled tool shipped with the IDE: ``app/resources/tools/jadx/``
   (same shapes as above). A ``.gitkeep``-style placeholder directory is
   *not* treated as an installation.
3. ``PATH`` lookup for ``jadx``, ``jadx.bat``, ``jadx.cmd``.

If nothing is found, :func:`decompile_with_jadx` returns a structured
:class:`JadxResult` with ``not_found=True`` and the exact user-facing
message *"JADX is required for Java decompilation but was not
found/configured."* - no fake decompilation is ever reported.

Security notes
--------------
* Processes are always started with an **argument list**; ``shell`` is
  never used, so nothing derived from the APK is interpreted by a shell.
* Only the JADX launcher itself is executed. DEX files are passed as file
  arguments - their *contents* are never executed, and no script, binary
  or manifest value taken from the APK is ever executed.
* Input file names are validated by :mod:`app.core.dex_discovery` against
  the strict ``classes[N].dex`` pattern before reaching this module.
"""

import glob
import os
import re
import shutil
import subprocess

from app.core.logger import logger


JADX_MISSING_MESSAGE = ("JADX is required for Java decompilation but was "
                        "not found/configured.")

_ENV_VAR = "JADX_PATH"
_LAUNCHER_NAMES = ("jadx.bat", "jadx.cmd", "jadx", "jadx.exe")
_JAR_PATTERN = "jadx-cli*.jar"


class JadxTool:
    """A located JADX installation.

    ``kind`` is one of ``"launcher"`` (a script/executable) or ``"jar"``
    (launched with ``java -jar``).
    """

    __slots__ = ("kind", "path", "source", "description")

    def __init__(self, kind, path, source, description=""):
        self.kind = kind
        self.path = path
        self.source = source
        self.description = description or path

    def command(self):
        """Return the base argument list for this tool (no shell)."""
        if self.kind == "jar":
            java = shutil.which("java") or shutil.which("java.exe")
            if not java:
                return None
            return [java, "-jar", self.path]
        return [self.path]

    def __repr__(self):
        return "JadxTool(kind=%r, path=%r, source=%r)" % (
            self.kind, self.path, self.source)


class JadxResult:
    """Structured result of a JADX invocation.

    Field names follow the Phase 03 contract: ``success``, ``not_found``,
    ``return_code``, ``stdout``, ``stderr``, ``timed_out`` and
    ``error_message``. ``ok`` / ``returncode`` / ``error`` are provided as
    aliases so the result can be handled like
    :class:`app.core.tool_runner.ToolResult`.
    """

    __slots__ = ("success", "not_found", "return_code", "stdout", "stderr",
                 "timed_out", "error_message", "command", "duration")

    def __init__(self, success=False, not_found=False, return_code=None,
                 stdout="", stderr="", timed_out=False, error_message="",
                 command=None, duration=0.0):
        self.success = bool(success)
        self.not_found = bool(not_found)
        self.return_code = return_code
        self.stdout = stdout or ""
        self.stderr = stderr or ""
        self.timed_out = bool(timed_out)
        self.error_message = error_message or ""
        self.command = list(command or [])
        self.duration = float(duration or 0.0)

    # -- aliases --------------------------------------------------------- #
    @property
    def ok(self):
        return self.success

    @property
    def returncode(self):
        return self.return_code

    @property
    def error(self):
        return self.error_message

    def output_tail(self, limit=2000):
        """Combined stdout/stderr tail, useful for the console log."""
        text = (self.stderr or "") + ("\n" if self.stderr and self.stdout else "") \
            + (self.stdout or "")
        text = text.strip()
        if len(text) > limit:
            text = text[-limit:]
        return text

    def to_dict(self):
        return {
            "success": self.success,
            "not_found": self.not_found,
            "return_code": self.return_code,
            "timed_out": self.timed_out,
            "error_message": self.error_message,
            "duration": self.duration,
        }

    def __repr__(self):
        return ("JadxResult(success=%r, return_code=%r, timed_out=%r, "
                "not_found=%r)" % (self.success, self.return_code,
                                   self.timed_out, self.not_found))


# ---------------------------------------------------------------------- #
# Detection
# ---------------------------------------------------------------------- #
def bundled_jadx_dir():
    """Directory that may contain a JADX distribution shipped with the IDE."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "resources", "tools", "jadx"))


def _jar_in(directory):
    matches = sorted(glob.glob(os.path.join(directory, _JAR_PATTERN)))
    return matches[-1] if matches else None


def _launcher_kind(path):
    """Classify a launcher file: batch/cmd/exe/none -> launcher."""
    extension = os.path.splitext(path)[1].lower()
    if extension in (".jar", ".zip"):
        return "jar"
    return "launcher"


def _tool_from_directory(directory, source):
    """Resolve a JADX *distribution* directory into a JadxTool."""
    if not directory or not os.path.isdir(directory):
        return None

    description = "JADX distribution at %s" % directory

    # Distribution layout: <root>/bin/jadx.bat + <root>/lib/jadx-cli*.jar
    for name in _LAUNCHER_NAMES:
        candidate = os.path.join(directory, "bin", name)
        if os.path.isfile(candidate):
            return JadxTool(_launcher_kind(candidate), candidate, source,
                            description)

    # Directory that is itself a launcher, or holds one.
    for name in _LAUNCHER_NAMES:
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            return JadxTool(_launcher_kind(candidate), candidate, source,
                            description)

    jar = _jar_in(os.path.join(directory, "lib")) or _jar_in(directory)
    if jar:
        return JadxTool("jar", jar, source, description)
    return None


def _tool_from_path(candidate, source):
    """Resolve one explicit candidate path (file or directory)."""
    if not candidate:
        return None
    if os.path.isdir(candidate):
        return _tool_from_directory(candidate, source)
    if not os.path.isfile(candidate):
        return None
    name = os.path.basename(candidate).lower()
    if name.endswith(".jar"):
        return JadxTool("jar", candidate, source)
    return JadxTool(_launcher_kind(candidate), candidate, source)


def find_jadx(environ=None):
    """Locate a usable JADX.

    Returns a :class:`JadxTool` or ``None`` when JADX is neither configured
    nor available on ``PATH``. Never raises.
    """
    env = os.environ if environ is None else environ

    # 1. Explicit configuration.
    raw = (env.get(_ENV_VAR) or "").strip()
    if raw:
        for candidate in raw.split(os.pathsep):
            candidate = candidate.strip().strip('"').strip("'")
            if not candidate:
                continue
            tool = _tool_from_path(candidate, "configured via %s" % _ENV_VAR)
            if tool:
                return tool

    # 2. Bundled distribution.
    tool = _tool_from_directory(bundled_jadx_dir(), "bundled with IDE resources")
    if tool:
        return tool

    # 3. PATH.
    for name in _LAUNCHER_NAMES:
        resolved = shutil.which(name)
        if resolved:
            return JadxTool("launcher", resolved, "found on PATH (%s)" % name)

    return None


def jadx_status_text():
    """One-line, user-facing JADX status (``Not configured`` when absent)."""
    tool = find_jadx()
    if not tool:
        return "Not configured"
    if tool.kind == "jar" and not (shutil.which("java") or shutil.which("java.exe")):
        return "Configured (java runtime missing)"
    return tool.description


def jadx_missing_message():
    """The exact message shown when JADX cannot be located."""
    return JADX_MISSING_MESSAGE


# ---------------------------------------------------------------------- #
# Execution
# ---------------------------------------------------------------------- #
def _safe_env():
    """Environment for the child process: nothing APK-derived is injected."""
    env = dict(os.environ)
    here = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    env["PATH"] = here + os.pathsep + env.get("PATH", "")
    return env


def run_jadx(command, cwd=None, timeout=None):
    """Run a prepared JADX argument list safely and capture the result.

    ``shell`` is never used. Missing executables, timeouts and OS errors are
    reported as a :class:`JadxResult` instead of raising.
    """
    if not command:
        return JadxResult(not_found=True,
                         error_message="Empty JADX command was requested.")

    logger.info("JADX process started")

    import time
    started = time.time()

    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_safe_env(),
            check=False,
            shell=False,
        )
    except FileNotFoundError as exc:
        message = "JADX executable not found: %s" % exc
        logger.error(message)
        return JadxResult(not_found=True, error_message=message,
                          command=command, duration=time.time() - started)
    except subprocess.TimeoutExpired:
        message = "JADX timed out."
        logger.error(message)
        return JadxResult(timed_out=True, stderr=message,
                          error_message=message, command=command,
                          duration=time.time() - started)
    except OSError as exc:
        message = "Could not run JADX: %s" % exc
        logger.error(message)
        return JadxResult(error_message=message, command=command,
                          duration=time.time() - started)

    duration = time.time() - started
    result = JadxResult(
        success=completed.returncode == 0,
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        command=command,
        duration=duration,
    )
    if not result.success:
        result.error_message = "JADX exited with code %s." % completed.returncode
        logger.error(result.error_message)
    else:
        logger.info("JADX process completed successfully (%.1fs)" % duration)
    return result


def build_jadx_command(tool, dex_files, output_dir, extra_args=()):
    """Build the JADX argument list for ``dex_files`` -> ``output_dir``.

    Returns ``None`` when the tool cannot be launched (e.g. a jar without a
    Java runtime). All arguments are separate list items; nothing is ever
    passed through a shell.
    """
    base = tool.command() if tool else None
    if not base:
        return None
    command = list(base)
    command.append("-d")
    command.append(output_dir)
    for argument in extra_args:
        command.append(str(argument))
    for dex in dex_files:
        command.append(str(dex))
    return command


def decompile_with_jadx(dex_files, output_dir, tool=None, timeout=None,
                        extra_args=(), cwd=None):
    """Decompile ``dex_files`` into ``output_dir`` using JADX.

    Returns a :class:`JadxResult`. The decoded APK and the original APK are
    never touched; only ``output_dir`` (a generated directory created by
    the caller) is written to. Never raises.
    """
    dex_files = [str(path) for path in (dex_files or []) if path]
    if not dex_files:
        message = "No DEX files available for Java decompilation."
        logger.error(message)
        return JadxResult(error_message=message)

    missing = [path for path in dex_files if not os.path.isfile(path)]
    if missing:
        message = "DEX file(s) missing: %s" % os.path.basename(missing[0])
        logger.error(message)
        return JadxResult(error_message=message)

    tool = tool if tool is not None else find_jadx()
    if not tool:
        message = jadx_missing_message()
        logger.error("JADX not found")
        logger.error(message)
        return JadxResult(not_found=True, error_message=message)

    command = build_jadx_command(tool, dex_files, output_dir, extra_args)
    if not command:
        message = ("JADX was found at '%s' but cannot be launched "
                   "(java runtime missing)." % tool.path)
        logger.error(message)
        return JadxResult(not_found=True, error_message=message, command=[])

    logger.info("JADX detected: %s" % tool.description)
    logger.info("Running JADX on %d DEX file(s) -> %s"
                % (len(dex_files), output_dir))
    return run_jadx(command, cwd=cwd, timeout=timeout)


def jadx_version(tool=None, timeout=30):
    """Best-effort ``jadx --version`` probe (used for status reporting).

    Returns the version string, or an empty string when unavailable.
    """
    tool = tool if tool is not None else find_jadx()
    base = tool.command() if tool else None
    if not base:
        return ""
    result = run_jadx(list(base) + ["--version"], timeout=timeout)
    if not result.success:
        return ""
    match = re.search(r"(\d[\w.\-+]*)", result.stdout or "")
    return match.group(1) if match else (result.stdout or "").strip()[:40]