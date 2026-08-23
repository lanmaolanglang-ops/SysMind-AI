from __future__ import annotations

from sysmind.domain.diagnosis import DiagnosisCategory


def classify_question(question: str) -> tuple[DiagnosisCategory, bool]:
    normalized = question.casefold()
    groups: tuple[tuple[DiagnosisCategory, tuple[str, ...]], ...] = (
        ("network", ("网络", "联网", "上网", "dns", "ping", "代理", "network", "internet")),
        ("crash", ("崩溃", "闪退", "报错", "crash", "exception", "停止工作")),
        ("performance", ("卡", "慢", "掉帧", "cpu", "内存", "磁盘", "风扇", "performance")),
    )
    matches = [category for category, words in groups if any(word in normalized for word in words)]
    return (matches[0] if matches else "performance", len(matches) == 1)
