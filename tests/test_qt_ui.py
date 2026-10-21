"""Safety and pixel-data checks for the new Qt/WebEngine interface.

These tests never construct a device worker or open a USB endpoint.
"""
import unittest
from types import SimpleNamespace

from app_qt import PixelHouseQt, frame_colors, thumbnail_colors
from pixelhouse.effects import COLS, ROWS, make_frames


class QtInterfaceTests(unittest.TestCase):
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

    def test_upload_requires_confirmation(self):
        controller = SimpleNamespace(_upload=lambda: self.fail("upload started"))
        with self.assertRaisesRegex(ValueError, "确认"):
            PixelHouseQt.action(controller, "upload", {})

    def test_schedule_rejects_invalid_time(self):
        controller = SimpleNamespace(rules=[])
        with self.assertRaisesRegex(ValueError, "有效"):
            PixelHouseQt.action(controller, "schedule_add", {"start": "99:99", "end": "18:00", "mode": 1})
        self.assertEqual(controller.rules, [])


if __name__ == "__main__":
    unittest.main()
