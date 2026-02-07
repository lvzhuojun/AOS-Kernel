"""
持久化记忆层（MemoryManager）

- 将 state.memory 中的 lessons_learned 保存到本地 memory.json
- RecoveryAgent 成功完成 REPLAN 后写入经验
- IntentParser 启动时加载 memory.json 中的历史经验
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_MEMORY_PATH = Path(__file__).resolve().parent.parent / "memory.json"


def _normalize_for_match(text: str) -> set[str]:
    """简单分词得到关键词集合，用于相似度匹配。"""
    text = (text or "").strip().lower()
    tokens = re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]+", text)
    return set(t for t in tokens if len(t) > 0)


# 动作关键词：用于区分「读/创建/运行/删除」等不同意图，避免「读取文件」误用「创建文件」的缓存
_ACTION_READ = {"读", "读取", "read", "打开", "open", "查看", "view", "列出", "list"}
_ACTION_CREATE_WRITE = {"创建", "写", "写入", "create", "write", "新建", "添加", "add"}
_ACTION_RUN = {"运行", "执行", "run", "execute"}
_ACTION_DELETE = {"删除", "delete", "移除", "remove"}


def _get_action_tags(tokens: set[str]) -> set[str]:
    """从意图分词中提取动作标签，用于校验缓存是否同质。"""
    tags = set()
    for t in tokens:
        if t in _ACTION_READ:
            tags.add("read")
        elif t in _ACTION_CREATE_WRITE:
            tags.add("create")
        elif t in _ACTION_RUN:
            tags.add("run")
        elif t in _ACTION_DELETE:
            tags.add("delete")
    return tags


class MemoryManager:
    """持久化记忆：lessons_learned + successful_plans（语义缓存）。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path or _DEFAULT_MEMORY_PATH)

    def _load_raw(self) -> Dict[str, Any]:
        """读取 memory.json 为字典；文件不存在或异常时返回空字典。"""
        if not self._path.is_file():
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_raw(self, data: Dict[str, Any]) -> None:
        """将字典写入 memory.json（UTF-8，保留其它键）。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_lessons(self) -> List[Dict[str, Any]]:
        """加载 lessons_learned 列表（恢复层写入的经验）。"""
        data = self._load_raw()
        out = data.get("lessons_learned")
        return out if isinstance(out, list) else []

    def save_lessons(self, lessons_learned: List[Dict[str, Any]]) -> None:
        data = self._load_raw()
        data["lessons_learned"] = lessons_learned
        self._save_raw(data)

    def append_lesson(self, lesson: Dict[str, Any], max_entries: int = 100) -> None:
        """追加一条恢复经验到 lessons_learned，保留最近 max_entries 条。"""
        lessons = self.load_lessons()
        lessons.append(lesson)
        self.save_lessons(lessons[-max_entries:])

    def load_successful_plans(self) -> List[Dict[str, Any]]:
        """加载 successful_plans 列表（意图 + 计划）。"""
        data = self._load_raw()
        out = data.get("successful_plans")
        return out if isinstance(out, list) else []

    def record_successful_plan(
        self, intent: str, plan: List[Dict[str, Any]], max_entries: int = 50
    ) -> None:
        """将一次成功执行的意图与计划写入 successful_plans，供语义缓存匹配。"""
        if not intent or not plan:
            return
        plans = self.load_successful_plans()
        plans = [p for p in plans if (p.get("intent") or "").strip() != intent.strip()]
        plans.append({"intent": intent.strip(), "plan": list(plan)})
        data = self._load_raw()
        data["successful_plans"] = plans[-max_entries:]
        self._save_raw(data)

    def find_similar_lesson(self, intent: str) -> Optional[Dict[str, Any]]:
        """
        关键词/模糊匹配：是否有类似意图的成功计划，返回 {intent, plan} 或 None。
        提高阈值并做动作校验，避免「读取文件」误用「创建文件」的计划缓存。
        """
        intent = (intent or "").strip()
        if not intent:
            return None
        current_tokens = _normalize_for_match(intent)
        if len(current_tokens) < 1:
            return None
        current_actions = _get_action_tags(current_tokens)
        min_overlap = 4  # 至少 4 个关键词重叠（原 2 太宽松）
        min_ratio = 0.4  # 重叠数 / min(|当前|, |历史|) >= 0.4

        for entry in reversed(self.load_successful_plans()):
            stored_intent = (entry.get("intent") or "").strip()
            stored_plan = entry.get("plan")
            if not stored_plan or not isinstance(stored_plan, list):
                continue
            stored_tokens = _normalize_for_match(stored_intent)
            stored_actions = _get_action_tags(stored_tokens)
            # 动作不一致则不复用：例如当前是「读」、历史是「创建」则跳过
            if current_actions and stored_actions and not (current_actions & stored_actions):
                continue
            overlap = len(current_tokens & stored_tokens)
            if overlap < min_overlap:
                if not (stored_intent in intent or intent in stored_intent):
                    continue
            else:
                ratio = overlap / min(len(current_tokens), len(stored_tokens)) if stored_tokens else 0
                if ratio < min_ratio:
                    continue
            return {"intent": stored_intent, "plan": stored_plan}
        return None

    def load_intent_cache(self) -> List[Dict[str, Any]]:
        """加载意图解析缓存列表，每项含 user_input 与解析结果。"""
        data = self._load_raw()
        out = data.get("intent_cache")
        return out if isinstance(out, list) else []

    def get_intent_from_cache(self, user_input: str) -> Optional[Dict[str, Any]]:
        """若 user_input 与缓存中某条完全一致，返回该条解析结果（不含 user_input 键），否则返回 None。"""
        key = (user_input or "").strip()
        if not key:
            return None
        for entry in reversed(self.load_intent_cache()):
            if (entry.get("user_input") or "").strip() == key:
                return {
                    "intent": entry.get("intent", ""),
                    "constraints": list(entry.get("constraints") or []),
                    "suggested_tools": list(entry.get("suggested_tools") or []),
                    "confidence": float(entry.get("confidence", 0.5)),
                    "clarification_questions": list(entry.get("clarification_questions") or []),
                }
        return None

    def add_intent_to_cache(
        self,
        user_input: str,
        intent: str,
        constraints: List[str],
        suggested_tools: List[str],
        confidence: float,
        clarification_questions: List[str],
        max_entries: int = 50,
    ) -> None:
        """将一次意图解析结果写入缓存（按 user_input 去重，保留最近 max_entries 条）。"""
        key = (user_input or "").strip()
        if not key:
            return
        data = self._load_raw()
        cache = list(data.get("intent_cache") or [])
        cache = [c for c in cache if (c.get("user_input") or "").strip() != key]
        cache.append({
            "user_input": key,
            "intent": (intent or "").strip(),
            "constraints": list(constraints or []),
            "suggested_tools": list(suggested_tools or []),
            "confidence": float(confidence),
            "clarification_questions": list(clarification_questions or []),
        })
        data["intent_cache"] = cache[-max_entries:]
        self._save_raw(data)


__all__ = ["MemoryManager"]
