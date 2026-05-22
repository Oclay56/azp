from __future__ import annotations

import ctypes
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, Button, Canvas, Frame, Label, Tk, Text, messagebox

from .local_helper_setup import check_local_helper_setup, format_setup_report


ROOT_DIR = Path(__file__).resolve().parents[1]
WPARAM = ctypes.c_size_t
LPARAM = ctypes.c_ssize_t
LRESULT = ctypes.c_ssize_t

HELPER_BG = "#03041D"
HELPER_FG = "#F4F0FF"
HELPER_MUTED_FG = "#C9C7D9"
HELPER_PANEL_BG = "#070923"
HELPER_BUTTON_BG = "#11143A"
HELPER_BUTTON_ACTIVE_BG = "#1A1E55"
LOGO_FONT_FAMILY = "Segoe Script"

SIDEBAR_BG = "#050719"
PANEL_BG = "#090B22"
PANEL_ALT_BG = "#0D102A"
PANEL_BORDER = "#20264F"
PANEL_BORDER_ACTIVE = "#4E58A8"
MUTED_TEXT = "#A7A8C2"
ACCENT = "#7877FF"
ACCENT_DARK = "#24245E"
READY = "#40D97D"
WARNING = "#F7B955"
ERROR = "#FF5B6E"


def should_minimize_to_tray(window_state: str, *, tray_supported: bool) -> bool:
    return tray_supported and window_state == "iconic"


def mode_description(mode: str) -> str:
    if mode == "build":
        return "Build mode can click exact validated legs into the visible slip for review only."
    return "Review mode reads exact Stake UI boards and leaves the slip untouched."


class WindowsTrayIcon:
    WM_TRAYICON = 0x0400 + 31
    WM_DESTROY = 0x0002
    WM_COMMAND = 0x0111
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205

    NIF_MESSAGE = 0x00000001
    NIF_ICON = 0x00000002
    NIF_TIP = 0x00000004
    NIM_ADD = 0x00000000
    NIM_DELETE = 0x00000002
    TPM_RETURNCMD = 0x0100
    TPM_RIGHTBUTTON = 0x0002
    MF_STRING = 0x0000
    IDI_APPLICATION = 32512

    RESTORE_COMMAND = 1001
    EXIT_COMMAND = 1002

    def __init__(
        self,
        tooltip: str,
        *,
        on_restore: Callable[[], None],
        on_exit: Callable[[], None],
    ) -> None:
        self.tooltip = tooltip[:127]
        self.on_restore = on_restore
        self.on_exit = on_exit
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._hwnd: int | None = None
        self._hicon: int | None = None
        self._visible = False
        self._wndproc = None
        self._class_name = f"AZP_LOCAL_HELPER_TRAY_{id(self)}"

    @staticmethod
    def is_supported() -> bool:
        return sys.platform == "win32"

    def show(self) -> bool:
        if not self.is_supported():
            return False
        if self._visible:
            return True

        if not self._thread or not self._thread.is_alive():
            self._ready.clear()
            self._thread = threading.Thread(target=self._message_loop, daemon=True)
            self._thread.start()

        if not self._ready.wait(timeout=2) or not self._hwnd:
            return False

        data = self._notify_data()
        shell32 = ctypes.windll.shell32
        self._visible = bool(shell32.Shell_NotifyIconW(self.NIM_ADD, ctypes.byref(data)))
        return self._visible

    def hide(self) -> None:
        if not self._visible or not self._hwnd:
            return
        data = self._notify_data()
        ctypes.windll.shell32.Shell_NotifyIconW(self.NIM_DELETE, ctypes.byref(data))
        self._visible = False

    def close(self) -> None:
        if not self.is_supported():
            return
        self.hide()
        if self._hwnd:
            ctypes.windll.user32.PostMessageW.argtypes = [
                wintypes.HWND,
                wintypes.UINT,
                WPARAM,
                LPARAM,
            ]
            ctypes.windll.user32.PostMessageW(self._hwnd, self.WM_DESTROY, 0, 0)

    def _notify_data(self):
        class NotifyIconData(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HANDLE),
                ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256),
                ("uTimeoutOrVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", ctypes.c_byte * 16),
                ("hBalloonIcon", wintypes.HANDLE),
            ]

        data = NotifyIconData()
        data.cbSize = ctypes.sizeof(NotifyIconData)
        data.hWnd = self._hwnd
        data.uID = 1
        data.uFlags = self.NIF_MESSAGE | self.NIF_ICON | self.NIF_TIP
        data.uCallbackMessage = self.WM_TRAYICON
        data.hIcon = self._hicon or ctypes.windll.user32.LoadIconW(None, self.IDI_APPLICATION)
        data.szTip = self.tooltip
        return data

    def _message_loop(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
        user32.DefWindowProcW.restype = LRESULT

        WNDPROC = ctypes.WINFUNCTYPE(
            LRESULT,
            wintypes.HWND,
            wintypes.UINT,
            WPARAM,
            LPARAM,
        )

        class WndClass(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == self.WM_TRAYICON:
                if lparam == self.WM_LBUTTONDBLCLK:
                    self.on_restore()
                    return 0
                if lparam == self.WM_RBUTTONUP:
                    self._show_menu(hwnd)
                    return 0
            if msg == self.WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            if msg == self.WM_COMMAND:
                command = wparam & 0xFFFF
                if command == self.RESTORE_COMMAND:
                    self.on_restore()
                elif command == self.EXIT_COMMAND:
                    self.on_exit()
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc = WNDPROC(wndproc)
        hinstance = kernel32.GetModuleHandleW(None)
        self._hicon = user32.LoadIconW(None, self.IDI_APPLICATION)

        wndclass = WndClass()
        wndclass.lpfnWndProc = self._wndproc
        wndclass.hInstance = hinstance
        wndclass.hIcon = self._hicon
        wndclass.lpszClassName = self._class_name
        user32.RegisterClassW(ctypes.byref(wndclass))

        self._hwnd = user32.CreateWindowExW(
            0,
            self._class_name,
            self._class_name,
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            hinstance,
            None,
        )
        self._ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _show_menu(self, hwnd: int) -> None:
        user32 = ctypes.windll.user32
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, self.MF_STRING, self.RESTORE_COMMAND, "Restore")
        user32.AppendMenuW(menu, self.MF_STRING, self.EXIT_COMMAND, "Exit")

        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(hwnd)
        command = user32.TrackPopupMenu(
            menu,
            self.TPM_RETURNCMD | self.TPM_RIGHTBUTTON,
            point.x,
            point.y,
            0,
            hwnd,
            None,
        )
        user32.DestroyMenu(menu)
        if command == self.RESTORE_COMMAND:
            self.on_restore()
        elif command == self.EXIT_COMMAND:
            self.on_exit()


class ChromeWindowDock:
    GWL_STYLE = -16
    WS_CHILD = 0x40000000
    WS_VISIBLE = 0x10000000
    WS_POPUP = 0x80000000
    WS_CAPTION = 0x00C00000
    WS_THICKFRAME = 0x00040000
    WS_SYSMENU = 0x00080000
    WS_MAXIMIZEBOX = 0x00010000
    WS_MINIMIZEBOX = 0x00020000
    SW_SHOW = 5

    def __init__(self, host: Frame, *, log: Callable[[str], None]) -> None:
        self.host = host
        self.log = log
        self.process: subprocess.Popen[bytes] | None = None
        self.hwnd: int | None = None
        self.original_parent: int | None = None
        self.original_style: int | None = None
        self._dock_attempts = 0

    @staticmethod
    def is_supported() -> bool:
        return sys.platform == "win32"

    def start_debug_chrome(self) -> bool:
        if not self.is_supported():
            self.log("Embedded Chrome is only supported on Windows. Opening externally instead.\n")
            return False

        try:
            from . import local_stake_helper

            local_stake_helper._load_dotenv(ROOT_DIR / ".env")
            chrome_path = local_stake_helper._chrome_path()
            if not chrome_path:
                self.log("Could not find Chrome. Set AZP_CHROME_PATH if needed.\n")
                return False

            cdp_url = local_stake_helper.DEFAULT_CDP_URL
            port = local_stake_helper._cdp_port(cdp_url)
            profile_dir = Path(
                local_stake_helper.os.getenv("AZP_STAKE_CHROME_PROFILE")
                or local_stake_helper.DEFAULT_CHROME_USER_DATA_DIR
            )
            if not profile_dir.is_absolute():
                profile_dir = ROOT_DIR / profile_dir
            profile_dir.mkdir(parents=True, exist_ok=True)

            args = local_stake_helper._debug_chrome_args(chrome_path, profile_dir, port)
            self.process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.log("Opening Stake debug Chrome session...\n")
            if _wait_for_cdp(local_stake_helper, cdp_url):
                return True
            self.log("Chrome opened, but the debug port is not ready yet. Falling back to helper autostart.\n")
            return False
        except Exception as exc:
            self.log(f"Could not start embedded Chrome session: {exc}\n")
            return False

    def dock_when_ready(self, root: Tk) -> None:
        if not self.is_supported():
            return
        self._dock_attempts = 0
        self._try_dock(root)

    def resize(self) -> None:
        if not self.hwnd or not self.is_supported():
            return
        width = max(self.host.winfo_width(), 1)
        height = max(self.host.winfo_height(), 1)
        ctypes.windll.user32.MoveWindow(self.hwnd, 0, 0, width, height, True)

    def release(self) -> None:
        if not self.hwnd or not self.is_supported():
            return
        user32 = ctypes.windll.user32
        try:
            if self.original_style is not None:
                _set_window_long(self.hwnd, self.GWL_STYLE, self.original_style)
            user32.SetParent(self.hwnd, self.original_parent or 0)
            user32.ShowWindow(self.hwnd, self.SW_SHOW)
        finally:
            self.hwnd = None
            self.original_parent = None
            self.original_style = None

    def _try_dock(self, root: Tk) -> None:
        self._dock_attempts += 1
        hwnd = _find_chrome_window(self.process.pid if self.process else None)
        if hwnd:
            if self._dock_window(hwnd):
                self.log("Stake browser docked into helper window.\n")
                return

        if self._dock_attempts < 30:
            root.after(500, lambda: self._try_dock(root))
            return

        self.log("Could not dock Chrome. The helper will still work with Chrome externally.\n")

    def _dock_window(self, hwnd: int) -> bool:
        try:
            self.host.update_idletasks()
            host_hwnd = self.host.winfo_id()
            user32 = ctypes.windll.user32
            self.original_parent = user32.GetParent(hwnd)
            self.original_style = _get_window_long(hwnd, self.GWL_STYLE)
            child_style = (
                self.original_style
                & ~(
                    self.WS_POPUP
                    | self.WS_CAPTION
                    | self.WS_THICKFRAME
                    | self.WS_SYSMENU
                    | self.WS_MAXIMIZEBOX
                    | self.WS_MINIMIZEBOX
                )
            ) | self.WS_CHILD | self.WS_VISIBLE

            user32.SetParent(hwnd, host_hwnd)
            _set_window_long(hwnd, self.GWL_STYLE, child_style)
            user32.ShowWindow(hwnd, self.SW_SHOW)
            self.hwnd = hwnd
            self.resize()
            self.host.bind("<Configure>", lambda _event: self.resize())
            return True
        except Exception as exc:
            self.log(f"Chrome dock attempt failed: {exc}\n")
            return False


class AzpHelperGui:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("Stake-GPT Helper")
        self.root.geometry("1320x820")
        self.root.minsize(1060, 680)
        self.root.configure(bg=HELPER_BG)

        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()
        self._closing = False
        self._hidden_to_tray = False
        self._active_section = "review"
        self._chrome_prepared = False
        self.nav_buttons: dict[str, Button] = {}
        self.status_dot: Canvas | None = None
        self.status_label: Label | None = None
        self.mode_label: Label | None = None
        self.detail_label: Label | None = None
        self.side_title: Label | None = None
        self.side_text: Text | None = None
        self.browser_placeholder: Frame | None = None
        self.browser_status: Label | None = None
        self.log: Text | None = None

        self.tray_icon = WindowsTrayIcon(
            "Stake-GPT Helper",
            on_restore=lambda: self.root.after(0, self.restore_from_tray),
            on_exit=lambda: self.root.after(0, self.close),
        )

        self._build_shell()
        self.chrome_dock = ChromeWindowDock(self.browser_host, log=self._write_log)
        self._set_active_section("review")
        self._write_intro()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Unmap>", self.on_unmap)
        self.root.after(100, self.drain_output)

    def run(self) -> None:
        self.root.mainloop()

    def start_helper(self, mode: str) -> None:
        if self.process and self.process.poll() is None:
            messagebox.showinfo("Stake-GPT Helper", "Helper is already running.")
            return

        python_exe = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
        setup_report = check_local_helper_setup(ROOT_DIR)
        if not setup_report["ok"]:
            report_text = format_setup_report(setup_report)
            self._write_log(report_text + "\n\n")
            messagebox.showerror("Stake-GPT Helper", report_text)
            self._show_panel_text("Setup", report_text)
            return

        self._set_active_section(mode)
        self._set_status("starting", f"starting {mode} mode...", WARNING)
        self._set_browser_status("Opening Stake debug session...")
        self._write_log(f"Starting helper in {mode} mode...\n")

        self._chrome_prepared = self.chrome_dock.start_debug_chrome()
        if self._chrome_prepared:
            self.chrome_dock.dock_when_ready(self.root)

        command = [str(python_exe), "-m", "app.local_stake_helper", "--mode", mode]
        if self._chrome_prepared:
            command.append("--no-autostart-chrome")

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            command,
            cwd=ROOT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=creationflags,
        )
        threading.Thread(target=self.capture_output, daemon=True).start()

    def run_setup_check(self) -> None:
        self._set_active_section("setup")
        report_text = format_setup_report(check_local_helper_setup(ROOT_DIR))
        self._show_panel_text("Setup Check", report_text)
        self._write_log(report_text + "\n\n")
        if "Ready." in report_text:
            self._set_status("ready", "setup ready", READY)
        else:
            self._set_status("attention", "setup needs attention", WARNING)

    def run_cache_cleanup(self) -> None:
        self._set_active_section("cache")
        python_exe = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
        if not python_exe.exists():
            messagebox.showerror(
                "Stake-GPT Helper",
                f"Could not find {python_exe}. Run the project setup first.",
            )
            return
        if not (ROOT_DIR / ".env").exists():
            messagebox.showerror(
                "Stake-GPT Helper",
                f"Could not find {ROOT_DIR / '.env'}. The cleanup needs Supabase settings.",
            )
            return

        self._set_status("cleaning", "cleaning Supabase cache...", WARNING)
        self._show_panel_text("Cache", "Supabase cache cleanup is running...\n\nOld local UI jobs will be expired and removed according to your current retention settings.")
        self._write_log("Running Supabase cache cleanup...\n")
        threading.Thread(target=self._run_cache_cleanup_thread, daemon=True).start()

    def show_logs(self) -> None:
        self._set_active_section("logs")
        self._show_panel_text(
            "Logs",
            "Live helper logs stay below. Use this tab when you want the raw process output and failure details.",
        )

    def show_settings(self) -> None:
        self._set_active_section("settings")
        self._show_panel_text(
            "Settings",
            (
                "Current setup\n"
                f"- Project: {ROOT_DIR}\n"
                "- Browser: debug Chrome profile under data/chrome-stake-ui\n"
                "- Safety: review-only. No stake amount or Place Bet action.\n"
                "- Minimize: sends helper to the Windows system tray."
            ),
        )

    def stop_helper(self) -> None:
        if not self.process or self.process.poll() is not None:
            self._set_status("idle", "idle", MUTED_TEXT)
            self._write_log("Helper is not running.\n")
            return

        self._write_log("Stopping helper...\n")
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
        self._set_status("stopped", "stopped", MUTED_TEXT)
        self._write_log("Helper stopped.\n")

    def close(self) -> None:
        self._closing = True
        self.tray_icon.close()
        self.stop_helper()
        self.chrome_dock.release()
        self.root.destroy()

    def on_unmap(self, _event=None) -> None:
        if self._closing or self._hidden_to_tray:
            return
        try:
            window_state = self.root.state()
        except Exception:
            return
        if should_minimize_to_tray(
            window_state,
            tray_supported=self.tray_icon.is_supported(),
        ):
            self.root.after(50, self.minimize_to_tray)

    def minimize_to_tray(self) -> None:
        if self._closing or self._hidden_to_tray:
            return
        if self.tray_icon.show():
            self._hidden_to_tray = True
            self.root.withdraw()
            self._write_log("Helper minimized to system tray. Double-click the tray icon to restore.\n")
        else:
            self._write_log("System tray unavailable; helper stayed minimized.\n")

    def restore_from_tray(self) -> None:
        self.tray_icon.hide()
        self._hidden_to_tray = False
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def capture_output(self) -> None:
        if not self.process or not self.process.stdout:
            return
        for line in self.process.stdout:
            self.output_queue.put(line)
        code = self.process.wait()
        self.output_queue.put(f"Helper exited with code {code}.\n")

    def drain_output(self) -> None:
        while True:
            try:
                line = self.output_queue.get_nowait()
            except queue.Empty:
                break
            self._write_log(line)
            lower = line.lower()
            if "waiting for stake ui jobs" in lower:
                self._set_status("ready", "waiting for GPT jobs", READY)
                self._set_browser_status("Stake helper is ready. Ask GPT for UI-backed SGM boards or build mode.")
            elif "completed job" in lower:
                self._set_status("ready", "completed job; waiting for next job", READY)
            elif "supabase cleanup" in lower and "exited with code 0" in lower:
                self._set_status("ready", "cache cleaned", READY)
            elif "supabase cleanup" in lower:
                self._set_status("cache", "cache cleanup updated", READY)
            elif "helper poll error" in lower:
                self._set_status("retrying", "connection issue; retrying", WARNING)
            elif "failed job" in lower:
                self._set_status("blocked", "job failed; waiting for next job", ERROR)
            elif "error" in lower:
                self._set_status("error", "helper error", ERROR)
            elif "exited with code" in lower:
                self._set_status("stopped", "stopped", MUTED_TEXT)
        self.root.after(100, self.drain_output)

    def _build_shell(self) -> None:
        shell = Frame(self.root, bg=HELPER_BG)
        shell.pack(fill=BOTH, expand=True, padx=14, pady=14)

        self.sidebar = Frame(shell, bg=SIDEBAR_BG, width=220, highlightthickness=1, highlightbackground=PANEL_BORDER)
        self.sidebar.pack(side=LEFT, fill="y")
        self.sidebar.pack_propagate(False)
        self._build_sidebar(self.sidebar)

        workspace = Frame(shell, bg=HELPER_BG)
        workspace.pack(side=LEFT, fill=BOTH, expand=True, padx=(12, 0))

        browser_panel = Frame(workspace, bg=PANEL_BG, highlightthickness=1, highlightbackground=PANEL_BORDER_ACTIVE)
        browser_panel.pack(side=LEFT, fill=BOTH, expand=True)
        self._build_browser_panel(browser_panel)

        right_panel = Frame(workspace, bg=PANEL_BG, width=340, highlightthickness=1, highlightbackground=PANEL_BORDER)
        right_panel.pack(side=RIGHT, fill="y", padx=(12, 0))
        right_panel.pack_propagate(False)
        self._build_right_panel(right_panel)

    def _build_sidebar(self, parent: Frame) -> None:
        header = Frame(parent, bg=SIDEBAR_BG)
        header.pack(fill="x", padx=18, pady=(18, 14))

        Canvas(header, width=28, height=28, bg=SIDEBAR_BG, bd=0, highlightthickness=0).pack(side=LEFT)
        title = Label(
            header,
            text="Stake-GPT\nHelper",
            justify="left",
            font=("Segoe UI", 12, "bold"),
            bg=SIDEBAR_BG,
            fg=HELPER_FG,
        )
        title.pack(side=LEFT, padx=(8, 0))

        nav = Frame(parent, bg=SIDEBAR_BG)
        nav.pack(fill="x", padx=14, pady=(4, 0))
        self._add_nav_button(nav, "review", "Review", lambda: self.start_helper("review"))
        self._add_nav_button(nav, "build", "Build", lambda: self.start_helper("build"))
        self._add_nav_button(nav, "setup", "Setup", self.run_setup_check)
        self._add_nav_button(nav, "cache", "Cache", self.run_cache_cleanup)
        self._add_nav_button(nav, "logs", "Logs", self.show_logs)
        self._add_nav_button(nav, "settings", "Settings", self.show_settings)

        spacer = Frame(parent, bg=SIDEBAR_BG)
        spacer.pack(fill=BOTH, expand=True)

        health = Frame(parent, bg=PANEL_BG, highlightthickness=1, highlightbackground=PANEL_BORDER)
        health.pack(fill="x", padx=14, pady=(0, 14))
        top = Frame(health, bg=PANEL_BG)
        top.pack(fill="x", padx=14, pady=(14, 4))
        self.status_dot = Canvas(top, width=12, height=12, bg=PANEL_BG, bd=0, highlightthickness=0)
        self.status_dot.pack(side=LEFT)
        self.status_label = Label(
            top,
            text="Helper ready",
            bg=PANEL_BG,
            fg=HELPER_FG,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self.status_label.pack(side=LEFT, padx=(8, 0))
        self.mode_label = Label(
            health,
            text="All systems operational",
            bg=PANEL_BG,
            fg=MUTED_TEXT,
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.mode_label.pack(fill="x", padx=14, pady=(0, 14))

        Button(parent, text="Stop", command=self.stop_helper, **_nav_button_style()).pack(
            fill="x", padx=14, pady=(0, 18), ipady=8
        )
        self._draw_status_dot(READY)

    def _build_browser_panel(self, parent: Frame) -> None:
        header = Frame(parent, bg=PANEL_BG)
        header.pack(fill="x", padx=16, pady=(14, 8))
        Label(
            header,
            text="Stake Session",
            bg=PANEL_BG,
            fg=HELPER_FG,
            font=("Segoe UI", 13, "bold"),
        ).pack(side=LEFT)
        self.browser_status = Label(
            header,
            text="Idle",
            bg=PANEL_BG,
            fg=MUTED_TEXT,
            font=("Segoe UI", 10),
        )
        self.browser_status.pack(side=RIGHT)

        self.browser_host = Frame(parent, bg="#050716", highlightthickness=1, highlightbackground=PANEL_BORDER)
        self.browser_host.pack(fill=BOTH, expand=True, padx=16, pady=(0, 16))
        self.browser_placeholder = Frame(self.browser_host, bg="#050716")
        self.browser_placeholder.place(relx=0, rely=0, relwidth=1, relheight=1)

        Label(
            self.browser_placeholder,
            text="Stake session idle",
            bg="#050716",
            fg=HELPER_FG,
            font=("Segoe UI", 22, "bold"),
        ).place(relx=0.5, rely=0.42, anchor="center")
        Label(
            self.browser_placeholder,
            text="Choose Review or Build. The debug Chrome window will open here when available.",
            bg="#050716",
            fg=MUTED_TEXT,
            font=("Segoe UI", 11),
        ).place(relx=0.5, rely=0.5, anchor="center")

    def _build_right_panel(self, parent: Frame) -> None:
        self.side_title = Label(
            parent,
            text="Activity",
            bg=PANEL_BG,
            fg=HELPER_FG,
            font=("Segoe UI", 13, "bold"),
            anchor="w",
        )
        self.side_title.pack(fill="x", padx=16, pady=(16, 8))

        self.detail_label = Label(
            parent,
            text="Review-only helper. It never enters a stake amount and never clicks Place Bet.",
            bg=PANEL_BG,
            fg=MUTED_TEXT,
            font=("Segoe UI", 10),
            wraplength=290,
            justify="left",
            anchor="w",
        )
        self.detail_label.pack(fill="x", padx=16, pady=(0, 12))

        self.side_text = Text(
            parent,
            height=8,
            wrap="word",
            font=("Segoe UI", 10),
            bg=PANEL_ALT_BG,
            fg=HELPER_FG,
            insertbackground=HELPER_FG,
            selectbackground=HELPER_BUTTON_ACTIVE_BG,
            selectforeground=HELPER_FG,
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=PANEL_BORDER,
            highlightcolor=PANEL_BORDER_ACTIVE,
        )
        self.side_text.pack(fill="x", padx=16, pady=(0, 12))

        Label(
            parent,
            text="Logs",
            bg=PANEL_BG,
            fg=HELPER_FG,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(6, 8))

        self.log = Text(
            parent,
            wrap="word",
            font=("Consolas", 9),
            bg="#050716",
            fg=HELPER_FG,
            insertbackground=HELPER_FG,
            selectbackground=HELPER_BUTTON_ACTIVE_BG,
            selectforeground=HELPER_FG,
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=PANEL_BORDER,
            highlightcolor=PANEL_BORDER_ACTIVE,
        )
        self.log.pack(fill=BOTH, expand=True, padx=16, pady=(0, 16))

    def _add_nav_button(self, parent: Frame, key: str, label: str, command: Callable[[], None]) -> None:
        button = Button(parent, text=label, command=command, anchor="w", **_nav_button_style())
        button.pack(fill="x", pady=5, ipady=9)
        self.nav_buttons[key] = button

    def _set_active_section(self, key: str) -> None:
        self._active_section = key
        for button_key, button in self.nav_buttons.items():
            if button_key == key:
                button.configure(bg=ACCENT_DARK, fg=HELPER_FG, activebackground=ACCENT_DARK)
            else:
                button.configure(bg=SIDEBAR_BG, fg=MUTED_TEXT, activebackground=HELPER_BUTTON_BG)
        if key in {"review", "build"}:
            self._show_panel_text(key.title(), mode_description(key))

    def _set_status(self, short: str, message: str, color: str) -> None:
        if self.status_label:
            self.status_label.configure(text=f"Helper {short}")
        if self.mode_label:
            self.mode_label.configure(text=message)
        self._draw_status_dot(color)

    def _draw_status_dot(self, color: str) -> None:
        if not self.status_dot:
            return
        self.status_dot.delete("all")
        self.status_dot.create_oval(2, 2, 10, 10, fill=color, outline=color)

    def _set_browser_status(self, text: str) -> None:
        if self.browser_status:
            self.browser_status.configure(text=text)

    def _show_panel_text(self, title: str, text: str) -> None:
        if self.side_title:
            self.side_title.configure(text=title)
        if not self.side_text:
            return
        self.side_text.configure(state="normal")
        self.side_text.delete("1.0", END)
        self.side_text.insert(END, text)
        self.side_text.configure(state="disabled")

    def _write_intro(self) -> None:
        self._write_log("Pick a mode. Close this window when you are done.\n")
        self._write_log("Build Mode never enters a stake amount and never clicks Place Bet.\n\n")
        self._write_log(format_setup_report(check_local_helper_setup(ROOT_DIR)) + "\n\n")

    def _write_log(self, text: str) -> None:
        if not self.log:
            return
        self.log.insert(END, text)
        self.log.see(END)

    def _run_cache_cleanup_thread(self) -> None:
        python_exe = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
        completed = subprocess.run(
            [str(python_exe), "-m", "app.supabase_cache"],
            cwd=ROOT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        output = completed.stdout or ""
        if output:
            self.output_queue.put(output)
        self.output_queue.put(f"Supabase cache cleanup exited with code {completed.returncode}.\n")


def _nav_button_style() -> dict[str, str | int]:
    return {
        "bg": SIDEBAR_BG,
        "fg": MUTED_TEXT,
        "activebackground": HELPER_BUTTON_BG,
        "activeforeground": HELPER_FG,
        "relief": "flat",
        "borderwidth": 0,
        "highlightthickness": 0,
        "font": ("Segoe UI", 10, "bold"),
        "padx": 16,
    }


def _wait_for_cdp(local_stake_helper, cdp_url: str, *, timeout_seconds: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if local_stake_helper._cdp_is_ready(cdp_url):
            return True
        time.sleep(0.25)
    return local_stake_helper._cdp_is_ready(cdp_url)


def create_stake_logo_header(parent) -> Canvas:
    canvas = Canvas(
        parent,
        height=92,
        bg=HELPER_BG,
        bd=0,
        highlightthickness=0,
        relief="flat",
    )

    def redraw(_event=None) -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        center_x = width // 2
        baseline_y = 45
        font = (LOGO_FONT_FAMILY, 50, "bold italic")

        canvas.create_text(
            center_x + 4,
            baseline_y + 6,
            text="Stake",
            font=font,
            fill="#01020D",
            anchor="center",
        )
        canvas.create_text(
            center_x + 2,
            baseline_y + 3,
            text="Stake",
            font=font,
            fill="#111324",
            anchor="center",
        )
        canvas.create_text(
            center_x,
            baseline_y,
            text="Stake",
            font=font,
            fill="#FFFFFF",
            anchor="center",
        )
        canvas.create_text(
            center_x - 1,
            baseline_y - 1,
            text="Stake",
            font=font,
            fill="#F8F6FF",
            anchor="center",
        )

    canvas.bind("<Configure>", redraw)
    canvas.after(1, redraw)
    return canvas


def _get_window_long(hwnd: int, index: int) -> int:
    user32 = ctypes.windll.user32
    if hasattr(user32, "GetWindowLongPtrW"):
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        return int(user32.GetWindowLongPtrW(hwnd, index))
    user32.GetWindowLongW.restype = ctypes.c_long
    return int(user32.GetWindowLongW(hwnd, index))


def _set_window_long(hwnd: int, index: int, value: int) -> int:
    user32 = ctypes.windll.user32
    if hasattr(user32, "SetWindowLongPtrW"):
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        return int(user32.SetWindowLongPtrW(hwnd, index, value))
    user32.SetWindowLongW.restype = ctypes.c_long
    return int(user32.SetWindowLongW(hwnd, index, value))


def _find_chrome_window(preferred_pid: int | None = None) -> int | None:
    if sys.platform != "win32":
        return None

    user32 = ctypes.windll.user32
    matches: list[tuple[int, int]] = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True

        class_name = _window_class(hwnd)
        if class_name != "Chrome_WidgetWin_1":
            return True

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        title = _window_title(hwnd).lower()

        score = 0
        if preferred_pid and pid.value == preferred_pid:
            score += 100
        if "stake" in title:
            score += 20
        if score:
            matches.append((score, hwnd))
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    if not matches:
        return None
    return max(matches, key=lambda item: item[0])[1]


def _window_title(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _window_class(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer.value


def main() -> int:
    app = AzpHelperGui()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
