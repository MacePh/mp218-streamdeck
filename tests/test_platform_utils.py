import ctypes
import sys
import unittest
from unittest import mock

from core import platform_utils


class PlatformUtilsTests(unittest.TestCase):
    def test_sendinput_input_struct_is_full_union_size(self) -> None:
        # x64 Windows INPUT must include the mouse branch so sizeof is 40, not ~32.
        import sys

        if sys.maxsize > 2**32:
            self.assertEqual(ctypes.sizeof(platform_utils.INPUT), 40)

    def test_paste_ctrl_v_falls_back_to_keybd_event_when_sendinput_fails(self) -> None:
        fake_windll = mock.Mock()
        fake_windll.user32.SendInput.return_value = 0
        keybd = fake_windll.user32.keybd_event
        with mock.patch.object(platform_utils.ctypes, "windll", fake_windll):
            platform_utils._paste_ctrl_v()

        self.assertGreaterEqual(keybd.call_count, 4)

    def test_send_unicode_text_returns_false_when_sendinput_rejects_event(self) -> None:
        fake_windll = mock.Mock()
        fake_windll.user32.SendInput.side_effect = [1, 0]

        with mock.patch.object(platform_utils.ctypes, "windll", fake_windll):
            self.assertFalse(platform_utils.send_unicode_text("A"))

    def test_send_text_windows_restores_known_target_before_paste(self) -> None:
        with mock.patch(
            "core.platform_utils._try_pywinauto_insert_at_focus", return_value=False
        ), mock.patch("core.platform_utils.restore_foreground_window", return_value=True) as restore_window, mock.patch(
            "core.platform_utils.paste_text_via_clipboard", return_value=True
        ) as paste_text, mock.patch("core.platform_utils.send_unicode_text") as send_unicode_text:
            strategy = platform_utils.send_text_windows("hello", target_hwnd=456)

        restore_window.assert_called_once_with(456, use_alt_unlock=False)
        paste_text.assert_called_once_with("hello")
        send_unicode_text.assert_not_called()
        self.assertEqual(strategy, "clipboard-restored")

    def test_send_text_windows_prefers_uia_when_edit_focus_succeeds(self) -> None:
        with mock.patch(
            "core.platform_utils._try_pywinauto_insert_at_focus", return_value=True
        ), mock.patch("core.platform_utils.restore_foreground_window", return_value=True), mock.patch(
            "core.platform_utils.paste_text_via_clipboard", return_value=True
        ) as paste_text:
            strategy = platform_utils.send_text_windows("hello", target_hwnd=456)

        paste_text.assert_not_called()
        self.assertEqual(strategy, "uia-restored")

    def test_send_text_windows_falls_back_to_clipboard_when_restore_fails(self) -> None:
        with mock.patch(
            "core.platform_utils._try_pywinauto_insert_at_focus", return_value=False
        ), mock.patch("core.platform_utils.restore_foreground_window", return_value=False) as restore_window, mock.patch(
            "core.platform_utils.paste_text_via_clipboard", return_value=True
        ) as paste_text:
            strategy = platform_utils.send_text_windows("hello", target_hwnd=456)

        self.assertEqual(restore_window.call_count, 3)
        self.assertEqual(
            restore_window.call_args_list,
            [
                mock.call(456, use_alt_unlock=False),
                mock.call(456, use_alt_unlock=True),
                mock.call(456, use_alt_unlock=True),
            ],
        )
        paste_text.assert_called_once_with("hello")
        self.assertEqual(strategy, "clipboard-fallback")

    def test_send_text_windows_falls_back_to_clipboard_when_unicode_injection_looks_unreliable(self) -> None:
        with mock.patch("core.platform_utils._wait_for_foreground_window", return_value=123), mock.patch(
            "core.platform_utils._get_foreground_window", return_value=123
        ), mock.patch("core.platform_utils.send_unicode_text", return_value=True) as send_unicode_text, mock.patch(
            "core.platform_utils.paste_text_via_clipboard", return_value=True
        ) as paste_text:
            strategy = platform_utils.send_text_windows("hello")

        send_unicode_text.assert_called_once_with("hello")
        paste_text.assert_called_once_with("hello")
        self.assertEqual(strategy, "clipboard")

    def test_send_text_windows_uses_clipboard_when_unicode_injection_fails(self) -> None:
        with mock.patch("core.platform_utils._wait_for_foreground_window", return_value=123), mock.patch(
            "core.platform_utils.send_unicode_text", return_value=False
        ), mock.patch("core.platform_utils.paste_text_via_clipboard", return_value=True) as paste_text:
            strategy = platform_utils.send_text_windows("hello")

        paste_text.assert_called_once_with("hello")
        self.assertEqual(strategy, "clipboard")

    def test_get_clipboard_unicode_text_reads_bounded_global_size(self) -> None:
        """Avoid ctypes.wstring_at on CF_UNICODETEXT (can AV if block is not NUL-terminated)."""
        fake_windll = mock.Mock()
        fake_windll.user32.OpenClipboard.return_value = 1
        fake_windll.user32.CloseClipboard.return_value = 1
        fake_windll.user32.IsClipboardFormatAvailable.return_value = 1
        fake_windll.user32.GetClipboardData.return_value = 99
        fake_windll.kernel32.GlobalSize.return_value = 6
        fake_windll.kernel32.GlobalLock.return_value = 4096
        fake_windll.kernel32.GlobalUnlock.return_value = 1

        hi_utf16 = "hi".encode("utf-16-le") + b"\x00\x00"
        self.assertEqual(len(hi_utf16), 6)

        with mock.patch.object(platform_utils.ctypes, "windll", fake_windll), mock.patch(
            "core.platform_utils.ctypes.string_at", return_value=hi_utf16
        ) as string_at:
            out = platform_utils._get_clipboard_unicode_text()

        self.assertEqual(out, "hi")
        string_at.assert_called_once()
        self.assertEqual(string_at.call_args[0][1], 6)

    @unittest.skipUnless(sys.platform == "win32", "Windows-only clipboard prototypes")
    def test_clipboard_global_lock_is_pointer_sized(self) -> None:
        """Regression: default ctypes c_int truncates GlobalLock on 64-bit, causing false 'GlobalLock failed'."""
        self.assertIs(ctypes.windll.kernel32.GlobalLock.restype, ctypes.c_void_p)
        self.assertIs(ctypes.windll.kernel32.GlobalAlloc.restype, ctypes.c_void_p)


if __name__ == "__main__":
    unittest.main()
