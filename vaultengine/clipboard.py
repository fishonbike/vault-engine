"""Cross-platform clipboard access through OS tools — stdlib subprocess, no deps.

macOS uses pbcopy/pbpaste; Windows uses PowerShell; Linux uses wl-clipboard,
xclip, or xsel (whichever is installed). Raises :class:`ClipboardError` with an
actionable message when no tool is available.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

_TIMEOUT = 10


class ClipboardError(Exception):
    pass


def _candidates():
    """Return (paste_commands, copy_commands) for the current platform."""
    if sys.platform == "darwin":
        return [["pbpaste"]], [["pbcopy"]]
    if sys.platform == "win32":
        return ([["powershell", "-noprofile", "-command", "Get-Clipboard"]],
                [["powershell", "-noprofile", "-command", "$input | Set-Clipboard"]])
    paste, copy = [], []
    if shutil.which("wl-paste"):
        paste.append(["wl-paste", "--no-newline"])
    if shutil.which("wl-copy"):
        copy.append(["wl-copy"])
    if shutil.which("xclip"):
        paste.append(["xclip", "-selection", "clipboard", "-o"])
        copy.append(["xclip", "-selection", "clipboard", "-i"])
    if shutil.which("xsel"):
        paste.append(["xsel", "--clipboard", "--output"])
        copy.append(["xsel", "--clipboard", "--input"])
    return paste, copy


def _pick(cmds):
    for cmd in cmds:
        if sys.platform == "win32" or shutil.which(cmd[0]):
            return cmd
    return None


def read_clipboard() -> str:
    cmd = _pick(_candidates()[0])
    if not cmd:
        raise ClipboardError(
            "找不到剪贴板读取工具（macOS: pbpaste；Linux: 装 xclip / xsel / wl-clipboard）")
    try:
        proc = subprocess.run(cmd, capture_output=True, encoding="utf-8",
                              timeout=_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ClipboardError(f"读取剪贴板失败：{exc}") from exc
    return proc.stdout or ""


def write_clipboard(text: str) -> None:
    cmd = _pick(_candidates()[1])
    if not cmd:
        raise ClipboardError(
            "找不到剪贴板写入工具（macOS: pbcopy；Linux: 装 xclip / xsel / wl-clipboard）")
    try:
        subprocess.run(cmd, input=text, encoding="utf-8", timeout=_TIMEOUT,
                       check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ClipboardError(f"写入剪贴板失败：{exc}") from exc
