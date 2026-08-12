# ==========================================================================
#  易课 EasyClass v1.0.0 | Silicon UI
#  icon_drawer.py  ——  矢量图标绘制模块
#  -------------------------------------------------------------------------
#  职责：
#   · 使用 QPainter 纯矢量绘制，无任何外部图片资源
#   · 托盘图标：绘制"易"字文字图标
#   · 天气图标：根据和风天气 icon code 分类绘制 晴/云/雨/雪/雾/雷电 等
# ==========================================================================

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPixmap, QFont, QPen, QBrush, QImage, QPainterPath

import os

# 应用图标文件（用户提供，位于项目根目录）
_APP_ICON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favicon.ico")


class IconDrawer:
    """矢量图标绘制工具类（全部为静态方法）。"""

    # 颜色常量
    SUN = QColor("#FFD166")
    RAIN = QColor("#4EA8FF")
    SNOW = QColor("#EAF2FF")
    BOLT = QColor("#FFD166")

    @staticmethod
    def _canvas(size):
        """创建透明背景画布。"""
        pixmap = QPixmap(int(size), int(size))
        pixmap.fill(Qt.transparent)
        return pixmap

    # ------------------------------------------------------------------
    #  应用图标（favicon.ico，圆角处理）
    # ------------------------------------------------------------------
    @staticmethod
    def _load_icon_pixmap(size):
        """加载 favicon.ico 并等比缩放到 size（失败返回 None）。"""
        try:
            img = QImage(_APP_ICON_PATH)
            if img.isNull():
                return None
            pm = QPixmap.fromImage(img)
            return pm.scaled(int(size), int(size), Qt.KeepAspectRatio,
                             Qt.SmoothTransformation)
        except Exception:
            return None

    @staticmethod
    def app_icon(size=64, radius=None):
        """圆角应用图标（QPixmap），用于托盘 / 窗口 / 设置页 / 关于页。"""
        pm = IconDrawer._load_icon_pixmap(size)
        if pm is None:
            return None
        if radius is None:
            radius = max(1, int(size * 0.22))
        canvas = QPixmap(pm.size())
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, pm.width(), pm.height()), radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pm)
        painter.end()
        return canvas

    @staticmethod
    def app_icon_round(size=64):
        """圆形应用图标（QPixmap），用于托盘。"""
        pm = IconDrawer._load_icon_pixmap(size)
        if pm is None:
            return None
        canvas = QPixmap(pm.size())
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, pm.width(), pm.height())
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pm)
        painter.end()
        return canvas

    @staticmethod
    def app_icon_qicon(size=64, radius=None):
        """圆角应用图标（QIcon）。"""
        pm = IconDrawer.app_icon(size=size, radius=radius)
        if pm is None:
            return None
        from PySide6.QtGui import QIcon
        return QIcon(pm)

    # ------------------------------------------------------------------
    #  托盘文字图标："易"
    # ------------------------------------------------------------------
    @staticmethod
    def text_icon(text, size, color="#F0F0F5"):
        """绘制居中的纯文字图标（用于系统托盘）。"""
        pixmap = IconDrawer._canvas(size)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        font = QFont("Microsoft YaHei UI", int(size * 0.52))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(color))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
        painter.end()
        return pixmap

    # ------------------------------------------------------------------
    #  天气图标入口
    # ------------------------------------------------------------------
    @staticmethod
    def weather_icon(code, size, fg="#F0F0F5"):
        """
        根据和风天气 icon code 返回对应的天气矢量图标。
        code: 和风天气图标编号（字符串或整数）
        size: 图标边长（像素，建议传入已缩放的数值）
        fg:   前景描边/云朵颜色（跟随主题）
        """
        try:
            code = int(code)
        except (TypeError, ValueError):
            code = 999

        cloud = QColor(fg)
        pixmap = IconDrawer._canvas(size)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        s = size

        # 白天/夜晚统一处理（夜间用同款云图标 + 半透明月亮可忽略）
        if code == 100 or 150 <= code <= 154:
            IconDrawer._paint_sun(painter, s)
        elif 101 <= code <= 103:
            IconDrawer._paint_partly(painter, s, cloud)
        elif code == 104:
            IconDrawer._paint_cloud(painter, s, cloud)
        elif 300 <= code <= 399:
            IconDrawer._paint_rain(painter, s, cloud)
        elif 400 <= code <= 499:
            IconDrawer._paint_snow(painter, s, cloud)
        elif 500 <= code <= 599:
            IconDrawer._paint_fog(painter, s, cloud)
        elif code == 900:
            IconDrawer._paint_hot(painter, s)
        elif code == 901:
            IconDrawer._paint_cold(painter, s)
        else:
            IconDrawer._paint_unknown(painter, s, cloud)

        painter.end()
        return pixmap

    # ------------------------------------------------------------------
    #  内部绘制方法
    # ------------------------------------------------------------------

    @staticmethod
    def _paint_sun(painter, size):
        """晴天：太阳 + 光芒。"""
        center = QPointF(size * 0.5, size * 0.5)
        r = size * 0.18
        # 光芒
        pen = QPen(IconDrawer.SUN, max(2, size * 0.05))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        for i in range(8):
            angle = i * 45
            outer = size * 0.34
            inner = size * 0.24
            p1 = QPointF(center.x() + inner * _cos(angle), center.y() + inner * _sin(angle))
            p2 = QPointF(center.x() + outer * _cos(angle), center.y() + outer * _sin(angle))
            painter.drawLine(p1, p2)
        # 太阳本体
        painter.setPen(Qt.NoPen)
        painter.setBrush(IconDrawer.SUN)
        painter.drawEllipse(center, r, r)

    @staticmethod
    def _paint_cloud(painter, size, color):
        """阴天：云朵。"""
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        cx, cy = size * 0.5, size * 0.52
        painter.drawEllipse(QPointF(cx - size * 0.14, cy - size * 0.02), size * 0.14, size * 0.14)
        painter.drawEllipse(QPointF(cx + size * 0.12, cy - size * 0.03), size * 0.17, size * 0.17)
        painter.drawEllipse(QPointF(cx + size * 0.00, cy - size * 0.13), size * 0.20, size * 0.20)
        painter.drawEllipse(QPointF(cx + size * 0.02, cy - size * 0.02), size * 0.26, size * 0.26)

    @staticmethod
    def _paint_partly(painter, size, color):
        """多云：太阳露出 + 云朵。"""
        # 云（右前）
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        cx, cy = size * 0.58, size * 0.54
        painter.drawEllipse(QPointF(cx - size * 0.12, cy - size * 0.02), size * 0.13, size * 0.13)
        painter.drawEllipse(QPointF(cx + size * 0.10, cy - size * 0.04), size * 0.16, size * 0.16)
        painter.drawEllipse(QPointF(cx + size * 0.00, cy - size * 0.12), size * 0.18, size * 0.18)
        painter.drawEllipse(QPointF(cx + size * 0.02, cy - size * 0.02), size * 0.24, size * 0.24)
        # 太阳（左上，被云遮住一部分）
        painter.setBrush(IconDrawer.SUN)
        painter.drawEllipse(QPointF(size * 0.30, size * 0.32), size * 0.13, size * 0.13)

    @staticmethod
    def _paint_rain(painter, size, color):
        """雨天：云 + 雨滴。"""
        IconDrawer._paint_cloud(painter, size * 0.72, color)
        painter.setPen(Qt.NoPen)
        painter.setBrush(IconDrawer.RAIN)
        painter.save()
        painter.translate(size * 0.14, size * 0.72)
        for i, dx in enumerate((-0.08, 0.04, 0.16)):
            painter.drawRoundedRect(
                QRectF(dx * size, 0, size * 0.055, size * 0.10),
                size * 0.02, size * 0.02,
            )
        painter.restore()

    @staticmethod
    def _paint_snow(painter, size, color):
        """雪天：云 + 雪花。"""
        IconDrawer._paint_cloud(painter, size * 0.72, color)
        painter.setPen(Qt.NoPen)
        painter.setBrush(IconDrawer.SNOW)
        painter.save()
        painter.translate(size * 0.14, size * 0.72)
        for i, (dx, r) in enumerate(((-0.07, 0.035), (0.04, 0.045), (0.15, 0.035))):
            painter.drawEllipse(QPointF(dx * size, 0), r * size, r * size)
        painter.restore()

    @staticmethod
    def _paint_fog(painter, size, color):
        """雾天：云 + 下方雾线。"""
        IconDrawer._paint_cloud(painter, size * 0.7, color)
        pen = QPen(QColor(color), max(2, size * 0.045))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        y0 = size * 0.62
        for i, width in enumerate((0.34, 0.48, 0.30)):
            painter.drawLine(
                QPointF(size * (0.5 - width / 2), y0 + i * size * 0.08),
                QPointF(size * (0.5 + width / 2), y0 + i * size * 0.08),
            )

    @staticmethod
    def _paint_hot(painter, size):
        """炎热：太阳 + 波浪热浪。"""
        IconDrawer._paint_sun(painter, size * 0.8)
        pen = QPen(IconDrawer.SUN, max(2, size * 0.04))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        y0 = size * 0.62
        for i, amplitude in enumerate((0.06, 0.10)):
            y = y0 + i * size * 0.09
            painter.drawArc(
                QRectF(size * 0.30, y - amplitude * size, size * 0.40, 2 * amplitude * size),
                0, 180 * 16,
            )

    @staticmethod
    def _paint_cold(painter, size):
        """寒冷：六瓣雪花。"""
        center = QPointF(size * 0.5, size * 0.5)
        r = size * 0.24
        pen = QPen(IconDrawer.SNOW, max(2, size * 0.045))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for i in range(6):
            angle = i * 60
            p1 = QPointF(center.x() + r * _cos(angle), center.y() + r * _sin(angle))
            painter.drawLine(center, p1)
            # 短分支
            for branch in (30, -30):
                a = angle + branch
                p2 = QPointF(
                    center.x() + r * 0.55 * _cos(angle) + r * 0.22 * _cos(a),
                    center.y() + r * 0.55 * _sin(angle) + r * 0.22 * _sin(a),
                )
                painter.drawLine(
                    QPointF(center.x() + r * 0.55 * _cos(angle), center.y() + r * 0.55 * _sin(angle)),
                    p2,
                )

    @staticmethod
    def _paint_unknown(painter, size, color):
        """未知天气：云 + 问号。"""
        IconDrawer._paint_cloud(painter, size * 0.78, color)
        painter.setPen(QColor(color))
        font = QFont("Microsoft YaHei UI", int(size * 0.30))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            QRectF(size * 0.18, size * 0.56, size * 0.64, size * 0.36),
            Qt.AlignCenter, "?",
        )


# 三角函数小工具（避免反复 import math 的写法）
import math  # noqa: E402


def _sin(degrees):
    return math.sin(math.radians(degrees))


def _cos(degrees):
    return math.cos(math.radians(degrees))
