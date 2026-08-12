# ==========================================================================
#  易课 EasyClass v1.0.0 | Silicon UI
#  main.py  ——  程序入口
#  -------------------------------------------------------------------------
#  启动流程：
#   1. 检查 config.json / schedule.json，不存在则从模板复制
#   2. 加载配置并初始化 QApplication
#   3. 初始化 ThemeManager（读取主题，应用 QSS）
#   4. 初始化 CourseManager / WeatherManager
#   5. 创建灵动岛主窗口（启动后自动从顶部滑入显示）
#   6. 创建系统托盘图标
#   7. 注册全局热键 Ctrl+E（编辑课程表）
#   8. 启动定时器：时间每秒 / 课程每10秒 / 天气每30分钟
#   9. 常驻后台运行
# ==========================================================================

import sys
import logging
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import QApplication

import utils
from theme_manager import ThemeManager
from course_manager import CourseManager
from weather_manager import WeatherManager
from island_window import IslandWindow
from tray_icon import TrayIcon
from settings_dialog import ScheduleEditor


def setup_logging():
    """日志写入 data/logs/app.log。"""
    utils.ensure_data_dir()
    log_path = os.path.join(utils.LOG_DIR, "app.log")
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        encoding="utf-8",
    )


def main():
    # ---------- 1. 数据目录与日志 ----------
    utils.ensure_data_dir()
    utils.migrate_old_files()
    setup_logging()
    logging.info("易课 EasyClass 启动")

    # ---------- 3. 配置文件检查 ----------
    utils.ensure_config_files()
    config = utils.load_config()

    # ---------- 4. 应用初始化 ----------
    app = QApplication(sys.argv)
    app.setApplicationName(utils.APP_NAME)
    app.setApplicationVersion(utils.APP_VERSION)
    app.setQuitOnLastWindowClosed(False)   # 无窗口时保持托盘运行
    app.setStyle("Fusion")                 # 保证 QSS 在跨平台一致渲染
    utils.install_button_press_animation(app)   # 按钮按下滑动动画

    # 应用已导入的自定义字体（永久保存在 data/fonts/）
    utils.apply_saved_font(config.get("custom_font_file", ""))

    # 应用图标
    from icon_drawer import IconDrawer
    app_icon = IconDrawer.app_icon_qicon(64)
    if app_icon is not None:
        app.setWindowIcon(app_icon)

    # ---------- 5. 主题管理 ----------
    theme = ThemeManager(app, config)

    # ---------- 6. 课程表管理 ----------
    courses = CourseManager()

    # ---------- 7. 天气管理 ----------
    weather = WeatherManager(config)

    # ---------- 8. 灵动岛主窗口（默认隐藏） ----------
    island = IslandWindow(theme, courses, weather, config)
    # 天气数据 → 灵动岛（修复：原先未连接导致岛窗天气不更新）
    weather.updated.connect(island._on_weather)
    weather.failed.connect(island._on_weather_failed)

    # ---------- 9. 回调函数 ----------
    def open_editor():
        """打开课程表编辑器（托盘 / Ctrl+E，无需密码，直接进入编辑）。"""
        editor = ScheduleEditor(courses, parent=None)
        editor.exec()

    admin_window = {"window": None}

    def open_settings():
        """打开管理后台（扁平化设置界面，无需密码）。"""
        from admin_window import AdminWindow
        if admin_window["window"] is None:
            admin_window["window"] = AdminWindow(config, theme, island, weather, courses)
        admin_window["window"].show()
        admin_window["window"].raise_()
        admin_window["window"].activateWindow()

    # ---------- 10. 系统托盘 ----------
    tray = TrayIcon(island, theme, weather, config, callbacks={
        "open_editor": open_editor,
        "open_settings": open_settings,
        "quit_app": app.quit,
    })
    tray.show()

    # ---------- 11. 全局热键 Ctrl+E（编辑课程表） ----------
    MOD_CONTROL = 0x0002
    hotkey = utils.GlobalHotkey(MOD_CONTROL, ord("E"), parent=app)
    hotkey.triggered.connect(open_editor)

    # 兜底：应用级快捷键
    shortcut = QShortcut(QKeySequence("Ctrl+E"), island)
    shortcut.setContext(Qt.ApplicationShortcut)
    shortcut.activated.connect(open_editor)

    # ---------- 12. 启动定时器 ----------
    weather.start()          # 立即刷新 + 30 分钟自动更新
    island.update_time()
    island.update_course()

    # ---------- 13. 启动即显示灵动岛（从顶部非线性滑入到位） ----------
    island.slide_in()

    # ---------- 14. 退出清理 ----------
    app.aboutToQuit.connect(weather.stop)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
