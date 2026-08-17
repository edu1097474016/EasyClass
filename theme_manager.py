# ==========================================================================
#  易课 EasyClass v1.0.0 | Silicon UI
#  theme_manager.py  ——  主题管理模块
#  -------------------------------------------------------------------------
#  职责：
#   · 深色/浅色主题动态加载（两套 QSS 文件，无需重启程序）
#   · Qt 样式表不支持 CSS 变量：将 res/style_*.qss 中的 "--xxx: value;"
#     变量行解析出来，并把 var(--xxx) 替换为真实颜色值后应用
#   · 主题状态持久化到 config.json
#   · 主题切换淡入淡出动画 + 通知各窗口刷新自绘颜色
# ==========================================================================

import os

from PySide6.QtCore import QObject, Signal, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor

from utils import RES_DIR, load_config, save_config, make_font, font_family_css


class ThemeManager(QObject):
    """全局主题管理器。"""

    DARK = "dark"
    LIGHT = "light"

    # 主题切换完成信号：参数为新主题名
    theme_changed = Signal(str)

    # 动态颜色表（供自绘组件读取，与 QSS 颜色变量一一对应）
    COLORS = {
        DARK: {
            "bg_main": "#121218",
            "bg_card": "#1E202D",
            "text_main": "#F0F0F5",
            "text_secondary": "#A0A0B8",
            "border": "rgba(255,255,255,0.08)",
            "primary": "#8B5CF6",
            "danger": "#F43F5E",
            "success": "#22C55E",
            "separator": "rgba(255,255,255,0.12)",
            "warning_bg": "rgba(244,63,94,0.20)",
            "icon_fg": "#D8D8E8",
            "acrylic_abgr": 0xD82D201E,
            "shadow": "rgba(0,0,0,0.3)",
        },
        LIGHT: {
            "bg_main": "#F8F9FA",
            "bg_card": "#FFFFFF",
            "text_main": "#1F2937",
            "text_secondary": "#6B7280",
            "border": "rgba(0,0,0,0.08)",
            "primary": "#7C3AED",
            "danger": "#E11D48",
            "success": "#16A34A",
            "separator": "rgba(0,0,0,0.12)",
            "warning_bg": "rgba(225,29,72,0.10)",
            "icon_fg": "#374151",
            "acrylic_abgr": 0xD8FFFFFF,
            "shadow": "rgba(0,0,0,0.08)",
        },
    }

    def __init__(self, app, config=None):
        super().__init__()
        self.app = app
        self.config = config if config is not None else load_config()
        self.current_theme = self.DARK
        self._fade_widgets = []
        # 自定义主题色（默认取当前主题内置 primary）
        custom = self.config.get("theme_color", "")
        self.primary_color = custom if QColor(custom).isValid() else None

        # 从 config.json 读取主题
        saved = self.config.get("theme", self.DARK)
        if saved in (self.DARK, self.LIGHT):
            self.current_theme = saved
        else:
            self.current_theme = self.DARK

        self.apply_theme(animate=False)

    # ------------------------------------------------------------------
    #  主题切换
    # ------------------------------------------------------------------
    def toggle_theme(self):
        """一键切换深色/浅色。"""
        if self.current_theme == self.DARK:
            self.set_light_theme()
        else:
            self.set_dark_theme()

    def set_dark_theme(self):
        if self.current_theme == self.DARK:
            return
        self.current_theme = self.DARK
        self.apply_theme(animate=True)
        self.save_theme_to_config()

    def set_light_theme(self):
        if self.current_theme == self.LIGHT:
            return
        self.current_theme = self.LIGHT
        self.apply_theme(animate=True)
        self.save_theme_to_config()

    # ------------------------------------------------------------------
    #  主题色
    # ------------------------------------------------------------------
    def current_primary(self):
        """返回当前生效的主题色（自定义优先，否则用主题内置值）。"""
        if self.primary_color:
            return self.primary_color
        return self.COLORS[self.current_theme]["primary"]

    def set_primary_color(self, color_hex):
        """设置全局主题色（QSS + 自绘组件），并持久化到 config.json。"""
        if not color_hex or not QColor(color_hex).isValid():
            return
        if color_hex.upper() != self.current_primary().upper():
            self.primary_color = color_hex
            self.apply_theme(animate=False)
        self.config["theme_color"] = color_hex
        save_config(self.config)

    def _primary_overrides(self):
        """把自定义主题色注入 QSS 变量替换表。"""
        primary = self.current_primary()
        base = QColor(primary)
        if not base.isValid():
            return {}
        hover = QColor(base.red(), base.green(), base.blue(), 217)     # 0.85
        pressed = QColor(base.red(), base.green(), base.blue(), 178)   # 0.70
        return {
            "--primary-color": primary,
            "--toggle-on": primary,
            "--primary-hover": "rgba(%d, %d, %d, 0.85)" % (
                hover.red(), hover.green(), hover.blue()),
            "--primary-pressed": "rgba(%d, %d, %d, 0.70)" % (
                pressed.red(), pressed.green(), pressed.blue()),
            "--font-family": font_family_css(),
        }

    def _sync_colors(self):
        """把生效主题色同步进自绘组件读取的 COLORS 表。"""
        self.COLORS[self.current_theme]["primary"] = self.current_primary()

    # ------------------------------------------------------------------
    #  应用主题
    # ------------------------------------------------------------------
    def apply_theme(self, animate=True):
        """读取对应 QSS 文件并应用到全局，同时触发主题切换动画。"""
        qss_path = os.path.join(RES_DIR, "style_dark.qss" if self.current_theme == self.DARK else "style_light.qss")
        qss = self._read_and_substitute(qss_path, overrides=self._primary_overrides())
        self._sync_colors()
        self.app.setStyleSheet(qss)

        # 通知自绘组件刷新颜色
        self.app.setProperty("__theme", self.current_theme)
        self.theme_changed.emit(self.current_theme)

        # 切换动画：所有顶层窗口淡入淡出
        if animate:
            self._play_fade_animation()

    def _play_fade_animation(self):
        """主题切换时对顶层窗口做淡入淡出（opacity 0.85→1.0，0.15秒）。"""
        fade_targets = [w for w in self.app.topLevelWidgets() if w.isVisible() and w.windowOpacity() > 0]
        for widget in fade_targets:
            anim = QPropertyAnimation(widget, b"windowOpacity", widget)
            anim.setDuration(150)
            anim.setStartValue(0.85)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start()

    def save_theme_to_config(self):
        """把当前主题写入 config.json。"""
        self.config["theme"] = self.current_theme
        save_config(self.config)

    # ------------------------------------------------------------------
    #  QSS 变量替换
    # ------------------------------------------------------------------
    def _read_and_substitute(self, qss_path, overrides=None):
        """读取 QSS，解析顶部变量行并替换 var(--xxx)。overrides 可覆盖变量值。"""
        with open(qss_path, "r", encoding="utf-8") as f:
            raw = f.read()

        variables = {}
        kept_lines = []
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("--") and ":" in stripped:
                key, value = stripped.split(":", 1)
                variables[key.strip()] = value.strip().rstrip(";")
            else:
                kept_lines.append(line)

        if overrides:
            variables.update(overrides)

        css = "\n".join(kept_lines)
        for key, value in variables.items():
            css = css.replace("var(%s)" % key, value)
        return css

    # ------------------------------------------------------------------
    #  颜色查询
    # ------------------------------------------------------------------
    def color(self, key):
        """返回当前主题下的动态颜色值。"""
        return self.COLORS[self.current_theme].get(key)

    def is_dark(self):
        return self.current_theme == self.DARK
