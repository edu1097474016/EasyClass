# ==========================================================================
#  易课 EasyClass v1.0.0 | Silicon UI
#  admin_window.py  ——  管理后台（扁平化设置界面）
#  -------------------------------------------------------------------------
#  职责：
#   · 仿 Flat UI：左侧导航栏 + QStackedWidget 页面切换
#   · 所有设置归类到左侧 Tab：首页概览 / 外观 / 灵动岛 / 天气 / 课程表 / 安全 / 关于
#   · 支持深色/浅色主题，以及自定义主题色（全局即时生效）
#   · 管理后台打开无需密码
#   · 全部使用布局管理器 + 滚动区，控件无遮挡、均可操作
#   · 不使用 emoji，全部为纯文本
# ==========================================================================

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QFrame,
    QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget,
    QScrollArea, QSlider, QLineEdit, QComboBox, QColorDialog,
    QApplication,
)

import utils
from utils import s, ToggleSwitch
from theme_manager import ThemeManager
from course_manager import CourseManager
from weather_manager import WeatherManager
from settings_dialog import show_toast, ScheduleEditor
from island_window import IslandWindow

# 预设主题色（第一个为默认翠绿色）
PRESET_COLORS = [
    ("#40916C", "翠绿"),
    ("#2D6A4F", "深绿"),
    ("#8B5CF6", "紫色"),
    ("#2563EB", "蓝色"),
    ("#0D9488", "青绿"),
    ("#F59E0B", "橙色"),
    ("#E11D48", "玫红"),
]


def theme_colors():
    theme = QApplication.instance().property("__theme") or "dark"
    return ThemeManager.COLORS.get(theme, ThemeManager.COLORS["dark"])


class AdminWindow(QMainWindow):
    """易课管理后台主窗口。"""

    NAV = [
        ("首页概览", 0),
        ("外观设置", 1),
        ("灵动岛", 2),
        ("天气", 3),
        ("课程表", 4),
        ("安全设置", 5),
        ("关于", 6),
    ]

    def __init__(self, config, theme_manager, island, weather_manager,
                 course_manager, parent=None):
        super().__init__(parent)
        self.config = config
        self.theme = theme_manager
        self.island = island
        self.weather = weather_manager
        self.courses = course_manager

        self._palette = {}
        self._weather_error = ""

        self.setWindowTitle("易课管理后台")
        self.resize(s(1020), s(680))
        self.setMinimumSize(s(860), s(600))

        central = QWidget(self)
        central.setObjectName("adminRoot")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._build_sidebar(root)
        self._build_pages(root)

        self.theme.theme_changed.connect(lambda _t: self._apply_style())
        self.weather.updated.connect(lambda _d: self._on_weather_update())
        self.weather.failed.connect(self._on_weather_failed)
        self._apply_style()

    # ==================================================================
    #  侧边栏
    # ==================================================================
    def _build_sidebar(self, root):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(s(200))
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(s(12), s(26), s(12), s(18))
        lay.setSpacing(s(4))

        logo = QLabel("易课管理")
        logo.setObjectName("logo")
        lay.addWidget(logo)

        self._nav_buttons = []
        for text, index in self.NAV:
            btn = QPushButton(text)
            btn.setProperty("class", "nav")
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(s(40))
            btn.clicked.connect(lambda _=False, i=index: self._switch_page(i))
            lay.addWidget(btn)
            self._nav_buttons.append(btn)
        self._nav_buttons[0].setChecked(True)

        lay.addStretch(1)
        ver = QLabel("%s v%s" % (utils.APP_NAME, utils.APP_VERSION))
        ver.setObjectName("version")
        lay.addWidget(ver)
        root.addWidget(sidebar)

    # ==================================================================
    #  页面容器
    # ==================================================================
    def _build_pages(self, root):
        self.stack = QStackedWidget()
        self.stack.setObjectName("contentStack")
        builders = [
            self._build_dashboard,
            self._build_appearance,
            self._build_island,
            self._build_weather_page,
            self._build_schedule,
            self._build_security,
            self._build_about,
        ]
        for builder in builders:
            self.stack.addWidget(self._scroll_page(builder))
        root.addWidget(self.stack, 1)

    def _switch_page(self, index):
        self.stack.setCurrentIndex(index)
        if index == 0:
            self._refresh_dashboard()
        elif index == 4:
            self._update_schedule_preview()

    def _scroll_page(self, builder):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(s(40), s(26), s(40), s(30))
        layout.setSpacing(s(16))
        builder(layout)
        layout.addStretch(1)
        scroll.setWidget(container)
        return scroll

    # ==================================================================
    #  通用构建辅助
    # ==================================================================
    def _header(self, layout, breadcrumb, title):
        bc = QLabel(breadcrumb)
        bc.setProperty("class", "page-breadcrumb")
        layout.addWidget(bc)
        t = QLabel(title)
        t.setProperty("class", "page-title")
        layout.addWidget(t)

    def _card(self, layout, title=None):
        frame = QFrame()
        frame.setProperty("class", "card")
        frame.setAttribute(Qt.WA_StyledBackground, True)
        cl = QVBoxLayout(frame)
        cl.setContentsMargins(s(24), s(18), s(24), s(18))
        cl.setSpacing(s(14))
        if title:
            lbl = QLabel(title)
            lbl.setProperty("class", "card-title")
            cl.addWidget(lbl)
        layout.addWidget(frame)
        return cl

    def _row(self, layout, title, widget, hint=None):
        row = QHBoxLayout()
        row.setSpacing(s(12))
        left = QVBoxLayout()
        left.setSpacing(s(2))
        t = QLabel(title)
        t.setProperty("class", "setting-title")
        left.addWidget(t)
        if hint:
            h = QLabel(hint)
            h.setProperty("class", "setting-hint")
            h.setWordWrap(True)
            left.addWidget(h)
        row.addLayout(left)
        row.addStretch(1)
        row.addWidget(widget)
        layout.addLayout(row)

    def _save_btn(self, on_click, text="保存设置"):
        btn = QPushButton(text)
        btn.setProperty("class", "primary")
        btn.setFixedHeight(s(40))
        btn.setMinimumWidth(s(130))
        btn.clicked.connect(on_click)
        return btn

    def _stat_card(self, title, value):
        frame = QFrame()
        frame.setProperty("class", "stat-card")
        frame.setAttribute(Qt.WA_StyledBackground, True)
        v = QVBoxLayout(frame)
        v.setContentsMargins(s(20), s(16), s(20), s(16))
        v.setSpacing(s(6))
        t = QLabel(title)
        t.setProperty("class", "setting-hint")
        v.addWidget(t)
        val = QLabel(value)
        val.setProperty("class", "stat-value")
        v.addWidget(val)
        return frame, val

    # ==================================================================
    #  页面 1：首页概览
    # ==================================================================
    def _build_dashboard(self, layout):
        self._header(layout, "首页 / 概览", "管理后台")

        grid = QGridLayout()
        grid.setSpacing(s(16))
        self._stat_theme, self._stat_theme_v = self._stat_card("主题模式", "深色模式")
        self._stat_island, self._stat_island_v = self._stat_card("灵动岛", "已隐藏")
        self._stat_weather, self._stat_weather_v = self._stat_card("天气", "未配置")
        self._stat_course, self._stat_course_v = self._stat_card("今日课程", "0 节")
        grid.addWidget(self._stat_theme, 0, 0)
        grid.addWidget(self._stat_island, 0, 1)
        grid.addWidget(self._stat_weather, 1, 0)
        grid.addWidget(self._stat_course, 1, 1)
        layout.addLayout(grid)

        cl = self._card(layout, "快捷操作")
        btn_row = QHBoxLayout()
        btn_row.setSpacing(s(12))
        self._btn_toggle_island = QPushButton("隐藏灵动岛")
        self._btn_toggle_island.clicked.connect(self._toggle_island)
        btn_refresh = QPushButton("刷新天气")
        btn_refresh.clicked.connect(lambda: self.weather.refresh(force=True))
        btn_editor = QPushButton("打开课程表编辑器")
        btn_editor.setProperty("class", "primary")
        btn_editor.clicked.connect(self._open_editor)
        btn_row.addWidget(self._btn_toggle_island)
        btn_row.addWidget(btn_refresh)
        btn_row.addWidget(btn_editor)
        btn_row.addStretch(1)
        cl.addLayout(btn_row)

        self._refresh_dashboard()

    def _refresh_dashboard(self, *_args):
        if not hasattr(self, "_stat_theme"):
            return
        self._stat_theme_v.setText(
            "浅色模式" if self.theme.current_theme == self.theme.LIGHT else "深色模式")
        visible = self.island is not None and self.island.isVisible()
        self._stat_island_v.setText("显示中" if visible else "已隐藏")
        if hasattr(self, "_btn_toggle_island"):
            self._btn_toggle_island.setText("隐藏灵动岛" if visible else "显示灵动岛")
        self._stat_weather_v.setText(self._weather_status_text())
        self._stat_course_v.setText("%d 节" % len(self.courses.courses_for_day()))

    def _weather_status_text(self):
        cache = self.weather.cache
        if cache:
            parts = ["%s  %s°C" % (cache.get("city", "未知"), cache.get("temp", "--"))]
            air = cache.get("air")
            if air and air.get("aqi") not in (None, "--"):
                parts.append("AQI %s" % air.get("aqi"))
            if cache.get("warnings"):
                parts.append("预警 %d 条" % len(cache["warnings"]))
            return "  ".join(parts)
        key = self.config.get("weather_api_key", "")
        if not key or "请填写" in key or "你的API密钥" in key:
            return "未配置"
        return "待刷新"

    def _on_weather_update(self):
        self._weather_error = ""
        self._refresh_dashboard()
        self._update_weather_status()

    def _on_weather_failed(self, info):
        self._weather_error = info.get("message", "网络异常")
        self._refresh_dashboard()
        self._update_weather_status()

    def _toggle_island(self):
        if self.island is not None:
            self.island.toggle_visible()
            self._refresh_dashboard()

    def _open_editor(self):
        editor = ScheduleEditor(self.courses, parent=self)
        editor.exec()
        self._update_schedule_preview()
        self._refresh_dashboard()

    # ==================================================================
    #  页面 2：外观设置
    # ==================================================================
    def _build_appearance(self, layout):
        self._header(layout, "设置 / 外观", "外观设置")

        cl = self._card(layout, "主题模式")
        self.theme_switch = ToggleSwitch()
        self.theme_state_label = QLabel()
        self.theme_state_label.setProperty("class", "setting-hint")
        row = QHBoxLayout()
        row.addWidget(self.theme_state_label)
        row.addStretch(1)
        row.addWidget(self.theme_switch)
        cl.addLayout(row)
        self.theme_switch.toggled.connect(self._on_theme_toggled)
        self._sync_theme_controls()

        cl = self._card(layout, "主题色")
        sw_row = QHBoxLayout()
        sw_row.setSpacing(s(10))
        self._swatch_buttons = []
        for hex_color, name in PRESET_COLORS:
            sw = QPushButton()
            sw.setFixedSize(s(30), s(30))
            sw.setCursor(Qt.PointingHandCursor)
            sw.setToolTip(name)
            sw.setStyleSheet(
                "QPushButton { background: %s; border: none; padding: 0px; border-radius: 6px; }"
                % hex_color)
            sw.clicked.connect(lambda _=False, c=hex_color: self._apply_primary(c))
            sw_row.addWidget(sw)
            self._swatch_buttons.append(sw)
        custom_btn = QPushButton("自定义颜色")
        custom_btn.clicked.connect(self._pick_custom_color)
        sw_row.addWidget(custom_btn)
        sw_row.addStretch(1)
        cl.addLayout(sw_row)

        self._primary_label = QLabel()
        self._primary_label.setProperty("class", "setting-hint")
        cl.addWidget(self._primary_label)

        cl = self._card(layout, "窗口透明度")
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(int(float(self.config.get("opacity", 0.65)) * 100))
        self._opacity_value = QLabel()
        self._opacity_value.setProperty("class", "setting-hint")
        self.opacity_slider.valueChanged.connect(
            lambda v: self._opacity_value.setText("%d%%" % v))
        self._opacity_value.setText("%d%%" % self.opacity_slider.value())
        row = QHBoxLayout()
        row.addWidget(self._opacity_value)
        row.addStretch(1)
        cl.addLayout(row)
        cl.addWidget(self.opacity_slider)

        layout.addWidget(self._save_btn(self._save_appearance))

    def _sync_theme_controls(self):
        if not hasattr(self, "theme_switch"):
            return
        light = self.theme.current_theme == self.theme.LIGHT
        self.theme_switch.blockSignals(True)
        self.theme_switch.set_checked_animated(light)
        self.theme_switch.blockSignals(False)
        self.theme_state_label.setText("浅色模式" if light else "深色模式")

    def _on_theme_toggled(self, checked):
        self.theme_state_label.setText("浅色模式" if checked else "深色模式")
        if checked and self.theme.current_theme == self.theme.DARK:
            self.theme.set_light_theme()
        elif not checked and self.theme.current_theme == self.theme.LIGHT:
            self.theme.set_dark_theme()
        self._refresh_dashboard()

    def _apply_primary(self, hex_color):
        self.theme.set_primary_color(hex_color)
        self._update_primary_label()
        show_toast("主题色已应用")

    def _pick_custom_color(self):
        color = QColorDialog.getColor(
            QColor(self.theme.current_primary()), self, "自定义主题色")
        if color.isValid():
            self._apply_primary(color.name().upper())

    def _update_primary_label(self):
        if hasattr(self, "_primary_label"):
            self._primary_label.setText("当前主题色：%s" % self.theme.current_primary())
        self._update_swatches()

    def _save_appearance(self):
        opacity = self.opacity_slider.value() / 100.0
        self.config["opacity"] = opacity
        if self.island is not None:
            self.island.set_window_opacity(opacity)
        utils.save_config(self.config)
        show_toast("外观设置已保存")

    # ==================================================================
    #  页面 3：灵动岛
    # ==================================================================
    def _build_island(self, layout):
        self._header(layout, "设置 / 灵动岛", "灵动岛")

        cl = self._card(layout, "宽度比例")
        self.width_slider = QSlider(Qt.Horizontal)
        self.width_slider.setRange(50, 95)
        self.width_slider.setValue(
            int(float(self.config.get("island_width_ratio", 0.85)) * 100))
        self._width_value = QLabel()
        self._width_value.setProperty("class", "setting-hint")
        self.width_slider.valueChanged.connect(
            lambda v: self._width_value.setText("%d%%" % v))
        self._width_value.setText("%d%%" % self.width_slider.value())
        row = QHBoxLayout()
        row.addWidget(self._width_value)
        row.addStretch(1)
        cl.addLayout(row)
        cl.addWidget(self.width_slider)

        cl = self._card(layout, "显示模式")
        self.fullscreen_switch = ToggleSwitch()
        self.fullscreen_switch.set_checked_animated(
            self.island.is_fullscreen() if self.island else False)
        self.fullscreen_switch.toggled.connect(self._on_fullscreen_toggled)
        self._row(cl, "全屏模式", self.fullscreen_switch, "铺满目标屏幕可用范围")

        self.passthrough_switch = ToggleSwitch()
        self.passthrough_switch.set_checked_animated(
            self.island.is_pass_through() if self.island else False)
        self.passthrough_switch.toggled.connect(self._on_passthrough_toggled)
        self._row(cl, "鼠标穿透", self.passthrough_switch, "开启后灵动岛不再响应鼠标")

        self.hover_switch = ToggleSwitch()
        self.hover_switch.set_checked_animated(
            self.island.hover_hide_enabled() if self.island else True)
        self.hover_switch.toggled.connect(self._on_hover_hide_toggled)
        self._row(cl, "靠近自动隐藏", self.hover_switch,
                  "鼠标靠近灵动岛时自动隐藏，鼠标移开后恢复显示")

        cl = self._card(layout, "显示器")
        self.screen_combo = QComboBox()
        screens = QGuiApplication.screens()
        current = self.island.screen_index() if self.island else 0
        for i, scr in enumerate(screens):
            name = scr.name() or "显示器 %d" % (i + 1)
            self.screen_combo.addItem(
                "%s (%dx%d)" % (name, scr.geometry().width(), scr.geometry().height()), i)
        if 0 <= current < self.screen_combo.count():
            self.screen_combo.setCurrentIndex(current)
        self.screen_combo.currentIndexChanged.connect(self._on_screen_changed)
        self._row(cl, "目标屏幕", self.screen_combo, "灵动岛显示在所选屏幕顶部")

        layout.addWidget(self._save_btn(self._save_island))

    def _on_fullscreen_toggled(self, checked):
        if self.island is not None:
            self.island.set_fullscreen(checked)
        self._refresh_dashboard()

    def _on_passthrough_toggled(self, checked):
        if self.island is not None:
            self.island.set_pass_through(checked)
        self._refresh_dashboard()

    def _on_hover_hide_toggled(self, checked):
        self.config["hover_hide"] = checked
        if self.island is not None:
            self.island.set_hover_hide(checked)
        utils.save_config(self.config)
        self._refresh_dashboard()

    def _on_screen_changed(self, index):
        if self.island is not None:
            self.island.set_screen_index(index)

    def _save_island(self):
        ratio = self.width_slider.value() / 100.0
        self.config["island_width_ratio"] = ratio
        if self.island is not None:
            self.island.set_width_ratio(ratio)
        utils.save_config(self.config)
        show_toast("灵动岛设置已保存")

    # ==================================================================
    #  页面 4：天气
    # ==================================================================
    def _build_weather_page(self, layout):
        self._header(layout, "设置 / 天气", "天气设置")

        cl = self._card(layout, "和风天气")

        self.auto_locate_switch = ToggleSwitch()
        self.auto_locate_switch.set_checked_animated(
            bool(self.config.get("auto_locate", True)))
        self.auto_locate_switch.toggled.connect(self._on_auto_locate_toggled)
        self._row(cl, "自动定位", self.auto_locate_switch,
                  "通过公网 IP 自动定位当前电脑所在城市")

        self.city_edit = QLineEdit()
        self.city_edit.setText(self.config.get("weather_city", "北京"))
        self.city_edit.setPlaceholderText("输入城市，如：北京")
        self.city_edit.setFixedWidth(s(220))
        self._row(cl, "城市", self.city_edit, "关闭自动定位后可手动填写")

        self.host_edit = QLineEdit()
        self.host_edit.setText(self.config.get("api_host", "https://api.qweather.com"))
        self.host_edit.setPlaceholderText("https://你的专属Host")
        self.host_edit.setFixedWidth(s(320))
        self._row(cl, "API Host", self.host_edit,
                  "在控制台-设置中查看你的专属 Host（如 abc.qweatherapi.com）")

        self.key_edit = QLineEdit()
        self.key_edit.setText(self.config.get("weather_api_key", ""))
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("请输入和风天气 API Key")
        self.key_edit.setFixedWidth(s(320))
        self._row(cl, "API Key", self.key_edit)

        self._sync_auto_locate_controls()

        cl = self._card(layout, "天气状态")
        self._weather_status = QLabel()
        self._weather_status.setWordWrap(True)
        self._weather_status.setProperty("class", "setting-hint")
        cl.addWidget(self._weather_status)
        refresh_btn = QPushButton("立即刷新天气")
        refresh_btn.clicked.connect(lambda: self.weather.refresh(force=True))
        cl.addWidget(refresh_btn)
        self._update_weather_status()

        layout.addWidget(self._save_btn(self._save_weather))

    def _sync_auto_locate_controls(self):
        auto = self.auto_locate_switch.isChecked()
        self.city_edit.setEnabled(not auto)

    def _on_auto_locate_toggled(self, checked):
        self._sync_auto_locate_controls()

    def _save_weather(self):
        self.config["weather_city"] = self.city_edit.text().strip() or "北京"
        self.config["weather_api_key"] = self.key_edit.text().strip()
        host = self.host_edit.text().strip()
        self.config["api_host"] = host or "https://api.qweather.com"
        self.config["auto_locate"] = self.auto_locate_switch.isChecked()
        utils.save_config(self.config)
        self.weather.update_config(self.config)
        self._refresh_dashboard()
        show_toast("天气设置已保存")

    def _update_weather_status(self):
        """在天气页展示完整的当前天气数据。"""
        if not hasattr(self, "_weather_status"):
            return
        cache = self.weather.cache
        if cache:
            lines = []
            lines.append("%s · %s · %s°C（体感 %s°C）" % (
                cache.get("city", "未知"),
                cache.get("text", "未知"),
                cache.get("temp", "--"),
                cache.get("feels_like", "--")))
            air = cache.get("air")
            if air and air.get("aqi") not in (None, "--"):
                lines.append("空气质量 AQI %s · %s%s" % (
                    air.get("aqi"), air.get("category", ""),
                    "（首要污染物：%s）" % air["primary"] if air.get("primary") else ""))
            lines.append("湿度 %s%% · 风向 %s %s级 · 气压 %shPa" % (
                cache.get("humidity", "--"), cache.get("wind_dir", "--"),
                cache.get("wind_scale", "--"), cache.get("pressure", "--")))
            indices = cache.get("indices") or []
            if indices:
                parts = []
                for i in indices[:5]:
                    cat = i.get("category") or i.get("level") or ""
                    parts.append("%s%s" % (i.get("name", ""), cat))
                lines.append("生活指数：" + " · ".join(parts))
            warnings = cache.get("warnings") or []
            if warnings:
                for w in warnings[:2]:
                    lines.append("预警[%s] %s" % (w.get("level", ""), w.get("title", "")))
            else:
                lines.append("当前无天气预警")
            self._weather_status.setText("\n".join(lines))
        else:
            if self._weather_error:
                self._weather_status.setText("天气获取失败：%s" % self._weather_error)
                return
            key = self.config.get("weather_api_key", "")
            if not key or "请填写" in key or "你的API密钥" in key:
                self._weather_status.setText("未配置 API Key，请在上方填写")
            else:
                self._weather_status.setText("等待刷新，请点击下方按钮或稍候自动刷新")

    # ==================================================================
    #  页面 5：课程表
    # ==================================================================
    def _build_schedule(self, layout):
        self._header(layout, "设置 / 课程表", "课程表")

        cl = self._card(layout, "今日课程")
        self._today_courses_label = QLabel()
        self._today_courses_label.setWordWrap(True)
        self._today_courses_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._today_courses_label.setProperty("class", "setting-hint")
        cl.addWidget(self._today_courses_label)
        self._update_schedule_preview()

        cl = self._card(layout, "课程表编辑")
        info = QLabel("在编辑器内可对周一至周日进行增删改，保存后立即生效。"
                      "管理后台打开编辑器无需密码。")
        info.setProperty("class", "setting-hint")
        info.setWordWrap(True)
        cl.addWidget(info)
        btn = QPushButton("打开课程表编辑器")
        btn.setProperty("class", "primary")
        btn.setFixedHeight(s(40))
        btn.clicked.connect(self._open_editor)
        cl.addWidget(btn)

    def _update_schedule_preview(self):
        if not hasattr(self, "_today_courses_label"):
            return
        courses = self.courses.courses_for_day()
        if not courses:
            text = "今天没有课程安排"
        else:
            lines = []
            for i, c in enumerate(courses, 1):
                parts = ["第 %d 节" % i,
                         "%s - %s" % (c.get("start", ""), c.get("end", ""))]
                if c.get("name"):
                    parts.append(c.get("name", ""))
                if c.get("teacher"):
                    parts.append("教师：%s" % c.get("teacher", ""))
                if c.get("room"):
                    parts.append("教室：%s" % c.get("room", ""))
                lines.append("  ".join(parts))
            text = "\n".join(lines)
        self._today_courses_label.setText(text)

    # ==================================================================
    #  页面 6：安全设置
    # ==================================================================
    def _build_security(self, layout):
        self._header(layout, "设置 / 安全", "安全设置")

        cl = self._card(layout, "编辑密码")
        hint = QLabel("课程表编辑器的访问密码，双击灵动岛或按 Ctrl+E 打开编辑器时校验。")
        hint.setProperty("class", "setting-hint")
        hint.setWordWrap(True)
        cl.addWidget(hint)
        self.pass_edit = QLineEdit()
        self.pass_edit.setText(self.config.get("password", "admin123"))
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.pass_edit.setFixedWidth(s(240))
        self._row(cl, "新密码", self.pass_edit)

        note = QLabel("管理后台本身无需密码，本机用户可直接打开。")
        note.setProperty("class", "setting-hint")
        note.setWordWrap(True)
        cl.addWidget(note)

        layout.addWidget(self._save_btn(self._save_security))

    def _save_security(self):
        pwd = self.pass_edit.text().strip() or "admin123"
        self.config["password"] = pwd
        utils.save_config(self.config)
        show_toast("密码已更新")

    # ==================================================================
    #  页面 7：关于
    # ==================================================================
    def _build_about(self, layout):
        self._header(layout, "关于", "关于易课")

        cl = self._card(layout)
        name = QLabel("易课 EasyClass")
        name.setProperty("class", "card-title")
        name.setStyleSheet("font-size: 20px; font-weight: 800;")
        cl.addWidget(name)

        version = QLabel("版本 v%s" % utils.APP_VERSION)
        version.setProperty("class", "setting-hint")
        cl.addWidget(version)

        desc = QLabel("基于 Python + PySide6 的 Windows 桌面灵动岛教室信息看板。"
                      "固定置顶显示课程信息、时钟、日期、天气与预警，课程切换自动更新。")
        desc.setWordWrap(True)
        desc.setProperty("class", "setting-hint")
        cl.addWidget(desc)

        for title, text in (
            ("功能特性",
             "灵动岛信息栏 / 深色浅色主题 / 可自定义主题色 / 课程表编辑 / "
             "和风天气自动刷新 / 系统托盘 / 多显示器自适应 / 鼠标穿透"),
            ("技术栈", "Python 3.9+ / PySide6 6.5+ / requests"),
            ("数据来源", "和风天气 QWeather（dev.qweather.com）"),
            ("开源许可", "MIT License"),
        ):
            sub = QLabel(title)
            sub.setProperty("class", "setting-title")
            cl.addWidget(sub)
            body = QLabel(text)
            body.setWordWrap(True)
            body.setProperty("class", "setting-hint")
            cl.addWidget(body)

        tag = QLabel(utils.APP_TAG)
        tag.setProperty("class", "setting-hint")
        cl.addWidget(tag)

    # ==================================================================
    #  主题色色块
    # ==================================================================
    def _update_swatches(self):
        if not hasattr(self, "_swatch_buttons"):
            return
        current = self.theme.current_primary().upper()
        border = self._palette.get("swatch_border", "#1A1A1A")
        for sw, (hex_color, _name) in zip(self._swatch_buttons, PRESET_COLORS):
            if hex_color.upper() == current:
                sw.setStyleSheet(
                    "QPushButton { background: %s; border: 2px solid %s; "
                    "padding: 0px; border-radius: 6px; }" % (hex_color, border))
            else:
                sw.setStyleSheet(
                    "QPushButton { background: %s; border: 2px solid transparent; "
                    "padding: 0px; border-radius: 6px; }" % hex_color)

    # ==================================================================
    #  样式
    # ==================================================================
    @staticmethod
    def _rgba(color_hex, alpha):
        c = QColor(color_hex)
        return "rgba(%d, %d, %d, %s)" % (c.red(), c.green(), c.blue(), str(alpha))

    def _apply_style(self):
        colors = theme_colors()
        primary = self.theme.current_primary()
        dark = self.theme.current_theme == self.theme.DARK
        base = QColor(primary)

        if dark:
            sidebar_bg = "#17181F"
            content_bg = "#121218"
            nav_hover = "rgba(255, 255, 255, 0.08)"
            btn_hover = "rgba(255, 255, 255, 0.10)"
            input_bg = "rgba(30, 32, 45, 0.85)"
            swatch_border = "#FFFFFF"
            stat_bg = "rgba(255, 255, 255, 0.03)"
            scrollbar = "#A0A0B8"
        else:
            sidebar_bg = "#F3F5F6"
            content_bg = "#FFFFFF"
            nav_hover = "#E8EBED"
            btn_hover = "rgba(0, 0, 0, 0.06)"
            input_bg = "#FFFFFF"
            swatch_border = "#1A1A1A"
            stat_bg = "#F9FAFB"
            scrollbar = "#9CA3AF"

        self._palette = {
            "content_bg": content_bg,
            "sidebar_bg": sidebar_bg,
            "text_main": colors["text_main"],
            "text_secondary": colors["text_secondary"],
            "border": colors["border"],
            "primary": primary,
            "primary_hover": base.lighter(112).name(),
            "primary_pressed": base.darker(112).name(),
            "nav_hover": nav_hover,
            "nav_active_bg": self._rgba(primary, 0.16),
            "btn_hover": btn_hover,
            "input_bg": input_bg,
            "card_bg": colors["bg_card"],
            "swatch_border": swatch_border,
            "stat_bg": stat_bg,
            "scrollbar": scrollbar,
        }
        self.setStyleSheet(self._STYLE % self._palette)

        self._sync_theme_controls()
        self._update_primary_label()
        self._update_swatches()
        self._update_schedule_preview()
        self._refresh_dashboard()

    # ==================================================================
    #  事件
    # ==================================================================
    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_dashboard()

    # ==================================================================
    #  样式表
    # ==================================================================
    _STYLE = """
QWidget {
    background: transparent;
    color: %(text_main)s;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
    font-size: 13px;
}
QMainWindow, QWidget#adminRoot { background: %(content_bg)s; }
QStackedWidget#contentStack { background: %(content_bg)s; }

QFrame#sidebar {
    background: %(sidebar_bg)s;
    border-right: 1px solid %(border)s;
}
QLabel#logo {
    font-size: 19px;
    font-weight: 800;
    color: %(primary)s;
    padding-left: 4px;
    margin-bottom: 16px;
}
QLabel#version {
    color: %(text_secondary)s;
    font-size: 11px;
    padding-left: 4px;
}

QPushButton[class="nav"] {
    background: transparent;
    border: none;
    border-radius: 6px;
    color: %(text_secondary)s;
    text-align: left;
    padding-left: 14px;
    font-size: 13px;
}
QPushButton[class="nav"]:hover { background: %(nav_hover)s; color: %(text_main)s; }
QPushButton[class="nav"]:checked {
    background: %(nav_active_bg)s;
    color: %(primary)s;
    font-weight: 600;
}

QLabel[class="page-breadcrumb"] { color: %(text_secondary)s; font-size: 12px; }
QLabel[class="page-title"] {
    font-size: 24px; font-weight: 700; color: %(text_main)s; margin-bottom: 4px;
}
QLabel[class="card-title"] { font-size: 15px; font-weight: 600; color: %(text_main)s; }
QLabel[class="setting-title"] { font-size: 13px; color: %(text_main)s; }
QLabel[class="setting-hint"] { font-size: 11px; color: %(text_secondary)s; }
QLabel[class="stat-value"] { font-size: 20px; font-weight: 700; color: %(primary)s; }

QFrame[class="card"] {
    background: %(card_bg)s;
    border: 1px solid %(border)s;
    border-radius: 10px;
}
QFrame[class="stat-card"] {
    background: %(stat_bg)s;
    border: 1px solid %(border)s;
    border-radius: 10px;
}

QPushButton {
    background: transparent;
    color: %(text_main)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 6px 16px;
    font-size: 13px;
}
QPushButton:hover { background: %(btn_hover)s; }
QPushButton:pressed { background: %(nav_active_bg)s; }
QPushButton:disabled { color: %(text_secondary)s; background: transparent; }
QPushButton[class="primary"] {
    background: %(primary)s;
    color: #FFFFFF;
    border: none;
    font-weight: 600;
}
QPushButton[class="primary"]:hover { background: %(primary_hover)s; }
QPushButton[class="primary"]:pressed { background: %(primary_pressed)s; }

QLineEdit {
    background: %(input_bg)s;
    color: %(text_main)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 8px 12px;
    selection-background-color: %(primary)s;
    selection-color: #FFFFFF;
}
QLineEdit:focus { border-color: %(primary)s; }
QLineEdit:disabled { color: %(text_secondary)s; }

QComboBox {
    background: %(input_bg)s;
    color: %(text_main)s;
    border: 1px solid %(border)s;
    border-radius: 6px;
    padding: 6px 12px;
}
QComboBox:focus { border-color: %(primary)s; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background: %(card_bg)s;
    color: %(text_main)s;
    border: 1px solid %(border)s;
    selection-background-color: %(primary)s;
    selection-color: #FFFFFF;
}

QSlider::groove:horizontal { height: 4px; background: %(border)s; border-radius: 2px; }
QSlider::sub-page:horizontal { background: %(primary)s; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #FFFFFF; width: 14px; height: 14px;
    margin: -5px 0; border-radius: 7px; border: 1px solid %(border)s;
}
QSlider::handle:horizontal:hover { background: %(primary)s; border-color: %(primary)s; }

QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }

QScrollBar:vertical { background: transparent; width: 8px; border-radius: 4px; margin: 2px; }
QScrollBar::handle:vertical { background: %(scrollbar)s; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: %(primary)s; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; background: transparent; }
QScrollBar:horizontal { background: transparent; height: 8px; border-radius: 4px; margin: 2px; }
QScrollBar::handle:horizontal { background: %(scrollbar)s; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: %(primary)s; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; background: transparent; }
"""


if __name__ == "__main__":
    import sys

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    utils.ensure_config_files()
    config = utils.load_config()
    theme = ThemeManager(app, config)
    courses = CourseManager()
    weather = WeatherManager(config)
    island = IslandWindow(theme, courses, weather, config)

    window = AdminWindow(config, theme, island, weather, courses)
    window.show()
    sys.exit(app.exec())
