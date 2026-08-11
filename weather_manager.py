# ==========================================================================
#  易课 EasyClass v1.0.0 | Silicon UI
#  weather_manager.py  ——  天气管理模块（和风天气）
#  -------------------------------------------------------------------------
#  职责：
#   · 调用和风天气免费 API 获取实时天气（QThread 异步，不阻塞界面）
#   · 30 分钟自动更新；最近一次成功数据写入 weather_cache.json
#   · 网络异常时输出缓存数据（岛窗显示 "[缓存] ..."），不弹错误框
#   · 免费版 API 说明：https://dev.qweather.com/
# ==========================================================================

import os
from datetime import datetime

from PySide6.QtCore import QObject, QThread, Signal, QTimer

from utils import BASE_DIR, load_json, save_json


class WeatherWorker(QThread):
    """后台请求线程：城市编码查询 + 实时天气查询。"""

    ok = Signal(dict)
    fail = Signal(dict)

    GEO_API = "https://geoapi.qweather.com/v2/city/lookup"
    NOW_API = "https://devapi.qweather.com/v7/weather/now"
    TIMEOUT = 8

    def __init__(self, api_key, city, parent=None):
        super().__init__(parent)
        self.api_key = api_key
        self.city = city

    def run(self):
        """在工作线程内执行网络请求，结果通过信号返回。"""
        try:
            # 未配置密钥：不联网，直接告知"未配置"
            if not self.api_key or "请填写" in self.api_key or "你的API密钥" in self.api_key:
                self.fail.emit({"message": "未配置API密钥"})
                return

            import requests

            # 1. 城市编码查询
            geo_resp = requests.get(
                self.GEO_API,
                params={"location": self.city, "key": self.api_key},
                timeout=self.TIMEOUT,
            )
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()
            if geo_data.get("code") != "200" or not geo_data.get("location"):
                self.fail.emit({"message": "城市编码查询失败"})
                return
            location_id = geo_data["location"][0]["id"]

            # 2. 实时天气查询
            now_resp = requests.get(
                self.NOW_API,
                params={"location": location_id, "key": self.api_key},
                timeout=self.TIMEOUT,
            )
            now_resp.raise_for_status()
            now_data = now_resp.json()
            if now_data.get("code") != "200" or "now" not in now_data:
                self.fail.emit({"message": "天气查询失败"})
                return

            now = now_data["now"]
            result = {
                "temp": now.get("temp", "--"),
                "feels_like": now.get("feelsLike", "--"),
                "text": now.get("text", "未知"),
                "code": self._icon_code(now.get("icon")),
                "city": self.city,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "provider": "hefeng",
            }
            self.ok.emit(result)
        except Exception as exc:
            self.fail.emit({"message": "网络异常: %s" % type(exc).__name__})

    @staticmethod
    def _icon_code(icon):
        """把和风 icon 字符串安全转换为整数，供图标绘制分类使用。"""
        try:
            return int(icon)
        except (TypeError, ValueError):
            return 999


class WeatherManager(QObject):
    """天气管理器：负责调度刷新线程、缓存与信号转发。"""

    updated = Signal(dict)   # 成功：{"temp","text","code","city","time","cached"}
    failed = Signal(dict)    # 失败：{"cached": 最近缓存或None, "message": str}

    AUTO_REFRESH_MS = 30 * 60 * 1000  # 30 分钟

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config if config is not None else {}
        self.api_key = self.config.get("weather_api_key", "")
        self.city = self.config.get("weather_city", "北京")
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
        self._worker = WeatherWorker(self.api_key, self.city)
        self._worker.ok.connect(self._on_ok)
        self._worker.fail.connect(self._on_fail)
        self._worker.start()

    def update_config(self, config):
        """设置/天气页保存后更新配置并立刻刷新。"""
        self.config = config
        self.api_key = config.get("weather_api_key", "")
        self.city = config.get("weather_city", "北京")
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
        return os.path.join(BASE_DIR, "weather_cache.json")

    def _load_cache(self):
        data = load_json(self.cache_path(), None)
        return data if isinstance(data, dict) else None

    def _save_cache(self, data):
        try:
            save_json(self.cache_path(), data)
        except Exception:
            pass
