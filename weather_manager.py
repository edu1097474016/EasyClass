# ==========================================================================
#  易课 EasyClass v1.0.0 | Silicon UI
#  weather_manager.py  ——  天气管理模块（和风天气）
#  -------------------------------------------------------------------------
#  职责：
#   · 自动定位：通过 IP 获取当前电脑位置（经纬度），保留手动填城市选项
#   · 实时天气 + 空气质量 + 天气预警 + 7天预报 + 24小时 + 分钟级降水 + 生活指数
#   · QThread 异步请求，不阻塞界面；30 分钟自动刷新
#   · 失败时使用缓存兜底，不弹错误框
#   · API Host 可配置（和风天气新版要求每个开发者使用专属 Host）
# ==========================================================================

import os
from datetime import datetime

from PySide6.QtCore import QObject, QThread, Signal, QTimer

from utils import data_file, load_json, save_json


# ------------------------------------------------------------------
#  预警等级 → 颜色（新版预警数据自带 color 字段，兼容映射）
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
    """把预警 API 返回的 color 代码映射为十六进制颜色。"""
    if not color_key:
        return "#EF4444"
    return WARNING_COLORS.get(str(color_key).lower(), "#EF4444")


def aqi_color(aqi):
    """根据 AQI 数值返回等级颜色。"""
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
    """后台请求线程：定位 + 实时天气 + 空气质量 + 预警 + 预报。"""

    ok = Signal(dict)
    fail = Signal(dict)

    IP_API = "http://ip-api.com/json/"
    GEO_PATH = "/geo/v2/city/lookup"
    NOW_PATH = "/v7/weather/now"
    AIR_PATH = "/v7/air/now"
    WARN_PATH = "/v7/warning/now"
    FORECAST_PATH = "/v7/weather/7d"
    HOURLY_PATH = "/v7/weather/24h"
    MINUTELY_PATH = "/v7/minutely/5m"
    INDICES_PATH = "/v7/indices/1d"
    TIMEOUT = 8

    def __init__(self, api_key, city, api_host, auto_locate, parent=None):
        super().__init__(parent)
        self.api_key = (api_key or "").strip()
        self.city = (city or "").strip()
        self.api_host = (api_host or "https://api.qweather.com").strip().rstrip("/")
        self.auto_locate = auto_locate

    # ------------------------------------------------------------------
    #  HTTP 封装
    # ------------------------------------------------------------------
    def _headers(self):
        """新接口用 X-QW-Api-Key 头，旧接口用 key 查询参数，两者都带上。"""
        return {"X-QW-Api-Key": self.api_key}

    def _get(self, path, params):
        """发起 GET 请求并解析 JSON，失败返回 None。"""
        import requests
        query = dict(params)
        query.setdefault("key", self.api_key)     # 兼容旧接口
        query.setdefault("lang", "zh")
        resp = requests.get(
            self.api_host + path,
            params=query,
            headers=self._headers(),
            timeout=self.TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        return resp.json()

    @staticmethod
    def _code_ok(data):
        return data is not None and data.get("code") in ("200", "2001")

    # ------------------------------------------------------------------
    #  自动定位（IP）
    # ------------------------------------------------------------------
    def _auto_locate(self):
        """通过公网 IP 获取当前电脑的经纬度与城市。"""
        try:
            import requests
            resp = requests.get(self.IP_API, params={
                "lang": "zh-CN",
                "fields": "status,countryCode,regionName,city,lat,lon",
            }, timeout=6)
            data = resp.json()
            if data.get("status") == "success" and data.get("lat") and data.get("lon"):
                return {
                    "lat": data["lat"],
                    "lon": data["lon"],
                    "city": data.get("city") or data.get("regionName") or "",
                }
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    #  城市 → Location ID
    # ------------------------------------------------------------------
    def _geo_lookup(self, location):
        data = self._get(self.GEO_PATH, {"location": location, "number": 1})
        if not self._code_ok(data) or not data.get("location"):
            return None
        loc = data["location"][0]
        return {
            "id": loc["id"],
            "name": loc.get("name", ""),
            "adm2": loc.get("adm2", ""),
            "adm1": loc.get("adm1", ""),
        }

    # ------------------------------------------------------------------
    #  主流程
    # ------------------------------------------------------------------
    def run(self):
        """在工作线程内依次获取定位与各类天气数据。"""
        try:
            if not self.api_key or "请填写" in self.api_key or "你的API密钥" in self.api_key:
                self.fail.emit({"message": "未配置API密钥"})
                return

            import requests  # 确保 requests 可用

            # 1. 定位：自动定位优先，否则按手动城市名
            located = self._auto_locate() if self.auto_locate else None
            city_name = ""
            if located:
                geo = self._geo_lookup("%s,%s" % (located["lat"], located["lon"]))
            else:
                geo = self._geo_lookup(self.city or "北京")
            if not geo:
                self.fail.emit({"message": "城市编码查询失败"})
                return

            location_id = geo["id"]
            city_name = located.get("city") if located else geo["adm2"] or geo["name"]

            # 2. 实时天气
            now = self._get(self.NOW_PATH, {"location": location_id})
            if not self._code_ok(now) or "now" not in now:
                self.fail.emit({"message": "天气查询失败"})
                return
            now_data = now["now"]

            # 3. 空气质量 / 预警 / 预报等（失败不阻塞主流程）
            air = self._get(self.AIR_PATH, {"location": location_id})
            air_data = air.get("now") if air and self._code_ok(air) else {}

            warn = self._get(self.WARN_PATH, {"location": location_id})
            warnings = self._parse_warnings(warn)

            forecast = self._get(self.FORECAST_PATH, {"location": location_id})
            daily = forecast.get("daily", []) if forecast and self._code_ok(forecast) else []

            hourly = self._get(self.HOURLY_PATH, {"location": location_id})
            hourly_data = hourly.get("hourly", []) if hourly and self._code_ok(hourly) else []

            minutely = self._get(self.MINUTELY_PATH, {"location": location_id})
            minutely_data = minutely.get("summary", "") if minutely and self._code_ok(minutely) else ""

            indices = self._get(self.INDICES_PATH, {"location": location_id, "type": "1,2,3,5,6"})
            indices_data = indices.get("daily", []) if indices and self._code_ok(indices) else []

            result = {
                "temp": now_data.get("temp", "--"),
                "feels_like": now_data.get("feelsLike", "--"),
                "text": now_data.get("text", "未知"),
                "code": self._icon_code(now_data.get("icon")),
                "icon": now_data.get("icon", "999"),
                "wind_dir": now_data.get("windDir", ""),
                "wind_scale": now_data.get("windScale", ""),
                "wind_speed": now_data.get("windSpeed", ""),
                "humidity": now_data.get("humidity", "--"),
                "pressure": now_data.get("pressure", "--"),
                "vis": now_data.get("vis", "--"),
                "precip": now_data.get("precip", "--"),
                "cloud": now_data.get("cloud", "--"),
                "dew": now_data.get("dew", "--"),
                "air": {
                    "aqi": air_data.get("aqi", "--"),
                    "category": air_data.get("category", ""),
                    "primary": air_data.get("primary", ""),
                    "pm2p5": air_data.get("pm2p5", "--"),
                    "pm10": air_data.get("pm10", "--"),
                    "o3": air_data.get("o3", "--"),
                    "no2": air_data.get("no2", "--"),
                    "so2": air_data.get("so2", "--"),
                    "co": air_data.get("co", "--"),
                } if air_data else None,
                "warnings": warnings,
                "daily": daily,
                "hourly": hourly_data,
                "minutely": minutely_data,
                "indices": indices_data,
                "city": city_name,
                "location": {
                    "name": geo["name"],
                    "adm2": geo["adm2"],
                    "adm1": geo["adm1"],
                    "id": location_id,
                },
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "provider": "hefeng",
            }
            self.ok.emit(result)
        except Exception as exc:
            self.fail.emit({"message": "网络异常: %s" % type(exc).__name__})

    # ------------------------------------------------------------------
    #  预警解析
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_warnings(data):
        if not data or not data.get("warning"):
            return []
        result = []
        for w in data["warning"]:
            result.append({
                "id": w.get("id", ""),
                "sender": w.get("sender", ""),
                "title": w.get("title", "天气预警"),
                "type": w.get("type", ""),
                "typeName": w.get("typeName", ""),
                "level": w.get("level", ""),
                "color": w.get("color", "red"),
                "color_hex": warning_color_hex(w.get("color")),
                "text": w.get("text", ""),
                "pubTime": w.get("pubTime", ""),
            })
        return result

    @staticmethod
    def _icon_code(icon):
        """把和风 icon 字符串安全转换为整数，供图标绘制分类使用。"""
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
        self.api_key = self.config.get("weather_api_key", "")
        self.city = self.config.get("weather_city", "北京")
        self.api_host = self.config.get("api_host", "https://api.qweather.com")
        self.auto_locate = bool(self.config.get("auto_locate", True))
        self._worker = None
        self.cache = self._load_cache()

        self.timer = QTimer(self)
        self.timer.setInterval(self.AUTO_REFRESH_MS)
        self.timer.timeout.connect(self.refresh)

    # ------------------------------------------------------------------
    #  生命周期
    # ------------------------------------------------------------------
    def start(self):
        """启动天气管理：立即刷新一次 + 开启 30 分钟定时器。"""
        self.refresh()
        self.timer.start()

    def stop(self):
        """停止定时器并等待后台线程退出，避免退出时崩溃。"""
        self.timer.stop()
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait(9000)

    def refresh(self):
        """发起一次异步天气刷新（若已有请求在跑则跳过）。"""
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = WeatherWorker(
            self.api_key, self.city, self.api_host, self.auto_locate)
        self._worker.ok.connect(self._on_ok)
        self._worker.fail.connect(self._on_fail)
        self._worker.start()

    def update_config(self, config):
        """设置/天气页保存后更新配置并立刻刷新。"""
        self.config = config
        self.api_key = config.get("weather_api_key", "")
        self.city = config.get("weather_city", "北京")
        self.api_host = config.get("api_host", "https://api.qweather.com")
        self.auto_locate = bool(config.get("auto_locate", True))
        self.refresh()

    # ------------------------------------------------------------------
    #  内部回调
    # ------------------------------------------------------------------
    def _on_ok(self, data):
        """请求成功：写入缓存并广播。"""
        self.cache = data
        self._save_cache(data)
        data["cached"] = False
        self.updated.emit(data)

    def _on_fail(self, info):
        """请求失败：携带缓存数据广播（岛窗据此展示 '[缓存] ...'）。"""
        cached = dict(self.cache) if self.cache else None
        self.failed.emit({
            "cached": cached,
            "message": info.get("message", "网络异常"),
        })

    # ------------------------------------------------------------------
    #  缓存
    # ------------------------------------------------------------------
    def cache_path(self):
        return data_file("weather_cache.json")

    def _load_cache(self):
        data = load_json(self.cache_path(), None)
        return data if isinstance(data, dict) else None

    def _save_cache(self, data):
        try:
            save_json(self.cache_path(), data)
        except Exception:
            pass
