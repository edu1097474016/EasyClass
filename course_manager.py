# ==========================================================================
#  易课 EasyClass v1.0.0 | Silicon UI
#  course_manager.py  ——  课程表数据管理模块
#  -------------------------------------------------------------------------
#  职责：
#   · schedule.json 的读取 / 保存 / 增删改
#   · 根据系统时间判断：当前课程、下一节课、下节课预告（提前10分钟）
#   · 周一~周日七天数据，字典键与 JSON 结构一一对应
# ==========================================================================

import os
from datetime import datetime, date

from PySide6.QtCore import QObject, Signal

from utils import BASE_DIR, load_json, save_json


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
        self.path = path or os.path.join(BASE_DIR, "schedule.json")
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

    def save(self):
        """保存到 schedule.json 并广播变更信号。"""
        save_json(self.path, self.data)
        self.changed.emit()

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

    def current_status(self, now=None):
        """
        根据系统时间判断当前课程状态，返回 dict：
          - empty:    今天是否完全没有课程
          - current:  正在上的课（dict）或 None
          - next:     下一节课（dict）或 None
          - preview:  是否处于"下节课提前10分钟预告"状态
          - remaining: 当前课程剩余分钟数（无课时为 None）
        """
        if now is None:
            now = datetime.now()
        courses = self.courses_for_day(now)
        if not courses:
            return {"empty": True, "current": None, "next": None,
                    "preview": False, "remaining": None, "next_minutes": None}

        now_min = now.hour * 60 + now.minute
        current = None
        next_course = None
        remaining = None

        for course in courses:
            start = self._to_minutes(course.get("start", ""))
            end = self._to_minutes(course.get("end", ""))
            if start <= now_min < end:
                current = course
                remaining = end - now_min
                break

        if current is None:
            for course in courses:
                start = self._to_minutes(course.get("start", ""))
                if now_min < start:
                    next_course = course
                    break

        # 下节课预告：开始前 10 分钟内
        preview = False
        next_minutes = None
        if next_course is not None:
            start_min = self._to_minutes(next_course.get("start", ""))
            next_minutes = start_min - now_min
            preview = 0 <= next_minutes <= 10

        return {"empty": False, "current": current, "next": next_course,
                "preview": preview, "remaining": remaining, "next_minutes": next_minutes}
