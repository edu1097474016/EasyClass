# ==========================================================================
#  易课 EasyClass v1.0.0 | Silicon UI
#  weather_manager.py  ——  天气管理模块（UApiPro 免费接口）
#  -------------------------------------------------------------------------
#  职责：
#   · 自动定位：不传 city 参数，由 UApiPro 按公网 IP 自动返回所在城市天气
#   · 手动填城市：传 city=城市名 查询指定城市天气
#   · 实时天气（天气/温度/湿度/风向风力/预警），无需 API Key，完全免费
#   · QThread 异步请求，不阻塞界面；30 分钟自动刷新（可设置）
#   · 失败时使用缓存兜底，不弹错误框
#   · 接口：https://uapis.cn/api/v1/misc/weather
# ==========================================================================

import logging
import time
from datetime import datetime

from PySide6.QtCore import QObject, QThread, Signal, QTimer

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
#  预警等级（中文） → 颜色键
# ------------------------------------------------------------------
LEVEL_COLOR_KEYS = {
    "白": "white",
    "灰": "gray",
    "绿": "green",
    "蓝": "blue",
    "黄": "yellow",
    "橙": "orange",
    "红": "red",
    "紫": "purple",
    "黑": "black",
}

# ------------------------------------------------------------------
#  预警颜色键 → 十六进制颜色
# ------------------------------------------------------------------
WARNING_COLORS = {
    "white": "#E5E7EB",
    "gray": "#9CA3AF",
    "green": "#22C55E",
    "blue": "#3B82F6",
    "yellow": "#FACC15",
    "amber": "#F59E0B",
    "orange": "#F97316",
    "red": "#EF4444",
    "purple": "#8B5CF6",
    "black": "#111827",
}


def warning_color_hex(color_key):
    """把预警颜色键（如 yellow / red）映射为十六进制颜色。"""
    if not color_key:
        return "#EF4444"
    return WARNING_COLORS.get(str(color_key).lower(), "#EF4444")


def aqi_color(aqi):
    """根据 AQI 数值返回等级颜色（uapi 天气接口不含 AQI，保留兼容）。"""
    try:
        aqi = int(aqi)
    except (TypeError, ValueError):
        return "#9CA3AF"
    if aqi <= 50:
        return "#22C55E"      # 优
    if aqi <= 100:
        return "#EAB308"      # 良
    if aqi <= 150:
        return "#F59E0B"      # 轻度污染
    if aqi <= 200:
        return "#F97316"      # 中度污染
    if aqi <= 300:
        return "#EF4444"      # 重度污染
    return "#7F1D1D"          # 严重污染


class WeatherWorker(QThread):
    """后台请求线程：调 UApiPro 获取实时天气 + 预警（免费、无需 API Key）。"""

    ok = Signal(dict)
    fail = Signal(dict)

    API_URL = "https://uapis.cn/api/v1/misc/weather"
    TIMEOUT = 8

    def __init__(self, city, auto_locate, parent=None):
        super().__init__(parent)
        self.city = (city or "").strip()
        self.auto_locate = auto_locate
        self._last_error = ""

    # ------------------------------------------------------------------
    #  主流程
    # ------------------------------------------------------------------
    def run(self):
        """在工作线程内请求 UApiPro 天气接口并解析结果。"""
        try:
            import requests
            params = {}
            if not self.auto_locate:
                if not self.city:
                    self.fail.emit({"message": "未填写城市，请在天气设置中指定"})
                    return
                params["city"] = self.city

            try:
                resp = requests.get(
                    self.API_URL,
                    params=params,
                    timeout=self.TIMEOUT,
                    headers={"User-Agent": "EasyClass/1.0 (Windows)"},
                )
            except Exception as exc:
                self._last_error = "网络异常: %s" % type(exc).__name__
                self.fail.emit({"message": self._last_error})
                return

            if resp.status_code != 200:
                self._last_error = "HTTP %s" % resp.status_code
                self.fail.emit({"message": "天气查询失败：%s" % self._last_error})
                return

            data = resp.json()
            if not isinstance(data, dict) or "weather" not in data:
                self._last_error = "接口返回格式异常"
                self.fail.emit({"message": "天气查询失败：%s" % self._last_error})
                return

            self.ok.emit(self._build_result(data))
        except Exception as exc:
            self.fail.emit({"message": "网络异常: %s" % type(exc).__name__})

    # ------------------------------------------------------------------
    #  结果组装
    # ------------------------------------------------------------------
    @classmethod
    def _build_result(cls, data):
        """把 uapi 返回的天气数据映射为灵动岛可用的统一结构。"""
        city_name = (data.get("district") or data.get("city") or "未知").strip()
        temp = data.get("temperature")
        icon = str(data.get("weather_icon") or "999")
        wind_scale = str(data.get("wind_power") or "").replace("级", "").strip()

        return {
            "temp": temp if temp is not None else "--",
            "feels_like": temp if temp is not None else "--",
            "text": data.get("weather") or "未知",
            "code": cls._icon_code(icon),
            "icon": icon,
            "wind_dir": data.get("wind_direction") or "",
            "wind_scale": wind_scale,
            "wind_speed": "",
            "humidity": data.get("humidity") if data.get("humidity") is not None else "--",
            "pressure": "--",
            "vis": "--",
            "precip": "--",
            "cloud": "--",
            "dew": "--",
            "air": None,
            "warnings": cls._parse_warnings(data, city_name),
            "daily": [],
            "hourly": [],
            "minutely": "",
            "indices": [],
            "city": city_name,
            "location": {
                "id": str(data.get("adcode") or ""),
                "lat": None,
                "lon": None,
            },
            "report_time": data.get("report_time") or "",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "provider": "uapi",
        }

    # ------------------------------------------------------------------
    #  预警解析（uapi：alerts 数组，只取标题与等级做轻量展示）
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_warnings(data, default_location):
        if not data:
            return []
        alerts = data.get("alerts") or []
        result = []
        for a in alerts:
            level = (a.get("level") or "").strip()
            color_key = LEVEL_COLOR_KEYS.get(level[:1], "red")
            result.append({
                "id": a.get("publish_time", ""),
                "sender": a.get("publisher", ""),
                "title": a.get("title", "天气预警"),
                "type": a.get("type", ""),
                "typeName": a.get("type", ""),
                "level": level,
                "color": color_key,
                "color_hex": warning_color_hex(color_key),
                "text": a.get("text", ""),
                "pubTime": a.get("publish_time", ""),
                "location": default_location,
            })
        return result

    @staticmethod
    def _icon_code(icon):
        """把 uapi 的 weather_icon 字符串安全转换为整数，供图标绘制分类使用。"""
        try:
            return int(icon)
        except (TypeError, ValueError):
            return 999


class WeatherManager(QObject):
    """天气管理器：调度刷新线程、缓存与信号转发。"""

    updated = Signal(dict)   # 成功：完整天气数据 dict
    failed = Signal(dict)    # 失败：{"cached": 最近缓存或None, "message": str}

    AUTO_REFRESH_MS = 30 * 60 * 1000  # 30 分钟

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config if config is not None else {}
        self.city = self.config.get("weather_city", "北京")
        self.auto_locate = bool(self.config.get("auto_locate", True))
        self.refresh_minutes = max(1, int(self.config.get("weather_refresh_minutes", 30)))
        self._worker = None
        self._cooldown_until = 0.0
        self.cache = None   # 仅内存保留最近一次成功数据

        self.timer = QTimer(self)
        self.timer.setInterval(self.refresh_minutes * 60 * 1000)
        self.timer.timeout.connect(self.refresh)

    # ------------------------------------------------------------------
    #  生命周期
    # ------------------------------------------------------------------
    def start(self):
        """启动天气管理：立即刷新一次 + 开启定时刷新。"""
        self.refresh()
        self.timer.start()

    def stop(self):
        """停止定时器并等待后台线程退出，避免退出时崩溃。"""
        self.timer.stop()
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait(9000)

    def refresh(self, force=False):
        """发起一次异步天气刷新（若已有请求在跑则跳过）。

        失败后进入 60 秒冷却：避免在接口被限制时反复请求。
        手动操作可传 force=True 强制刷新。
        """
        if not force and time.time() < self._cooldown_until:
            return
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = WeatherWorker(self.city, self.auto_locate)
        self._worker.ok.connect(self._on_ok)
        self._worker.fail.connect(self._on_fail)
        self._worker.start()
        logger.info("天气刷新已发起: 城市=%s 自动定位=%s", self.city, self.auto_locate)

    def set_refresh_minutes(self, minutes):
        """设置天气自动刷新间隔（分钟），实时生效。"""
        self.refresh_minutes = max(1, int(minutes))
        self.timer.setInterval(self.refresh_minutes * 60 * 1000)

    def update_config(self, config):
        """设置/天气页保存后更新配置并立刻刷新。"""
        self.config = config
        self.city = config.get("weather_city", "北京")
        self.auto_locate = bool(config.get("auto_locate", True))
        self.set_refresh_minutes(config.get("weather_refresh_minutes", 30))
        logger.info("天气配置已更新: 城市=%s 自动定位=%s 刷新=%d分钟",
                    self.city, self.auto_locate, self.refresh_minutes)
        self.refresh()

    # ------------------------------------------------------------------
    #  内部回调
    # ------------------------------------------------------------------
    def _on_ok(self, data):
        """请求成功：仅保留在内存，广播实时数据。"""
        self.cache = data
        data["cached"] = False
        logger.info("天气刷新成功: %s %s°C %s | 预警%d条",
                    data.get("city", "?"), data.get("temp", "?"),
                    data.get("text", "?"), len(data.get("warnings") or []))
        self.updated.emit(data)

    def _on_fail(self, info):
        """请求失败：进入冷却、不携带任何缓存兜底，直接广播真实错误。"""
        self._cooldown_until = time.time() + 60
        self.cache = None
        logger.warning("天气刷新失败: %s（60 秒冷却）", info.get("message", "网络异常"))
        self.failed.emit({
            "cached": None,
            "message": info.get("message", "网络异常"),
        })
