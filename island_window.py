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
#   · Linux 兼容：修复灵动岛无法定位到顶部的问题
# ==========================================================================

import logging
import sys
from datetime import datetime

from PySide6.QtCore import (
    Qt, QRect, QPoint, QPointF, QRectF, QObject, QEvent,
    Property, QTimer, QPropertyAnimation, QEasingCurve, QAbstractAnimation,
    QSize,
)
from PySide6.QtGui import (
    QPainter, QColor, QFontMetricsF, QGuiApplication, QPixmap, QCursor,
)
from PySide6.QtWidgets import (
    QWidget, QLabel, QFrame, QHBoxLayout, QVBoxLayout, QGridLayout,
    QGraphicsOpacityEffect, QSizePolicy, QApplication, QStackedWidget,
    QPushButton,
)

import utils
from utils import s, make_font, make_blur, enable_acrylic, disable_acrylic
from icon_drawer import IconDrawer
from course_manager import CourseManager
from weather_manager import aqi_color, warning_color_hex

logger = logging.getLogger(__name__)

WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
WEEKDAY_CN2 = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 统一字号：14px ≈ 10.5pt（Qt 磅值自动按 DPI 缩放）
FONT_MAIN = 10.5

# 检测运行平台
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
IS_MAC = sys.platform == "darwin"


def theme_colors():
    theme = QApplication.instance().property("__theme") or "dark"
    from theme_manager import ThemeManager
    return ThemeManager.COLORS.get(theme, ThemeManager.COLORS["dark"])


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


class _CourseResizeFilter(QObject):
    """事件过滤器：课程面板尺寸变化（换屏/缩放）时实时重居中一言。"""

    def __init__(self, island, parent=None):
        super().__init__(parent)
        self._island = island

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize:
            self._island._recenter_hitokoto()
        return False


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


class _ScrollLabel(QWidget):
    """横向滚动文字（跑马灯）：内容超宽时自动滚动显示全文，放得下则静止左对齐。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self._color = QColor("#FFFFFF")
        self._natural_w = 0
        self._offset = 0.0
        self._anim = QPropertyAnimation(self, b"_so", self)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._anim.finished.connect(self._on_scroll_done)
        self._anim_ref = self._anim
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    _so = Property(float, lambda self: self._offset,
                   lambda self, v: self._set_offset(v))

    def _set_offset(self, value):
        self._offset = value
        self.update()

    def set_text(self, text):
        self._text = text or ""
        self._measure()
        self._anim.stop()
        self._offset = 0.0
        self.restart_scroll()
        self.update()

    def set_color(self, color):
        self._color = QColor(color) if isinstance(color, str) else QColor(color)

    def _measure(self):
        fm = QFontMetricsF(self.font())
        self._natural_w = int(fm.horizontalAdvance(self._text)) + s(4)

    def restart_scroll(self):
        if not self._text or self.width() <= 0:
            return
        self._anim.stop()
        if self._natural_w <= self.width():
            self._offset = 0.0
            self.update()
            return
        distance = self._natural_w - self.width() + s(8)
        duration = int(max(4000, distance * 3))
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(float(-distance))
        self._anim.setDuration(duration)
        self._anim.start()

    def _on_scroll_done(self):
        QTimer.singleShot(1500, self.restart_scroll)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.FontChange:
            self._measure()
            if self.isVisible():
                self.restart_scroll()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.restart_scroll()

    def sizeHint(self):
        return QSize(self._natural_w, s(26))

    def minimumSizeHint(self):
        return QSize(s(4), s(26))

    def paintEvent(self, event):
        if not self._text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        font = self.font()
        painter.setFont(font)
        fm = QFontMetricsF(font)
        y = (self.height() - fm.height()) / 2 + fm.ascent()
        painter.setPen(self._color)
        painter.drawText(QPointF(self._offset, y), self._text)
        painter.end()


class RightCarousel(QWidget):
    """最右侧分段轮播：首段固定为 天气+AQI，其后每段为一条预警；淡入淡出切换。
    预警文字以最右侧为基准、向右对齐，过长时用省略号截断右端。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._warnings = []
        self._index = 0
        self._max_width = 1000000
        self._scroll_mode = False
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(1.0)

        self.weather_display = WeatherDisplay(self)
        self.warning_label = QLabel("", self)
        self.warning_label.setFont(make_font(FONT_MAIN, bold=True))
        self.warning_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.warning_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.warning_scroll = _ScrollLabel(self)
        self.warning_scroll.setFont(make_font(FONT_MAIN, bold=True))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.weather_display)
        layout.addWidget(self.warning_label)
        layout.addWidget(self.warning_scroll)
        self.warning_label.hide()
        self.warning_scroll.hide()

        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._advance)

        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(300)
        self._fade.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.hide()

    def set_weather(self, data):
        self.weather_display.set_weather(data)
        self.show()

    def set_error(self, message):
        self.weather_display.set_error(message)
        self.show()

    def set_warnings(self, warnings):
        self._warnings = list(warnings or [])
        self._index = 0
        self._timer.stop()
        self._effect.setOpacity(1.0)
        self._apply_segment()
        self.show()
        self.updateGeometry()
        if len(self._warnings) >= 1:
            self._timer.start()

    def segment_count(self):
        return 1 + len(self._warnings)

    def _advance(self):
        if self.segment_count() <= 1:
            return
        self._index = (self._index + 1) % self.segment_count()
        self._fade.stop()
        self._effect.setOpacity(0.0)
        self._apply_segment()
        self._fade.start()

    def set_mode(self, mode):
        self._scroll_mode = (mode == "scroll")
        if self._index > 0:
            self._apply_segment()

    def _warning_text(self):
        w = self._warnings[self._index - 1] if self._warnings else {}
        title = w.get("title") or "".join(
            [w.get("typeName", ""), w.get("level", "")]) or "天气预警"
        who = w.get("location") or ""
        return "%s发布%s" % (who, title) if who else title

    def _apply_segment(self):
        if self._index == 0:
            self.warning_label.hide()
            self.warning_scroll.hide()
            self.weather_display.show()
            self.updateGeometry()
            return
        w = self._warnings[self._index - 1]
        color = w.get("color_hex") or warning_color_hex(w.get("color"))
        text = self._warning_text()
        avail = self._max_width if self._max_width < 1000000 else (self.width() or s(160))
        self.weather_display.hide()
        if self._scroll_mode:
            self.warning_label.hide()
            self.warning_scroll.set_text(text)
            self.warning_scroll.set_color(color)
            self.warning_scroll.show()
        else:
            self.warning_scroll.hide()
            self.warning_label.setStyleSheet("color: %s; background: transparent;" % color)
            fm = QFontMetricsF(self.warning_label.font())
            self.warning_label.setText(fm.elidedText(text, Qt.ElideLeft, avail))
            self.warning_label.show()
        self.updateGeometry()

    def cap_width(self, avail):
        if avail <= 0:
            return
        self._max_width = avail
        self.setMaximumWidth(avail)
        if self._index > 0:
            self._apply_segment()
        self.updateGeometry()

    def sizeHint(self):
        if self._index == 0:
            return self.weather_display.sizeHint()
        text = self._warning_text()
        if self._scroll_mode:
            fm = QFontMetricsF(self.warning_scroll.font())
            cap = self._max_width if self._max_width < 1000000 else (self.width() or s(160))
            return QSize(min(int(fm.horizontalAdvance(text)) + s(4), cap), s(26))
        fm = QFontMetricsF(self.warning_label.font())
        return QSize(int(fm.horizontalAdvance(text)) + s(4), s(26))

    def minimumSizeHint(self):
        return self.sizeHint()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._index > 0:
            self._apply_segment()


class CourseProgress(QWidget):
    """课程进度条：灵动岛底部细线，上课时按进度填充。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._percent = 0.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()

    def set_progress(self, percent):
        percent = max(0.0, min(100.0, float(percent or 0.0)))
        if abs(percent - self._percent) > 0.05:
            self._percent = percent
            self.update()

    def set_percent(self, percent):
        self.set_progress(percent)

    def paintEvent(self, event):
        if self.width() <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        radius = h / 2
        track = QColor(theme_colors()["border"])
        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(0, 0, self.width(), h, radius, radius)
        fill_w = int(self.width() * self._percent / 100.0)
        if fill_w > 0:
            primary = QColor(theme_colors()["primary"])
            gradient = QColor(primary)
            painter.setBrush(gradient)
            painter.drawRoundedRect(0, 0, fill_w, h, radius, radius)
        painter.end()


class HitokotoLabel(QWidget):
    """每日一言（Hitokoto）：位于课程模块与时间之间。
    支持两种显示方式（_mode）：
     · "elide"  —— 遮挡：超宽文字按可用宽度省略号截断（原算法）
     · "scroll" —— 滚动：超宽文字横向滚动（跑马灯）显示全文，保留出处。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "scroll"
        self._sentence = ""
        self._source = ""
        self._full_text = ""
        self._natural_w = 0
        self._label = QLabel("", self)
        self._label.setFont(make_font(FONT_MAIN))
        self._label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        self._offset = 0.0
        self._scroll_anim = QPropertyAnimation(self, b"_so", self)
        self._scroll_anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._scroll_anim.finished.connect(self._on_scroll_done)
        self._anim_ref = self._scroll_anim
        self._in_pause = False
        self._last_scroll_avail = None
        self._pause_timer = QTimer(self)
        self._pause_timer.setSingleShot(True)
        self._pause_timer.setInterval(1500)
        self._pause_timer.timeout.connect(self._resume_scroll)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.hide()

    _so = Property(float, lambda self: self._offset,
                   lambda self, v: self._set_offset(v))

    def _set_offset(self, value):
        self._offset = value
        self.update()

    def set_mode(self, mode):
        self._mode = "scroll" if mode == "scroll" else "elide"
        self._scroll_anim.stop()
        self._in_pause = False
        self._pause_timer.stop()
        self._last_scroll_avail = None
        self._offset = 0.0
        if self._sentence:
            self._rebuild_text()
            self._apply_style()
            self.updateGeometry()
            if self.isVisible():
                self.restart_scroll()
            self.update()

    def set_quote(self, data):
        sentence = (data.get("hitokoto") or "").strip()
        if not sentence:
            self.hide()
            return
        self._sentence = sentence
        self._source = (data.get("from") or "").strip()
        self._scroll_anim.stop()
        self._in_pause = False
        self._pause_timer.stop()
        self._last_scroll_avail = None
        self._offset = 0.0
        self._rebuild_text()
        self._apply_style()
        self.updateGeometry()
        self.show()
        self.restart_scroll()

    def _rebuild_text(self):
        if self._mode == "scroll" and self._source:
            self._full_text = "「%s」——《%s》" % (self._sentence, self._source)
        else:
            self._full_text = "「%s」" % self._sentence
        fm = QFontMetricsF(make_font(FONT_MAIN))
        self._natural_w = int(fm.horizontalAdvance(self._full_text)) + s(4)
        self._update_elided()
        self.update()

    def _apply_style(self):
        self._label.setStyleSheet("color: %s;" % theme_colors()["text_secondary"])

    def _update_elided(self):
        if not self._full_text:
            return
        avail = self.width() if self.width() > 0 else s(120)
        fm = QFontMetricsF(self._label.font())
        self._label.setText(fm.elidedText(self._full_text, Qt.ElideRight, avail))

    def restart_scroll(self):
        avail = self.width()
        if not self._full_text or avail <= 0:
            return
        if self._mode != "scroll" or self._natural_w <= avail:
            self._scroll_anim.stop()
            self._in_pause = False
            self._pause_timer.stop()
            self._last_scroll_avail = None
            self._offset = 0.0
            self._label.setVisible(True)
            self.update()
            return
        if self._in_pause:
            return
        if (self._scroll_anim.state() == QAbstractAnimation.State.Running
                and self._last_scroll_avail is not None
                and abs(avail - self._last_scroll_avail) <= s(4)):
            return
        self._label.setVisible(False)
        distance = self._natural_w - avail + s(10)
        duration = int(max(4000, distance * 3))
        self._scroll_anim.stop()
        self._scroll_anim.setStartValue(0.0)
        self._scroll_anim.setEndValue(float(-distance))
        self._scroll_anim.setDuration(duration)
        self._scroll_anim.start()
        self._last_scroll_avail = avail
        self.update()

    def _resume_scroll(self):
        self._in_pause = False
        self.restart_scroll()

    def _on_scroll_done(self):
        self._in_pause = True
        self._pause_timer.start()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.FontChange:
            self._natural_w = int(QFontMetricsF(self._label.font()).horizontalAdvance(
                self._full_text)) + s(4)
            if self._full_text:
                self._update_elided()
                if self._mode == "scroll" and self.isVisible():
                    self.restart_scroll()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._mode == "scroll":
            self.restart_scroll()
        else:
            self._update_elided()

    def paintEvent(self, event):
        if self._mode != "scroll" or not self._label.isHidden():
            return
        if not self._full_text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        font = make_font(FONT_MAIN)
        painter.setFont(font)
        fm = QFontMetricsF(font)
        y = (self.height() - fm.height()) / 2 + fm.ascent()
        painter.setPen(QColor(theme_colors()["text_secondary"]))
        painter.drawText(QPointF(self._offset, y), self._full_text)
        painter.end()

    def sizeHint(self):
        if not self._full_text:
            return QSize(s(4), s(26))
        return QSize(self._natural_w, s(26))

    def minimumSizeHint(self):
        return self.sizeHint()


class WeatherDisplay(QWidget):
    """天气显示：矢量图标 + 当前天气（小雨等）+ 温度 + AQI（固定显示，不参与轮播）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0.0
        self._icon = QPixmap()
        self._text = ""
        self._temp = "--°C"
        self._error = False
        self._cached = False
        self._air = None
        self._compact = False
        self._err_text = "网络异常"
        self._err_offset = 0.0
        self._err_anim = QPropertyAnimation(self, b"_eo", self)
        self._err_anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._err_anim.finished.connect(self._on_err_scroll_done)
        self._err_anim_ref = self._err_anim
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setMinimumWidth(s(70))

    _a = Property(float, lambda self: self._angle,
                  lambda self, v: self._set_angle(v))

    _eo = Property(float, lambda self: self._err_offset,
                   lambda self, v: self._set_err_offset(v))

    def _set_angle(self, value):
        self._angle = value
        self.update()

    def _set_err_offset(self, value):
        self._err_offset = value
        self.update()

    def restart_err_scroll(self):
        if not self._error or not self._err_text:
            return
        self._err_anim.stop()
        fm = QFontMetricsF(make_font(FONT_MAIN))
        tw = fm.horizontalAdvance(self._err_text)
        avail = max(s(10), self.width() - s(26))
        if tw <= avail:
            self._err_offset = 0.0
            self.update()
            return
        distance = tw - avail + s(10)
        duration = int(max(4000, distance * 3))
        self._err_anim.setStartValue(0.0)
        self._err_anim.setEndValue(float(-distance))
        self._err_anim.setDuration(duration)
        self._err_anim.start()

    def _on_err_scroll_done(self):
        QTimer.singleShot(1500, self.restart_err_scroll)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._error:
            self.restart_err_scroll()

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
        w = s(2) + s(18)
        if self._text:
            w += s(6) + fm.horizontalAdvance(self._text)
        w += s(6) + fm.horizontalAdvance(self._temp)
        if with_aqi:
            aqi = self._aqi_text()
            if aqi:
                w += s(10) + fm.horizontalAdvance(aqi)
        return int(w) + s(2)

    def full_width(self):
        return self._measure(True)

    def compact_width(self):
        return self._measure(False)

    def set_compact(self, compact):
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
        self._err_anim.stop()
        self._err_offset = 0.0
        self._cached = bool(data.get("cached"))
        self._text = data.get("text", "") or ""
        self._temp = "%s°C" % data.get("temp", "--")
        self._air = data.get("air") or None
        self._icon = IconDrawer.weather_icon(
            data.get("code", 999), s(18), fg=colors["icon_fg"])
        self.updateGeometry()
        self.update()

    def set_error(self, message):
        colors = theme_colors()
        self._error = True
        self._cached = False
        self._air = None
        self._text = ""
        self._temp = "--°C"
        self._icon = QPixmap()
        self._err_text = (message or "网络异常").strip() or "网络异常"
        self.updateGeometry()
        self.restart_err_scroll()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        colors = theme_colors()

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

        # 根据 AQI 确定文字颜色
        aqi_val = None
        if self._air:
            try:
                aqi_val = int(self._air.get("aqi"))
            except (TypeError, ValueError):
                aqi_val = None
        aqi_c = aqi_color(aqi_val) if aqi_val is not None else None

        if self._text and not self._error:
            painter.setPen(QColor(colors["text_secondary"]))
            painter.drawText(
                QRectF(text_x, (self.height() - fm.height()) / 2,
                       fm.horizontalAdvance(self._text), fm.height()),
                Qt.AlignLeft | Qt.AlignVCenter, self._text)
            text_x += fm.horizontalAdvance(self._text) + s(6)

        rect = QRectF(text_x, (self.height() - fm.height()) / 2,
                      self.width() - text_x, fm.height())

        if self._error:
            painter.setPen(QColor(colors["danger"]))
            text = self._err_text
            x0 = text_x + self._err_offset
            rect = QRectF(x0, (self.height() - fm.height()) / 2,
                          self.width() - x0, fm.height())
        else:
            # 温度文字：AQI 可用时跟随 AQI 等级颜色，否则用主题色
            if aqi_c:
                pen = QColor(aqi_c)
                pen.setAlpha(200)
                painter.setPen(pen)
            else:
                painter.setPen(QColor(colors["text_main"]))
            text = self._temp
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, text)

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
#  顶部导航栏主窗口（Linux 兼容修复版）
# ==========================================================================

class IslandWindow(QWidget):
    """固定顶部、全屏宽的导航栏信息条。"""

    NAV_HEIGHT = 40
    HIDE_WEATHER_WIDTH = 560
    HIDE_COURSE_WIDTH = 320
    HOVER_HIDE_MARGIN = 60
    HOVER_HIDE_INTERVAL = 100

    def __init__(self, theme_manager, course_manager, weather_manager, config, parent=None):
        super().__init__(parent)
        self.theme = theme_manager
        self.course_manager = course_manager
        self.weather_manager = weather_manager
        self.config = config

        self._screen_index = int(config.get("island_screen", 0))
        self._fullscreen = bool(config.get("island_fullscreen", False))
        self._pass_through = bool(config.get("island_passthrough", False))
        self._width_ratio = float(config.get("island_width_ratio", 1.0))
        self._glass_style = config.get("island_glass_style", "auto")
        self._glass_custom = config.get("island_glass_custom", "#1E202D")
        self._material = config.get("island_material", "frosted")
        self._shape = config.get("island_shape", "rect")
        self._opacity = float(config.get("opacity", 0.9))
        self._course_full_text = "今日无课程安排"
        self._warnings = []
        self._weather_data = None

        self._cstatus = None
        self._carousel_items = []
        self._carousel_index = 0
        self._course_elide_avail = 0

        self._hover_hide = bool(config.get("hover_hide", True))
        self._hover_auto_hidden = False
        self._sliding = False
        self._hover_margin = int(config.get("hover_hide_margin", 60))
        self._hover_interval = int(config.get("hover_hide_interval", 100))

        self._progress_height = int(config.get("course_progress_height", 3))
        self._hitokoto_category = config.get("hitokoto_category", "") or ""
        self._hitokoto_refresh_ms = max(
            60, int(config.get("hitokoto_refresh_minutes", 15))) * 60 * 1000
        self._text_mode = config.get("text_mode", "scroll") or "scroll"
        if self._text_mode not in ("elide", "scroll"):
            self._text_mode = "scroll"

        # 位置偏移（用户手动调整后的增量，像素）
        self._pos_x_offset = int(config.get("island_pos_x_offset", 0))
        self._pos_y_offset = int(config.get("island_pos_y_offset", 0))
        # 拖拽模式标记（由管理后台触发）
        self._drag_mode = False
        self._drag_start = None

        # ---- 窗口配置：置顶 / 无边框 / 不抢焦点 / 透明背景 ----
        # Linux 兼容：使用 Qt.Window 替代 Qt.Tool
        if IS_LINUX:
            self.setWindowFlags(
                Qt.WindowStaysOnTopHint |
                Qt.FramelessWindowHint |
                Qt.Window |
                Qt.WindowDoesNotAcceptFocus
            )
        else:
            self.setWindowFlags(
                Qt.WindowStaysOnTopHint |
                Qt.FramelessWindowHint |
                Qt.Tool |
                Qt.WindowDoesNotAcceptFocus
            )

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        icon = IconDrawer.app_icon_qicon(64)
        if icon is not None:
            self.setWindowIcon(icon)

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
        self.outer_frame = QFrame(self)
        outer_layout = QGridLayout(self.outer_frame)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.setColumnStretch(0, 1)
        outer_layout.setRowStretch(0, 1)

        self.bg_frame = QFrame(self.outer_frame)
        self.bg_frame.setObjectName("islandBackground")
        self.bg_frame.setAttribute(Qt.WA_StyledBackground, True)
        self.bg_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.bg_frame.setStyleSheet(
            "background-color: %s; border: none; border-radius: 0px;" % self._glass_bg())
        self._blur_effect = make_blur(self.bg_frame, radius=8)
        outer_layout.addWidget(self.bg_frame, 0, 0)

        self.content_widget = QWidget(self.outer_frame)
        self.content_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content = QHBoxLayout(self.content_widget)
        content.setContentsMargins(s(4), 0, s(20), 0)
        content.setSpacing(s(8))
        content.setAlignment(Qt.AlignVCenter)
        outer_layout.addWidget(self.content_widget, 0, 0)

        self._build_course_section(content)

        self.hitokoto_label = HitokotoLabel(self.content_widget)
        self.hitokoto_label.hide()

        content.addStretch(1)

        self.right_carousel = RightCarousel(self.content_widget)
        self.weather_display = self.right_carousel.weather_display
        content.addWidget(self.right_carousel)

        self.hitokoto_label.set_mode(self._text_mode)
        self.right_carousel.set_mode(self._text_mode)

        self._build_center_section(self.content_widget)

        self._build_warning_overlay()

        self.course_progress = CourseProgress(self.outer_frame)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.outer_frame)

    def _build_course_section(self, content):
        panel = CoursePanel(self.content_widget)
        row = QHBoxLayout(panel)
        row.setContentsMargins(s(2), 0, 0, 0)
        row.setSpacing(s(8))
        row.setAlignment(Qt.AlignVCenter)

        self.course_dot = QFrame(panel)
        self.course_dot.setFixedSize(s(6), s(6))
        self.course_dot.setAttribute(Qt.WA_StyledBackground, True)
        self.course_dot.setStyleSheet("background: #22C55E; border-radius: %dpx;" % s(3))
        row.addWidget(self.course_dot)

        self.course_label = QLabel("今日无课程安排", panel)
        self.course_label.setFont(make_font(FONT_MAIN, bold=False))
        self.course_label.setMinimumWidth(0)
        self.course_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        row.addWidget(self.course_label)

        content.addWidget(panel)
        self.course_panel = panel

        self._course_effect = QGraphicsOpacityEffect(panel)
        panel.setGraphicsEffect(self._course_effect)
        self._course_effect.setOpacity(1.0)

        if not hasattr(self, "_course_resize_filter"):
            self._course_resize_filter = _CourseResizeFilter(self)
        panel.installEventFilter(self._course_resize_filter)

    def _build_center_section(self, parent):
        box = QWidget(parent)
        box.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(s(12))
        row.setAlignment(Qt.AlignCenter)

        self.time_label = DigitalTimeLabel(size_pt=11.0, parent=box)
        fm_clock = QFontMetricsF(make_font(11.0, bold=True))
        self.time_label.setFixedWidth(int(fm_clock.horizontalAdvance("00:00:00")) + s(18))

        self.date_label = QLabel("", box)
        self.date_label.setFont(make_font(FONT_MAIN))
        self.date_label.setStyleSheet("color: %s;" % theme_colors()["text_secondary"])
        self.date_label.setAlignment(Qt.AlignCenter)
        fm_date = QFontMetricsF(make_font(FONT_MAIN))
        self.date_label.setMinimumWidth(int(fm_date.horizontalAdvance("08-11 周三")))

        row.addWidget(self.time_label)
        row.addWidget(self.date_label)
        self.center_group = box
        self.center_group.setFixedSize(self.center_group.sizeHint())

    def _recenter_time(self):
        if not hasattr(self, "center_group"):
            return
        w = self.content_widget.width()
        h = self.content_widget.height()
        self.center_group.move(
            (w - self.center_group.width()) // 2,
            (h - self.center_group.height()) // 2)

    def _update_right_fit(self):
        if not hasattr(self, "right_carousel"):
            return
        gap = s(10)
        right_avail = self.content_widget.width() - (
            self.center_group.x() + self.center_group.width()) - s(20) - gap
        if right_avail <= 0:
            return
        self.right_carousel.cap_width(right_avail)

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
        self._breath_anim = utils.create_loop_animation(
            self.course_panel, b"glow",
            [(0.0, 0.0), (0.5, 1.0), (1.0, 0.0)],
            duration=2000, easing=QEasingCurve.Type.InOutSine)

        self._course_fade = QPropertyAnimation(self._course_effect, b"opacity", self._course_effect)
        self._course_fade.setDuration(500)
        self._course_fade.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._course_fade.setStartValue(0.55)
        self._course_fade.setEndValue(1.0)

        self._warn_anim = utils.create_loop_animation(
            self._warn_effect, b"opacity",
            [(0.0, 0.7), (0.5, 1.0), (1.0, 0.7)],
            duration=1500, easing=QEasingCurve.Type.InOutQuint)

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

        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(self._hover_interval)
        self._hover_timer.timeout.connect(self._check_hover_hide)
        self._hover_timer.start()

        self._carousel_timer = QTimer(self)
        self._carousel_timer.timeout.connect(self._on_carousel_tick)

        self._hitokoto_queue = []
        self._hitokoto_shown = False
        self._hitokoto_timer = QTimer(self)
        self._hitokoto_timer.setInterval(self._hitokoto_refresh_ms)
        self._hitokoto_timer.timeout.connect(self._on_hitokoto_tick)
        self._hitokoto_timer.start()
        self._fetch_hitokoto()

    # ==================================================================
    #  每日一言（Hitokoto）
    # ==================================================================
    def _fetch_hitokoto(self):
        if hasattr(self, "_hitokoto_worker") and self._hitokoto_worker.isRunning():
            return
        from hitokoto import HitokotoFetcher
        max_len = 21 if self._text_mode == "elide" else 0
        self._hitokoto_worker = HitokotoFetcher(
            self._hitokoto_category, count=3, max_len=max_len, parent=self)
        self._hitokoto_worker.ok.connect(self._on_hitokoto_batch)
        self._hitokoto_worker.fail.connect(self._on_hitokoto_fail)
        self._hitokoto_worker.start()

    def _on_hitokoto_batch(self, quotes):
        self._hitokoto_queue.extend(quotes)
        logger.info("一言缓存 +%d 条（当前缓存 %d 条）", len(quotes), len(self._hitokoto_queue))
        if not self._hitokoto_shown:
            self._show_next_hitokoto()

    def _on_hitokoto_tick(self):
        self._show_next_hitokoto()

    def _show_next_hitokoto(self):
        if self._hitokoto_queue:
            quote = self._hitokoto_queue.pop(0)
            self._hitokoto_shown = True
            self.hitokoto_label.set_quote(quote)
            self._apply_adaptive_visibility()
            logger.info("一言显示: %s", (quote.get("hitokoto") or "")[:20])
        else:
            self._hitokoto_shown = False
            self.hitokoto_label.hide()
            self._apply_adaptive_visibility()
            self._fetch_hitokoto()

    def _on_hitokoto_fail(self, _msg):
        self._hitokoto_shown = False
        self.hitokoto_label.hide()
        self._apply_adaptive_visibility()

    def set_hitokoto_category(self, category):
        self._hitokoto_category = (category or "").strip()
        self._hitokoto_queue.clear()
        self._fetch_hitokoto()

    def set_hitokoto_refresh(self, minutes):
        self._hitokoto_refresh_ms = max(1, int(minutes)) * 60 * 1000
        self._hitokoto_timer.setInterval(self._hitokoto_refresh_ms)

    def set_text_mode(self, mode):
        self._text_mode = "scroll" if mode == "scroll" else "elide"
        if hasattr(self, "hitokoto_label"):
            self.hitokoto_label.set_mode(self._text_mode)
        if hasattr(self, "right_carousel"):
            self.right_carousel.set_mode(self._text_mode)
        self._hitokoto_queue = []
        self._fetch_hitokoto()
        self._apply_adaptive_visibility()

    # ==================================================================
    #  鼠标靠近自动隐藏
    # ==================================================================
    def _hover_zone(self):
        rect = self.calculate_island_geometry()
        rect.setBottom(rect.bottom() + s(self._hover_margin))
        return rect

    def _check_hover_hide(self):
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
        self._hover_hide = bool(enabled)
        if not self._hover_hide and self._hover_auto_hidden:
            self._hover_auto_hidden = False
            if not self.isVisible():
                self.slide_in()

    def set_hover_margin(self, margin):
        self._hover_margin = max(10, min(400, int(margin)))

    def set_hover_interval(self, ms):
        self._hover_interval = max(30, min(2000, int(ms)))
        if hasattr(self, "_hover_timer"):
            self._hover_timer.setInterval(self._hover_interval)

    def hover_margin(self):
        return self._hover_margin

    def hover_interval(self):
        return self._hover_interval

    def hover_hide_enabled(self):
        return self._hover_hide

    # ==================================================================
    #  材质（毛玻璃 / 亚克力）
    # ==================================================================
    def _glass_bg(self):
        style = self._glass_style
        alpha = 0.5 if self._material == "acrylic" else 0.72
        if style == "dark":
            return "rgba(30, 30, 40, %s)" % alpha
        if style == "light":
            return "rgba(255, 255, 255, %s)" % alpha
        if style == "custom":
            c = QColor(self._glass_custom or "#1E202D")
            return "rgba(%d, %d, %d, %s)" % (c.red(), c.green(), c.blue(), alpha)
        theme = QApplication.instance().property("__theme") or "dark"
        if theme == "light":
            return "rgba(255, 255, 255, %s)" % alpha
        return "rgba(30, 30, 40, %s)" % alpha

    def _corner_radius(self):
        if self._shape == "capsule":
            return max(0, self.height() // 2)
        return 0

    def _apply_glass_bg(self):
        if hasattr(self, "bg_frame"):
            self.bg_frame.setStyleSheet(
                "background-color: %s; border: none; border-radius: %dpx;"
                % (self._glass_bg(), self._corner_radius()))

    def _apply_material(self):
        """应用当前材质：Linux 下不支持毛玻璃/亚克力，使用半透明背景。"""
        if not hasattr(self, "bg_frame"):
            return

        # Linux 下禁用模糊效果，使用纯色半透明背景
        if IS_LINUX:
            if self._blur_effect is not None:
                self._blur_effect.setEnabled(False)
            self._apply_glass_bg()
            return

        if self._material == "acrylic":
            if self._blur_effect is not None:
                self._blur_effect.setEnabled(False)
            enable_acrylic(self, theme_colors()["acrylic_abgr"])
        else:
            if self._blur_effect is not None:
                self._blur_effect.setEnabled(True)
            disable_acrylic(self)
        self._apply_glass_bg()

    def set_glass_style(self, style, custom_hex=""):
        self._glass_style = style
        if custom_hex:
            self._glass_custom = custom_hex
        self._apply_glass_bg()

    def glass_style(self):
        return self._glass_style

    def material(self):
        return self._material

    def set_material(self, material):
        material = "acrylic" if material == "acrylic" else "frosted"
        if material != self._material:
            self._material = material
            self._apply_material()
            logger.info("灵动岛材质切换: %s", material)

    def shape(self):
        return self._shape

    def set_shape(self, shape):
        shape = "capsule" if shape == "capsule" else "rect"
        if shape != self._shape:
            self._shape = shape
            self._apply_glass_bg()
            logger.info("灵动岛形状切换: %s", shape)

    # ==================================================================
    #  屏幕适配（多显示器 / 热插拔）- Linux 兼容修复
    # ==================================================================
    def current_screen(self):
        screens = QGuiApplication.screens()
        if not screens:
            return None
        if 0 <= self._screen_index < len(screens):
            return screens[self._screen_index]
        return QGuiApplication.primaryScreen()

    def calculate_island_geometry(self):
        """
        计算灵动岛几何位置。
        Linux 修复：使用 geometry() 获取完整屏幕区域，正确处理顶部坐标。
        支持用户手动调整的位置偏移（_pos_x_offset, _pos_y_offset）。
        """
        screen = self.current_screen()
        if screen is None:
            return QRect(0, 0, s(1000), s(self.NAV_HEIGHT))

        # 使用 geometry() 获取完整屏幕区域
        screen_geom = screen.geometry()
        dpi = screen.logicalDotsPerInch()
        scale = dpi / 96.0
        height = int(self.NAV_HEIGHT * scale)

        if self._fullscreen:
            width = screen_geom.width()
            x = screen_geom.x()
        else:
            ratio = max(0.5, min(1.0, self._width_ratio))
            width = int(screen_geom.width() * ratio)
            x = screen_geom.x() + (screen_geom.width() - width) // 2

        # Linux 修复：正确处理顶部坐标
        y = screen_geom.y()
        if IS_LINUX:
            # 尝试使用 availableGeometry 的顶部位置（可能排除面板）
            avail_geom = screen.availableGeometry()
            if avail_geom.y() > screen_geom.y():
                y = avail_geom.y()
            # 确保 y 不为负数（Wayland 兼容）
            if y < 0:
                y = 0

        # 应用手动调整的位置偏移
        x += self._pos_x_offset
        y += self._pos_y_offset

        logger.debug(f"Island geometry: x={x}, y={y}, width={width}, height={height}")
        return QRect(x, y, width, height)

    def apply_geometry(self):
        self.setGeometry(self.calculate_island_geometry())
        self._apply_adaptive_visibility()

    def _apply_adaptive_visibility(self):
        if not hasattr(self, "content_widget"):
            return
        width = self.width()
        self.right_carousel.setVisible(width >= self.HIDE_WEATHER_WIDTH)
        self.course_panel.setVisible(width >= self.HIDE_COURSE_WIDTH)
        self._layout_warning_overlay()
        self.content_widget.layout().activate()
        self._recenter_time()
        self._fit_left_modules()
        self._update_course_elide()
        self._update_right_fit()
        self._reposition_progress()

    def _fit_left_modules(self):
        clock_left = self.center_group.x()
        if clock_left <= 0 or self.content_widget.width() <= 0:
            return
        fm = QFontMetricsF(make_font(FONT_MAIN))
        quote_max_w = int(fm.horizontalAdvance("一" * 21)) + s(4)
        gap = s(10)
        course_overhead = s(6) + s(8) + s(2)
        hitokoto_on = getattr(self, "hitokoto_label", None) is not None \
            and self.hitokoto_label.isVisible()
        if hitokoto_on and self.hitokoto_label._mode == "elide":
            reserved = min(quote_max_w, int((clock_left - gap) * 0.45))
            course_avail = clock_left - gap - gap - reserved - course_overhead
            if course_avail >= s(60) and reserved >= s(50):
                self._course_elide_avail = course_avail
                self._recenter_hitokoto()
                return
            self.hitokoto_label.hide()
            self._hitokoto_shown = False
        elif hitokoto_on:
            min_quote = s(60)
            course_avail = clock_left - gap - gap - min_quote - course_overhead
            if course_avail < s(60):
                course_avail = s(60)
            self._course_elide_avail = course_avail
            self._recenter_hitokoto()
            return
        self._course_elide_avail = clock_left - gap - course_overhead
        self._recenter_hitokoto()

    def _recenter_hitokoto(self):
        if not getattr(self, "_hitokoto_shown", False):
            return
        h = getattr(self, "hitokoto_label", None)
        if h is None or not h._full_text:
            return
        gap = s(10)
        course_right = self.course_panel.x() + self.course_panel.width()
        clock_left = self.center_group.x()
        avail = clock_left - gap - (course_right + gap)
        if avail < s(50):
            return
        self._position_hitokoto(course_right, avail)

    def _position_hitokoto(self, course_right, avail):
        h = self.hitokoto_label
        if avail < s(30):
            avail = s(30)
        if h._mode == "scroll" and h._natural_w > avail:
            w = avail
        else:
            w = min(h._natural_w, avail)
        h.setFixedSize(w, s(26))
        x = course_right + s(10) + (avail - w) // 2
        y = (self.content_widget.height() - h.height()) // 2
        h.move(x, y)
        h.show()
        if h._mode == "scroll":
            h.restart_scroll()
        else:
            h._update_elided()

    def _connect_screen_signals(self):
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
        self.time_label.set_text(now.strftime("%H:%M:%S"))
        self.date_label.setText("%02d-%02d %s" % (now.month, now.day, WEEKDAY_CN2[now.weekday()]))
        self._tick_course()

    # ==================================================================
    #  课程动态显示
    # ==================================================================
    def update_course(self):
        status = self.course_manager.current_status()
        old_status = self._cstatus.get("status") if self._cstatus else None
        self._cstatus = status
        if status.get("status") != old_status:
            logger.info("课程状态切换: %s -> %s（当前课=%s 下一节=%s 倒计时=%s秒）",
                        old_status, status.get("status"),
                        (status.get("current") or {}).get("name", "无"),
                        (status.get("next") or {}).get("name", "无"),
                        status.get("countdown", 0))

        colors = theme_colors()
        st = status.get("status")

        if status.get("empty"):
            self._set_course_text("今日无课程安排", dot=colors["success"],
                                  breathe=False, trigger_fade=True)
            self._set_progress(None)
            self._stop_carousel()
        elif st == "ended":
            self._set_course_text("今日课程已结束", dot=colors["text_secondary"],
                                  breathe=False, trigger_fade=True)
            self._set_progress(None)
            self._stop_carousel()
        elif st == "not_started":
            course = status.get("next") or {}
            text = "距上课 %s · %s" % (self._format_cd(status.get("countdown", 0)),
                                       course.get("name", ""))
            self._set_course_text(text, dot=colors["danger"], breathe=True, trigger_fade=True)
            self._set_progress(status.get("progress"))
            self._stop_carousel()
        elif st == "teaching":
            course = status.get("current") or {}
            name = course.get("name", "")
            teacher = course.get("teacher", "")
            who = "%s %s" % (name, teacher) if teacher else name
            text = "上课中 · %s · 剩 %s" % (who, self._format_cd(status.get("countdown", 0)))
            self._set_course_text(text, dot=colors["primary"], breathe=True, trigger_fade=True)
            self._set_progress(status.get("progress"))
            self._stop_carousel()
        elif st == "break":
            items = status.get("remaining") or []
            self._carousel_items = items
            self._carousel_index = 0
            self._set_progress(status.get("progress"))
            if not items:
                self._set_course_text("课间休息", dot=colors["text_secondary"],
                                      breathe=False, trigger_fade=True)
                self._stop_carousel()
            else:
                self._update_carousel_screen(trigger_fade=True)
                self._start_carousel()
        else:
            self._set_course_text("今日课程已结束", dot=colors["text_secondary"],
                                  breathe=False, trigger_fade=True)
            self._set_progress(None)
            self._stop_carousel()

    def _tick_course(self):
        if not hasattr(self, "_cstatus") or self._cstatus is None:
            return
        new = self.course_manager.current_status()
        old = self._cstatus
        if (new.get("status") != old.get("status")
                or new.get("empty") != old.get("empty")):
            self.update_course()
            return
        self._cstatus = new
        st = new.get("status")
        colors = theme_colors()
        if st == "teaching":
            course = new.get("current") or {}
            name = course.get("name", "")
            teacher = course.get("teacher", "")
            who = "%s %s" % (name, teacher) if teacher else name
            text = "上课中 · %s · 剩 %s" % (who, self._format_cd(new.get("countdown", 0)))
            self._set_course_text(text, dot=colors["primary"], breathe=True, trigger_fade=False)
            self._set_progress(new.get("progress"))
        elif st == "not_started":
            course = new.get("next") or {}
            text = "距上课 %s · %s" % (self._format_cd(new.get("countdown", 0)),
                                       course.get("name", ""))
            self._set_course_text(text, dot=colors["danger"], breathe=True, trigger_fade=False)
            self._set_progress(new.get("progress"))
        elif st == "break":
            self._set_progress(new.get("progress"))
            if self._carousel_index == 0 and self._carousel_items:
                self._update_carousel_screen(trigger_fade=False)

    @staticmethod
    def _format_cd(seconds):
        return CourseManager.format_countdown(seconds)

    def _set_progress(self, percent):
        if hasattr(self, "course_progress"):
            if percent is None:
                self.course_progress.hide()
            else:
                self.course_progress.set_progress(percent)
                self.course_progress.show()
                self._reposition_progress()

    def _reposition_progress(self):
        if not hasattr(self, "course_progress"):
            return
        self.course_progress.setGeometry(
            0, self.outer_frame.height() - s(self._progress_height),
            self.outer_frame.width(), s(self._progress_height))
        self.course_progress.raise_()

    def _set_course_text(self, text, dot, breathe, trigger_fade=False):
        self._course_full_text = text
        self.course_dot.setStyleSheet(
            "background: %s; border-radius: %dpx;" % (dot, s(3)))
        self._set_breathing(breathe)
        if trigger_fade and hasattr(self, "_course_fade"):
            self._course_fade.start()
        self._update_course_elide()

    def _update_course_elide(self):
        if not hasattr(self, "course_label"):
            return
        reserved = getattr(self, "_course_elide_avail", 0)
        avail = reserved or (self.center_group.x() - s(4))
        if avail <= 0:
            avail = s(200)
        fm = QFontMetricsF(self.course_label.font())
        elided = fm.elidedText(self._course_full_text, Qt.ElideRight, avail)
        self.course_label.setText(elided)
        self.course_label.updateGeometry()
        lay = self.content_widget.layout()
        lay.invalidate()
        lay.activate()
        self._recenter_hitokoto()

    # ------------------------------------------------------------------
    #  课间课程预告轮播
    # ------------------------------------------------------------------
    def _start_carousel(self):
        if len(self._carousel_items) <= 1:
            self._carousel_timer.stop()
            return
        self._restart_carousel_timer()

    def _stop_carousel(self):
        self._carousel_timer.stop()
        self._carousel_items = []
        self._carousel_index = 0

    def _restart_carousel_timer(self):
        if len(self._carousel_items) <= 1:
            self._carousel_timer.stop()
            return
        interval = 5000 if self._carousel_index == 0 else 3000
        self._carousel_timer.setInterval(interval)
        self._carousel_timer.start()

    def _on_carousel_tick(self):
        if not self._carousel_items:
            return
        self._carousel_index = (self._carousel_index + 1) % len(self._carousel_items)
        self._update_carousel_screen(trigger_fade=True)
        self._restart_carousel_timer()

    def _update_carousel_screen(self, trigger_fade):
        items = self._carousel_items
        if not items:
            return
        idx = self._carousel_index % len(items)
        course = items[idx]
        colors = theme_colors()
        if idx == 0:
            text = "下一节 · %s · 距上课 %s" % (
                course.get("name", ""),
                self._format_cd(self._cstatus.get("countdown", 0) if self._cstatus else 0))
            dot = colors["danger"]
            breathe = True
        else:
            text = "%s %s" % (course.get("name", ""), course.get("start", ""))
            dot = colors["text_secondary"]
            breathe = False
        self._set_course_text(text, dot=dot, breathe=breathe, trigger_fade=trigger_fade)

    # ==================================================================
    #  天气更新
    # ==================================================================
    def _on_weather(self, data):
        self._shake_anim.stop()
        self._warnings = data.get("warnings", []) or []
        self._weather_data = data
        self.right_carousel.set_weather(data)
        self.right_carousel.set_warnings(self._warnings)
        self._update_right_fit()
        logger.info("灵动岛天气更新: %s %s°C %s | 预警%d条",
                    data.get("city", "?"), data.get("temp", "?"),
                    data.get("text", "?"), len(self._warnings))

    def _on_weather_failed(self, info):
        self._weather_data = None
        self._warnings = []
        message = info.get("message", "网络异常")
        self.right_carousel.set_error(message)
        self.right_carousel.set_warnings([])
        self._update_right_fit()
        self._shake_anim.start()
        logger.warning("灵动岛天气错误: %s", message)

    # ==================================================================
    #  主题切换
    # ==================================================================
    def _on_theme_changed(self, theme_name):
        colors = theme_colors()
        self._apply_glass_bg()
        self._apply_material()
        self.date_label.setStyleSheet("color: %s;" % colors["text_secondary"])
        self.warning_label.setStyleSheet("color: %s;" % colors["danger"])
        self.warning_panel.setStyleSheet(
            "background-color: %s; border-radius: %dpx; border: none;"
            % (colors["warning_bg"], s(8)))
        self.course_label.setFont(make_font(FONT_MAIN, bold=False))
        self.date_label.setFont(make_font(FONT_MAIN))
        if hasattr(self, "right_carousel"):
            self.right_carousel.warning_label.setFont(make_font(FONT_MAIN, bold=True))
            self.right_carousel.warning_scroll.setFont(make_font(FONT_MAIN, bold=True))
            self._update_right_fit()
        if hasattr(self, "hitokoto_label"):
            self.hitokoto_label._apply_style()
            self.hitokoto_label._update_elided()
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
    #  显示 / 隐藏（顶部滑入滑出）- Linux 兼容修复
    # ==================================================================
    def slide_in(self):
        self.apply_geometry()
        screen = self.current_screen()
        if screen is None:
            self.show()
            self.raise_()
            return
        # 从 calculate_island_geometry() 获取正确的目标位置，
        # 而非依赖 self.pos()（Linux 下窗口管理器可能会覆盖位置）
        geom = self.calculate_island_geometry()
        target = QPoint(geom.x(), geom.y())
        if IS_LINUX:
            start = QPoint(target.x(), target.y() - s(10))
        else:
            start = QPoint(target.x(), target.y() - self.height() - s(2))

        self.move(start)
        self.setWindowOpacity(self._opacity)
        self.show()
        self.raise_()
        # Linux 下窗口管理器可能在 show() 后重新定位窗口，
        # 用 QTimer.singleShot 强制恢复到正确位置
        if IS_LINUX:
            QTimer.singleShot(0, lambda: self.move(target))
        self._sliding = True
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.finished.connect(self._on_slide_done)
        anim.start()
        logger.info("灵动岛滑入显示")

    def slide_out(self):
        screen = self.current_screen()
        if screen is None:
            self.hide()
            return
        geom = self.calculate_island_geometry()
        if IS_LINUX:
            end = QPoint(self.x(), geom.y() - s(10))
        else:
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
        logger.info("灵动岛滑出隐藏")

    def _on_slide_done(self):
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
        self._width_ratio = float(ratio)
        if self.isVisible():
            self.apply_geometry()

    def set_progress_height(self, height):
        self._progress_height = max(1, min(8, int(height)))
        if self.isVisible():
            self._reposition_progress()

    def progress_height(self):
        return self._progress_height

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
        """鼠标穿透：开启后整个灵动岛窗口对鼠标事件透明。"""
        self._pass_through = bool(enabled)
        for widget in self.findChildren(QWidget):
            widget.setAttribute(Qt.WA_TransparentForMouseEvents, self._pass_through)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self._pass_through)
        # Windows 下使用 WS_EX_TRANSPARENT
        if IS_WINDOWS:
            self._apply_click_through_windows()

    def is_pass_through(self):
        return self._pass_through

    # ------------------------------------------------------------------
    #  位置偏移 & 拖拽模式
    # ------------------------------------------------------------------
    def set_position_offset(self, x_offset, y_offset):
        """设置位置偏移量并立即生效。"""
        self._pos_x_offset = int(x_offset)
        self._pos_y_offset = int(y_offset)
        if self.isVisible():
            self.apply_geometry()

    def position_offset(self):
        """返回当前 (x_offset, y_offset)。"""
        return (self._pos_x_offset, self._pos_y_offset)

    def enter_drag_mode(self):
        """进入拖拽模式：允许鼠标拖动灵动岛。"""
        self._drag_mode = True
        self._drag_start = None
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        for widget in self.findChildren(QWidget):
            widget.setAttribute(Qt.WA_TransparentForMouseEvents, False)

    def exit_drag_mode(self):
        """退出拖拽模式：恢复正常状态。"""
        self._drag_mode = False
        self._drag_start = None
        if self._pass_through:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            for widget in self.findChildren(QWidget):
                widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def mousePressEvent(self, event):
        if self._drag_mode and event.button() == Qt.LeftButton:
            self._drag_start = event.globalPosition().toPoint() - self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_mode and self._drag_start is not None:
            new_pos = event.globalPosition().toPoint() - self._drag_start
            self.move(new_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_mode and event.button() == Qt.LeftButton:
            self._drag_start = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _apply_click_through_windows(self):
        """Windows 窗口级鼠标穿透。"""
        if not IS_WINDOWS:
            return
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
        self._apply_glass_bg()
        self._apply_adaptive_visibility()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_material()
        self.apply_geometry()
        if IS_WINDOWS:
            self._apply_click_through_windows()