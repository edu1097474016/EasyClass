# ==========================================================================
#  易课 EasyClass v1.0.0 | Silicon UI
#  utils.py  ——  自适应工具函数模块
#  -------------------------------------------------------------------------
#  职责：
#   · DPI / 分辨率缩放：scale() 将所有尺寸按 DPI(96 基准)动态缩放
#   · 配置读写：config.json / schedule.json / weather_cache.json
#   · 通用控件工厂：阴影效果、iOS 开关、全局热键
#   · Windows 毛玻璃（Acrylic）支持
#   · 跨平台开机自启动：Windows / Linux / macOS
# ==========================================================================

import os
import sys
import json
import re
import shutil
import ctypes
import logging
import platform

from PySide6.QtCore import (
    Qt, QRect, QPoint, QObject, QEvent, Signal, Property,
    QAbstractNativeEventFilter, QPropertyAnimation, QEasingCurve,
)
from PySide6.QtGui import QGuiApplication, QFont, QColor, QPainter
from PySide6.QtWidgets import (
    QApplication, QAbstractButton, QPushButton,
    QGraphicsDropShadowEffect, QGraphicsBlurEffect,
)

# ---------------- 应用元信息 ----------------
APP_NAME = "易课"
APP_ID = "com.easyclass.app"  # 用于 Linux .desktop 文件
APP_VERSION = "1.0.0"
APP_TAG = "易课 EasyClass v1.0.0 | Silicon UI"

# 检测运行平台
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"
IS_MAC = platform.system() == "Darwin"

# 项目根目录（与各 .py 模块同级）
IS_FROZEN = bool(getattr(sys, "frozen", False))
if IS_FROZEN:
    # PyInstaller 打包：资源（res/模板/图标）在 _MEIPASS，用户数据在 exe 同目录
    _MEIPASS = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    RES_ROOT = _MEIPASS
    APP_DIR = os.path.dirname(sys.executable)
else:
    RES_ROOT = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = RES_ROOT

BASE_DIR = APP_DIR                 # 应用运行目录（数据/迁移等）
RES_DIR = os.path.join(RES_ROOT, "res")   # 打包资源目录（QSS）
DATA_DIR = os.path.join(APP_DIR, "data")
LOG_DIR = os.path.join(DATA_DIR, "logs")
FONTS_DIR = os.path.join(DATA_DIR, "fonts")


def ensure_data_dir():
    """创建 data/ 目录（含 logs/、fonts/ 子目录）。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(FONTS_DIR, exist_ok=True)


def data_file(name):
    """返回 data/ 目录下的文件绝对路径。"""
    return os.path.join(DATA_DIR, name)


def migrate_old_files():
    """把旧版位于项目根目录的配置文件迁移到 data/ 目录。"""
    ensure_data_dir()
    for name in ("config.json", "schedule.json", "weather_cache.json"):
        old = os.path.join(BASE_DIR, name)
        new = os.path.join(DATA_DIR, name)
        if os.path.exists(old) and not os.path.exists(new):
            try:
                shutil.move(old, new)
            except Exception:
                try:
                    shutil.copyfile(old, new)
                except Exception:
                    pass

FONT_FAMILY = "Microsoft YaHei UI"

# 自定义字体（导入的字体文件 → 全局生效的字体系列名）
CUSTOM_FONT_FAMILY = None


def set_custom_font_family(family):
    """设置全局自定义字体系列名（None 时回退默认微软雅黑）。"""
    global CUSTOM_FONT_FAMILY
    CUSTOM_FONT_FAMILY = family or None


def custom_font_family():
    """返回当前生效的字体系列名。"""
    return CUSTOM_FONT_FAMILY or FONT_FAMILY


def load_custom_font_file(font_path):
    """
    导入自定义字体文件（.ttf/.otf/.ttc）：
    复制到 data/fonts/ 持久保存，注册到 Qt，并返回 (family, 持久化相对文件名)。
    失败返回 None。
    """
    try:
        from PySide6.QtGui import QFontDatabase
        ensure_data_dir()
        base = os.path.basename(font_path)
        dest = os.path.join(FONTS_DIR, base)
        if not os.path.exists(dest) or not os.path.samefile(font_path, dest):
            shutil.copyfile(font_path, dest)
        fid = QFontDatabase.addApplicationFont(dest)
        if fid < 0:
            return None
        families = QFontDatabase.applicationFontFamilies(fid)
        if not families:
            return None
        family = families[0]
        set_custom_font_family(family)
        return (family, base)
    except Exception:
        return None


def apply_saved_font(custom_font_file):
    """启动时根据 config 中保存的字体文件名应用自定义字体。"""
    if not custom_font_file:
        return False
    path = os.path.join(FONTS_DIR, os.path.basename(custom_font_file))
    if os.path.exists(path):
        result = load_custom_font_file(path)
        return result is not None
    return False

# ==========================================================================
#  DPI 与分辨率自适应
# ==========================================================================

def get_screen(screen_index=0):
    """返回指定索引的屏幕，索引越界时回退到主屏。"""
    screens = QGuiApplication.screens()
    if not screens:
        return None
    if 0 <= screen_index < len(screens):
        return screens[screen_index]
    return QGuiApplication.primaryScreen()


def get_scale_factor(screen=None):
    """DPI 缩放系数：以 96 DPI 为基准，例如 150% 缩放返回 1.5。"""
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    if screen is None:
        return 1.0
    dpi = screen.logicalDotsPerInch()
    return max(1.0, dpi / 96.0)


def s(value, screen=None):
    """按 DPI 缩放一个像素尺寸，返回整数。所有界面尺寸都应走该函数。"""
    return int(round(value * get_scale_factor(screen)))


def screen_available(screen=None):
    """返回指定屏幕的可视区域（排除任务栏等）。"""
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    if screen is None:
        return QRect(0, 0, 1024, 768)
    return screen.availableGeometry()


def make_font(size_pt, bold=False):
    """按磅值创建字体，Qt 自动根据 DPI 缩放磅值（字体自适应核心）。
    支持浮点磅值（如 10.5pt ≈ 14px）。
    优先使用用户导入的自定义字体（CUSTOM_FONT_FAMILY）。"""
    font = QFont(custom_font_family())
    font.setPointSizeF(float(size_pt))
    font.setBold(bold)
    return font


def is_os_dark():
    """探测系统当前是否为深色模式（用于首次启动默认主题）。"""
    if IS_WINDOWS:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 0
        except Exception:
            return True
    # Linux / macOS 暂不探测，默认深色
    return True


# ==========================================================================
#  配置文件读写
# ==========================================================================

def ensure_config_files():
    """config.json / schedule.json 不存在时从模板复制（写入 data/）。"""
    ensure_data_dir()
    for target, template in (
        ("config.json", "config.template.json"),
        ("schedule.json", "schedule.template.json"),
    ):
        target_path = os.path.join(DATA_DIR, target)
        if not os.path.exists(target_path):
            template_path = os.path.join(RES_ROOT, template)
            if os.path.exists(template_path):
                shutil.copyfile(template_path, target_path)


def load_json(path, default=None):
    """读取 JSON 文件，失败时返回 default。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def save_json(path, data):
    """保存 JSON 文件（UTF-8，保留中文）。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_config():
    """加载主配置 data/config.json，缺省字段自动补齐。"""
    ensure_data_dir()
    migrate_old_files()
    ensure_config_files()
    default = {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "weather_city": "北京",
        "auto_locate": True,
        "weather_refresh_minutes": 30,
        "opacity": 0.65,
        "password": "admin123",
        "api_provider": "uapi",
        "island_width_ratio": 1.0,
        "island_glass_style": "auto",
        "island_glass_custom": "#1E202D",
        "island_material": "frosted",
        "island_fullscreen": False,
        "island_passthrough": False,
        "island_screen": 0,
        "hover_hide": True,
        "hover_hide_margin": 60,
        "hover_hide_interval": 100,
        "autostart": False,
        "custom_font_file": "",
        "course_progress_height": 3,
        "hitokoto_category": "",
        "hitokoto_refresh_minutes": 15,
        "text_mode": "scroll",
        "theme": "dark",
        "theme_color": "#40916C",
    }
    cfg = load_json(data_file("config.json"), {})
    for key, value in default.items():
        cfg.setdefault(key, value)
    return cfg


def save_config(cfg):
    """保存主配置 data/config.json。"""
    save_json(data_file("config.json"), cfg)


# ==========================================================================
#  视觉效果工具
# ==========================================================================

def make_shadow(widget, color=QColor(0, 0, 0, 90), blur_radius=20, offset=0):
    """为控件添加柔光阴影（QGraphicsDropShadowEffect）。"""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur_radius)
    effect.setOffset(offset, offset)
    effect.setColor(color)
    widget.setGraphicsEffect(effect)
    return effect


def make_blur(widget, radius=5):
    """为控件添加毛玻璃模糊效果（QGraphicsBlurEffect）。"""
    effect = QGraphicsBlurEffect(widget)
    effect.setBlurRadius(radius)
    widget.setGraphicsEffect(effect)
    return effect


def _set_accent_state(hwnd, state, flags=2, gradient=0):
    """设置 Windows DWM 毛玻璃状态（4=亚克力模糊，0=关闭）。"""
    try:
        class AccentPolicy(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_uint),
                ("AccentFlags", ctypes.c_uint),
                ("GradientColor", ctypes.c_uint),
                ("AnimationId", ctypes.c_uint),
            ]

        class WinCompatAttrData(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_int),
                ("Data", ctypes.POINTER(AccentPolicy)),
                ("SizeOfData", ctypes.c_size_t),
            ]

        accent = AccentPolicy(state, flags, gradient, 0)
        data = WinCompatAttrData(19, ctypes.pointer(accent), ctypes.sizeof(accent))
        ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
    except Exception:
        pass


def enable_acrylic(window, abgr=0xD82D201E):
    """
    Windows 10/11 亚克力（Acrylic）材质。
    通过 DWM SetWindowCompositionAttribute 开启背景模糊，
    失败时静默忽略（仍保留 rgba 半透明玻璃质感）。
    abgr 参数格式为 0xAABBGGRR。
    """
    if not IS_WINDOWS:
        return
    try:
        hwnd = int(window.winId())
        _set_accent_state(hwnd, 4, 2, abgr)   # 4 = ACCENT_ENABLE_ACRYLICBLURBEHIND
    except Exception:
        pass


def disable_acrylic(window):
    """关闭 DWM 亚克力模糊（AccentState=0），用于切回毛玻璃材质。"""
    if not IS_WINDOWS:
        return
    try:
        hwnd = int(window.winId())
        _set_accent_state(hwnd, 0, 0, 0)
    except Exception:
        pass


# ==========================================================================
#  开机自启动（跨平台）
# ==========================================================================

def _get_autostart_command():
    """获取当前程序的自启动命令（跨平台）。"""
    if IS_FROZEN:
        # 打包后的 exe / 可执行文件
        return f'"{sys.executable}"'
    else:
        # 源码运行
        if IS_WINDOWS:
            exe = sys.executable
            if exe.lower().endswith("python.exe"):
                pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
                if os.path.exists(pythonw):
                    exe = pythonw
            main_py = os.path.join(BASE_DIR, "main.py")
            return f'"{exe}" "{main_py}"'
        elif IS_LINUX or IS_MAC:
            return f'"{sys.executable}" "{os.path.join(BASE_DIR, "main.py")}"'
        else:
            return f'"{sys.executable}" "{os.path.join(BASE_DIR, "main.py")}"'


def autostart_enabled():
    """
    查询开机自启动是否已启用（跨平台）。
    - Windows: 读取注册表 Run 项
    - Linux: 检查 ~/.config/autostart/ 下是否存在 .desktop 文件
    - macOS: 检查 ~/Library/LaunchAgents/ 下是否存在 .plist 文件
    """
    if IS_WINDOWS:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_READ)
            try:
                value, _ = winreg.QueryValueEx(key, APP_NAME)
                return bool(value and value.strip())
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False

    elif IS_LINUX:
        autostart_dir = os.path.expanduser("~/.config/autostart")
        desktop_path = os.path.join(autostart_dir, f"{APP_ID}.desktop")
        if os.path.exists(desktop_path):
            try:
                with open(desktop_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    return "Exec=" in content and APP_NAME in content
            except Exception:
                pass
        return False

    elif IS_MAC:
        launch_dir = os.path.expanduser("~/Library/LaunchAgents")
        plist_path = os.path.join(launch_dir, f"{APP_ID}.plist")
        if os.path.exists(plist_path):
            try:
                import plistlib
                with open(plist_path, "rb") as f:
                    data = plistlib.load(f)
                    return data.get("Label") == APP_ID
            except Exception:
                pass
        return False

    return False


def set_autostart(enabled):
    """
    启用/禁用开机自启动（跨平台）。
    - Windows: 写入/删除 HKCU Run 注册表项
    - Linux: 创建/删除 ~/.config/autostart/*.desktop 文件
    - macOS: 创建/删除 ~/Library/LaunchAgents/*.plist 文件
    """
    if IS_WINDOWS:
        _set_autostart_windows(enabled)
    elif IS_LINUX:
        _set_autostart_linux(enabled)
    elif IS_MAC:
        _set_autostart_macos(enabled)


def _set_autostart_windows(enabled):
    """Windows 注册表自启动。"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE)
        try:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _get_autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
        logging.getLogger(__name__).info(f"Windows 自启动 {'启用' if enabled else '禁用'}: {APP_NAME}")
    except Exception as exc:
        logging.getLogger(__name__).warning(f"Windows 自启动设置失败: {exc}")


def _set_autostart_linux(enabled):
    """Linux XDG Autostart (.desktop 文件)。"""
    autostart_dir = os.path.expanduser("~/.config/autostart")
    os.makedirs(autostart_dir, exist_ok=True)
    desktop_path = os.path.join(autostart_dir, f"{APP_ID}.desktop")

    if enabled:
        # 查找图标文件
        icon_path = os.path.join(RES_ROOT, "favicon.ico")
        if not os.path.exists(icon_path):
            icon_path = ""

        content = f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
Comment={APP_NAME} - 教室信息看板
Exec={_get_autostart_command()}
Icon={icon_path}
Terminal=false
StartupNotify=false
X-GNOME-Autostart-enabled=true
Categories=Utility;
"""
        try:
            with open(desktop_path, "w", encoding="utf-8") as f:
                f.write(content)
            # 设置可执行权限
            os.chmod(desktop_path, 0o755)
            logging.getLogger(__name__).info(f"Linux 自启动已启用: {desktop_path}")
        except Exception as exc:
            logging.getLogger(__name__).warning(f"Linux 自启动创建失败: {exc}")
    else:
        try:
            if os.path.exists(desktop_path):
                os.remove(desktop_path)
                logging.getLogger(__name__).info(f"Linux 自启动已禁用: {desktop_path}")
        except Exception as exc:
            logging.getLogger(__name__).warning(f"Linux 自启动删除失败: {exc}")


def _set_autostart_macos(enabled):
    """macOS LaunchAgents (.plist 文件)。"""
    launch_dir = os.path.expanduser("~/Library/LaunchAgents")
    os.makedirs(launch_dir, exist_ok=True)
    plist_path = os.path.join(launch_dir, f"{APP_ID}.plist")

    if enabled:
        try:
            import plistlib
            # 确保日志目录存在
            os.makedirs(LOG_DIR, exist_ok=True)

            plist_data = {
                "Label": APP_ID,
                "ProgramArguments": _get_autostart_command().split(),
                "RunAtLoad": True,
                "KeepAlive": False,
                "ProcessType": "Background",
                "StandardOutPath": os.path.join(LOG_DIR, "autostart.log"),
                "StandardErrorPath": os.path.join(LOG_DIR, "autostart_error.log"),
            }
            with open(plist_path, "wb") as f:
                plistlib.dump(plist_data, f)

            # 加载 LaunchAgent
            try:
                import subprocess
                subprocess.run(["launchctl", "load", plist_path], check=False)
            except Exception:
                pass

            logging.getLogger(__name__).info(f"macOS 自启动已启用: {plist_path}")
        except Exception as exc:
            logging.getLogger(__name__).warning(f"macOS 自启动创建失败: {exc}")
    else:
        try:
            if os.path.exists(plist_path):
                # 先卸载
                try:
                    import subprocess
                    subprocess.run(["launchctl", "unload", plist_path], check=False)
                except Exception:
                    pass
                os.remove(plist_path)
                logging.getLogger(__name__).info(f"macOS 自启动已禁用: {plist_path}")
        except Exception as exc:
            logging.getLogger(__name__).warning(f"macOS 自启动删除失败: {exc}")


def paint_round_rect(painter, rect, radius, color, width=1):
    """绘制圆角矩形边框（用于自绘呼吸/发光效果）。"""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor(color))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(
        rect.adjusted(width // 2, width // 2, -width // 2, -width // 2),
        radius, radius,
    )
    painter.restore()


_RGBA_RE = re.compile(
    r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+)\s*)?\)",
    re.IGNORECASE,
)


def parse_color(css_color, fallback=QColor(0, 0, 0, 90)):
    """
    把 CSS 颜色字符串（#RRGGBB / rgb() / rgba()）解析为 QColor。
    Qt 原生不支持解析 rgba() 字符串，因此单独处理。
    """
    if css_color is None:
        return fallback
    text = str(css_color).strip()
    match = _RGBA_RE.match(text)
    if match:
        r, g, b = int(match.group(1)), int(match.group(2)), int(match.group(3))
        alpha = float(match.group(4)) if match.group(4) is not None else 1.0
        return QColor(r, g, b, max(0, min(255, int(round(alpha * 255)))))
    color = QColor(text)
    return color if color.isValid() else fallback


# ==========================================================================
#  属性动画辅助
# ==========================================================================

def create_loop_animation(obj, prop_name, key_values, duration=2000, easing=QEasingCurve.Type.InOutSine):
    """
    创建无限循环动画，key_values 形如 [(0.0, v0), (0.5, v1), (1.0, v0)]。
    返回动画对象，调用 start() 生效。
    """
    anim = QPropertyAnimation(obj, prop_name, obj)
    anim.setDuration(duration)
    anim.setLoopCount(-1)
    anim.setEasingCurve(easing)
    for pos, value in key_values:
        anim.setKeyValueAt(pos, value)
    return anim


def animate_property(obj, prop_name, end_value, duration=300, easing=QEasingCurve.Type.OutCubic):
    """一次性属性动画，返回动画对象（已 start）。"""
    anim = QPropertyAnimation(obj, prop_name, obj)
    anim.setDuration(duration)
    anim.setEndValue(end_value)
    anim.setEasingCurve(easing)
    anim.start()
    return anim


# ==========================================================================
#  全局热键（Windows）
# ==========================================================================

class _HotkeyFilter(QAbstractNativeEventFilter):
    """原生消息过滤器，拦截 WM_HOTKEY。"""

    WM_HOTKEY = 0x0312

    def __init__(self, callback, hotkey_id):
        super().__init__()
        self._callback = callback
        self._hotkey_id = hotkey_id

    def nativeEventFilter(self, event_type, message):
        if not IS_WINDOWS:
            return False, 0
        try:
            types = (b"windows_generic_MSG", "windows_generic_MSG")
            if event_type not in types:
                return False, 0
            msg = message[0]
            if int(msg.message) == self.WM_HOTKEY and int(msg.wParam) == self._hotkey_id:
                self._callback()
                return True, 0
        except Exception:
            pass
        return False, 0


class GlobalHotkey(QObject):
    """注册系统级快捷键（例如 Ctrl+E），注册失败时静默降级。"""

    triggered = Signal()

    def __init__(self, modifier, vkey, hotkey_id=0x3000, parent=None):
        super().__init__(parent)
        self._filter = None
        self._ok = False
        if not IS_WINDOWS:
            return
        try:
            # hWnd 传 None：WM_HOTKEY 直接投递到本线程消息队列
            self._ok = bool(
                ctypes.windll.user32.RegisterHotKey(None, hotkey_id, modifier, vkey)
            )
            if self._ok:
                self._filter = _HotkeyFilter(lambda: self.triggered.emit(), hotkey_id)
                QApplication.instance().installNativeEventFilter(self._filter)
        except Exception:
            self._ok = False

    def is_registered(self):
        return self._ok


# ==========================================================================
#  iOS 风格滑动开关
# ==========================================================================

class ToggleSwitch(QAbstractButton):
    """iOS 风格滑动开关，带滑钮动画。纯 QPainter 自绘，无外部图片。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim_value = 0.0
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(s(44), s(26))
        self.toggled.connect(self._animate_toggle)

    # 用 Property 支持平滑滑钮动画（0=关，1=开）
    _p = Property(float, lambda self: self._anim_value, lambda self, v: self._set_anim(v))

    def _set_anim(self, value):
        self._anim_value = value
        self.update()

    def _animate_toggle(self, checked):
        anim = QPropertyAnimation(self, b"_p", self)
        anim.setDuration(180)
        anim.setEndValue(1.0 if checked else 0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._knob_anim = anim   # 持有引用，防止动画对象被垃圾回收导致滑块不动
        anim.start()

    def set_checked_animated(self, checked):
        """无动画地设置初始状态。"""
        self.blockSignals(True)
        self.setChecked(checked)
        self.blockSignals(False)
        self._anim_value = 1.0 if checked else 0.0
        self.update()

    @staticmethod
    def _theme_primary():
        """读取当前生效的主题色（支持自定义主题色）。"""
        try:
            from theme_manager import ThemeManager
            theme = QApplication.instance().property("__theme") or "dark"
            return ThemeManager.COLORS.get(theme, ThemeManager.COLORS["dark"])["primary"]
        except Exception:
            theme = QApplication.instance().property("__theme") or "dark"
            return "#8B5CF6" if theme == "dark" else "#7C3AED"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        value = max(0.0, min(1.0, self._anim_value))

        # 轨道颜色：开=主题色，关=灰色
        theme = QApplication.instance().property("__theme") or "dark"
        if value > 0.5 or self.isChecked():
            color = QColor(self._theme_primary())
        else:
            color = QColor("#333344" if theme == "dark" else "#D1D5DB")
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, w, h, h // 2, h // 2)

        # 白色滑钮
        knob_d = int(h - s(4))
        x = int(s(2) + (w - knob_d - s(4)) * value)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(x, int(s(2)), knob_d, knob_d)
        painter.end()


# ==========================================================================
#  按钮按下滑动动画（全局）
# ==========================================================================

class _ButtonPressFilter(QObject):
    """全局事件过滤器：为所有 QPushButton 添加按下/松开滑动动画。"""

    def __init__(self, offset=2, duration=90, parent=None):
        super().__init__(parent)
        self._offset = offset
        self._duration = duration
        self._press = {}   # id(button) -> 按下前基准位置

    def _animate(self, btn, base_pos, dy):
        anim = QPropertyAnimation(btn, b"pos", btn)
        anim.setDuration(self._duration)
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        anim.setStartValue(btn.pos())
        anim.setEndValue(base_pos + QPoint(0, dy))
        anim.start()
        btn._press_anim = anim   # 持有引用防止被回收

    def eventFilter(self, obj, event):
        if isinstance(obj, QPushButton):
            etype = event.type()
            if etype == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._press[id(obj)] = obj.pos()
                self._animate(obj, obj.pos(), self._offset)
            elif etype == QEvent.MouseButtonRelease and id(obj) in self._press:
                base = self._press.pop(id(obj))
                self._animate(obj, base, 0)
            elif etype == QEvent.MouseButtonDblClick and id(obj) not in self._press:
                self._press[id(obj)] = obj.pos()
                self._animate(obj, obj.pos(), self._offset)
        return False


def install_button_press_animation(app, offset=2, duration=90):
    """为应用内所有 QPushButton 安装按下滑动动画。

    按下时按钮内容下沉 offset 像素，松开/移出时弹回（OutQuad 非线性）。
    """
    filt = _ButtonPressFilter(offset=offset, duration=duration)
    app.installEventFilter(filt)
    # 挂在 app 上持有引用，防止事件过滤器被垃圾回收
    if not hasattr(app, "_button_press_filters"):
        app._button_press_filters = []
    app._button_press_filters.append(filt)
    return filt