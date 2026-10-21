"""Mac platform behavior without opening or writing to a physical keyboard."""

import plistlib
import queue
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pixelhouse import device, startup
from pixelhouse.paths import data_dir


class MacSupportTests(unittest.TestCase):
    def test_hid_uses_vendor_usage_not_interface_number(self):
        keyboard = {"usage_page": 0xFF60, "usage": 0x61,
                    "interface_number": -1, "serial_number": "ABC", "path": b"dp104"}
        other = {**keyboard, "usage": 0x62, "path": b"other"}
        with patch.object(device.sys, "platform", "darwin"), \
             patch("pixelhouse.device.hid.enumerate", return_value=[other, keyboard]):
            self.assertIs(device.find_keyboard(), keyboard)

    def test_single_mac_serial_port_uses_callout_device(self):
        descriptor = {"serial_number": "HID-SERIAL"}
        port = SimpleNamespace(vid=device.VID, pid=device.PID,
                               serial_number="CDC-SERIAL", device="/dev/cu.usbmodem123")
        with patch.object(device.sys, "platform", "darwin"), \
             patch("pixelhouse.device.list_ports.comports", return_value=[port]):
            self.assertEqual(device.find_port(descriptor), port.device)
        with patch.object(device.sys, "platform", "darwin"), \
             patch("pixelhouse.device.list_ports.comports", return_value=[port, port]):
            self.assertIsNone(device.find_port(descriptor))

    def test_mac_discovery_never_probes_serial(self):
        worker = device.DeviceWorker(None, queue.Queue())
        with patch.object(device.sys, "platform", "darwin"), \
             patch("pixelhouse.device.find_port", return_value="/dev/cu.usbmodem123"), \
             patch("pixelhouse.device.probe_serial") as probe:
            state = worker._serial_state({"serial_number": "ABC"})
        probe.assert_not_called()
        self.assertTrue(state["serial"])
        self.assertFalse(state["serial_verified"])

    def test_hid_connection_remains_visible_without_cdc_port(self):
        worker = device.DeviceWorker(None, queue.Queue())
        with patch("pixelhouse.device.find_port", return_value=None):
            state = worker._serial_state({"serial_number": "ABC"})
        self.assertTrue(state["connected"])
        self.assertFalse(state["serial"])
        self.assertEqual(state["serial_error"], "HID 上传能力待确认（CDC 串口未出现）")

    def test_firmware_without_cdc_selects_hid_upload(self):
        worker = device.DeviceWorker(None, queue.Queue())
        with patch("pixelhouse.device.find_port", return_value=None), \
             patch("pixelhouse.device.hid_cdc_support", return_value=False):
            state = worker._serial_state({"serial_number": "ABC"}, object())
        self.assertTrue(state["connected"])
        self.assertFalse(state["serial"])
        self.assertEqual(state["transport"], "hid")
        self.assertFalse(worker.serial_failed)

    def test_unknown_hid_upload_capability_does_not_send_blindly(self):
        worker = device.DeviceWorker(None, queue.Queue())
        with patch("pixelhouse.device.find_port", return_value=None), \
             patch("pixelhouse.device.hid_cdc_support", return_value=None):
            state = worker._serial_state({"serial_number": "ABC"}, object())
        self.assertIsNone(state["transport"])
        self.assertTrue(worker.serial_failed)

    def test_mac_startup_writes_valid_current_user_launch_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Library" / "LaunchAgents" / "agent.plist"
            with patch.object(startup.sys, "platform", "darwin"), \
                 patch("pixelhouse.startup.mac_agent_path", return_value=path):
                startup.set_enabled(True)
                self.assertTrue(startup.is_enabled())
                data = plistlib.loads(path.read_bytes())
                self.assertEqual(data["ProgramArguments"][-1], "--tray")
                self.assertTrue(data["RunAtLoad"])
                startup.set_enabled(False)
                self.assertFalse(path.exists())

    def test_mac_data_directory(self):
        with patch("pixelhouse.paths.sys.platform", "darwin"), \
             patch("pixelhouse.paths.Path.home", return_value=Path("/Users/example")):
            self.assertEqual(data_dir(), Path("/Users/example/Library/Application Support/DP104_PixelHouse"))

    def test_packaged_windows_startup_command_uses_current_exe(self):
        path = Path("C:/Program Files/DP104/DP104_PixelHouse.exe")
        with patch.object(startup.sys, "frozen", True, create=True):
            self.assertEqual(startup.command_for_app(path), f'"{path.resolve()}" --tray')


if __name__ == "__main__":
    unittest.main()
