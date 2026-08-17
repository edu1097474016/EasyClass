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
import signal
import logging
import logging.handlers
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
    """日志写入 data/logs/app.log（滚动文件）+ 控制台；只记录 WARNING 及以上（报错）信息。"""
    utils.ensure_data_dir()
    log_path = os.path.join(utils.LOG_DIR, "app.log")
    logger = logging.getLogger()
    logger.setLevel(logging.WARNING)   # 只记录报错，避免详细日志刷屏
    logger.handlers.clear()
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    def excepthook(exc_type, exc_value, exc_tb):
        logger.critical("未捕获异常", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = excepthook


def main():
    # ---------- 1. 数据目录与日志 ----------
    utils.ensure_data_dir()
    utils.migrate_old_files()
    setup_logging()
    logging.info("易课 EasyClass 启动 | 数据目录: %s", utils.DATA_DIR)

    # ---------- 3. 配置文件检查 ----------
    utils.ensure_config_files()
    config = utils.load_config()
    logging.info("配置已加载: 主题=%s 城市=%s 自动定位=%s 材质=%s 宽度比例=%s",
                 config.get("theme"), config.get("weather_city", "北京"),
                 config.get("auto_locate"), config.get("island_material", "frosted"),
                 config.get("island_width_ratio", 1.0))

    # ---------- 4. 应用初始化 ----------
    app = QApplication(sys.argv)
    app.setApplicationName(utils.APP_NAME)
    app.setApplicationVersion(utils.APP_VERSION)
    app.setQuitOnLastWindowClosed(False)   # 无窗口时保持托盘运行
    app.setStyle("Fusion")                 # 保证 QSS 在跨平台一致渲染
    utils.install_button_press_animation(app)   # 按钮按下滑动动画
    logging.info("QApplication 初始化完成")

    # Ctrl+C 优雅退出：把 SIGINT 转成正常的 app.quit()，
    # 让主事件循环正常退出并触发 aboutToQuit 清理（天气线程停止、托盘销毁等）
    def _on_sigint(_signum, _frame):
        qapp = QApplication.instance()
        if qapp is not None:
            qapp.quit()

    signal.signal(signal.SIGINT, _on_sigint)

    # 应用已导入的自定义字体（永久保存在 data/fonts/）
    font_ok = utils.apply_saved_font(config.get("custom_font_file", ""))
    logging.info("自定义字体应用: %s 文件=%s", font_ok, config.get("custom_font_file", "无"))

    # 应用图标
    from icon_drawer import IconDrawer
    app_icon = IconDrawer.app_icon_qicon(64)
    if app_icon is not None:
        app.setWindowIcon(app_icon)

    # ---------- 5. 主题管理 ----------
    theme = ThemeManager(app, config)
    logging.info("主题初始化: %s 主色=%s", theme.current_theme, theme.current_primary())

    # ---------- 6. 课程表管理 ----------
    courses = CourseManager()
    logging.info("课程表已加载: %s 共 %d 天有课", courses.path,
                 sum(1 for k in courses.DAY_KEYS if courses.data.get(k)))

    # ---------- 7. 天气管理 ----------
    weather = WeatherManager(config)
    logging.info("天气管理器初始化: 提供商=uapi 城市=%s 自动定位=%s",
                 config.get("weather_city"), config.get("auto_locate"))

    # ---------- 8. 灵动岛主窗口（默认隐藏） ----------
    island = IslandWindow(theme, courses, weather, config)
    # 天气数据 → 灵动岛（修复：原先未连接导致岛窗天气不更新）
    weather.updated.connect(island._on_weather)
    weather.failed.connect(island._on_weather_failed)
    logging.info("灵动岛窗口创建完成，信号已连接")

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
    logging.info("启动定时器已开启：天气/课程/时钟")

    # ---------- 13. 启动即显示灵动岛（从顶部非线性滑入到位） ----------
    island.slide_in()
    logging.info("灵动岛已滑入显示")

    # ---------- 14. 首次启动：提示填写天气 API 与课程信息（data/config.json 标记） ----------
    if not config.get("welcome_done", False):
        config["welcome_done"] = True
        utils.save_config(config)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            None, "欢迎使用 易课 EasyClass awa",
            "首次使用，请先完成基础设置：\n\n"
            "1. 天气：在「设置 → 天气」中开启自动定位，或手动填写城市\n"
            "2. 课程表：在「设置 → 课程表」中编辑或导入课表\n\n"
            "完成后灵动岛会自动显示课程、倒计时、天气与预警（天气接口免费，无需 API Key）。",
            QMessageBox.Ok)
        open_settings()

    # ---------- 15. 退出清理 ----------
    app.aboutToQuit.connect(weather.stop)
    logging.info("程序主循环启动，常驻后台运行")

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
