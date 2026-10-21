"""Current-user login startup for the DP104 tray console."""

from __future__ import annotations

import os
import plistlib
import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "DP104_PixelHouse"
MAC_LABEL = "com.dp104pixelhouse.tray"


def mac_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"


def mac_program_arguments(app_path: Path | None = None) -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(app_path or sys.executable).resolve()), "--tray"]
    script = Path(app_path or Path(__file__).resolve().parents[1] / "app_qt.py").resolve()
    return [str(Path(sys.executable).resolve()), str(script), "--tray"]


def command_for_app(app_path: Path | None = None) -> str:
    """Use the packaged exe, or pythonw plus app_qt.py for source runs."""
    if getattr(sys, "frozen", False):
        executable = Path(app_path or sys.executable).resolve()
        return f'"{executable}" --tray'
    script = Path(app_path or Path(__file__).resolve().parents[1] / "app_qt.py").resolve()
    runner = Path(sys.executable).with_name("pythonw.exe")
    if not runner.exists():
        runner = Path(sys.executable)
    return f'"{runner.resolve()}" "{script}" --tray'


def is_enabled(command: str | None = None) -> bool:
    if sys.platform == "darwin":
        try:
            with mac_agent_path().open("rb") as stream:
                data = plistlib.load(stream)
            return data.get("Label") == MAC_LABEL and data.get("ProgramArguments") == mac_program_arguments()
        except (OSError, ValueError, TypeError):
            return False
    if os.name != "nt":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return False
    return str(value).casefold() == (command or command_for_app()).casefold()


def set_enabled(enabled: bool, command: str | None = None) -> None:
    if sys.platform == "darwin":
        path = mac_agent_path()
        if not enabled:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"Label": MAC_LABEL, "ProgramArguments": mac_program_arguments(),
                "RunAtLoad": True, "KeepAlive": False,
                "LimitLoadToSessionType": "Aqua"}
        temporary = path.with_suffix(".tmp")
        with temporary.open("wb") as stream:
            plistlib.dump(data, stream)
        temporary.replace(path)
        return
    if os.name != "nt":
        raise OSError("开机启动仅支持 Windows")
    import winreg
    if enabled:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ,
                              command or command_for_app())
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass
