# ==========================================================================
#  易课 EasyClass v1.0.0 | Silicon UI
#  hitokoto.py  ——  每日一言（Hitokoto）获取模块
#  -------------------------------------------------------------------------
#  职责：
#   · 后台线程请求 https://v1.hitokoto.cn/ 获取随机句子（免费、无需 API Key）
#   · 按最大字数筛选：句子+出处总长超过 max_len 的丢弃；出处过长则只保留句子
#   · 一次获取一批（count 条合格句子），供程序启动时预缓存
#   · 失败静默，不影响主界面
# ==========================================================================

import logging

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class HitokotoFetcher(QThread):
    """后台批量获取经过字数筛选的一言句子。"""

    ok = Signal(list)       # 合格句子列表：[{'hitokoto':..., 'from':...}, ...]
    fail = Signal(str)      # 失败原因

    URL = "https://v1.hitokoto.cn/"
    TIMEOUT = 8

    def __init__(self, category="", count=5, max_len=21, parent=None):
        super().__init__(parent)
        self.category = (category or "").strip()
        self.count = max(1, int(count))
        self.max_len = max(4, int(max_len))

    @staticmethod
    def _acceptable(data, max_len):
        """判断一条句子是否放得下（只算句子 + 书名号，<= max_len 字）。"""
        sentence = (data.get("hitokoto") or "").strip()
        if not sentence:
            return None
        plain = "「%s」" % sentence
        if len(plain) <= max_len:
            return {"hitokoto": sentence, "from": ""}
        return None

    def run(self):
        import requests
        got = 0
        attempts = 0
        max_attempts = max(self.count * 8, 24)
        while got < self.count and attempts < max_attempts:
            attempts += 1
            try:
                params = {"charset": "utf-8"}
                if self.category:
                    params["c"] = self.category
                resp = requests.get(self.URL, params=params, timeout=self.TIMEOUT)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                acc = self._acceptable(data, self.max_len)
                if acc:
                    got += 1
                    # 逐条推送：第一条尽快显示，其余入缓存
                    logger.info("一言获取成功(%d/%d): %s", got, self.count,
                                (acc.get("hitokoto") or "")[:20])
                    self.ok.emit([acc])
            except Exception as exc:
                logger.warning("一言请求异常: %s", type(exc).__name__)
                break
        if got == 0:
            logger.warning("一言获取失败：未取到合格字数的句子（max_len=%d）", self.max_len)
            self.fail.emit("no fit quote")
