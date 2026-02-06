"""
Intent Parser（意图解析层）

职责：
- 使用 LLM（优先 Gemini 1.5 Pro）将用户输入解析为结构化的 AOSState
- 根据置信度决定是否进入“需求澄清”流程
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.state import AOSState
from utils import LLMClient


INTENT_SYSTEM_PROMPT = """
你是 AOS-Kernel 的“意图解析模块”（Intent Parser）。

目标：
- 读取用户的自然语言指令
- 提取结构化信息：intent, constraints, suggested_tools, confidence, clarification_questions

输出要求：
- 严格输出一个 JSON 对象，不要输出任何解释性文字或多余内容
- 字段定义：
  - intent: 核心目标。使用简洁的一句话概括用户的主要意图。
  - constraints: 字符串列表。仅包含用户明确提到的限制条件，例如：
    - 使用什么语言或技术栈（如 "使用 Python"、"不要用 Docker"）
    - 资源或权限限制（如 "不要联网"、"只能读 D 盘"）
  - suggested_tools: 字符串列表。你认为适合完成该任务的工具名称（抽象名称即可，例如 "file_system_reader", "log_frequency_analyzer"）。
  - confidence: 浮点数，范围 0.0 - 1.0，用于表示你对当前 intent 判定的置信度。
  - clarification_questions: 字符串列表。当信息不足或需求模糊时，给出 1-3 条澄清问题；否则给空列表。

示例（仅作格式参考）：
{
  "intent": "分析 D 盘 logs 文件夹，找出报错最多的行",
  "constraints": ["仅访问 D:/logs", "只读文件，不修改内容"],
  "suggested_tools": ["file_system_reader", "log_frequency_analyzer"],
  "confidence": 0.86,
  "clarification_questions": []
}
""".strip()


class IntentParser:
    """意图解析器"""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self._llm = llm_client or LLMClient.from_env()

    def _call_llm(self, user_input: str) -> Dict[str, Any]:
        """调用 LLM 并解析为字典，带有本地兜底逻辑"""
        user_prompt = f"用户输入：{user_input}\n请根据上面的要求输出 JSON。"

        raw = self._llm.generate(
            system_prompt=INTENT_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("LLM 返回的 JSON 顶层不是对象")
        except Exception:
            # 回退到一个保守的默认结构
            data = {
                "intent": user_input.strip(),
                "constraints": [],
                "suggested_tools": [],
                "confidence": 0.5,
                "clarification_questions": [
                    "请用更具体的语言描述你的需求，例如目标、约束条件和期望输出。"
                ],
            }

        return data

    def parse(self, user_input: str) -> AOSState:
        """
        解析用户输入为 AOSState

        - 使用 LLM 提取 intent / constraints / suggested_tools / confidence
        - 若 confidence < 0.7，则进入“需求澄清”阶段：
          - current_phase = "awaiting_clarification"
          - error 字段写入需要用户补充的问题
        """
        data = self._call_llm(user_input)

        intent: str = str(data.get("intent") or "").strip() or user_input.strip()
        constraints: List[str] = list(data.get("constraints") or [])
        suggested_tools: List[str] = list(data.get("suggested_tools") or [])

        try:
            confidence = float(data.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5

        clarification_questions_raw = data.get("clarification_questions") or []
        clarification_questions: List[str] = [
            str(q).strip()
            for q in clarification_questions_raw
            if str(q).strip()
        ]

        # 基础状态构建
        state = AOSState(
            intent=intent,
            plan=[],
            memory={
                "constraints": constraints,
                "suggested_tools": suggested_tools,
                "intent_confidence": confidence,
                "clarification_questions": clarification_questions,
            },
            tool_calls=[],
            execution_results={},
            verification_feedback={},
            retry_count=0,
            current_phase="understanding",
        )

        # 需求澄清机制
        if confidence < 0.7:
            state.current_phase = "awaiting_clarification"
            if clarification_questions:
                state.error = "；".join(clarification_questions)
            else:
                state.error = "当前意图置信度较低，请用更具体的语言描述你的需求。"

        return state


__all__ = ["IntentParser"]

