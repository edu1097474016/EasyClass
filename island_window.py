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

from datetime import datetime, date

from PySide6.QtCore import (
    Qt, QRect, QPoint, QRectF,
    Signal, Property, QTimer, QPropertyAnimation, QEasingCurve, QAbstractAnimation,
    QSize, QSizeF,
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QFontMetricsF, QGuiApplication, QPixmap,
)
from PySide6.QtWidgets import (
    QWidget, QLabel, QFrame, QHBoxLayout, QVBoxLayout, QGridLayout,
    QGraphicsOpacityEffect, QSizePolicy, QApplication,
)

import utils
from utils import s, make_font, make_shadow, make_blur, enable_acrylic
from icon_drawer import IconDrawer

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
        self._min_w = s(64)

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


class WeatherDisplay(QWidget):
    """右侧温度显示：矢量图标 + 温度（单行）；网络异常时摇摆动画（±3°）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0.0
        self._icon = QPixmap()
        self._temp = "--°C"
        self._error = False
        self._cached = False
        self._err_text = "⚡ 网络异常"
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setMinimumWidth(s(70))

    _a = Property(float, lambda self: self._angle,
                  lambda self, v: self._set_angle(v))

    def _set_angle(self, value):
        self._angle = value
        self.update()

    def set_weather(self, data):
        colors = theme_colors()
        self._error = False
        self._cached = bool(data.get("cached"))
        self._temp = "%s°C" % data.get("temp", "--")
        self._icon = IconDrawer.weather_icon(
            data.get("code", 999), s(18), fg=colors["icon_fg"])
        self.update()

    def set_error(self, cached, message):
        colors = theme_colors()
        self._error = True
        self._cached = cached is not None
        if cached:
            self._temp = "%s°C" % cached.get("temp", "--")
            self._icon = IconDrawer.weather_icon(
                cached.get("code", 999), s(18), fg=colors["icon_fg"])
        else:
            self._temp = "--°C"
            self._icon = QPixmap()
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
        painter.restore()
        painter.end()


# ==========================================================================
#  顶部导航栏主窗口
# ==========================================================================

class IslandWindow(QWidget):
    """固定顶部、全屏宽的导航栏信息条。"""

    editor_requested = Signal()

    NAV_HEIGHT = 40            # 高度固定 40px（× DPI 缩放）
    HIDE_WEATHER_WIDTH = 560   # 宽度小于该值（逻辑像素）时隐藏天气
    HIDE_COURSE_WIDTH = 320    # 极端窄屏再隐藏课程

    def __init__(self, theme_manager, course_manager, weather_manager, config, parent=None):
        super().__init__(parent)
        self.theme = theme_manager
        self.course_manager = course_manager
        self.weather_manager = weather_manager
        self.config = config

        self._screen_index = 0
        self._fullscreen = False
        self._width_ratio = float(config.get("island_width_ratio", 1.0))
        self._opacity = float(config.get("opacity", 0.9))
        self._pass_through = False
        self._course_full_text = "今日无课程安排"

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
            "background-color: %s; border: none; border-radius: 0px;" % nav_bar_color())
        make_blur(self.bg_frame, radius=8)
        outer_layout.addWidget(self.bg_frame, 0, 0)

        # 内容层（透明，浮于背景之上）
        self.content_widget = QWidget(self.outer_frame)
        self.content_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content = QHBoxLayout(self.content_widget)
        content.setContentsMargins(s(20), 0, s(20), 0)   # padding: 0 20px
        content.setSpacing(s(8))
        content.setAlignment(Qt.AlignVCenter)
        outer_layout.addWidget(self.content_widget, 0, 0)

        # 左：课程信息（可收缩，超出时省略号）
        self._build_course_section(content)

        content.addStretch(1)                            # 左侧弹性空间

        # 中：时钟 + 日期（永不压缩）
        self._build_center_section(content)

        content.addStretch(1)                            # 右侧弹性空间

        # 右：温度
        self._build_weather_section(content)

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

        content.addWidget(panel, stretch=0)
        self.course_panel = panel

        # 课程切换淡入（InOutCubic 0.5s）
        self._course_effect = QGraphicsOpacityEffect(panel)
        panel.setGraphicsEffect(self._course_effect)
        self._course_effect.setOpacity(1.0)

    # ------------------------------------------------------------------
    #  中：时钟 + 日期
    # ------------------------------------------------------------------
    def _build_center_section(self, content):
        box = QWidget(self.content_widget)
        box.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(s(12))
        row.setAlignment(Qt.AlignCenter)

        self.time_label = DigitalTimeLabel(size_pt=11.0, parent=box)
        # 时钟固定宽度：按最宽文本 "00:00" 计算，预留弹性缩放余量
        fm_clock = QFontMetricsF(make_font(11.0, bold=True))
        self.time_label.setFixedWidth(int(fm_clock.horizontalAdvance("00:00")) + s(18))

        self.date_label = QLabel("", box)
        self.date_label.setFont(make_font(FONT_MAIN))
        self.date_label.setStyleSheet("color: %s;" % theme_colors()["text_secondary"])
        self.date_label.setAlignment(Qt.AlignCenter)
        # 日期最小宽度：按最宽形态 "08-11 周三" 计算，保证永远完整
        fm_date = QFontMetricsF(make_font(FONT_MAIN))
        self.date_label.setMinimumWidth(int(fm_date.horizontalAdvance("08-11 周三")))

        row.addWidget(self.time_label)
        row.addWidget(self.date_label)
        content.addWidget(box, stretch=0)
        self.center_group = box
        # 时钟+日期按内容宽度固定尺寸，任何情况下禁止压缩
        self.center_group.setFixedSize(self.center_group.sizeHint())

    # ------------------------------------------------------------------
    #  右：温度
    # ------------------------------------------------------------------
    def _build_weather_section(self, content):
        self.weather_display = WeatherDisplay(self.content_widget)
        content.addWidget(self.weather_display, stretch=0)

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

    # ==================================================================
    #  屏幕适配（多显示器 / 热插拔）
    # ==================================================================
    def current_screen(self):
        return utils.get_screen(self._screen_index)

    def calculate_island_geometry(self):
        """全屏宽 + 固定高度：width = 屏幕可用宽度，height = 40 × DPI。"""
        screen = self.current_screen()
        if screen is None:
            return QRect(0, 0, s(1000), s(self.NAV_HEIGHT))
        available = screen.availableGeometry()
        dpi = screen.logicalDotsPerInch()
        scale = dpi / 96.0
        width = available.width()
        height = int(self.NAV_HEIGHT * scale)
        return QRect(available.x(), available.y(), width, height)

    def apply_geometry(self):
        self.setGeometry(self.calculate_island_geometry())
        self._apply_adaptive_visibility()

    def _apply_adaptive_visibility(self):
        """防重叠：宽度不足时优先隐藏"天气"，再隐藏"课程"；时钟+日期永不隐藏。
        同时根据窗口宽度对左侧课程文字做省略号截断。"""
        if not hasattr(self, "content_widget"):
            return
        width = self.width()
        self.weather_display.setVisible(width >= s(self.HIDE_WEATHER_WIDTH))
        self.course_panel.setVisible(width >= s(self.HIDE_COURSE_WIDTH))
        self._layout_warning_overlay()
        self._update_course_elide()

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
        # 时钟 HH:MM（去秒）
        self.time_label.set_text(now.strftime("%H:%M"))
        # 日期 MM-DD 周X
        self.date_label.setText("%02d-%02d %s" % (now.month, now.day, WEEKDAY_CN2[now.weekday()]))

    def update_course(self):
        if hasattr(self, "_course_fade"):
            self._course_fade.start()

        status = self.course_manager.current_status()
        colors = theme_colors()
        current = status.get("current")
        next_course = status.get("next")

        if status.get("empty"):
            self._set_course_text("今日无课程安排", dot=colors["success"])
            self._set_breathing(False)
        elif current:
            name = current.get("name", "")
            teacher = current.get("teacher", "")
            text = "%s · %s" % (name, teacher) if teacher else name
            self._set_course_text("正在上课 · %s" % text, dot=colors["primary"])
            self._set_breathing(True)
        elif next_course and status.get("preview"):
            self._set_course_text(
                "下一节 · %s（%d分钟后）" % (next_course.get("name", ""), status["next_minutes"]),
                dot=colors["danger"])
            self._set_breathing(True)
        elif next_course:
            self._set_course_text(
                "休息中 · 下一节 %s %s" % (next_course.get("name", ""), next_course.get("start", "")),
                dot=colors["text_secondary"])
            self._set_breathing(False)
        else:
            self._set_course_text("今日课程已结束", dot=colors["text_secondary"])
            self._set_breathing(False)

    def _set_course_text(self, text, dot):
        self._course_full_text = text
        self.course_dot.setStyleSheet("background: %s; border-radius: %dpx;" % (dot, s(3)))
        self._update_course_elide()

    def _update_course_elide(self):
        """左侧文字超出宽度时省略号截断，防止挤压中间时钟。"""
        if not hasattr(self, "course_label"):
            return
        avail = self.course_panel.width()
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
        self.weather_display.set_weather(data)

    def _on_weather_failed(self, info):
        self.weather_display.set_error(info.get("cached"), info.get("message", ""))
        self._shake_anim.start()

    # ==================================================================
    #  主题切换
    # ==================================================================
    def _on_theme_changed(self, theme_name):
        colors = theme_colors()
        self.bg_frame.setStyleSheet(
            "background-color: %s; border: none; border-radius: 0px;" % nav_bar_color(theme_name))
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
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.start()

    def slide_out(self):
        screen = self.current_screen()
        if screen is None:
            self.hide()
            return
        end = QPoint(self.x(), self.y() - self.height() - s(2))
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.setStartValue(self.pos())
        anim.setEndValue(end)
        anim.finished.connect(self.hide)
        anim.start()

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
        # 顶部导航栏固定全宽，宽度比例不再生效（仅保留兼容接口）
        self._width_ratio = float(ratio)

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
        """鼠标穿透：开启后整个导航栏忽略鼠标事件（仅保留双击关闭热键）。"""
        self._pass_through = bool(enabled)
        for widget in self.findChildren(QWidget):
            widget.setAttribute(Qt.WA_TransparentForMouseEvents, self._pass_through)

    def is_pass_through(self):
        return self._pass_through

    # ==================================================================
    #  事件处理
    # ==================================================================
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_adaptive_visibility()

    def mouseDoubleClickEvent(self, event):
        self.editor_requested.emit()
        super().mouseDoubleClickEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        enable_acrylic(self, theme_colors()["acrylic_abgr"])
        self.apply_geometry()
