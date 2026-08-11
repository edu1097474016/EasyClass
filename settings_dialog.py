# ==========================================================================
#  易课 EasyClass v1.0.0 | Silicon UI
#  settings_dialog.py  ——  对话框模块（设置 / 课程表编辑 / 弹窗 / Toast）
#  -------------------------------------------------------------------------
#  职责：
#   · GlassDialog：半透明遮罩 + 居中卡片 + 弹出缩放动画（OutBack 0.3s）的基类
#   · PasswordDialog：密码验证（错误时抖动动画，默认密码 admin123）
#   · AddCourseDialog：添加/编辑课程表单
#   · ScheduleEditor：七天后 Tab 的课程表编辑器
#   · SettingsDialog：主题 / 透明度 / 天气 / 密码等设置
#   · Toast：底部滑入滑出的轻提示（成功绿色 / 失败红色）
# ==========================================================================

from copy import deepcopy

from PySide6.QtCore import (
    Qt, QRect, QPoint, QTime, Signal,
    QPropertyAnimation, QEasingCurve, QTimer,
)
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import (
    QDialog, QWidget, QLabel, QFrame, QPushButton, QLineEdit, QTimeEdit,
    QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QSlider,
    QScrollArea, QTabWidget, QGraphicsDropShadowEffect, QApplication,
)

import utils
from utils import s, make_font, make_shadow
from theme_manager import ThemeManager
from course_manager import CourseManager


def current_colors():
    """返回当前主题的动态颜色字典（供自绘组件使用）。"""
    theme = QApplication.instance().property("__theme") or "dark"
    return ThemeManager.COLORS.get(theme, ThemeManager.COLORS["dark"])


def _label(text, pt, bold=False, color=None, parent=None):
    """创建带指定磅值字体与颜色的 QLabel。"""
    lbl = QLabel(text, parent)
    lbl.setFont(make_font(pt, bold))
    if color:
        lbl.setStyleSheet("color: %s;" % color)
    return lbl


def _hrule(parent=None):
    """创建 1px 分隔线。"""
    line = QFrame(parent)
    line.setProperty("class", "separator")
    line.setFixedHeight(s(1))
    return line


# ==========================================================================
#  基类：半透明遮罩对话框
# ==========================================================================

class GlassDialog(QDialog):
    """
    模态对话框基类：
     - 覆盖整个主屏，背景绘制半透明遮罩（rgba(0,0,0,~0.5)）
     - 居中卡片（var(--bg-card) 毛玻璃质感 + 柔光阴影）
     - 弹出动画：卡片从中心放大淡入（OutBack，0.3秒）
    """

    def __init__(self, parent=None, card_size=(900, 650), dim_alpha=140, title=""):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)

        self._dim_alpha = dim_alpha
        self._animating = False
        screen = utils.screen_available(None)

        # 卡片尺寸（缩放后并限制不超过屏幕 92%）
        max_w = int(screen.width() * 0.92)
        max_h = int(screen.height() * 0.92)
        card_w = min(s(card_size[0]), max_w)
        card_h = min(s(card_size[1]), max_h)

        self.setGeometry(screen)

        self.card = QFrame(self)
        self.card.setObjectName("glassCard")
        self.card.setProperty("class", "card")
        self.card.setFixedSize(card_w, card_h)
        self.card.setAttribute(Qt.WA_StyledBackground, True)

        self._body = QVBoxLayout(self.card)
        self._body.setContentsMargins(s(28), s(20), s(28), s(20))
        self._body.setSpacing(s(12))

        if title:
            self._add_title_bar(title)

        make_shadow(self.card, QColor(0, 0, 0, 100), blur_radius=28)

    # ------------------------------------------------------------------
    #  布局辅助
    # ------------------------------------------------------------------
    def _add_title_bar(self, title):
        """添加标题栏：标题 + 右侧 ✕ 关闭按钮。"""
        bar = QHBoxLayout()
        bar.setSpacing(s(8))
        title_lbl = _label(title, 16, bold=True)
        bar.addWidget(title_lbl)
        bar.addStretch(1)
        close_btn = QPushButton("✕")
        close_btn.setProperty("class", "icon-btn")
        close_btn.setFixedSize(s(36), s(36))
        close_btn.setToolTip("关闭")
        close_btn.clicked.connect(self.reject)
        bar.addWidget(close_btn)
        self._body.addLayout(bar)
        self._body.addWidget(_hrule(self.card))

    def body_layout(self):
        return self._body

    def add_widget(self, widget):
        self._body.addWidget(widget)

    def add_layout(self, layout):
        self._body.addLayout(layout)

    def add_stretch(self, stretch=1):
        self._body.addStretch(stretch)

    # ------------------------------------------------------------------
    #  绘制遮罩
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, self._dim_alpha))

    # ------------------------------------------------------------------
    #  显示与弹出动画
    # ------------------------------------------------------------------
    def _center_rect(self):
        """计算卡片在主屏中的居中矩形。"""
        scr = utils.screen_available(None)
        x = scr.x() + (scr.width() - self.card.width()) // 2
        y = scr.y() + (scr.height() - self.card.height()) // 2
        return QRect(x, y, self.card.width(), self.card.height())

    def _play_pop_animation(self):
        """卡片弹出动画：由 88% 大小放大至 100%（OutBack 0.3s）。"""
        final = self._center_rect()
        self._animating = True
        start = QRect(
            final.center().x() - final.width() // 2,
            final.center().y() - final.height() // 2,
            int(final.width() * 0.88),
            int(final.height() * 0.88),
        )
        self.card.setGeometry(start)
        anim = QPropertyAnimation(self.card, b"geometry", self.card)
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.OutBack)
        anim.setStartValue(start)
        anim.setEndValue(final)
        anim.finished.connect(self._on_pop_finished)
        anim.start()

    def _on_pop_finished(self):
        self._animating = False

    def showEvent(self, event):
        super().showEvent(event)
        self._play_pop_animation()

    def resizeEvent(self, event):
        """窗口尺寸变化时保持卡片居中（仅在无弹出动画时执行）。"""
        super().resizeEvent(event)
        if not self._animating:
            self.card.setGeometry(self._center_rect())


# ==========================================================================
#  Toast 轻提示
# ==========================================================================

_toasts = []


class Toast(QWidget):
    """底部滑入滑出、2 秒自动消失的轻提示。"""

    def __init__(self, text, success=True, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        frame = QFrame(self)
        frame.setObjectName("toast")
        frame.setProperty("class", "toast")
        frame.setAttribute(Qt.WA_StyledBackground, True)
        make_shadow(frame, QColor(0, 0, 0, 110), blur_radius=20, offset=2)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(s(18), s(12), s(18), s(12))
        layout.setSpacing(s(10))

        colors = current_colors()
        accent = colors["success"] if success else colors["danger"]
        dot = QLabel("●")
        dot.setStyleSheet("color: %s;" % accent)
        dot.setFont(make_font(12, True))
        layout.addWidget(dot)

        msg = QLabel(text)
        msg.setFont(make_font(12))
        layout.addWidget(msg)

        self._frame = frame
        self.setFixedSize(frame.sizeHint().width() + s(4), frame.sizeHint().height() + s(4))
        self._position_bottom_center()

    def _position_bottom_center(self):
        scr = utils.screen_available(None)
        x = scr.x() + (scr.width() - self.width()) // 2
        y = scr.y() + scr.height() - self.height() - s(48)
        self.move(x, y)

    def animate_in(self):
        """底部滑入（InOutCubic 0.3s）。"""
        self.show()
        self.raise_()
        target = self.pos()
        start = QPoint(target.x(), target.y() + s(30))
        self.move(start)
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.setStartValue(start)
        anim.setEndValue(target)
        anim.start()
        QTimer.singleShot(2000, self.animate_out)

    def animate_out(self):
        """向下滑出后销毁（InOutCubic 0.3s）。"""
        if self.pos().y() > self.y() + s(40):
            return
        target = QPoint(self.x(), self.y() + s(30))
        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.setStartValue(self.pos())
        anim.setEndValue(target)
        anim.finished.connect(self._finish_out)
        anim.start()

    def _finish_out(self):
        if self in _toasts:
            _toasts.remove(self)
        self.deleteLater()


def show_toast(text, success=True, parent=None):
    """全局 Toast 提示入口。"""
    toast = Toast(text, success=success, parent=parent)
    _toasts.append(toast)
    toast.animate_in()


# ==========================================================================
#  密码验证对话框
# ==========================================================================

class PasswordDialog(GlassDialog):
    """编辑课程表前的密码验证，密码错误时卡片抖动。"""

    def __init__(self, password="admin123", parent=None):
        super().__init__(parent, card_size=(420, 320), dim_alpha=170, title="易课 ✦ 密码验证")
        self._password = password

        icon_lbl = _label("🔒", 40)
        icon_lbl.setAlignment(Qt.AlignCenter)
        self.add_widget(icon_lbl)

        hint = _label("请输入密码以编辑课程表", 14)
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: %s;" % current_colors()["text_secondary"])
        self.add_widget(hint)

        self.edit = QLineEdit(self.card)
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setPlaceholderText("请输入密码")
        self.edit.setFont(make_font(13))
        self.edit.setMinimumHeight(s(44))
        self.add_widget(self.edit)

        btns = QHBoxLayout()
        btns.setSpacing(s(12))
        ok_btn = QPushButton("确定")
        ok_btn.setProperty("class", "primary")
        ok_btn.setMinimumHeight(s(44))
        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumHeight(s(44))
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        self.add_layout(btns)

        ok_btn.clicked.connect(self._try_accept)
        cancel_btn.clicked.connect(self.reject)
        self.edit.returnPressed.connect(self._try_accept)
        self.edit.setFocus()

    def _try_accept(self):
        """校验密码：正确则接受，错误则抖动。"""
        if self.edit.text() == self._password:
            self.accept()
        else:
            self.edit.clear()
            self.edit.setFocus()
            self._shake()

    def _shake(self):
        """密码错误抖动动画（InOutCubic 0.4s，左右 ±14px）。"""
        start = self.card.pos()
        k = s(14)
        anim = QPropertyAnimation(self.card, b"pos", self.card)
        anim.setDuration(400)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.setKeyValueAt(0.00, start)
        anim.setKeyValueAt(0.25, start + QPoint(k, 0))
        anim.setKeyValueAt(0.50, start - QPoint(k, 0))
        anim.setKeyValueAt(0.75, start + QPoint(k // 2, 0))
        anim.setKeyValueAt(1.00, start)
        anim.start()


# ==========================================================================
#  添加/编辑课程对话框
# ==========================================================================

class AddCourseDialog(GlassDialog):
    """添加课程表单（弹出缩放淡入动画）。"""

    def __init__(self, parent=None, course=None, day_name="周一"):
        super().__init__(parent, card_size=(500, 480), dim_alpha=170,
                         title="易课 ✦ %s" % ("编辑课程" if course else "添加课程"))
        self._course = course or {}
        self._result = None

        info = _label("正在编辑：%s" % day_name, 12)
        info.setStyleSheet("color: %s;" % current_colors()["text_secondary"])
        self.add_widget(info)

        form = QFormLayout()
        form.setSpacing(s(12))
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.name_edit = self._make_edit(self._course.get("name", ""), "课程名称（必填）")
        self.teacher_edit = self._make_edit(self._course.get("teacher", ""), "教师姓名")
        self.room_edit = self._make_edit(self._course.get("room", ""), "教室编号")

        self.start_edit = QTimeEdit(self.card)
        self.start_edit.setDisplayFormat("HH:mm")
        self.start_edit.setTime(QTime.fromString(self._course.get("start", "08:00"), "HH:mm") or QTime(8, 0))
        self.end_edit = QTimeEdit(self.card)
        self.end_edit.setDisplayFormat("HH:mm")
        self.end_edit.setTime(QTime.fromString(self._course.get("end", "08:45"), "HH:mm") or QTime(8, 45))

        for label, widget in (
            ("课程名", self.name_edit), ("教师", self.teacher_edit),
            ("教室", self.room_edit), ("开始时间", self.start_edit),
            ("结束时间", self.end_edit),
        ):
            lbl = _label(label, 13)
            form.addRow(lbl, widget)

        self.add_layout(form)

        btns = QHBoxLayout()
        btns.setSpacing(s(12))
        ok_btn = QPushButton("确定")
        ok_btn.setProperty("class", "primary")
        ok_btn.setMinimumHeight(s(44))
        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumHeight(s(44))
        btns.addStretch(1)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        self.add_layout(btns)

        ok_btn.clicked.connect(self._confirm)
        cancel_btn.clicked.connect(self.reject)

    def _make_edit(self, value, placeholder):
        edit = QLineEdit(self.card)
        edit.setText(value)
        edit.setPlaceholderText(placeholder)
        edit.setFont(make_font(13))
        edit.setMinimumHeight(s(40))
        return edit

    def _confirm(self):
        """校验并生成课程数据。"""
        name = self.name_edit.text().strip()
        start = self.start_edit.time().toString("HH:mm")
        end = self.end_edit.time().toString("HH:mm")
        if not name:
            show_toast("课程名不能为空", success=False)
            return
        start_min = CourseManager._to_minutes(start)
        end_min = CourseManager._to_minutes(end)
        if start_min >= end_min:
            show_toast("结束时间必须晚于开始时间", success=False)
            return
        self._result = {
            "start": start,
            "end": end,
            "name": name,
            "teacher": self.teacher_edit.text().strip(),
            "room": self.room_edit.text().strip(),
        }
        self.accept()

    def course(self):
        return self._result


# ==========================================================================
#  课程卡片
# ==========================================================================

class CourseCard(QFrame):
    """编辑器中的单条课程卡片。"""

    delete_requested = Signal(int)
    edit_requested = Signal(int)

    def __init__(self, index, course, parent=None):
        super().__init__(parent)
        self.index = index
        self.course = course
        self.setProperty("class", "course-card")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(s(16), s(12), s(16), s(12))
        layout.setSpacing(s(6))

        # 第一行：课程名 + 删除按钮
        row1 = QHBoxLayout()
        name_lbl = _label(course.get("name", "未命名课程"), 17, bold=True)
        row1.addWidget(name_lbl)
        row1.addStretch(1)
        del_btn = QPushButton("✕")
        del_btn.setProperty("class", "delete-btn")
        del_btn.setFixedSize(s(26), s(26))
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setToolTip("删除该课程")
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self.index))
        row1.addWidget(del_btn)
        layout.addLayout(row1)

        # 第二行：节次 + 时间
        start = course.get("start", "??:??")
        end = course.get("end", "??:??")
        time_lbl = _label("第 %d 节  ·  %s - %s" % (index + 1, start, end), 13)
        time_lbl.setStyleSheet("color: %s;" % current_colors()["text_secondary"])
        layout.addWidget(time_lbl)

        # 第三行：教师 + 教室
        row3 = QHBoxLayout()
        teacher = course.get("teacher", "")
        room = course.get("room", "")
        if teacher:
            t_lbl = _label("教师：%s" % teacher, 14)
            t_lbl.setStyleSheet("color: %s;" % current_colors()["primary"])
            row3.addWidget(t_lbl)
        if room:
            r_lbl = _label("教室：%s" % room, 14)
            r_lbl.setStyleSheet("color: %s;" % current_colors()["text_secondary"])
            row3.addWidget(r_lbl)
        row3.addStretch(1)
        layout.addLayout(row3)

    def mouseDoubleClickEvent(self, event):
        self.edit_requested.emit(self.index)
        super().mouseDoubleClickEvent(event)


# ==========================================================================
#  虚线"添加课程"按钮（QPainter 自绘）
# ==========================================================================

class DashedAddButton(QPushButton):
    """虚线边框的添加按钮。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("+ 添加课程")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(s(56))
        self.setAttribute(Qt.WA_Hover, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        colors = current_colors()
        rect = self.rect().adjusted(1, 1, -1, -1)

        if self.underMouse():
            fill = QColor(colors["primary"])
            fill.setAlpha(40)
            painter.setBrush(fill)
        else:
            painter.setBrush(Qt.NoBrush)

        pen = QPen(QColor(colors["primary"]))
        pen.setStyle(Qt.DashLine)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, 8, 8)

        painter.setPen(QColor(colors["text_main"]))
        font = make_font(14, bold=False)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())
        painter.end()


# ==========================================================================
#  课程表编辑器
# ==========================================================================

class ScheduleEditor(GlassDialog):
    """七天后 Tab 的课程表编辑器（模态）。"""

    def __init__(self, manager, parent=None):
        super().__init__(parent, card_size=(900, 650), dim_alpha=120,
                         title="易课 ✦ 编辑课程表")
        self.manager = manager
        # 工作副本：未保存前不写入 manager
        self.working = deepcopy(manager.data)

        self._tabs = []
        self._layouts = []
        self._add_buttons = []
        self._pending_anim_index = None

        # 顶部：Tab 胶囊样式
        self.tabs = QTabWidget(self.card)
        for day_name in manager.DAY_NAMES:
            page = QWidget(self.tabs)
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, s(8), 0, 0)
            page_layout.setSpacing(0)

            scroll = QScrollArea(page)
            scroll.setWidgetResizable(True)
            container = QWidget(scroll)
            container.setObjectName("courseContainer")
            list_layout = QVBoxLayout(container)
            list_layout.setContentsMargins(s(6), s(6), s(6), s(6))
            list_layout.setSpacing(s(4))
            scroll.setWidget(container)

            page_layout.addWidget(scroll)
            self.tabs.addTab(page, day_name)

            self._tabs.append(page)
            self._layouts.append(list_layout)
            add_btn = DashedAddButton(container)
            add_btn.clicked.connect(lambda _=False, d=len(self._layouts) - 1: self._on_add_course(d))
            self._add_buttons.append(add_btn)
            list_layout.addWidget(add_btn)
            list_layout.addStretch(1)

        self.add_widget(self.tabs)

        # 底部：保存 / 取消 / 清空当天
        btns = QHBoxLayout()
        btns.setSpacing(s(12))
        save_btn = QPushButton("保存")
        save_btn.setProperty("class", "primary")
        save_btn.setMinimumHeight(s(44))
        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumHeight(s(44))
        clear_btn = QPushButton("清空当天")
        clear_btn.setProperty("class", "danger")
        clear_btn.setMinimumHeight(s(44))
        btns.addWidget(save_btn)
        btns.addWidget(cancel_btn)
        btns.addStretch(1)
        btns.addWidget(clear_btn)
        self.add_layout(btns)

        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)
        clear_btn.clicked.connect(self._clear_current_day)

        self._rebuild_all()

    # ------------------------------------------------------------------
    #  数据与卡片重建
    # ------------------------------------------------------------------
    def _day_key(self, day_index):
        return self.manager.DAY_KEYS[day_index]

    def _rebuild_all(self):
        for day in range(7):
            self._rebuild_day(day)

    def _rebuild_day(self, day_index):
        """重建某一天的课程卡片列表。"""
        layout = self._layouts[day_index]
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget and widget is not self._add_buttons[day_index]:
                widget.deleteLater()

        key = self._day_key(day_index)
        courses = sorted(self.working.get(key, []),
                         key=lambda c: CourseManager._to_minutes(c.get("start", "00:00")))
        for i, course in enumerate(courses):
            card = CourseCard(i, course, self._tabs[day_index])
            card.delete_requested.connect(
                lambda idx, d=day_index: self._on_delete_course(d, idx))
            card.edit_requested.connect(
                lambda idx, d=day_index: self._on_edit_course(d, idx))
            layout.addWidget(card)
            if self._pending_anim_index == i:
                self._animate_card_in(card)
        layout.addWidget(self._add_buttons[day_index])
        layout.addStretch(1)
        self._pending_anim_index = None

    # ------------------------------------------------------------------
    #  动画
    # ------------------------------------------------------------------
    def _animate_card_in(self, card):
        """新卡片展开动画（InOutCubic 0.3s）。"""
        target = card.sizeHint().height()
        card.setMaximumHeight(0)
        anim = QPropertyAnimation(card, b"maximumHeight", card)
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.setStartValue(0)
        anim.setEndValue(target)
        anim.start()

    def _animate_card_out(self, card, on_done):
        """卡片收起动画（InOutCubic 0.3s），结束后回调。"""
        anim = QPropertyAnimation(card, b"maximumHeight", card)
        anim.setDuration(300)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.setStartValue(card.height())
        anim.setEndValue(0)
        anim.finished.connect(on_done)
        anim.start()

    # ------------------------------------------------------------------
    #  交互
    # ------------------------------------------------------------------
    def _on_add_course(self, day_index):
        day_name = self.manager.DAY_NAMES[day_index]
        dialog = AddCourseDialog(self, course=None, day_name=day_name)
        if dialog.exec() == QDialog.Accepted:
            course = dialog.course()
            if course is None:
                return
            key = self._day_key(day_index)
            self.working[key].append(course)
            self.working[key].sort(
                key=lambda c: CourseManager._to_minutes(c.get("start", "00:00")))
            self._pending_anim_index = self.working[key].index(course)
            self._rebuild_day(day_index)
            show_toast("已添加课程：%s" % course["name"])

    def _on_edit_course(self, day_index, index):
        key = self._day_key(day_index)
        courses = sorted(self.working.get(key, []),
                         key=lambda c: CourseManager._to_minutes(c.get("start", "00:00")))
        if not (0 <= index < len(courses)):
            return
        dialog = AddCourseDialog(self, course=courses[index],
                                 day_name=self.manager.DAY_NAMES[day_index])
        if dialog.exec() == QDialog.Accepted:
            updated = dialog.course()
            if updated is None:
                return
            # 更新（保持列表顺序）
            sorted_courses = sorted(
                self.working[key],
                key=lambda c: CourseManager._to_minutes(c.get("start", "00:00")))
            target = sorted_courses[index]
            for i, c in enumerate(self.working[key]):
                if c is target:
                    self.working[key][i] = updated
                    break
            self._rebuild_day(day_index)
            show_toast("已更新课程")

    def _on_delete_course(self, day_index, index):
        """删除课程：先收起卡片动画，再移除数据。"""
        layout = self._layouts[day_index]
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if isinstance(widget, CourseCard) and widget.index == index:
                self._animate_card_out(widget, lambda: self._do_delete(day_index, index))
                return
        self._do_delete(day_index, index)

    def _do_delete(self, day_index, index):
        key = self._day_key(day_index)
        sorted_courses = sorted(
            self.working[key],
            key=lambda c: CourseManager._to_minutes(c.get("start", "00:00")))
        if 0 <= index < len(sorted_courses):
            target = sorted_courses[index]
            self.working[key].remove(target)
            self._rebuild_day(day_index)
            show_toast("已删除课程", success=False)

    def _clear_current_day(self):
        day = self.tabs.currentIndex()
        key = self._day_key(day)
        if not self.working.get(key):
            show_toast("当天没有课程", success=False)
            return
        self.working[key] = []
        self._rebuild_day(day)
        show_toast("已清空 %s" % self.manager.DAY_NAMES[day], success=False)

    # ------------------------------------------------------------------
    #  保存
    # ------------------------------------------------------------------
    def _save(self):
        self.manager.data = self.working
        self.manager.save()
        show_toast("课程表已保存")
        self.accept()


# ==========================================================================
#  设置对话框
# ==========================================================================

class SettingsDialog(GlassDialog):
    """设置窗口：主题 / 透明度 / 天气 / 密码 / 岛宽度。"""

    def __init__(self, config, theme_manager, island, weather_manager, parent=None):
        super().__init__(parent, card_size=(560, 640), dim_alpha=120,
                         title="易课 ✦ 设置")
        self.config = config
        self.theme_manager = theme_manager
        self.island = island
        self.weather_manager = weather_manager
        colors = current_colors()

        # ---- 主题 ----
        theme_row = QHBoxLayout()
        theme_row.addWidget(_label("主题模式", 14, bold=True))
        theme_row.addStretch(1)
        self.theme_switch = utils.ToggleSwitch(self.card)
        self.theme_switch.set_checked_animated(theme_manager.current_theme == theme_manager.LIGHT)
        self.theme_state = _label(self._theme_text(), 13)
        self.theme_state.setStyleSheet("color: %s;" % colors["text_secondary"])
        theme_row.addWidget(self.theme_state)
        theme_row.addWidget(self.theme_switch)
        self.add_layout(theme_row)
        self.theme_switch.toggled.connect(self._on_theme_toggled)
        self.add_widget(_hrule(self.card))

        # ---- 透明度 ----
        self.opacity_slider = QSlider(Qt.Horizontal, self.card)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(int(float(self.config.get("opacity", 0.65)) * 100))
        self.opacity_value = _label("%d%%" % self.opacity_slider.value(), 13)
        self.opacity_value.setStyleSheet("color: %s;" % colors["text_secondary"])
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(_label("窗口透明度", 14, bold=True))
        opacity_row.addStretch(1)
        opacity_row.addWidget(self.opacity_value)
        self.add_layout(opacity_row)
        self.add_widget(self.opacity_slider)
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_value.setText("%d%%" % v))
        self.add_widget(_hrule(self.card))

        # ---- 岛宽度 ----
        self.width_slider = QSlider(Qt.Horizontal, self.card)
        self.width_slider.setRange(50, 95)
        self.width_slider.setValue(int(float(self.config.get("island_width_ratio", 0.85)) * 100))
        self.width_value = _label("%d%%" % self.width_slider.value(), 13)
        self.width_value.setStyleSheet("color: %s;" % colors["text_secondary"])
        width_row = QHBoxLayout()
        width_row.addWidget(_label("灵动岛宽度", 14, bold=True))
        width_row.addStretch(1)
        width_row.addWidget(self.width_value)
        self.add_layout(width_row)
        self.add_widget(self.width_slider)
        self.width_slider.valueChanged.connect(
            lambda v: self.width_value.setText("%d%%" % v))
        self.add_widget(_hrule(self.card))

        # ---- 天气 ----
        self.add_widget(_label("天气设置（和风天气）", 14, bold=True))
        grid = QGridLayout()
        grid.setSpacing(s(10))
        grid.addWidget(_label("城市", 13), 0, 0)
        self.city_edit = QLineEdit(self.card)
        self.city_edit.setText(self.config.get("weather_city", "北京"))
        grid.addWidget(self.city_edit, 0, 1)
        grid.addWidget(_label("API Key", 13), 1, 0)
        self.key_edit = QLineEdit(self.card)
        self.key_edit.setText(self.config.get("weather_api_key", ""))
        self.key_edit.setEchoMode(QLineEdit.Password)
        grid.addWidget(self.key_edit, 1, 1)
        self.add_layout(grid)

        hint = _label("免费申请：dev.qweather.com → 控制台 → 项目 Key", 11)
        hint.setStyleSheet("color: %s;" % colors["text_secondary"])
        self.add_widget(hint)
        self.add_widget(_hrule(self.card))

        # ---- 编辑密码 ----
        pass_row = QHBoxLayout()
        pass_row.addWidget(_label("编辑密码", 14, bold=True))
        self.pass_edit = QLineEdit(self.card)
        self.pass_edit.setText(self.config.get("password", "admin123"))
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.pass_edit.setMinimumHeight(s(40))
        pass_row.addStretch(1)
        pass_row.addWidget(self.pass_edit, 1)
        self.add_layout(pass_row)
        self.add_widget(_hrule(self.card))

        # ---- 底部按钮 ----
        btns = QHBoxLayout()
        btns.setSpacing(s(12))
        save_btn = QPushButton("保存")
        save_btn.setProperty("class", "primary")
        save_btn.setMinimumHeight(s(44))
        cancel_btn = QPushButton("取消")
        cancel_btn.setMinimumHeight(s(44))
        btns.addWidget(save_btn)
        btns.addWidget(cancel_btn)
        btns.addStretch(1)
        self.add_layout(btns)

        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)

    def _theme_text(self):
        return "浅色模式" if self.theme_manager.current_theme == self.theme_manager.LIGHT else "深色模式"

    def _on_theme_toggled(self, checked):
        self.theme_state.setText("浅色模式" if checked else "深色模式")
        self.theme_state.setStyleSheet(
            "color: %s;" % current_colors()["text_secondary"])

    def _save(self):
        """保存设置并即时生效。"""
        cfg = self.config

        # 主题
        want_light = self.theme_switch.isChecked()
        if want_light and self.theme_manager.current_theme == self.theme_manager.DARK:
            self.theme_manager.set_light_theme()
        elif not want_light and self.theme_manager.current_theme == self.theme_manager.LIGHT:
            self.theme_manager.set_dark_theme()

        # 透明度
        opacity = self.opacity_slider.value() / 100.0
        cfg["opacity"] = opacity
        if self.island is not None:
            self.island.set_window_opacity(opacity)

        # 岛宽度
        ratio = self.width_slider.value() / 100.0
        cfg["island_width_ratio"] = ratio
        if self.island is not None:
            self.island.set_width_ratio(ratio)

        # 天气
        cfg["weather_city"] = self.city_edit.text().strip() or "北京"
        cfg["weather_api_key"] = self.key_edit.text().strip()

        # 密码
        cfg["password"] = self.pass_edit.text().strip() or "admin123"

        utils.save_config(cfg)
        self.weather_manager.update_config(cfg)
        show_toast("设置已保存")
        self.accept()


# ==========================================================================
#  编辑器入口（带密码验证）
# ==========================================================================

def open_schedule_editor(parent, manager, config):
    """双击灵动岛 / Ctrl+E 调用的入口：先密码验证，再打开编辑器。"""
    password = config.get("password", "admin123")
    password_dialog = PasswordDialog(password, parent=None)
    if password_dialog.exec() == QDialog.Accepted:
        editor = ScheduleEditor(manager, parent=None)
        editor.exec()

