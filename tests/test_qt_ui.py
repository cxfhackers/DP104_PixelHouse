"""Safety and pixel-data checks for the new Qt/WebEngine interface.

These tests never construct a device worker or open a USB endpoint.
"""
import unittest
import queue
import time
from types import SimpleNamespace

from app_qt import PixelHouseQt, device_status_text, frame_colors, thumbnail_colors
from pixelhouse.effects import COLS, ROWS, make_frames
from pixelhouse import prototype_scenes


class QtInterfaceTests(unittest.TestCase):
    def test_device_card_explains_hid_without_cdc_as_ready(self):
        state = {"connected": True, "serial": False, "port": None,
                 "cdc_support": False, "transport": "hid"}
        self.assertIn("可通过 HID 上传", device_status_text(state))
        self.assertNotIn("未检测到", device_status_text(state))

    def test_window_controls_use_real_window_states(self):
        calls = []
        controller = SimpleNamespace(showMinimized=lambda: calls.append("minimize"),
                                     showMaximized=lambda: calls.append("maximize"),
                                     showNormal=lambda: calls.append("restore"),
                                     isMaximized=lambda: False,
                                     close_app=lambda: calls.append("close"))
        PixelHouseQt.action(controller, "window_minimize", {})
        PixelHouseQt.action(controller, "window_toggle_maximize", {})
        controller.isMaximized = lambda: True
        PixelHouseQt.action(controller, "window_toggle_maximize", {})
        PixelHouseQt.action(controller, "window_close", {})
        self.assertEqual(calls, ["minimize", "maximize", "restore", "close"])

    def test_preview_colors_have_exact_keyboard_shape(self):
        frames = make_frames("心跳")
        self.assertEqual(len(frame_colors(frames[0])), ROWS * COLS)
        self.assertEqual(len(thumbnail_colors(frames)), ROWS * COLS)
        self.assertTrue(any(thumbnail_colors(frames)))

    def test_selecting_effect_only_changes_preview(self):
        sent = []
        selected = []
        controller = SimpleNamespace(device=SimpleNamespace(send=lambda *args: sent.append(args)),
                                     set_preview=lambda *args: selected.append(args))
        PixelHouseQt.action(controller, "effect", {"name": "心跳"})
        self.assertEqual(selected[0][0], "心跳")
        self.assertEqual(sent, [])

    def test_gallery_cards_preview_the_exact_frames_selected_for_upload(self):
        self.assertEqual(len(prototype_scenes.SCENES), 14)
        gallery_previews = PixelHouseQt.bootstrap(SimpleNamespace())["galleryPreviews"]
        for name in prototype_scenes.SCENES:
            frames, fps = prototype_scenes.make_scene(name)
            self.assertEqual(fps, 8)
            self.assertEqual(len(frames), 8)
            self.assertTrue(all(len(frame) == ROWS * COLS * 3 for frame in frames))
            self.assertEqual(gallery_previews[name], frame_colors(frames[0]))
        sent = []
        selected = []
        controller = SimpleNamespace(device=SimpleNamespace(send=lambda *args: sent.append(args)),
                                     set_preview=lambda *args: selected.append(args),
                                     _upload=lambda: sent.append(("upload", selected[-1])))
        PixelHouseQt.action(controller, "gallery", {"name": "可爱猫咪"})
        self.assertEqual(selected[0][0], "可爱猫咪")
        self.assertEqual(sent, [])
        PixelHouseQt.action(controller, "upload", {"scene": "心动爱心", "confirmed": True})
        self.assertEqual(sent[0][0], "upload")
        self.assertEqual(sent[0][1], selected[-1])
        self.assertEqual(selected[-1][1], prototype_scenes.make_scene("心动爱心")[0])

    def test_upload_requires_confirmation(self):
        controller = SimpleNamespace(_upload=lambda: self.fail("upload started"))
        with self.assertRaisesRegex(ValueError, "确认"):
            PixelHouseQt.action(controller, "upload", {})

    def test_probe_explains_no_device_preview_mode(self):
        controller = SimpleNamespace(no_device=True)
        with self.assertRaisesRegex(ValueError, "无设备预览模式"):
            PixelHouseQt.action(controller, "probe", {})

    def test_probe_result_is_shown_in_device_card_state(self):
        sent = []
        controller = SimpleNamespace(no_device=False, probe_status="", notice="",
                                     device=SimpleNamespace(send=lambda *args: sent.append(args)))
        PixelHouseQt.action(controller, "probe", {})
        self.assertEqual(sent, [("probe_serial", None)])
        self.assertIn("正在检测", controller.probe_status)
        controller.updates = queue.Queue()
        controller.updates.put(("probe_result", "HID 已连接，但没有 USB CDC 串口"))
        controller.preview_playing = False
        controller.last_metrics_save = time.monotonic()
        PixelHouseQt.refresh(controller)
        self.assertEqual(controller.probe_status, "HID 已连接，但没有 USB CDC 串口")

    def test_schedule_rejects_invalid_time(self):
        controller = SimpleNamespace(rules=[])
        with self.assertRaisesRegex(ValueError, "有效"):
            PixelHouseQt.action(controller, "schedule_add", {"start": "99:99", "end": "18:00", "mode": 1})
        self.assertEqual(controller.rules, [])


if __name__ == "__main__":
    unittest.main()
