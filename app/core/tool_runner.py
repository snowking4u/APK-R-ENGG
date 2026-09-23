"""External tool detection and safe subprocess execution (Phase 02).

Apktool is required for APK decoding. We never assume it is installed
globally, and we never auto-download anything. Detection order:

1. Environment `APKTOOL_JAR` (path to an `apktool*.jar`) or `APKTOOL`
   (path to an executable), if set and the file exists.
2. A bundled jar shipped with the IDE (``resources/tools/apktool.jar``)
   if it exists on disk.
3. `apktool` / `apktool.bat` / `apktool.jar` found on PATH.

If none is found we return ``None``; the caller reports the exact
message: *"Apktool is required for APK decoding but was not found/
configured."*

Process execution uses argument lists (never a shell string), captures
stdout/stderr/return code, supports a timeout recognized as a decode
timeout (rather than a crash), and distinguishes a missing executable.
"""

import os
import shutil
import subprocess

from app.core.logger import logger


class ToolResult:
    """Result of running an external tool."""

    __slots__ = ("returncode", "stdout", "stderr", "timed_out",
                 "not_found", "error")

    def __init__(self, returncode=None, stdout="", stderr="",
                 timed_out=False, not_found=False, error=""):
        self.returncode = returncode
        self.stdout = stdout or ""
        self.stderr = stderr or ""
        self.timed_out = timed_out
        self.not_found = not_found
        self.error = error

    @property
    def ok(self):
        return not self.not_found and not self.error and not self.timed_out \
            and self.returncode == 0

    def __repr__(self):
        return "ToolResult(rc=%r, ok=%r, timed_out=%r, not_found=%r)" % (
            self.returncode, self.ok, self.timed_out, self.not_found)


def apktool_config_path():
    """Path to the user APKTOOL configuration file (created lazily)."""
    base = os.path.expanduser("~")
    return os.path.join(base, ".apk_reverse_engineering", "apktool.cfg")


def find_apktool():
    """Locate a usable Apktool.

    Returns ``(kind, path, description)`` where ``kind`` is ``"jar"`` or
    ``"executable"``, or ``None`` when not found/configured.
    """
    # 1. Explicit environment override.
    env_jar = os.environ.get("APKTOOL_JAR", "").strip()
    if env_jar and os.path.isfile(env_jar):
        return ("jar", env_jar, "configured via APKTOOL_JAR")

    env_exe = os.environ.get("APKTOOL", "").strip()
    if env_exe and os.path.isfile(env_exe):
        return ("executable", env_exe, "configured via APKTOOL")

    # 2. Bundled jar shipped with the IDE.
    bundled = os.path.join(os.path.dirname(__file__), "..", "..",
                           "resources", "tools", "apktool.jar")
    bundled = os.path.abspath(bundled)
    if os.path.isfile(bundled):
        return ("jar", bundled, "bundled with IDE resources")

    # 3. On PATH.
    for candidate in ("apktool", "apktool.bat", "apktool.jar"):
        resolved = shutil.which(candidate)
        if resolved:
            if candidate.endswith(".jar"):
                return ("jar", resolved, "found on PATH")
            return ("executable", resolved, "found on PATH (%s)" % candidate)

    return None


def apktool_missing_message():
    return ("Apktool is required for APK decoding but was not "
            "found/configured.")


def _command_for_apktool():
    """Build the base Apktool command (list form). Never uses a shell."""
    tool = find_apktool()
    if not tool:
        return None
    kind, path, _ = tool
    if kind == "jar":
        return ["java", "-jar", path]
    return [path]


def _env_python_path():
    """Extend PATH with the IDE directory so bundled tools resolve."""
    env = dict(os.environ)
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env["PATH"] = here + os.pathsep + env.get("PATH", "")
    return env


def run_tool(command, cwd=None, timeout=None, env=None):
    """Run an external tool safely and capture its output.

    ``command`` is an argument list. ``shell`` is never used, and nothing
    derived from the APK is interpreted by a shell.
    """
    if not command:
        return ToolResult(not_found=True,
                          error="Empty command was requested.")

    file_path = command[0]
    if not os.path.isfile(file_path):
        if not shutil.which(file_path):
            return ToolResult(not_found=True,
                              error="Tool not found: %s" % file_path)

    logger.info("Running external tool: %s" % " ".join(command))

    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env if env is not None else _env_python_path(),
            check=False,
        )
    except FileNotFoundError as exc:
        return ToolResult(not_found=True, error="Tool not found: %s" % exc)
    except subprocess.TimeoutExpired:
        logger.error("Tool execution timed out.")
        return ToolResult(timed_out=True, stderr="Command timed out.")
    except OSError as exc:
        logger.error("Could not run tool: %s" % exc)
        return ToolResult(error="Could not run tool: %s" % exc)

    return ToolResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def decode_with_apktool(original_apk, output_dir, timeout=None):
    """Decode ``original_apk`` into ``output_dir`` using Apktool.

    Returns a :class:`ToolResult`. Never modifies the source APK.
    """
    base = _command_for_apktool()
    if not base:
        message = apktool_missing_message()
        logger.error(message)
        return ToolResult(not_found=True, error=message)

    command = list(base) + ["d", "-f", "-o", output_dir, original_apk]
    logger.info("Apktool decode started: %s -> %s"
                % (original_apk, output_dir))
    return run_tool(command, cwd=output_dir and os.path.dirname(output_dir),
                    timeout=timeout)
