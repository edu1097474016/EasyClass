# ==========================================================================
#  易课 EasyClass v1.0.0 | Silicon UI
#  island_window.py  ——  顶部导航栏（Top Navigation Bar）
#  -------------------------------------------------------------------------
#  职责：
#   · 固定顶部、全屏宽的窄条信息栏：height 40px（× DPI 缩放）
#   · Flexbox 三段式：左(课程) 中(时钟+日期) 右(温度)，space-between 居中
#   · 毛玻璃：rgba(30,30,40,0.7) + QGraphicsBlurEffect(8px) + DWM Acrylic
#   · 统一 14px 字号；时钟 HH:MM（去秒）、日期 MM-DD 周X
#   · 防重叠：时钟+日期永不压缩；宽度不足时优先隐藏"天气"，再隐藏"课程"
#   · 屏幕热插拔 / 分辨率 / DPI 变更自动重新适配（多显示器独立适配）
# ==========================================================================

import math
from datetime import datetime, date

from PySide6.QtCore import (
    Qt, QRect, QPoint, QRectF,
    Property, QTimer, QPropertyAnimation, QEasingCurve, QAbstractAnimation,
    QSize, QSizeF,
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QFontMetricsF, QGuiApplication, QPixmap, QCursor,
)
from PySide6.QtWidgets import (
    QWidget, QLabel, QFrame, QHBoxLayout, QVBoxLayout, QGridLayout,
    QGraphicsOpacityEffect, QSizePolicy, QApplication, QStackedWidget,
)

import utils
from utils import s, make_font, make_shadow, make_blur, enable_acrylic
from icon_drawer import IconDrawer
from weather_manager import aqi_color, warning_color_hex

WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
WEEKDAY_CN2 = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"]

# 统一字号：14px ≈ 10.5pt（Qt 磅值自动按 DPI 缩放）
FONT_MAIN = 10.5


def theme_colors():
    theme = QApplication.instance().property("__theme") or "dark"
    from theme_manager import ThemeManager
    return ThemeManager.COLORS.get(theme, ThemeManager.COLORS["dark"])


def nav_bar_color(theme=None):
    """顶部导航栏底色：深色 rgba(30,30,40,0.7) / 浅色 rgba(255,255,255,0.72)。"""
    if theme is None:
        theme = QApplication.instance().property("__theme") or "dark"
    if theme == "light":
        return "rgba(255, 255, 255, 0.72)"
    return "rgba(30, 30, 40, 0.7)"


# ==========================================================================
#  自绘子组件
# ==========================================================================

class DigitalTimeLabel(QWidget):
    """数字时钟：HH:MM（去秒），内容变化时触发 OutElastic 弹性缩放动画。"""

    def __init__(self, size_pt=11, parent=None):
        super().__init__(parent)
        self._pulse = 0.0
        self._scale = 1.0
        self._text = "--:--"
        self._size_pt = size_pt
        self._anim = QPropertyAnimation(self, b"pulse")
        self._anim.setDuration(300)
        self._anim.setEasingCurve(QEasingCurve.Type.OutElastic)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._min_w = s(96)   # HH:MM:SS 秒级宽度

    _p = Property(float, lambda self: self._pulse,
                  lambda self, v: self._set_pulse(v))

    def _set_pulse(self, value):
        self._pulse = value
        self._scale = 1.0 + 0.04 * value
        self.update()

    def set_text(self, text):
        if text != self._text:
            self._text = text
            self._anim.start()
        self.update()

    def minimumSizeHint(self):
        return QSize(self._min_w, s(26))

    def sizeHint(self):
        return QSize(self._min_w, s(26))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        colors = theme_colors()
        font = make_font(self._size_pt, bold=True)
        painter.setFont(font)
        fm = QFontMetricsF(font)
        text_w = fm.horizontalAdvance(self._text)
        text_h = fm.height()
        rect = QRectF(-text_w / 2, -text_h / 2, text_w, text_h)

        painter.save()
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(self._scale, self._scale)
        painter.setPen(QColor(colors["text_main"]))
        painter.drawText(rect, Qt.AlignCenter, self._text)
        painter.restore()
        painter.end()


class CoursePanel(QFrame):
    """左侧课程信息面板：上课/预告时呼吸灯发光边框（InOutSine 2s 循环）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._glow = 0.0
        self._breathing = False
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

    _g = Property(float, lambda self: self._glow,
                  lambda self, v: self._set_glow(v))

    def _set_glow(self, value):
        self._glow = value
        self.update()

    def set_breathing(self, active):
        self._breathing = active
        if not active:
            self._glow = 0.0
        self.update()

    def paintEvent(self, event):
        if not self._breathing:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        primary = QColor(theme_colors()["primary"])
        color = QColor(primary)
        color.setAlpha(int(40 + 160 * self._glow))
        utils.paint_round_rect(painter, self.rect(), s(8), color, width=2)
        painter.end()


class FlipCard(QWidget):
    """翻牌器：前后两张牌面，绕竖直中轴翻转（宽向缩放 + 牌面切换）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._front = QPixmap()
        self._back = QPixmap()
        self._flip = 0.0
        self._on_done = None
        self._anim = QPropertyAnimation(self, b"flip", self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)   # 非线性缓动
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.finished.connect(self._finish)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()

    _f = Property(float, lambda self: self._flip,
                  lambda self, v: self._set_flip(v))

    def _set_flip(self, value):
        self._flip = value
        self.update()

    def set_pages(self, front, back):
        """设置正面/背面牌面。"""
        self._front = front
        self._back = back
        self._flip = 0.0
        self.update()

    def flip(self, on_done=None):
        """开始翻转，结束后回调。"""
        self._on_done = on_done
        self._flip = 0.0
        self._anim.start()

    def _finish(self):
        done = self._on_done
        self._on_done = None
        if done:
            done()

    def paintEvent(self, event):
        if self._front.isNull() and self._back.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        scale = abs(math.cos(math.pi * self._flip))   # 0.5 时收缩为一条线，此时换牌面
        pix = self._front if self._flip < 0.5 else self._back
        if pix.isNull():
            painter.end()
            return
        w = max(1, int(self.width() * scale))
        x = (self.width() - w) // 2
        painter.drawPixmap(x, 0, w, self.height(), pix)
        painter.end()


class WeatherDisplay(QWidget):
    """右侧温度显示：矢量图标 + 温度（单行）；网络异常时摇摆动画（±3°）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0.0
        self._icon = QPixmap()
        self._temp = "--°C"
        self._error = False
        self._cached = False
        self._air = None
        self._compact = False
        self._err_text = "网络异常"
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setMinimumWidth(s(70))

    _a = Property(float, lambda self: self._angle,
                  lambda self, v: self._set_angle(v))

    def _set_angle(self, value):
        self._angle = value
        self.update()

    def _aqi_text(self):
        if not self._air:
            return ""
        aqi = self._air.get("aqi")
        try:
            return "AQI %d" % int(aqi)
        except (TypeError, ValueError):
            return ""

    def _measure(self, with_aqi):
        fm = QFontMetricsF(make_font(FONT_MAIN))
        w = s(2) + s(18) + s(6) + fm.horizontalAdvance(self._temp)
        if with_aqi:
            aqi = self._aqi_text()
            if aqi:
                w += s(10) + fm.horizontalAdvance(aqi)
        return int(w) + s(2)

    def full_width(self):
        """带 AQI 的完整宽度。"""
        return self._measure(True)

    def compact_width(self):
        """去掉 AQI 后的紧凑宽度。"""
        return self._measure(False)

    def set_compact(self, compact):
        """压缩模式：空间不足时隐藏 AQI 徽标。"""
        compact = bool(compact)
        if compact != self._compact:
            self._compact = compact
            self.updateGeometry()
            self.update()

    def sizeHint(self):
        return QSize(self.compact_width() if self._compact else self.full_width(), s(26))

    def minimumSizeHint(self):
        return self.sizeHint()

    def set_weather(self, data):
        colors = theme_colors()
        self._error = False
        self._cached = bool(data.get("cached"))
        self._temp = "%s°C" % data.get("temp", "--")
        self._air = data.get("air") or None
        self._icon = IconDrawer.weather_icon(
            data.get("code", 999), s(18), fg=colors["icon_fg"])
        self.updateGeometry()
        self.update()

    def set_error(self, cached, message):
        colors = theme_colors()
        self._error = True
        self._cached = cached is not None
        self._air = (cached or {}).get("air") or None
        if cached:
            self._temp = "%s°C" % cached.get("temp", "--")
            self._icon = IconDrawer.weather_icon(
                cached.get("code", 999), s(18), fg=colors["icon_fg"])
        else:
            self._temp = "--°C"
            self._icon = QPixmap()
        self.updateGeometry()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        colors = theme_colors()

        # 摇摆：绕中心旋转
        painter.save()
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._angle)
        painter.translate(-self.width() / 2, -self.height() / 2)

        icon_size = s(18)
        x = s(2)
        y = (self.height() - icon_size) // 2
        if not self._icon.isNull():
            painter.drawPixmap(x, y, icon_size, icon_size, self._icon)

        font = make_font(FONT_MAIN)
        painter.setFont(font)
        fm = QFontMetricsF(font)
        text_x = x + icon_size + s(6)
        rect = QRectF(text_x, (self.height() - fm.height()) / 2,
                      self.width() - text_x, fm.height())

        if self._error:
            painter.setPen(QColor(colors["danger"]))
            text = "%s %s" % (self._temp, self._err_text) if self._cached else self._err_text
        else:
            painter.setPen(QColor(colors["text_main"]))
            text = self._temp
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, text)

        # 空气质量 AQI 徽标（温度右侧；紧凑模式不显示）
        aqi = self._aqi_text() if not self._compact else ""
        if aqi:
            aqi_w = fm.horizontalAdvance(aqi)
            ax = text_x + fm.horizontalAdvance(text) + s(10)
            pen = QColor(aqi_color(self._air.get("aqi")))
            pen.setAlpha(220)
            painter.setPen(pen)
            painter.drawText(
                QRectF(ax, (self.height() - fm.height()) / 2, aqi_w, fm.height()),
                Qt.AlignLeft | Qt.AlignVCenter, aqi)
        painter.restore()
        painter.end()


# ==========================================================================
#  顶部导航栏主窗口
# ==========================================================================

class IslandWindow(QWidget):
    """固定顶部、全屏宽的导航栏信息条。"""

    NAV_HEIGHT = 40            # 高度固定 40px（× DPI 缩放）
    HIDE_WEATHER_WIDTH = 560   # 宽度小于该值（逻辑像素）时隐藏天气
    HIDE_COURSE_WIDTH = 320    # 极端窄屏再隐藏课程
    HOVER_HIDE_MARGIN = 60     # 鼠标靠近灵动岛多少像素内自动隐藏
    HOVER_HIDE_INTERVAL = 100  # 靠近检测轮询间隔（毫秒，越小反应越快）

    def __init__(self, theme_manager, course_manager, weather_manager, config, parent=None):
        super().__init__(parent)
        self.theme = theme_manager
        self.course_manager = course_manager
        self.weather_manager = weather_manager
        self.config = config

        self._screen_index = 0
        self._fullscreen = False
        self._width_ratio = float(config.get("island_width_ratio", 1.0))
        self._glass_style = config.get("island_glass_style", "auto")
        self._glass_custom = config.get("island_glass_custom", "#1E202D")
        self._opacity = float(config.get("opacity", 0.9))
        self._pass_through = False
        self._course_full_text = "今日无课程安排"
        self._warnings = []
        self._weather_data = None

        # 鼠标靠近自动隐藏（默认开启）
        self._hover_hide = bool(config.get("hover_hide", True))
        self._hover_auto_hidden = False
        self._sliding = False

        # ---- 窗口配置：置顶 / 无边框 / 工具窗 / 不抢焦点 / 透明背景 ----
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool |
            Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self._build_ui()
        self._build_animations()
        self._build_timers()

        self._on_theme_changed(self.theme.current_theme)
        self.theme.theme_changed.connect(self._on_theme_changed)
        self._connect_screen_signals()

    # ==================================================================
    #  UI 构建
    # ==================================================================
    def _build_ui(self):
        # 外层容器：紧贴顶部，无阴影边距
        self.outer_frame = QFrame(self)
        outer_layout = QGridLayout(self.outer_frame)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.setColumnStretch(0, 1)
        outer_layout.setRowStretch(0, 1)

        # 背景（毛玻璃）：半透明底色 + 模糊
        self.bg_frame = QFrame(self.outer_frame)
        self.bg_frame.setObjectName("islandBackground")
        self.bg_frame.setAttribute(Qt.WA_StyledBackground, True)
        self.bg_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.bg_frame.setStyleSheet(
            "background-color: %s; border: none; border-radius: 0px;" % self._glass_bg())
        make_blur(self.bg_frame, radius=8)
        outer_layout.addWidget(self.bg_frame, 0, 0)

        # 内容层（透明，浮于背景之上）
        # 时间采用绝对定位精确居中，不随左右模块宽度变化而移动
        self.content_widget = QWidget(self.outer_frame)
        self.content_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content = QHBoxLayout(self.content_widget)
        content.setContentsMargins(s(20), 0, s(20), 0)   # padding: 0 20px
        content.setSpacing(0)
        content.setAlignment(Qt.AlignVCenter)
        outer_layout.addWidget(self.content_widget, 0, 0)

        # 左：课程信息（固定，可收缩，超出时省略号）
        self._build_course_section(content)
        content.addStretch(1)

        # 右：天气/AQI 与 预警 轮播
        self._build_weather_section(content)

        # 中：时钟 + 日期（绝对居中，永不移动、永不压缩）
        self._build_center_section(self.content_widget)

        # 预警：右上角浮层
        self._build_warning_overlay()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.outer_frame)

    # ------------------------------------------------------------------
    #  左：课程信息
    # ------------------------------------------------------------------
    def _build_course_section(self, content):
        panel = CoursePanel(self.content_widget)
        row = QHBoxLayout(panel)
        row.setContentsMargins(s(2), 0, 0, 0)
        row.setSpacing(s(8))
        row.setAlignment(Qt.AlignVCenter)

        # tiny 状态圆点
        self.course_dot = QFrame(panel)
        self.course_dot.setFixedSize(s(6), s(6))
        self.course_dot.setAttribute(Qt.WA_StyledBackground, True)
        self.course_dot.setStyleSheet("background: #22C55E; border-radius: %dpx;" % s(3))
        row.addWidget(self.course_dot)

        # 课程文字（不粗，margin-right 20px）
        self.course_label = QLabel("今日无课程安排", panel)
        self.course_label.setFont(make_font(FONT_MAIN, bold=False))
        self.course_label.setMinimumWidth(0)
        self.course_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        row.addWidget(self.course_label)

        content.addWidget(panel)
        self.course_panel = panel

        # 课程切换淡入（InOutCubic 0.5s）
        self._course_effect = QGraphicsOpacityEffect(panel)
        panel.setGraphicsEffect(self._course_effect)
        self._course_effect.setOpacity(1.0)

    # ------------------------------------------------------------------
    #  中：时钟 + 日期
    # ------------------------------------------------------------------
    def _build_center_section(self, parent):
        box = QWidget(parent)
        box.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(s(12))
        row.setAlignment(Qt.AlignCenter)

        self.time_label = DigitalTimeLabel(size_pt=11.0, parent=box)
        # 时钟固定宽度：按最宽文本 "00:00:00"（秒级）计算，预留弹性缩放余量
        fm_clock = QFontMetricsF(make_font(11.0, bold=True))
        self.time_label.setFixedWidth(int(fm_clock.horizontalAdvance("00:00:00")) + s(18))

        self.date_label = QLabel("", box)
        self.date_label.setFont(make_font(FONT_MAIN))
        self.date_label.setStyleSheet("color: %s;" % theme_colors()["text_secondary"])
        self.date_label.setAlignment(Qt.AlignCenter)
        # 日期最小宽度：按最宽形态 "08-11 周三" 计算，保证永远完整
        fm_date = QFontMetricsF(make_font(FONT_MAIN))
        self.date_label.setMinimumWidth(int(fm_date.horizontalAdvance("08-11 周三")))

        row.addWidget(self.time_label)
        row.addWidget(self.date_label)
        self.center_group = box
        # 时钟+日期按内容宽度固定尺寸，任何情况下禁止压缩
        self.center_group.setFixedSize(self.center_group.sizeHint())

    def _recenter_time(self):
        """把时间组绝对定位到内容区正中央（水平 + 垂直）。"""
        if not hasattr(self, "center_group"):
            return
        w = self.content_widget.width()
        h = self.content_widget.height()
        self.center_group.move(
            (w - self.center_group.width()) // 2,
            (h - self.center_group.height()) // 2)

    # ------------------------------------------------------------------
    #  右：天气/AQI 与 预警 轮播
    # ------------------------------------------------------------------
    def _build_weather_section(self, content):
        # 右侧用 QStackedWidget：天气/AQI 与 预警 二选一，保证绝不重叠
        self.right_stack = QStackedWidget(self.content_widget)
        self.right_stack.setStyleSheet(
            "QStackedWidget { border: none; background: transparent; }")
        self.right_stack.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.weather_display = WeatherDisplay(self.right_stack)
        self.warning_badge = QLabel("", self.right_stack)
        self.warning_badge.setFont(make_font(FONT_MAIN, bold=True))
        self.warning_badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.warning_badge.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        self.right_stack.addWidget(self.weather_display)
        self.right_stack.addWidget(self.warning_badge)

        self._warning_full_text = ""
        self._right_show_weather = True
        self.right_stack.setCurrentIndex(0)
        content.addWidget(self.right_stack)

        # 翻牌器浮层：覆盖在右侧上方，播放翻转动画
        self.flip_card = FlipCard(self.content_widget)

    def _show_weather(self):
        self._right_show_weather = True
        self.right_stack.setCurrentIndex(0)
        self.right_stack.show()
        self._update_weather_fit()

    def _show_warning(self):
        if not self._warnings:
            self._show_weather()
            return
        self._right_show_weather = False
        w = self._warnings[0]
        color = w.get("color_hex") or warning_color_hex(w.get("color"))
        title = w.get("title") or "".join(
            [w.get("typeName", ""), w.get("level", "")]) or "天气预警"
        self._warning_full_text = "预警 · %s" % title
        self.warning_badge.setStyleSheet("color: %s; background: transparent;" % color)
        self.right_stack.setCurrentIndex(1)
        self.right_stack.show()
        self._update_warning_elide()

    def _rotate_right(self):
        """右侧信息轮播：天气/AQI 与 预警 以翻牌效果轮流显示。"""
        current = self.right_stack.currentIndex()
        if self._warnings:
            target = 1 if current == 0 else 0
        else:
            target = 0
        if target != current:
            self._flip_to(target)
        else:
            self._right_show_weather = (target == 0)

    def _flip_to(self, index):
        """翻牌切换到 index 页（0=天气 1=预警）。"""
        if not hasattr(self, "flip_card"):
            self.right_stack.setCurrentIndex(index)
            self._right_show_weather = (index == 0)
            return
        front = self.right_stack.currentWidget().grab()
        back = self.right_stack.widget(index).grab()
        self.flip_card.set_pages(front, back)
        self.flip_card.setGeometry(self.right_stack.geometry())
        self.flip_card.raise_()
        self.flip_card.show()

        def on_done():
            self.right_stack.setCurrentIndex(index)
            self._right_show_weather = (index == 0)
            self.flip_card.hide()
            if index == 0:
                self._update_weather_fit()
            else:
                self._update_warning_elide()

        self.flip_card.flip(on_done)

    def _update_warning_elide(self, avail=0):
        if not hasattr(self, "warning_badge") or not self.warning_badge.isVisible():
            return
        if avail <= 0:
            # 布局未就绪时不截断，保留完整文字
            self.warning_badge.setText(self._warning_full_text)
            return
        fm = QFontMetricsF(self.warning_badge.font())
        self.warning_badge.setText(
            fm.elidedText(self._warning_full_text, Qt.ElideRight, avail))

    # ------------------------------------------------------------------
    #  预警浮层（右上角）
    # ------------------------------------------------------------------
    def _build_warning_overlay(self):
        self.warning_panel = QFrame(self.content_widget)
        self.warning_panel.setStyleSheet(
            "background-color: %s; border-radius: %dpx; border: none;"
            % (theme_colors()["warning_bg"], s(8)))
        self.warning_panel.setAttribute(Qt.WA_StyledBackground, True)
        row = QHBoxLayout(self.warning_panel)
        row.setContentsMargins(s(12), s(2), s(12), s(2))
        self.warning_label = QLabel("", self.warning_panel)
        self.warning_label.setFont(make_font(FONT_MAIN, bold=True))
        self.warning_label.setStyleSheet("color: %s;" % theme_colors()["danger"])
        row.addWidget(self.warning_label)
        self.warning_panel.hide()

        self._warn_effect = QGraphicsOpacityEffect(self.warning_panel)
        self.warning_panel.setGraphicsEffect(self._warn_effect)
        self._warn_effect.setOpacity(1.0)

    # ==================================================================
    #  动画
    # ==================================================================
    def _build_animations(self):
        # 课程呼吸灯（InOutSine 2s 循环）
        self._breath_anim = utils.create_loop_animation(
            self.course_panel, b"glow",
            [(0.0, 0.0), (0.5, 1.0), (1.0, 0.0)],
            duration=2000, easing=QEasingCurve.Type.InOutSine)

        # 课程切换淡入（InOutCubic 0.5s）
        self._course_fade = QPropertyAnimation(self._course_effect, b"opacity", self._course_effect)
        self._course_fade.setDuration(500)
        self._course_fade.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._course_fade.setStartValue(0.55)
        self._course_fade.setEndValue(1.0)

        # 预警脉冲（InOutQuint 1.5s 循环）
        self._warn_anim = utils.create_loop_animation(
            self._warn_effect, b"opacity",
            [(0.0, 0.7), (0.5, 1.0), (1.0, 0.7)],
            duration=1500, easing=QEasingCurve.Type.InOutQuint)

        # 天气异常摇摆（InOutCubic 2s 循环，±3°）
        self._shake_anim = utils.create_loop_animation(
            self.weather_display, b"angle",
            [(0.0, -3.0), (0.5, 3.0), (1.0, -3.0)],
            duration=2000, easing=QEasingCurve.Type.InOutCubic)

    def _set_breathing(self, active):
        if active:
            if self._breath_anim.state() != QAbstractAnimation.State.Running:
                self._breath_anim.start()
            self.course_panel.set_breathing(True)
        else:
            self._breath_anim.stop()
            self.course_panel.set_breathing(False)

    # ==================================================================
    #  定时器
    # ==================================================================
    def _build_timers(self):
        self._time_timer = QTimer(self)
        self._time_timer.setInterval(1000)
        self._time_timer.timeout.connect(self.update_time)
        self._time_timer.start()

        self._course_timer = QTimer(self)
        self._course_timer.setInterval(10000)
        self._course_timer.timeout.connect(self.update_course)
        self._course_timer.start()

        # 鼠标靠近自动隐藏轮询
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(self.HOVER_HIDE_INTERVAL)
        self._hover_timer.timeout.connect(self._check_hover_hide)
        self._hover_timer.start()

        # 右侧信息轮播：天气/AQI 与 预警 轮流显示
        self._right_timer = QTimer(self)
        self._right_timer.setInterval(5000)
        self._right_timer.timeout.connect(self._rotate_right)
        self._right_timer.start()

    # ==================================================================
    #  鼠标靠近自动隐藏
    # ==================================================================
    def _hover_zone(self):
        """鼠标靠近判定区域：灵动岛所在屏幕顶部的矩形（向下扩展边距）。"""
        rect = self.calculate_island_geometry()
        rect.setBottom(rect.bottom() + s(self.HOVER_HIDE_MARGIN))
        return rect

    def _check_hover_hide(self):
        """鼠标靠近灵动岛时自动隐藏，鼠标移开区域后自动恢复显示。"""
        if not self._hover_hide or self._sliding:
            return
        zone = self._hover_zone()
        cursor = QCursor.pos()
        if self.isVisible() and zone.contains(cursor):
            if not self._hover_auto_hidden:
                self._hover_auto_hidden = True
                self.slide_out()
        elif self._hover_auto_hidden and not self.isVisible() and not zone.contains(cursor):
            self._hover_auto_hidden = False
            self.slide_in()

    def set_hover_hide(self, enabled):
        """开启/关闭"鼠标靠近自动隐藏"。"""
        self._hover_hide = bool(enabled)
        if not self._hover_hide and self._hover_auto_hidden:
            # 关闭该功能时，若当前因靠近而被隐藏，则恢复显示
            self._hover_auto_hidden = False
            if not self.isVisible():
                self.slide_in()

    def hover_hide_enabled(self):
        return self._hover_hide

    # ==================================================================
    #  毛玻璃样式（可自定义）
    # ==================================================================
    def _glass_bg(self):
        """返回当前毛玻璃背景色：auto=跟随主题，dark/light=固定深浅，custom=自定义色。"""
        style = self._glass_style
        if style == "dark":
            return "rgba(30, 30, 40, 0.7)"
        if style == "light":
            return "rgba(255, 255, 255, 0.72)"
        if style == "custom":
            c = QColor(self._glass_custom or "#1E202D")
            return "rgba(%d, %d, %d, 0.72)" % (c.red(), c.green(), c.blue())
        return nav_bar_color()

    def _apply_glass_bg(self):
        if hasattr(self, "bg_frame"):
            self.bg_frame.setStyleSheet(
                "background-color: %s; border: none; border-radius: 0px;" % self._glass_bg())

    def set_glass_style(self, style, custom_hex=""):
        """设置毛玻璃样式：auto / dark / light / custom。"""
        self._glass_style = style
        if custom_hex:
            self._glass_custom = custom_hex
        self._apply_glass_bg()

    def glass_style(self):
        return self._glass_style

    # ==================================================================
    #  屏幕适配（多显示器 / 热插拔）
    # ==================================================================
    def current_screen(self):
        return utils.get_screen(self._screen_index)

    def calculate_island_geometry(self):
        """灵动岛几何：全屏模式占满整行，窗口模式按宽度比例水平居中。"""
        screen = self.current_screen()
        if screen is None:
            return QRect(0, 0, s(1000), s(self.NAV_HEIGHT))
        available = screen.availableGeometry()
        dpi = screen.logicalDotsPerInch()
        scale = dpi / 96.0
        height = int(self.NAV_HEIGHT * scale)
        if self._fullscreen:
            width = available.width()
            x = available.x()
        else:
            ratio = max(0.5, min(1.0, self._width_ratio))
            width = int(available.width() * ratio)
            x = available.x() + (available.width() - width) // 2
        return QRect(x, available.y(), width, height)

    def apply_geometry(self):
        self.setGeometry(self.calculate_island_geometry())
        self._apply_adaptive_visibility()

    def _apply_adaptive_visibility(self):
        """防重叠：宽度不足时优先隐藏"天气"，再隐藏"课程"；时钟+日期永不隐藏。
        各模块按与中心时钟的实际间距自动调整：左模块省略号截断，
        右模块按可用宽度自动压缩（隐藏 AQI）或整体隐藏。"""
        if not hasattr(self, "content_widget"):
            return
        width = self.width()
        self.right_stack.setVisible(width >= s(self.HIDE_WEATHER_WIDTH))
        self.course_panel.setVisible(width >= s(self.HIDE_COURSE_WIDTH))
        self._layout_warning_overlay()
        # 先完成布局，再把时间绝对定位到正中央
        self.content_widget.layout().activate()
        self._recenter_time()
        self._update_course_elide()
        self._update_weather_fit()

    def _update_weather_fit(self):
        """右模块防遮挡：可用宽度不足时先压缩天气（去掉 AQI），预警文字省略号截断。"""
        if not hasattr(self, "right_stack"):
            return
        right_avail = self.content_widget.width() - (
            self.center_group.x() + self.center_group.width()) - s(16)
        if right_avail <= 0:
            return   # 布局尚未就绪，保持当前状态
        if self.right_stack.currentIndex() == 0:
            full = self.weather_display.full_width()
            compact = self.weather_display.compact_width()
            if full <= right_avail:
                self.weather_display.set_compact(False)
                self.right_stack.show()
            elif compact <= right_avail:
                self.weather_display.set_compact(True)
                self.right_stack.show()
            else:
                self.right_stack.hide()   # 空间实在不够，整个右侧隐藏
        elif self.right_stack.currentIndex() == 1:
            self.right_stack.show()
            self._update_warning_elide(right_avail)

    def _connect_screen_signals(self):
        """监听屏幕增删 / 分辨率变更 / DPI 变更，自动重新适配。"""
        app = QGuiApplication.instance()

        def _re_adapt(*_args):
            self.apply_geometry()

        app.screenAdded.connect(_re_adapt)
        app.screenRemoved.connect(_re_adapt)
        app.primaryScreenChanged.connect(_re_adapt)
        for screen in QGuiApplication.screens():
            screen.geometryChanged.connect(_re_adapt)
            screen.logicalDotsPerInchChanged.connect(_re_adapt)
            screen.availableGeometryChanged.connect(_re_adapt)

    # ==================================================================
    #  内容更新
    # ==================================================================
    def update_time(self):
        now = datetime.now()
        # 时钟 HH:MM:SS（秒级）
        self.time_label.set_text(now.strftime("%H:%M:%S"))
        # 日期 MM-DD 周X
        self.date_label.setText("%02d-%02d %s" % (now.month, now.day, WEEKDAY_CN2[now.weekday()]))

    def update_course(self):
        """左侧课程信息固定显示（不参与轮播）。"""
        if hasattr(self, "_course_fade"):
            self._course_fade.start()
        colors = theme_colors()
        status = self.course_manager.current_status()
        current = status.get("current")
        next_course = status.get("next")

        if status.get("empty"):
            self._set_course_text("今日无课程安排", dot=colors["success"], breathe=False)
        elif current:
            name = current.get("name", "")
            teacher = current.get("teacher", "")
            text = "%s · %s" % (name, teacher) if teacher else name
            self._set_course_text("正在上课 · %s" % text, dot=colors["primary"], breathe=True)
        elif next_course and status.get("preview"):
            self._set_course_text(
                "下一节 · %s（%d分钟后）" % (next_course.get("name", ""), status["next_minutes"]),
                dot=colors["danger"], breathe=True)
        elif next_course:
            self._set_course_text(
                "休息中 · 下一节 %s %s" % (next_course.get("name", ""), next_course.get("start", "")),
                dot=colors["text_secondary"], breathe=False)
        else:
            self._set_course_text("今日课程已结束", dot=colors["text_secondary"], breathe=False)

    def _set_course_text(self, text, dot, breathe):
        self._course_full_text = text
        self.course_dot.setStyleSheet(
            "background: %s; border-radius: %dpx;" % (dot, s(3)))
        self._set_breathing(breathe)
        self._update_course_elide()

    def _update_course_elide(self):
        """左侧文字按与中心时钟的实际间距省略号截断，确保不遮挡时间。"""
        if not hasattr(self, "course_label"):
            return
        # 可用宽度 = 中心时钟左边界 - 左侧起点（content 左边距）
        avail = self.center_group.x() - s(20)
        if avail <= 0:
            avail = s(200)
        fm = QFontMetricsF(self.course_label.font())
        elided = fm.elidedText(self._course_full_text, Qt.ElideRight, avail)
        self.course_label.setText(elided)

    # ==================================================================
    #  天气更新
    # ==================================================================
    def _on_weather(self, data):
        self._shake_anim.stop()
        self._warnings = data.get("warnings", []) or []
        self._weather_data = data
        self.weather_display.set_weather(data)
        # 右侧回到天气显示，由轮播定时器切换
        self._right_show_weather = True
        self.right_stack.setCurrentIndex(0)
        self._update_weather_fit()

    def _on_weather_failed(self, info):
        self._weather_data = info.get("cached")
        self._warnings = (self._weather_data or {}).get("warnings", []) or []
        self.weather_display.set_error(info.get("cached"), info.get("message", ""))
        self._right_show_weather = True
        self.right_stack.setCurrentIndex(0)
        self._update_weather_fit()
        self._shake_anim.start()

    # ==================================================================
    #  主题切换
    # ==================================================================
    def _on_theme_changed(self, theme_name):
        colors = theme_colors()
        self._apply_glass_bg()
        self.date_label.setStyleSheet("color: %s;" % colors["text_secondary"])
        self.warning_label.setStyleSheet("color: %s;" % colors["danger"])
        self.warning_panel.setStyleSheet(
            "background-color: %s; border-radius: %dpx; border: none;"
            % (colors["warning_bg"], s(8)))
        self.time_label.update()
        self.course_panel.update()
        self.weather_display.update()

    # ==================================================================
    #  预警（右上角浮层）
    # ==================================================================
    def set_warning(self, text=None):
        if text:
            self.warning_label.setText(text)
            self.warning_panel.adjustSize()
            self.warning_panel.show()
            self._layout_warning_overlay()
            if self._warn_anim.state() != QAbstractAnimation.State.Running:
                self._warn_anim.start()
        else:
            if not self.warning_panel.isVisible():
                return
            self._warn_anim.stop()
            self._warn_effect.setOpacity(1.0)
            self.warning_panel.hide()

    def _layout_warning_overlay(self):
        if not hasattr(self, "warning_panel"):
            return
        self.warning_panel.adjustSize()
        self.warning_panel.move(
            self.content_widget.width() - self.warning_panel.width() - s(20),
            (self.content_widget.height() - self.warning_panel.height()) // 2)

    # ==================================================================
    #  显示 / 隐藏（顶部滑入滑出）
    # ==================================================================
    def slide_in(self):
        self.apply_geometry()
        screen = self.current_screen()
        if screen is None:
            self.show()
            self.raise_()
            return
        target = self.pos()
        start = QPoint(target.x(), target.y() - self.height() - s(2))
        self.move(start)
        self.setWindowOpacity(self._opacity)
        self.show()
        self.raise_()
        self._sliding = True
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.finished.connect(self._on_slide_done)
        anim.start()

    def slide_out(self):
        screen = self.current_screen()
        if screen is None:
            self.hide()
            return
        end = QPoint(self.x(), self.y() - self.height() - s(2))
        self._sliding = True
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.setStartValue(self.pos())
        anim.setEndValue(end)
        anim.finished.connect(self.hide)
        anim.finished.connect(self._on_slide_done)
        anim.start()

    def _on_slide_done(self):
        """滑入/滑出动画结束，清除滑动状态。"""
        self._sliding = False

    def toggle_visible(self):
        if self.isVisible():
            self.slide_out()
        else:
            self.slide_in()

    def show_island(self):
        if not self.isVisible():
            self.slide_in()

    # ==================================================================
    #  公开设置接口
    # ==================================================================
    def set_window_opacity(self, opacity):
        self._opacity = max(0.3, min(1.0, float(opacity)))
        if self.isVisible():
            self.setWindowOpacity(self._opacity)

    def set_width_ratio(self, ratio):
        """设置灵动岛宽度比例（窗口模式下生效），实时调整几何。"""
        self._width_ratio = float(ratio)
        if self.isVisible():
            self.apply_geometry()

    def set_screen_index(self, index):
        self._screen_index = index
        self.apply_geometry()

    def screen_index(self):
        return self._screen_index

    def set_fullscreen(self, fullscreen):
        self._fullscreen = bool(fullscreen)
        self.apply_geometry()

    def is_fullscreen(self):
        return self._fullscreen

    def set_pass_through(self, enabled):
        """鼠标穿透：开启后整个灵动岛窗口对鼠标事件透明（Windows WS_EX_TRANSPARENT）。"""
        self._pass_through = bool(enabled)
        for widget in self.findChildren(QWidget):
            widget.setAttribute(Qt.WA_TransparentForMouseEvents, self._pass_through)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self._pass_through)
        self._apply_click_through()

    def is_pass_through(self):
        return self._pass_through

    def _apply_click_through(self):
        """Windows 窗口级鼠标穿透：设置 WS_EX_TRANSPARENT 扩展样式。"""
        try:
            import ctypes
            hwnd = int(self.winId())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
            if self._pass_through:
                style |= 0x00000020    # WS_EX_TRANSPARENT
            else:
                style &= ~0x00000020
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
        except Exception:
            pass

    # ==================================================================
    #  事件处理
    # ==================================================================
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_adaptive_visibility()

    def showEvent(self, event):
        super().showEvent(event)
        enable_acrylic(self, theme_colors()["acrylic_abgr"])
        self.apply_geometry()
        self._apply_click_through()
