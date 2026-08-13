# ==========================================================================
#  易课 EasyClass v1.0.0 | Silicon UI
#  tray_icon.py  ——  系统托盘模块
#  -------------------------------------------------------------------------
#  职责：
#   · "易"字托盘图标（QPainter 绘制）+ 悬浮提示
#   · 右键菜单：显示/隐藏、编辑课程表、全屏/窗口、主题、透明度、
#               显示器切换、鼠标穿透、刷新天气、设置、关于、退出
#   · 左键单击：显示/隐藏灵动岛（滑入滑出动画）
# ==========================================================================

import logging

from PySide6.QtCore import Qt, QObject
from PySide6.QtGui import QIcon, QGuiApplication, QAction
from PySide6.QtWidgets import (
    QSystemTrayIcon, QMenu, QMessageBox,
)

import utils
from utils import APP_NAME, APP_VERSION, APP_TAG
from icon_drawer import IconDrawer
from settings_dialog import show_toast

logger = logging.getLogger(__name__)


class TrayIcon(QSystemTrayIcon):
    """系统托盘图标与菜单。"""

    def __init__(self, island, theme_manager, weather_manager, config,
                 callbacks, parent=None):
        super().__init__(parent)
        self.island = island
        self.theme = theme_manager
        self.weather = weather_manager
        self.config = config
        self.callbacks = callbacks

        self.setToolTip("易课 - 教室信息看板")
        self._apply_icon()
        self.theme.theme_changed.connect(lambda _t: self._apply_icon())

        # 右键菜单（每次弹出时重建动态项）
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self._build_menu)
        self.setContextMenu(self.menu)   # 修复：未绑定上下文菜单导致右键无反应

        # 左键单击：显示/隐藏主窗口
        self.activated.connect(self._on_activated)

    # ------------------------------------------------------------------
    def _apply_icon(self):
        # 托盘图标：圆角方形
        pixmap = IconDrawer.app_icon(64)
        if pixmap is None:
            color = self.theme.color("text_main")
            pixmap = IconDrawer.text_icon("易", 64, color=color)
        self.setIcon(QIcon(pixmap))

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.island.toggle_visible()

    # ------------------------------------------------------------------
    def _build_menu(self):
        menu = self.menu
        menu.clear()

        # 显示/隐藏主窗口
        show_act = QAction(
            "隐藏主窗口" if self.island.isVisible() else "显示主窗口", menu)
        show_act.triggered.connect(
            lambda: self.island.slide_out() if self.island.isVisible() else self.island.slide_in())
        menu.addAction(show_act)

        # 编辑课程表
        edit_act = QAction("编辑课程表 (Ctrl+E)", menu)
        edit_act.triggered.connect(self.callbacks["open_editor"])
        menu.addAction(edit_act)

        menu.addSeparator()

        # 全屏/窗口模式
        fs_act = QAction("切换全屏/窗口模式", menu)
        fs_act.setCheckable(True)
        fs_act.setChecked(self.island.is_fullscreen())
        fs_act.triggered.connect(
            lambda checked: self.island.set_fullscreen(checked))
        menu.addAction(fs_act)

        # 鼠标穿透
        pt_act = QAction("鼠标穿透模式", menu)
        pt_act.setCheckable(True)
        pt_act.setChecked(self.island.is_pass_through())
        pt_act.triggered.connect(
            lambda checked: self.island.set_pass_through(checked))
        menu.addAction(pt_act)

        # 切换主题
        theme_text = ("切换到浅色主题" if self.theme.current_theme == self.theme.DARK
                      else "切换到深色主题")
        theme_act = QAction(theme_text, menu)
        theme_act.triggered.connect(self.theme.toggle_theme)
        menu.addAction(theme_act)

        # 设置透明度子菜单
        opacity_menu = menu.addMenu("设置透明度")
        current_opacity = float(self.config.get("opacity", 0.65))
        for value in (0.3, 0.5, 0.7, 0.9, 1.0):
            act = QAction("%d%%" % int(value * 100), opacity_menu)
            act.setCheckable(True)
            act.setChecked(abs(value - current_opacity) < 0.001)
            act.triggered.connect(
                lambda _=False, v=value: self._set_opacity(v))
            opacity_menu.addAction(act)

        # 切换显示器子菜单（多显示器时）
        screens = QGuiApplication.screens()
        if len(screens) > 1:
            screen_menu = menu.addMenu("切换显示器")
            self._build_screen_menu(screen_menu, screens)

        # 刷新天气
        refresh_act = QAction("刷新天气", menu)
        refresh_act.triggered.connect(self._refresh_weather)
        menu.addAction(refresh_act)

        # 设置
        settings_act = QAction("设置…", menu)
        settings_act.triggered.connect(self.callbacks["open_settings"])
        menu.addAction(settings_act)

        menu.addSeparator()

        about_act = QAction("关于", menu)
        about_act.triggered.connect(self._show_about)
        menu.addAction(about_act)

        quit_act = QAction("退出程序", menu)
        quit_act.triggered.connect(self._quit)
        menu.addAction(quit_act)

    def _build_screen_menu(self, screen_menu, screens):
        for index, screen in enumerate(screens):
            name = screen.name() or "显示器 %d" % (index + 1)
            geometry = screen.geometry()
            label = "%s (%dx%d)" % (name, geometry.width(), geometry.height())
            act = QAction(label, screen_menu)
            act.setCheckable(True)
            act.setChecked(index == self.island.screen_index())
            act.triggered.connect(
                lambda _=False, i=index: self.island.set_screen_index(i))
            screen_menu.addAction(act)

    # ------------------------------------------------------------------
    def _refresh_weather(self):
        """刷新天气并用 Toast 提示结果（成功/失败）。"""
        def once_ok(data):
            self._unhook(once_ok, once_fail)
            try:
                city = data.get("city", "未知")
                temp = data.get("temp", "--")
                text = data.get("text", "")
                suffix = " %s" % text if text else ""
                show_toast("天气刷新成功：%s %s°C%s" % (city, temp, suffix))
                logger.info("托盘手动刷新天气成功: %s %s°C", city, temp)
            except Exception:
                pass

        def once_fail(info):
            self._unhook(once_ok, once_fail)
            try:
                show_toast("天气刷新失败：%s" % info.get("message", "网络异常"),
                           success=False)
                logger.warning("托盘手动刷新天气失败: %s", info.get("message", "网络异常"))
            except Exception:
                pass

        try:
            self.weather.updated.connect(once_ok)
            self.weather.failed.connect(once_fail)
        except Exception:
            return
        self.weather.refresh(force=True)

    def _unhook(self, once_ok, once_fail):
        """解除本次刷新的一次性连接，避免重复点击造成连接堆积。"""
        try:
            self.weather.updated.disconnect(once_ok)
        except Exception:
            pass
        try:
            self.weather.failed.disconnect(once_fail)
        except Exception:
            pass

    def _set_opacity(self, value):
        self.config["opacity"] = value
        try:
            utils.save_config(self.config)
        except Exception:
            pass
        self.island.set_window_opacity(value)

    def _show_about(self):
        QMessageBox.about(
            None, "关于 易课",
            "<b>%s</b> v%s<br><br>"
            "Silicon UI · 全面自适应灵动岛教室看板<br>"
            "天气数据来源：和风天气 (dev.qweather.com)<br>"
            "名言数据来源：Hitokoto一言 (hitokoto.cn)<br><br>"
            "易课 EasyClass v1.0.0 | Silicon UI" % (APP_NAME, APP_VERSION))

    def _quit(self):
        """退出程序：二次确认对话框。"""
        answer = QMessageBox.question(
            None, "退出确认",
            "确定要退出易课吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self.callbacks["quit_app"]()
