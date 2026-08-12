# ==========================================================================
#  易课 EasyClass v1.0.0 | Silicon UI
#  course_manager.py  ——  课程表数据管理模块
#  -------------------------------------------------------------------------
#  职责：
#   · schedule.json 的读取 / 保存 / 增删改
#   · 根据系统时间判断：当前课程、下一节课、下节课预告（提前10分钟）
#   · 周一~周日七天数据，字典键与 JSON 结构一一对应
# ==========================================================================

import logging
import os
from datetime import datetime, date

from PySide6.QtCore import QObject, Signal

from utils import data_file, load_json, save_json

logger = logging.getLogger(__name__)


class CourseManager(QObject):
    """课程表数据管理器。"""

    changed = Signal()

    # 一周七天的键，顺序：周一~周日
    DAY_KEYS = [
        "monday", "tuesday", "wednesday",
        "thursday", "friday", "saturday", "sunday",
    ]
    DAY_NAMES = [
        "周一", "周二", "周三",
        "周四", "周五", "周六", "周日",
    ]

    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.path = path or data_file("schedule.json")
        self.data = {key: [] for key in self.DAY_KEYS}
        self.load()

    # ------------------------------------------------------------------
    #  持久化
    # ------------------------------------------------------------------
    def load(self):
        """从 schedule.json 载入数据，缺省键自动补齐。"""
        raw = load_json(self.path, {})
        for key in self.DAY_KEYS:
            courses = raw.get(key, [])
            self.data[key] = [c for c in courses if isinstance(c, dict)] if isinstance(courses, list) else []
        logger.info("课程表已加载: %s（共 %d 节课）", self.path,
                    sum(len(v) for v in self.data.values()))

    def save(self):
        """保存到 schedule.json 并广播变更信号。"""
        save_json(self.path, self.data)
        self.changed.emit()
        logger.info("课程表已保存: %s（共 %d 节课）", self.path,
                    sum(len(v) for v in self.data.values()))

    # ------------------------------------------------------------------
    #  数据访问
    # ------------------------------------------------------------------
    def day_key(self, when=None):
        """返回给定日期（默认今天）对应的星期键。date.weekday(): 周一=0。"""
        if when is None:
            when = date.today()
        if isinstance(when, datetime):
            when = when.date()
        return self.DAY_KEYS[when.weekday()]

    def courses_for_day(self, when=None):
        """返回某天按开始时间排序的课程列表。"""
        key = self.day_key(when)
        courses = list(self.data.get(key, []))
        courses.sort(key=lambda c: self._to_minutes(c.get("start", "00:00")))
        return courses

    def add_course(self, day_index, course):
        """向某天添加课程，day_index 为 0~6（周一~周日）。"""
        key = self.DAY_KEYS[day_index]
        self.data[key].append(course)

    def remove_course(self, day_index, index):
        """删除某天的第 index 节课。"""
        key = self.DAY_KEYS[day_index]
        if 0 <= index < len(self.data[key]):
            del self.data[key][index]

    def clear_day(self, day_index):
        """清空某天全部课程。"""
        self.data[self.DAY_KEYS[day_index]] = []

    def total_courses(self, when=None):
        """返回某天的课程总数。"""
        return len(self.courses_for_day(when))

    # ------------------------------------------------------------------
    #  时间判断逻辑
    # ------------------------------------------------------------------
    @staticmethod
    def _to_minutes(hhmm):
        """把 'HH:MM' 转成当天分钟数，非法值返回 -1。"""
        try:
            h, m = hhmm.split(":")
            return int(h) * 60 + int(m)
        except (ValueError, AttributeError):
            return -1

    @staticmethod
    def format_countdown(seconds):
        """
        格式化倒计时（秒 → 文本）：
          <=0 → "00:00"；<60 → "X秒"；<3600 → "MM:SS"；其余 → "HH:MM:SS"
        """
        seconds = max(0, int(seconds))
        if seconds <= 0:
            return "00:00"
        if seconds < 60:
            return "%d秒" % seconds
        if seconds < 3600:
            return "%02d:%02d" % (seconds // 60, seconds % 60)
        return "%02d:%02d:%02d" % (seconds // 3600, (seconds % 3600) // 60, seconds % 60)

    @staticmethod
    def get_progress_percent(remaining, total):
        """进度百分比：(总时长-剩余)/总时长*100，保留 1 位小数，限制 0-100。"""
        try:
            remaining = float(remaining)
            total = float(total)
        except (TypeError, ValueError):
            return 0.0
        if total <= 0:
            return 0.0
        return max(0.0, min(100.0, round((total - remaining) / total * 100, 1)))

    def current_status(self, now=None):
        """
        根据系统时间判断当前课程状态（时间戳毫秒精度），返回 dict：
          - status:   'not_started' 未开始 / 'teaching' 上课中 / 'break' 课间 / 'ended' 已结束
          - empty:    今天是否完全没有课程
          - current:  正在上的课（teaching 时）或 None
          - previous: 刚结束的课（break 时）或 None
          - next:     下一节课（not_started/break 时）或 None
          - remaining: 从下一节开始的今日剩余课程列表
          - countdown: 距下课/上课的剩余秒数（int，>=0）
          - progress:  当前课进度百分比 0-100（teaching 时有效，否则 None）
          - next_minutes: 距下节课上课分钟数（int 或 None）
          - preview:   是否处于下节课提前 10 分钟预告
        """
        if now is None:
            now = datetime.now()
        courses = self.courses_for_day(now)
        if not courses:
            return {"status": "ended", "empty": True, "current": None,
                    "previous": None, "next": None, "remaining": [],
                    "countdown": 0, "progress": None, "next_minutes": None,
                    "preview": False}

        base = datetime(now.year, now.month, now.day)

        def to_ts(hhmm):
            """'HH:MM' → 当天时间戳（秒），与 now.timestamp() 同一时区基准。"""
            try:
                h, m = hhmm.split(":")
                dt = base.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
                return int(dt.timestamp())
            except (ValueError, AttributeError):
                return None

        events = []
        for c in courses:
            s_, e_ = to_ts(c.get("start", "")), to_ts(c.get("end", ""))
            if s_ is not None and e_ is not None and s_ < e_:
                events.append((s_, e_, c))
        events.sort(key=lambda x: x[0])
        if not events:
            return {"status": "ended", "empty": True, "current": None,
                    "previous": None, "next": None, "remaining": [],
                    "countdown": 0, "progress": None, "next_minutes": None,
                    "preview": False}

        now_ts = int(now.timestamp())
        first_start = events[0][0]
        last_end = events[-1][1]

        def build(**kw):
            data = {"status": "ended", "empty": False, "current": None,
                    "previous": None, "next": None, "remaining": [],
                    "countdown": 0, "progress": None, "next_minutes": None,
                    "preview": False}
            data.update(kw)
            return data

        if now_ts < first_start:
            c = events[0][2]
            cd = first_start - now_ts
            # 距上课等待进度：以当天 0 点为起点，随时间流逝递减（0→100% 后开课）
            day_start = int(base.timestamp())
            wait_total = first_start - day_start
            progress = self.get_progress_percent(now_ts - day_start, wait_total) \
                if wait_total > 0 else None
            return build(status="not_started", next=c,
                         remaining=[x[2] for x in events],
                         countdown=cd, progress=progress,
                         next_minutes=cd // 60, preview=cd <= 600)

        if now_ts >= last_end:
            return build(status="ended")

        for i, (s_, e_, c) in enumerate(events):
            if s_ <= now_ts < e_:
                cd = e_ - now_ts
                total = e_ - s_
                progress = self.get_progress_percent(now_ts - s_, total)
                return build(status="teaching", current=c,
                             countdown=cd, progress=progress)
            if now_ts < s_:
                prev = events[i - 1][2] if i > 0 else None
                prev_end = events[i - 1][1] if i > 0 else s_
                cd = s_ - now_ts
                remaining = [x[2] for x in events[i:]]
                # 课间等待进度：上一节课下课 → 下一节课上课
                wait_total = s_ - prev_end
                progress = self.get_progress_percent(now_ts - prev_end, wait_total) \
                    if wait_total > 0 else None
                return build(status="break", previous=prev, next=c,
                             remaining=remaining,
                             countdown=cd, progress=progress,
                             next_minutes=cd // 60, preview=cd <= 600)

        return build(status="ended")
