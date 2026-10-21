"""DP104_PixelHouse desktop app: custom pixel-glass UI with the existing device worker."""
from __future__ import annotations

import colorsys
import atexit
import ctypes
import datetime as dt
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Slot, QLibraryInfo
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QSystemTrayIcon, QMenu

from pixelhouse import ai_designer, image_import, lights, pets, presetlib, scheduler, startup, transitions
from pixelhouse.device import DeviceWorker, MODES
from pixelhouse.effects import COLS, EFFECTS, MAX_FRAMES, ROWS, dim_frames, make_frames
from pixelhouse.keymap import KEYS as PHYSICAL_KEYS
from pixelhouse.metrics import TypingMetrics
from pixelhouse.milestones import Milestones
from pixelhouse.paths import data_dir
from pixelhouse.presets import make_milestone_frames

ROOT = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    ROOT = Path(getattr(sys, "_MEIPASS", ROOT))


def ensure_ascii_qt_plugin_path():
    """Qt's macOS plugin scanner skips dylibs below a non-ASCII workspace path."""
    source = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    if source.exists() and not str(source).isascii():
        target = Path(tempfile.mkdtemp(prefix="dp104-qt-plugins-"))
        for plugin in source.rglob("*"):
            if plugin.is_file():
                link = target / plugin.relative_to(source)
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(plugin)
        os.environ["QT_PLUGIN_PATH"] = str(target)
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(target / "platforms")
        atexit.register(shutil.rmtree, target, ignore_errors=True)


def acquire_mutex():
    if sys.platform == "darwin":
        import fcntl
        path = data_dir() / "app.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise RuntimeError("已有 DP104 控制程序运行，请先退出旧程序。") from exc
        return handle
    if os.name == "nt":
        kernel = ctypes.windll.kernel32
        kernel.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel.CreateMutexW(None, False, "Local\\DP104_E560_E104_Controller")
        if not handle or kernel.GetLastError() == 183:
            if handle:
                kernel.CloseHandle(handle)
            raise RuntimeError("已有 DP104 控制程序运行，请先退出旧程序。")
        return handle
    return None


def frame_colors(frame: bytes, brightness: int = 255) -> list[str]:
    """The same HSV data sent to the keyboard, rendered without smoothing."""
    colors = []
    for offset in range(0, ROWS * COLS * 3, 3):
        hue, sat, val = frame[offset:offset + 3]
        val = round(val * brightness / 255)
        if val < 20:
            colors.append("")
            continue
        r, g, b = colorsys.hsv_to_rgb(hue / 255, sat / 255, val / 255)
        colors.append(f"#{round(r*255):02x}{round(g*255):02x}{round(b*255):02x}")
    return colors


def thumbnail_colors(frames: list[bytes]) -> list[str]:
    """Show the brightest point visited by each LED during an effect cycle."""
    result = bytearray(ROWS * COLS * 3)
    for frame in frames:
        for offset in range(0, len(result), 3):
            if frame[offset + 2] > result[offset + 2]:
                result[offset:offset + 3] = frame[offset:offset + 3]
    return frame_colors(bytes(result))


class AutoWorker:
    def __init__(self, device, milestones, updates):
        self.device, self.milestones, self.updates = device, milestones, updates
        self.schedule_path = data_dir() / "schedule.json"
        self.last_rule_key = ""
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name="dp104-auto", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2)

    def run(self):
        while not self.stop_event.is_set():
            try:
                config = scheduler.load(self.schedule_path)
                rule = scheduler.active_rule(config, dt.datetime.now())
                key = "" if rule is None else scheduler.rule_line(rule)
                if rule is None:
                    self.last_rule_key = ""
                elif key != self.last_rule_key:
                    self.last_rule_key = key
                    if rule["kind"] == "mode":
                        self.device.send("mode", int(rule["value"]))
                        self.updates.put(("notice", f"定时场景：{scheduler.describe(rule)} 已生效"))
                    else:
                        self.updates.put(("notice", "定时亮度规则未执行：当前固件屏幕亮度指令无可见效果"))
                keys = self.device.metrics.snapshot()["keys_today"]
                fired = self.milestones.sync(keys) if keys > 0 else None
                if fired and self.milestones.enabled and not self.device.uploading:
                    self.updates.put(("milestone", fired))
            except Exception:
                pass
            self.stop_event.wait(20)


class Bridge(QObject):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller

    @Slot(result=str)
    def bootstrap(self):
        return json.dumps(self.controller.bootstrap(), ensure_ascii=False)

    @Slot(result=str)
    def state(self):
        return json.dumps(self.controller.state(), ensure_ascii=False)

    @Slot(str, str, result=str)
    def action(self, name, payload):
        try:
            result = self.controller.action(name, json.loads(payload or "{}"))
            return json.dumps({"ok": True, "value": result}, ensure_ascii=False)
        except Exception as exc:
            self.controller.notice = str(exc)
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


class PixelHousePage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        if os.environ.get("DP104_PIXELHOUSE_DEBUG_UI") == "1":
            print(f"UI console {level} {source}:{line}: {message}", flush=True)


class PixelHouseQt(QWebEngineView):
    def __init__(self, mutex):
        super().__init__()
        self.mutex = mutex
        self.closing = False
        self.no_device = os.environ.get("DP104_PIXELHOUSE_NO_DEVICE") == "1"
        self.updates = queue.Queue()
        self.metrics = TypingMetrics(data_dir() / "typing.json")
        self.device = DeviceWorker(self.metrics, self.updates)
        self.milestones = Milestones(data_dir() / "milestone.json", enabled=sys.platform != "darwin")
        self.auto = AutoWorker(self.device, self.milestones, self.updates)
        self.device_state = {"connected": False, "serial": False, "port": None}
        self.lights_state = {"keys": {}, "bar": {}}
        self.mode = None
        self.notice = "小屋已开门，正在寻找 DP104 键盘…" if not self.no_device else "预览模式：未连接实体键盘"
        self.preview_name = "霓虹小猫"
        self.preview_frames, self.preview_fps = pets.make_scene("霓虹小猫")
        self.preview_index = 0
        self.preview_playing = True
        self.preview_speed = 1.0
        self.upload_brightness = 204
        self.ai_frames = None
        self.ai_generating = False
        self.ai_status = "写一句画面描述，让 AI 生成 8×24 动画。"
        self.ai_settings_path = data_dir() / "ai.json"
        self.ai_settings = ai_designer.load_settings(self.ai_settings_path)
        self.import_fit = "完整显示"
        self.slot_index = 0
        self.slots = ["" for _ in range(5)]
        self.pending_slot_export = False
        self.rules_config = scheduler.load(self.auto.schedule_path)
        self.rules = list(self.rules_config.get("rules", []))
        self.last_frame_tick = time.monotonic()
        self.last_metrics_save = time.monotonic()
        self.tray = None
        self.setWindowTitle("DP104_PixelHouse")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setStyleSheet("background-color: #0a1245;")
        self.setPage(PixelHousePage(self))
        self.page().setBackgroundColor(QColor("#0a1245"))
        self.setMinimumSize(940, 705)
        available = QApplication.primaryScreen().availableGeometry()
        scale = min(1.0, available.width() / 1460, available.height() / 1098)
        self.resize(round(1448 * scale), round(1086 * scale))
        self.move(available.center() - self.rect().center())
        self.bridge = Bridge(self)
        channel = QWebChannel(self.page())
        channel.registerObject("pixelhouse", self.bridge)
        self.page().setWebChannel(channel)
        self.load(QUrl.fromLocalFile(str(ROOT / "pixelhouse" / "ui" / "index.html")))
        self.loadFinished.connect(self._on_load_finished)
        self._setup_tray()
        if not self.no_device:
            self.device.start()
            self.auto.start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(130)
        if os.environ.get("DP104_PIXELHOUSE_SMOKE") == "1":
            QTimer.singleShot(6000, self.close_app)
        capture = os.environ.get("DP104_PIXELHOUSE_CAPTURE")
        if capture:
            QTimer.singleShot(3000, lambda: self.grab().save(capture))
        if "--tray" in sys.argv and self.tray:
            QTimer.singleShot(600, self.hide)
        else:
            self.show()

    def _on_load_finished(self, ok):
        if os.environ.get("DP104_PIXELHOUSE_DEBUG_UI") == "1":
            print(f"DP104 UI loaded: {ok}", flush=True)
        if not ok:
            QMessageBox.critical(self, "DP104_PixelHouse", "界面资源加载失败，请重新安装完整应用包。")

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.notice = "菜单栏不可用；请保持窗口打开"
            return
        pix = QPixmap(32, 32)
        pix.fill(QColor("#101743"))
        from PySide6.QtGui import QPainter, QPen
        painter = QPainter(pix)
        painter.setPen(QPen(QColor("#ff8dde"), 3))
        painter.drawRect(6, 8, 20, 18)
        painter.drawPoint(11, 15)
        painter.drawPoint(21, 15)
        painter.end()
        self.tray = QSystemTrayIcon(QIcon(pix), self)
        menu = QMenu()
        menu.setStyleSheet("QMenu {background:#161e56;color:#eef2ff;border:2px solid #89a7ff;} QMenu::item:selected{background:#374ac0;}")
        menu.addAction("打开 DP104_PixelHouse", self.show_window)
        menu.addAction("退出程序", self.close_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_window() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def closeEvent(self, event):
        if self.closing or not self.tray:
            event.accept()
        else:
            event.ignore()
            self.hide()

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def close_app(self):
        if self.closing:
            return
        self.closing = True
        self.timer.stop()
        if not self.no_device:
            self.auto.stop()
            self.device.stop()
        try:
            self.metrics.save()
        except OSError:
            pass
        if self.tray:
            self.tray.hide()
        if self.mutex and os.name == "nt":
            ctypes.windll.kernel32.CloseHandle(self.mutex)
        elif self.mutex:
            self.mutex.close()
        self.close()
        QApplication.quit()

    def refresh(self):
        while True:
            try:
                kind, value = self.updates.get_nowait()
            except queue.Empty:
                break
            if kind == "device":
                was_connected = self.device_state.get("connected")
                self.device_state = value
                if value.get("connected") and not was_connected:
                    self.device.send("light_read", None)
                elif not value.get("connected"):
                    self.mode = None
                    self.lights_state = {"keys": {}, "bar": {}}
            elif kind == "mode":
                self.mode = value
            elif kind == "notice":
                self.notice = str(value)
            elif kind == "ai_result":
                fps, frames = value
                self.ai_generating = False
                self.ai_frames = (fps, frames)
                self.set_preview("AI 作品", frames, fps)
                self.ai_status = f"完成！{len(frames)} 帧 @ {fps} fps，可保存或上屏。"
            elif kind == "ai_error":
                self.ai_generating = False
                self.ai_status = f"生成失败：{value}"
                self.notice = self.ai_status
            elif kind == "image_result":
                name, frames, fps = value
                self.set_preview(name, frames, fps)
                self.notice = f"已导入「{name}」：{len(frames)} 帧 @ {fps} fps"
            elif kind == "image_error":
                self.notice = f"导入失败：{value}"
            elif kind == "ai_test":
                self.notice = f"接口连接成功 · {value}"
            elif kind == "ai_test_error":
                self.notice = f"接口测试失败：{value}"
            elif kind == "text_slots":
                self.slots = list(value)
                if self.pending_slot_export:
                    self.pending_slot_export = False
                    target, _ = QFileDialog.getSaveFileName(self, "备份文本槽", "文本槽备份.json", "JSON (*.json)")
                    if target:
                        Path(target).write_text(json.dumps({"slots": self.slots}, ensure_ascii=False, indent=2), encoding="utf-8")
                        self.notice = f"文本槽已备份到 {target}"
                else:
                    self.notice = f"文本槽 {self.slot_index + 1} 已读入"
            elif kind == "lights_full":
                self.lights_state = value
                self.notice = "灯光当前值已读入"
            elif kind == "light_value":
                channel, sub, *values = value
                group = "keys" if channel == lights.KEYS else "bar"
                self.lights_state.setdefault(group, {})[sub] = values[0] if sub != 4 else values
            elif kind == "milestone":
                self._fire_milestone(value)
        now = time.monotonic()
        if self.preview_playing and len(self.preview_frames) > 1 and now - self.last_frame_tick >= 1 / max(1, self.preview_fps * self.preview_speed):
            self.preview_index = (self.preview_index + 1) % len(self.preview_frames)
            self.last_frame_tick = now
        if now - self.last_metrics_save > 25:
            self.last_metrics_save = now
            try:
                self.metrics.save()
            except OSError:
                pass

    def _fire_milestone(self, keys):
        state = self.device_state
        if state.get("connected") and state.get("serial") and self.mode != 2:
            self.device.send("animation", (make_milestone_frames(keys), 6))
            self.notice = f"达到 {keys:,} 键，庆祝画面已推送"
        else:
            self.notice = f"达到 {keys:,} 键，当前屏幕不可推送"

    def set_preview(self, name, frames, fps):
        if not frames or any(len(frame) != ROWS * COLS * 3 for frame in frames):
            raise ValueError("动画必须包含 8×24 HSV 画面")
        self.preview_name, self.preview_frames, self.preview_fps = name, frames, max(1, min(30, int(fps)))
        self.preview_index = 0
        self.preview_playing = True

    def bootstrap(self):
        return {
            "effects": list(EFFECTS),
            "effectPreviews": {name: thumbnail_colors(make_frames(name, 16)) for name in EFFECTS},
            "petPreviews": {name: frame_colors(pets.make_scene(name)[0][0]) for name in ("霓虹小猫", "兔兔跳跳")},
            "pets": [{"name": name, "description": description} for name, description, _, _ in pets.SCENES],
            "modes": [{"value": value, "name": name} for value, name in MODES.items()],
            "lightEffects": {group: lights.effect_options(group) for group in ("keys", "bar")},
            "ruleModes": [{"value": value, "name": name} for name, value in scheduler.MODE_CHOICES],
            "platform": sys.platform,
        }

    def state(self):
        snapshot = self.metrics.snapshot()
        cells, _ = self.metrics.cells_snapshot()
        connected = bool(self.device_state.get("connected"))
        port = self.device_state.get("port")
        return {
            "device": {**self.device_state, "mode": self.mode, "modeName": MODES.get(self.mode, "未知模式")},
            "notice": self.notice, "previewName": self.preview_name,
            "preview": frame_colors(self.preview_frames[self.preview_index], self.upload_brightness),
            "previewFps": self.preview_fps, "previewCount": len(self.preview_frames),
            "playing": self.preview_playing, "brightness": round(self.upload_brightness * 100 / 255),
            "uploading": bool(getattr(self.device, "uploading", False)),
            "presets": presetlib.names(), "aiGenerating": self.ai_generating,
            "aiStatus": self.ai_status, "settings": {"base_url": self.ai_settings["base_url"], "model": self.ai_settings["model"]},
            "metrics": snapshot, "heat": {f"{row}:{col}": count for (row, col), count in cells.items()},
            "keymap": [{"legend": key.legend, "row": key.row, "col": key.col, "x": key.x, "y": key.y, "width": key.width, "height": key.height} for key in PHYSICAL_KEYS],
            "rules": [scheduler.rule_line(rule) for rule in self.rules],
            "scheduleEnabled": bool(self.rules_config.get("enabled")),
            "milestoneEnabled": self.milestones.enabled, "milestoneStep": self.milestones.step,
            "startupEnabled": startup.is_enabled(), "slots": self.slots, "slotIndex": self.slot_index,
            "lights": self.lights_state, "lightsLoaded": {group: all(sub in self.lights_state.get(group, {}) for sub in (1, 2, 3, 4)) for group in ("keys", "bar")},
            "connectionText": ("键盘未连接" if not connected else f"{port or '串口未找到'} · {MODES.get(self.mode, '未知模式')}")
        }

    def _upload(self):
        if not self.device_state.get("connected"):
            self.notice = "尚未连接键盘；画面已留在预览，连接后再上屏"
            return
        if not self.device_state.get("serial"):
            self.notice = "USB 串口不可用，请检查连接后重试"
            return
        self.device.send("animation", (dim_frames(self.preview_frames, self.upload_brightness), self.preview_fps))
        self.notice = "正在检查串口并发送画面…"

    def _dialog_open(self, title, filter_):
        path, _ = QFileDialog.getOpenFileName(self, title, "", filter_, options=QFileDialog.Option.DontUseNativeDialog)
        return Path(path) if path else None

    def _dialog_save(self, title, initial, filter_):
        path, _ = QFileDialog.getSaveFileName(self, title, initial, filter_, options=QFileDialog.Option.DontUseNativeDialog)
        return Path(path) if path else None

    def action(self, name, data):
        if name == "window_drag":
            self.move(self.pos().x() + int(data.get("dx", 0)), self.pos().y() + int(data.get("dy", 0)))
        elif name == "window_start_drag":
            if self.windowHandle():
                self.windowHandle().startSystemMove()
        elif name == "window_close":
            self.close_app()
        elif name == "window_hide":
            self.hide()
        elif name == "window_show":
            self.show_window()
        elif name == "mode":
            value = int(data["value"])
            if value not in MODES:
                raise ValueError("未知屏幕模式")
            self.device.send("mode", value)
            self.notice = f"正在切换到「{MODES[value]}」…"
        elif name == "probe":
            self.device.send("probe_serial", None)
            self.notice = "正在重新探测 DP104…"
        elif name == "restart_usb":
            if os.name != "nt":
                raise ValueError("USB 软件重启仅在 Windows 可用")
            if not self.device_state.get("connected"):
                raise ValueError("请先连接 DP104")
            self.device.send("restart_usb", None)
            self.notice = "等待管理员确认后重启键盘 USB…"
        elif name == "effect":
            effect = str(data["name"])
            self.set_preview(effect, make_frames(effect), 8)
        elif name == "pet":
            pet = str(data["name"])
            frames, fps = pets.make_scene(pet)
            self.set_preview(pet, frames, fps)
        elif name == "play":
            self.preview_playing = bool(data["value"])
        elif name == "preview_speed":
            self.preview_speed = max(0.25, min(3.0, float(data["value"])))
        elif name == "brightness":
            self.upload_brightness = max(0, min(255, round(int(data["value"]) * 255 / 100)))
        elif name == "upload":
            if not data.get("confirmed"):
                raise ValueError("请先确认上传前的屏幕模式提示")
            self._upload()
        elif name == "save_preset":
            presetlib.save(str(data["name"]).strip(), self.preview_frames, self.preview_fps, "manual")
            self.notice = f"已保存预设「{data['name']}」"
        elif name == "preset_select":
            frames, fps = presetlib.load(data["name"])
            self.set_preview(data["name"], frames, fps)
        elif name == "preset_rename":
            presetlib.rename(data["name"], data["new"])
            self.notice = f"预设已改名为「{data['new']}」"
        elif name == "preset_delete":
            presetlib.delete(data["name"])
            self.notice = f"已删除预设「{data['name']}」"
        elif name == "preset_import":
            path = self._dialog_open("导入 DP104 预设", "JSON (*.json)")
            if path:
                imported = presetlib.import_from(path)
                self.notice = f"已导入预设「{imported}」"
        elif name == "preset_export":
            path = self._dialog_save("导出 DP104 预设", f"{data['name']}.json", "JSON (*.json)")
            if path:
                presetlib.export_to(data["name"], path)
                self.notice = f"已导出预设到 {path}"
        elif name == "import_animation":
            paths, _ = QFileDialog.getOpenFileNames(self, "导入动图或图片序列", "", "动画与图片 (*.gif *.tabml *.apng *.png *.webp *.jpg *.jpeg *.bmp)", options=QFileDialog.Option.DontUseNativeDialog)
            if paths:
                selection = [Path(p) for p in paths]
                self.notice = "正在转换图像…"
                def task():
                    try:
                        frames, fps = (image_import.import_tabml(selection[0]) if len(selection) == 1 and selection[0].suffix.lower() == ".tabml" else image_import.import_images(selection, data.get("fit", "完整显示")))
                        label = selection[0].stem if len(selection) == 1 else f"图片序列 · {len(selection)} 张"
                        self.updates.put(("image_result", (label, frames, fps)))
                    except Exception as exc:
                        self.updates.put(("image_error", str(exc)))
                threading.Thread(target=task, name="dp104-image-import", daemon=True).start()
        elif name == "ai_generate":
            if self.ai_generating:
                return None
            prompt = str(data.get("prompt", "")).strip()
            if not prompt:
                raise ValueError("先写一句画面描述")
            settings = ai_designer.load_settings(self.ai_settings_path)
            self.ai_generating = True
            self.ai_status = f"{settings['model']} 正在绘制…"
            def task():
                try:
                    fps, frames = ai_designer.generate(settings, prompt)
                    factor = max(1, min(int(data.get("tween", 1)), MAX_FRAMES // len(frames), 30 // fps))
                    frames, fps = transitions.tween_frames(frames, fps, factor)
                    self.updates.put(("ai_result", (fps, frames)))
                except Exception as exc:
                    self.updates.put(("ai_error", str(exc)))
            threading.Thread(target=task, name="dp104-ai", daemon=True).start()
        elif name == "ai_save":
            if not self.ai_frames:
                raise ValueError("先生成 AI 动画")
            fps, frames = self.ai_frames
            presetlib.save(str(data["name"]), frames, fps, "ai")
            self.notice = f"AI 作品已存为「{data['name']}」"
        elif name == "ai_settings":
            settings = {"base_url": data["base_url"], "api_key": data.get("api_key", "") or self.ai_settings["api_key"], "model": data["model"]}
            ai_designer.save_settings(self.ai_settings_path, settings)
            self.ai_settings = ai_designer.load_settings(self.ai_settings_path)
            self.notice = "AI 配置已保存"
        elif name == "ai_test":
            self.notice = "正在测试 AI 接口…"
            settings = ai_designer.load_settings(self.ai_settings_path)
            def task():
                try:
                    self.updates.put(("ai_test", ai_designer.test_connection(settings)))
                except Exception as exc:
                    self.updates.put(("ai_test_error", str(exc)))
            threading.Thread(target=task, name="dp104-ai-test", daemon=True).start()
        elif name == "ai_clear_key":
            settings = ai_designer.load_settings(self.ai_settings_path)
            settings["api_key"] = ""
            ai_designer.save_settings(self.ai_settings_path, settings)
            self.ai_settings = settings
            self.notice = "本机保存的 API Key 已清除"
        elif name == "slot_select":
            self.slot_index = max(0, min(4, int(data["index"])))
        elif name == "slot_read":
            self.device.send("text_backup", None)
            self.notice = "正在读取文本槽…"
        elif name == "slot_write":
            text = str(data.get("text", "")).upper()
            text.encode("ascii")
            if not text or len(text) > 30:
                raise ValueError("文本槽需要 1–30 个 ASCII 字符")
            self.device.send("text_write", (self.slot_index, text))
            self.notice = "正在写入文本槽…"
        elif name == "slot_export":
            self.pending_slot_export = True
            self.device.send("text_backup", None)
        elif name == "slot_restore":
            path = self._dialog_open("恢复文本槽", "JSON (*.json)")
            if path:
                slots = [str(v) for v in json.loads(path.read_text(encoding="utf-8")).get("slots", [])][:5]
                slots += [""] * (5 - len(slots))
                self.device.send("text_restore", slots)
                self.notice = "正在恢复文本槽…"
        elif name == "light_read":
            self.device.send("light_read", None)
            self.notice = "正在读取灯光设置…"
        elif name == "light_apply":
            group = data["group"]
            if group not in lights.GROUPS:
                raise ValueError("未知灯光分组")
            if not self.device_state.get("connected"):
                raise ValueError("请先连接 DP104")
            if not all(sub in self.lights_state.get(group, {}) for sub in (1, 2, 3, 4)):
                self.device.send("light_read", None)
                raise ValueError("先读取键盘当前设置，完成后再应用")
            channel = lights.GROUPS[group][0]
            color = lights.color_command_args(data["color"])
            effect = lights.effect_index(group, data["effect"])
            values = ((1, (int(data["brightness"]),)), (2, (effect or 0,)), (3, (int(data["speed"]),)), (4, color))
            self.device.send("light_apply", (group, channel, values))
            self.notice = f"正在应用{lights.GROUPS[group][2]}设置…"
        elif name == "schedule_add":
            rule = {"kind": "mode", "start": data["start"], "end": data["end"], "value": int(data["mode"])}
            clock = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d\Z")
            if (not clock.fullmatch(rule["start"]) or not clock.fullmatch(rule["end"])
                    or rule["start"] == rule["end"]
                    or rule["value"] not in {value for _, value in scheduler.MODE_CHOICES}):
                raise ValueError("规则需要有效的开始、结束时间和内置模式")
            self.rules.append(rule)
        elif name == "schedule_delete":
            index = int(data["index"])
            if 0 <= index < len(self.rules):
                del self.rules[index]
        elif name == "schedule_save":
            self.rules_config = {"enabled": bool(data["enabled"]), "rules": self.rules}
            scheduler.save(self.auto.schedule_path, self.rules_config)
            self.auto.last_rule_key = ""
            self.notice = "定时场景已保存"
        elif name == "milestone_save":
            self.milestones.configure(int(data["step"]), bool(data["enabled"]))
            self.notice = "打字里程碑设置已保存"
        elif name == "startup":
            startup.set_enabled(bool(data["enabled"]))
            self.notice = "开机启动已开启" if data["enabled"] else "开机启动已关闭"
        elif name == "open_data":
            path = data_dir()
            path.mkdir(parents=True, exist_ok=True)
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif os.name == "nt":
                os.startfile(path)
        elif name == "editor_get":
            return {"frames": [frame.hex() for frame in self.preview_frames], "fps": self.preview_fps, "name": self.preview_name}
        elif name == "editor_apply":
            frames = [bytes.fromhex(value) for value in data["frames"]]
            fps = int(data["fps"])
            if not 1 <= len(frames) <= MAX_FRAMES:
                raise ValueError("帧数需在 1–200 之间")
            self.set_preview(str(data.get("name") or self.preview_name), frames, fps)
            if data.get("save"):
                presetlib.save(str(data["save"]), frames, fps, "editor")
                self.notice = f"编辑结果已保存为「{data['save']}」"
            elif data.get("upload"):
                if not data.get("confirmed"):
                    raise ValueError("请先确认上传前的屏幕模式提示")
                self._upload()
            else:
                self.notice = "编辑结果已应用到预览"
        else:
            raise ValueError(f"不支持的操作：{name}")
        return None


def main():
    ensure_ascii_qt_plugin_path()
    app = QApplication(sys.argv)
    app.setApplicationName("DP104_PixelHouse")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet("QFileDialog,QMessageBox{background:#101947;color:#eef2ff;} QFileDialog QWidget{color:#eef2ff;background:#101947;} QFileDialog QPushButton,QMessageBox QPushButton{background:#273c9a;color:#eef2ff;border:2px solid #829ff2;padding:7px 14px;} QFileDialog QLineEdit,QFileDialog QComboBox{background:#0b163f;color:#eef2ff;border:1px solid #829ff2;padding:5px;} QFileDialog QListView,QFileDialog QTreeView{background:#0b163f;color:#eef2ff;selection-background-color:#385bc2;}")
    try:
        lock = acquire_mutex()
        window = PixelHouseQt(lock)
    except Exception as exc:
        QMessageBox.critical(None, "DP104_PixelHouse", str(exc))
        return 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
