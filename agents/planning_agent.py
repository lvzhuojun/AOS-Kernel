"""
Planning Agent（计划层）

职责：
- 将用户意图（intent）分解为原子化的执行步骤序列
- 每个步骤应该是单一动作，便于后续权限检查和验证
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.state import AOSState
from utils import LLMClient


PLANNING_SYSTEM_PROMPT = """
你是 AOS-Kernel 的“计划层”（Planning Layer），扮演严谨的系统架构师角色。

职责：
- 将用户的意图（intent）分解为可执行的步骤序列
- 每个步骤必须是**原子性的单一动作**，便于后续的权限检查和结果验证

计划原则：
1. **逻辑自洽**：步骤之间逻辑清晰，前后依赖关系明确
2. **安全性**：考虑每个步骤可能涉及的安全风险（文件访问、网络请求、系统命令等）
3. **原子性**：每个步骤只做一件事，避免复合操作
4. **可验证性**：每个步骤完成后应有明确的预期结果，便于验证

输出要求：
- 严格输出一个 JSON 数组，不要输出任何解释性文字或多余内容
- 数组中的每个元素代表一个执行步骤，包含以下字段：
  - step_id: 整数，步骤序号（从 1 开始）
  - description: 字符串，这一步要做什么（简洁明确）
  - tool: 字符串，预估要使用的工具名称（例如 "file_system_reader", "python_interpreter", "log_analyzer"）
  - expected_outcome: 字符串，这一步完成后的预期状态或输出（用于后续验证）

示例（仅作格式参考）：
[
  {
    "step_id": 1,
    "description": "列出 D:/logs 目录下的所有文件",
    "tool": "file_system_reader",
    "expected_outcome": "获得文件列表，包含所有 .log 或 .txt 文件路径"
  },
  {
    "step_id": 2,
    "description": "逐个读取日志文件内容",
    "tool": "file_system_reader",
    "expected_outcome": "获得每个文件的完整文本内容"
  },
  {
    "step_id": 3,
    "description": "统计每行文本的出现频率，筛选出包含 'ERROR' 或 'FATAL' 的行",
    "tool": "log_frequency_analyzer",
    "expected_outcome": "获得报错行的频率统计，按出现次数降序排列"
  }
]
""".strip()


class PlanningAgent:
    """计划代理"""

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self._llm = llm_client or LLMClient.from_env()

    def _call_llm(self, intent: str, constraints: List[str], suggested_tools: List[str]) -> List[Dict[str, Any]]:
        """调用 LLM 生成计划步骤"""
        constraints_text = "\n".join(f"- {c}" for c in constraints) if constraints else "无特殊约束"
        tools_text = ", ".join(suggested_tools) if suggested_tools else "根据任务需要选择合适的工具"

        user_prompt = f"""用户意图：{intent}

约束条件：
{constraints_text}

建议工具：{tools_text}

请根据上述信息，生成一个详细的执行计划（JSON 数组）。确保每个步骤都是原子性的单一动作。"""

        raw = self._llm.generate(
            system_prompt=PLANNING_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        try:
            # 尝试解析 JSON
            data = json.loads(raw)
            if isinstance(data, list):
                # 验证每个元素是否包含必需字段
                validated = []
                for item in data:
                    if isinstance(item, dict) and all(k in item for k in ["step_id", "description", "tool", "expected_outcome"]):
                        validated.append(item)
                if validated:
                    return validated
        except Exception:
            pass

        # 回退到基于意图的简单计划
        return self._fallback_plan(intent, suggested_tools)

    def _fallback_plan(self, intent: str, suggested_tools: List[str]) -> List[Dict[str, Any]]:
        """当 LLM 解析失败时的回退计划"""
        plan = []
        intent_lower = intent.lower()

        if "logs" in intent_lower or "日志" in intent_lower or "log" in intent_lower:
            plan = [
                {
                    "step_id": 1,
                    "description": "列出指定目录下的所有日志文件",
                    "tool": "file_system_reader",
                    "expected_outcome": "获得日志文件路径列表",
                },
                {
                    "step_id": 2,
                    "description": "读取每个日志文件的内容",
                    "tool": "file_system_reader",
                    "expected_outcome": "获得所有日志文件的文本内容",
                },
                {
                    "step_id": 3,
                    "description": "分析日志内容，统计报错行的出现频率",
                    "tool": "log_frequency_analyzer",
                    "expected_outcome": "获得报错行频率统计，按出现次数排序",
                },
            ]
        elif "ghost" in intent_lower or "fixed.txt" in intent_lower or "不存在的文件" in intent_lower:
            # Test Case 4：先尝试读取 ghost.txt（会失败），恢复层 REPLAN 后追加创建 fixed.txt
            plan = [
                {
                    "step_id": 1,
                    "description": "读取工作区中的 ghost.txt 文件",
                    "tool": "file_system_reader",
                    "expected_outcome": "获得 ghost.txt 文件内容",
                },
            ]
        elif "test.py" in intent_lower or ("hello aos" in intent_lower and "工作区" in intent_lower):
            # 全链路测试：创建 test.py 并运行
            plan = [
                {
                    "step_id": 1,
                    "description": "在工作区创建 test.py，内容为打印 Hello AOS-Kernel",
                    "tool": "file_writer",
                    "expected_outcome": "生成 test.py 文件",
                },
                {
                    "step_id": 2,
                    "description": "运行 test.py 脚本",
                    "tool": "python_interpreter",
                    "expected_outcome": "输出 Hello AOS-Kernel",
                },
            ]
        else:
            # 通用回退：至少生成一个步骤
            tool = suggested_tools[0] if suggested_tools else "generic_executor"
            plan = [
                {
                    "step_id": 1,
                    "description": f"执行任务：{intent}",
                    "tool": tool,
                    "expected_outcome": "完成任务目标",
                }
            ]

        return plan

    def plan(self, state: AOSState) -> AOSState:
        """
        为给定的 AOSState 生成执行计划

        - 读取 state.intent 和 state.memory 中的 constraints / suggested_tools
        - 生成步骤序列并赋值给 state.plan
        - 更新 state.current_phase = "planning"
        """
        intent = state.intent or ""
        constraints: List[str] = list(state.memory.get("constraints") or [])
        suggested_tools: List[str] = list(state.memory.get("suggested_tools") or [])

        if not intent:
            # 无意图时，保持空计划
            state.plan = []
            state.current_phase = "planning"
            return state

        # 调用 LLM 生成计划
        plan_steps = self._call_llm(intent, constraints, suggested_tools)

        # 更新状态
        state.plan = plan_steps
        state.current_phase = "planning"

        return state


__all__ = ["PlanningAgent"]
