# ==========================================================================
#  易课 EasyClass v1.0.0 | Silicon UI
#  weather_manager.py  ——  天气管理模块（和风天气）
#  -------------------------------------------------------------------------
#  职责：
#   · 自动定位：通过公网 IP 获取当前电脑位置（经纬度），保留手动填城市选项
#   · 实时天气 + 7天预报 + 24小时预报（经 LocationID）+ 空气质量 + 天气预警（经经纬度）
#   · QThread 异步请求，不阻塞界面；30 分钟自动刷新
#   · 失败时使用缓存兜底，不弹错误框
#   · API Host 可配置（和风天气新版要求每个开发者使用专属 Host）
#   · 注：GeoAPI 可能被账号安全限制拦截，故 LocationID 用内置城市表兜底
# ==========================================================================

import logging
import time
from datetime import datetime

from PySide6.QtCore import QObject, QThread, Signal, QTimer

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
#  内置城市表：城市名 → LocationID + 经纬度（GeoAPI 不可用时兜底）
#  覆盖各直辖市 / 省会 / 计划单列市 / 主要地级市
# ------------------------------------------------------------------
CITY_LOCATIONS = {
    "北京": {"id": "101010100", "lat": "39.90", "lon": "116.41"},
    "上海": {"id": "101020100", "lat": "31.23", "lon": "121.47"},
    "天津": {"id": "101030100", "lat": "39.08", "lon": "117.20"},
    "重庆": {"id": "101040100", "lat": "29.56", "lon": "106.55"},
    "哈尔滨": {"id": "101050101", "lat": "45.80", "lon": "126.53"},
    "长春": {"id": "101060101", "lat": "43.88", "lon": "125.32"},
    "沈阳": {"id": "101070101", "lat": "41.80", "lon": "123.43"},
    "呼和浩特": {"id": "101080101", "lat": "40.84", "lon": "111.75"},
    "石家庄": {"id": "101090101", "lat": "38.04", "lon": "114.51"},
    "太原": {"id": "101100101", "lat": "37.87", "lon": "112.55"},
    "西安": {"id": "101110101", "lat": "34.34", "lon": "108.94"},
    "济南": {"id": "101120101", "lat": "36.67", "lon": "117.00"},
    "乌鲁木齐": {"id": "101130101", "lat": "43.83", "lon": "87.62"},
    "拉萨": {"id": "101140101", "lat": "29.65", "lon": "91.14"},
    "西宁": {"id": "101150101", "lat": "36.62", "lon": "101.78"},
    "兰州": {"id": "101160101", "lat": "36.06", "lon": "103.83"},
    "银川": {"id": "101170101", "lat": "38.49", "lon": "106.23"},
    "郑州": {"id": "101180101", "lat": "34.75", "lon": "113.62"},
    "南京": {"id": "101190101", "lat": "32.06", "lon": "118.80"},
    "武汉": {"id": "101200101", "lat": "30.59", "lon": "114.31"},
    "杭州": {"id": "101210101", "lat": "30.27", "lon": "120.16"},
    "合肥": {"id": "101220101", "lat": "31.82", "lon": "117.23"},
    "福州": {"id": "101230101", "lat": "26.07", "lon": "119.30"},
    "南昌": {"id": "101240101", "lat": "28.68", "lon": "115.86"},
    "长沙": {"id": "101250101", "lat": "28.23", "lon": "112.94"},
    "贵阳": {"id": "101260101", "lat": "26.65", "lon": "106.63"},
    "成都": {"id": "101270101", "lat": "30.57", "lon": "104.07"},
    "广州": {"id": "101280101", "lat": "23.13", "lon": "113.26"},
    "昆明": {"id": "101290101", "lat": "24.88", "lon": "102.83"},
    "南宁": {"id": "101300101", "lat": "22.82", "lon": "108.37"},
    "海口": {"id": "101310101", "lat": "20.04", "lon": "110.20"},
    "深圳": {"id": "101280601", "lat": "22.54", "lon": "114.06"},
    "青岛": {"id": "101120201", "lat": "36.07", "lon": "120.38"},
    "大连": {"id": "101070201", "lat": "38.91", "lon": "121.61"},
    "厦门": {"id": "101230201", "lat": "24.48", "lon": "118.09"},
    "宁波": {"id": "101210401", "lat": "29.87", "lon": "121.55"},
    "苏州": {"id": "101190401", "lat": "31.30", "lon": "120.58"},
    "无锡": {"id": "101190201", "lat": "31.49", "lon": "120.31"},
    "温州": {"id": "101210701", "lat": "28.00", "lon": "120.70"},
    "佛山": {"id": "101280800", "lat": "23.02", "lon": "113.12"},
    "东莞": {"id": "101281601", "lat": "23.02", "lon": "113.75"},
    "珠海": {"id": "101280701", "lat": "22.27", "lon": "113.58"},
    "汕头": {"id": "101280501", "lat": "23.35", "lon": "116.68"},
    "惠州": {"id": "101280301", "lat": "23.11", "lon": "114.42"},
    "泉州": {"id": "101230501", "lat": "24.87", "lon": "118.68"},
    "烟台": {"id": "101120501", "lat": "37.46", "lon": "121.45"},
    "潍坊": {"id": "101120601", "lat": "36.71", "lon": "119.16"},
    "徐州": {"id": "101190801", "lat": "34.20", "lon": "117.28"},
    "常州": {"id": "101191101", "lat": "31.81", "lon": "119.97"},
    "南通": {"id": "101190501", "lat": "31.98", "lon": "120.89"},
    "嘉兴": {"id": "101210301", "lat": "30.75", "lon": "120.75"},
    "绍兴": {"id": "101210501", "lat": "30.03", "lon": "120.58"},
    "金华": {"id": "101210901", "lat": "29.08", "lon": "119.65"},
    "台州": {"id": "101210601", "lat": "28.66", "lon": "121.42"},
    "临海": {"id": "101210610", "lat": "28.85", "lon": "121.14"},
    "温岭": {"id": "101210611", "lat": "28.37", "lon": "121.37"},
    "玉环": {"id": "101210612", "lat": "28.13", "lon": "121.23"},
    "中山": {"id": "101281701", "lat": "22.52", "lon": "113.39"},
    "江门": {"id": "101281101", "lat": "22.58", "lon": "113.08"},
    "湛江": {"id": "101281001", "lat": "21.27", "lon": "110.36"},
    "桂林": {"id": "101300501", "lat": "25.27", "lon": "110.29"},
    "柳州": {"id": "101300301", "lat": "24.31", "lon": "109.42"},
    "三亚": {"id": "101310201", "lat": "18.25", "lon": "109.51"},
    "洛阳": {"id": "101180901", "lat": "34.62", "lon": "112.45"},
    "唐山": {"id": "101090501", "lat": "39.63", "lon": "118.18"},
    "保定": {"id": "101090201", "lat": "38.87", "lon": "115.46"},
    "邯郸": {"id": "101091001", "lat": "36.63", "lon": "114.54"},
    "香港": {"id": "101320101", "lat": "22.32", "lon": "114.17"},
    "澳门": {"id": "101330101", "lat": "22.19", "lon": "113.54"},
    "台北": {"id": "101340101", "lat": "25.03", "lon": "121.57"},
    "高雄": {"id": "101340201", "lat": "22.62", "lon": "120.31"},
}

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
    NOW_PATH = "/v7/weather/now"
    FORECAST_PATH = "/v7/weather/7d"
    HOURLY_PATH = "/v7/weather/24h"
    AIR_PATH = "/airquality/v1/current/{lat}/{lon}"
    WARN_PATH = "/weatheralert/v1/current/{lat}/{lon}"
    INDICES_PATH = "/v7/indices/1d"
    INDICES_TYPES = "1,2,3,5,6"   # 1穿衣 2洗车 3感冒 5运动 6紫外线
    TIMEOUT = 8

    def __init__(self, api_key, city, api_host, auto_locate, parent=None):
        super().__init__(parent)
        self.api_key = (api_key or "").strip()
        self.city = (city or "").strip()
        self.api_host = (api_host or "https://api.qweather.com").strip().rstrip("/")
        self.auto_locate = auto_locate
        self._last_error = ""

    # ------------------------------------------------------------------
    #  HTTP 封装
    # ------------------------------------------------------------------
    def _headers(self):
        """新接口用 X-QW-Api-Key 头，旧接口用 key 查询参数，两者都带上。"""
        return {"X-QW-Api-Key": self.api_key}

    def _get(self, path, params):
        """发起 GET 请求并解析 JSON；失败时记录错误详情并返回 None。"""
        import requests
        query = dict(params)
        query.setdefault("key", self.api_key)     # 兼容旧接口
        query.setdefault("lang", "zh")
        try:
            resp = requests.get(
                self.api_host + path,
                params=query,
                headers=self._headers(),
                timeout=self.TIMEOUT,
            )
        except Exception as exc:
            self._last_error = "网络异常: %s" % type(exc).__name__
            return None
        if resp.status_code == 200:
            return resp.json()
        # 解析 API 错误信息（如 Security Restriction 等），便于在界面提示
        detail = ""
        try:
            err = resp.json().get("error", {})
            detail = err.get("detail") or err.get("title") or ""
        except Exception:
            pass
        self._last_error = detail or "HTTP %s" % resp.status_code
        return None

    # ------------------------------------------------------------------
    #  自动定位（IP）
    # ------------------------------------------------------------------
    def _auto_locate(self):
        """
        通过公网 IP 获取当前电脑的经纬度与城市。
        
        Returns:
            dict | None: 包含 lat, lon, city 的字典，失败返回 None
        """
        import requests
        
        try:
            response = requests.get(
                self.IP_API,
                params={
                    "lang": "zh-CN",
                    "fields": "status,countryCode,regionName,city,lat,lon"
                },
                timeout=6,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "success":
                lat = data.get("lat")
                lon = data.get("lon")
                if lat is not None and lon is not None:
                    return {
                        "lat": float(lat),
                        "lon": float(lon),
                        "city": data.get("city") or data.get("regionName") or "未知城市",
                    }
                    
        except Exception as e:
            logger.debug(f"IP 定位失败: {e}")
            
        return None

    @staticmethod
    def _city_lookup(city_name):
        """在内置城市表中查询城市，返回 {id, lat, lon} 或 None。"""
        name = (city_name or "").strip()
        return CITY_LOCATIONS.get(name)

    # ------------------------------------------------------------------
    #  主流程
    # ------------------------------------------------------------------
    def run(self):
        """在工作线程内依次获取定位与各类天气数据。"""
        try:
            if not self.api_key or "请填写" in self.api_key or "你的API密钥" in self.api_key:
                logger.warning("天气刷新失败：未配置 API Key")
                self.fail.emit({"message": "未配置API密钥"})
                return

            # 1. 定位：开启自动定位 → 用 IP；关闭 → 用内置城市表
            located = self._auto_locate() if self.auto_locate else None
            city_name = self.city
            lat = lon = None
            if located:
                lat, lon = located["lat"], located["lon"]
                if not city_name:
                    city_name = located.get("city", "")
                logger.info("天气定位成功(IP): 城市=%s 经纬度=%s,%s", city_name, lat, lon)

            # 统一位置基准：城市名在表内一律用表内(城市中心)坐标，
            # 保证 IP 定位与手动填写同一城市时天气一致，且以更准的城市中心天气为准
            loc = self._city_lookup(city_name) if city_name else None
            if not loc and lat is None:
                loc = self._city_lookup(self.city)
                if not loc:
                    logger.warning("天气刷新失败：未收录城市 %s", self.city)
                    self.fail.emit({"message": "未收录城市：%s，请在天气设置中重新指定" % self.city})
                    return
            if loc:
                lat, lon = loc["lat"], loc["lon"]
                city_name = city_name or self.city
                logger.info("天气定位成功(城市表): 城市=%s 经纬度=%s,%s", city_name, lat, lon)

            # 2. 城市 → LocationID（内置表兜底，缺省用北京）
            city_loc = self._city_lookup(city_name) or self._city_lookup(self.city)
            location_id = (city_loc or CITY_LOCATIONS["北京"])["id"]
            city_name = city_name or self.city or "北京"
            # 城市名在表内用 LocationID（与手动填写完全一致）；表外城市用 IP 经纬度查询
            location_param = location_id if city_loc else ("%s,%s" % (lon, lat) if lat and lon else location_id)

            # 3. 实时天气
            now = self._get(self.NOW_PATH, {"location": location_param})
            if not now or now.get("code") != "200" or "now" not in now:
                logger.warning("天气查询失败: %s", self._last_error or "未知错误")
                self.fail.emit({"message": "天气查询失败：%s" % (self._last_error or "未知错误")})
                return
            now_data = now["now"]
            logger.info("实时天气: %s %s°C 体感%s°C 湿度%s%%",
                        now_data.get("text", "?"), now_data.get("temp", "?"),
                        now_data.get("feelsLike", "?"), now_data.get("humidity", "?"))

            # 4. 空气质量 / 预警（按经纬度，失败不阻塞主流程）
            air = self._get(self.AIR_PATH.format(lat=lat, lon=lon), {})
            air_data = self._parse_air(air)

            warn = self._get(self.WARN_PATH.format(lat=lat, lon=lon), {})
            warnings = self._parse_warnings(warn)

            # 5. 预报（失败不阻塞主流程）
            forecast = self._get(self.FORECAST_PATH, {"location": location_param})
            daily = forecast.get("daily", []) if forecast and forecast.get("code") == "200" else []

            hourly = self._get(self.HOURLY_PATH, {"location": location_param})
            hourly_data = hourly.get("hourly", []) if hourly and hourly.get("code") == "200" else []

            indices = self._get(self.INDICES_PATH, {
                "location": location_param, "type": self.INDICES_TYPES})
            indices_data = indices.get("daily", []) if indices and indices.get("code") == "200" else []

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
                "air": air_data,
                "warnings": warnings,
                "daily": daily,
                "hourly": hourly_data,
                "minutely": "",
                "indices": indices_data,
                "city": city_name,
                "location": {
                    "id": location_id,
                    "lat": lat,
                    "lon": lon,
                },
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "provider": "hefeng",
            }
            self.ok.emit(result)
        except Exception as exc:
            self.fail.emit({"message": "网络异常: %s" % type(exc).__name__})

    # ------------------------------------------------------------------
    #  空气质量解析（新版 /airquality/v1/current/{lat}/{lon}）
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_air(data):
        if not data:
            return None
        indexes = data.get("indexes") or []
        if not indexes:
            return None
        idx = next((x for x in indexes if x.get("code") == "qaqi"), None) or indexes[0]
        pollutants = {p.get("code"): p for p in (data.get("pollutants") or [])}

        def conc(code):
            p = pollutants.get(code) or {}
            c = p.get("concentration") or {}
            return c.get("value")

        return {
            "aqi": idx.get("aqiDisplay", idx.get("aqi")),
            "category": idx.get("category", ""),
            "level": idx.get("level", ""),
            "code": idx.get("code", ""),
            "primary": (idx.get("primaryPollutant") or {}).get("name", ""),
            "color": idx.get("color"),
            "pm2p5": conc("pm2p5"),
            "pm10": conc("pm10"),
            "o3": conc("o3"),
            "no2": conc("no2"),
            "so2": conc("so2"),
            "co": conc("co"),
        }

    # ------------------------------------------------------------------
    #  预警解析（新版 /weatheralert/v1/current/{lat}/{lon}）
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_warnings(data):
        if not data:
            return []
        alerts = data.get("alerts") or []
        result = []
        for a in alerts:
            color = a.get("color") or {}
            code = color.get("code")
            if code:
                color_hex = warning_color_hex(code)
            elif color.get("red") is not None:
                color_hex = "#%02X%02X%02X" % (
                    color.get("red"), color.get("green"), color.get("blue"))
            else:
                color_hex = "#EF4444"
            result.append({
                "id": a.get("id", ""),
                "sender": a.get("senderName", ""),
                "title": a.get("headline", "天气预警"),
                "type": (a.get("eventType") or {}).get("code", ""),
                "typeName": (a.get("eventType") or {}).get("name", ""),
                "level": code or "",
                "color": code or "red",
                "color_hex": color_hex,
                "text": a.get("description", ""),
                "pubTime": a.get("issuedTime", ""),
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
        self.refresh_minutes = max(1, int(self.config.get("weather_refresh_minutes", 30)))
        self._worker = None
        self._cooldown_until = 0.0
        self.cache = None   # 仅内存保留最近一次成功数据，失败不兜底显示

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

        失败后进入 60 秒冷却：避免在接口被限制时反复请求导致账号冻结。
        手动操作可传 force=True 强制刷新。
        """
        if not force and time.time() < self._cooldown_until:
            return
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = WeatherWorker(
            self.api_key, self.city, self.api_host, self.auto_locate)
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
        self.api_key = config.get("weather_api_key", "")
        self.city = config.get("weather_city", "北京")
        self.api_host = config.get("api_host", "https://api.qweather.com")
        self.auto_locate = bool(config.get("auto_locate", True))
        self.set_refresh_minutes(config.get("weather_refresh_minutes", 30))
        logger.info("天气配置已更新: 城市=%s 自动定位=%s 刷新=%d分钟",
                    self.city, self.auto_locate, self.refresh_minutes)
        self.refresh()

    # ------------------------------------------------------------------
    #  内部回调
    # ------------------------------------------------------------------
    def _on_ok(self, data):
        """请求成功：仅保留在内存，广播实时数据（不再写缓存文件）。"""
        self.cache = data
        data["cached"] = False
        logger.info("天气刷新成功: %s %s°C %s | 预警%d条 | AQI=%s",
                    data.get("city", "?"), data.get("temp", "?"),
                    data.get("text", "?"), len(data.get("warnings") or []),
                    (data.get("air") or {}).get("aqi", "-"))
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