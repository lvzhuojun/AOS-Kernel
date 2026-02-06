"""
Verification Agent（验证层 Layer 6）

对比 execution_results 与 plan 中的 expected_outcome，更新 verification_feedback。
支持简单验证（exit_code）与可选语义验证（LLM）。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.state import AOSState
from utils import LLMClient

VERIFY_STATUS_SUCCESS = "SUCCESS"
VERIFY_STATUS_FAILED = "FAILED"


class VerificationAgent:
    """
    验证代理：检查每步执行结果是否达到预期。
    输出写入 state.verification_feedback，每步标记 SUCCESS 或 FAILED。
    """

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self._llm = llm_client or LLMClient.from_env()

    def _semantic_verify(self, expected_outcome: str, result_text: str, success: bool) -> str:
        """
        可选：调用 LLM 判断“执行结果是否达到了预期目标？”。
        若 LLM 不可用或超时，则按 success 返回简短原因。
        """
        user_prompt = (
            f"预期目标：{expected_outcome}\n"
            f"执行结果（或错误信息）：{result_text[:500]}\n"
            f"请用一句话判断：执行结果是否达到了预期目标？回答 是 或 否，并简要说明原因。"
        )
        system_prompt = "你是 AOS-Kernel 的验证模块。根据预期目标与执行结果，判断是否达成。只输出判断结论和一句话原因。"
        try:
            raw = self._llm.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tier="cheap",
            )
            return (raw or "").strip() or ("达成" if success else "未达成")
        except Exception:
            return "达成" if success else "未达成（exit_code 非 0 或执行异常）"

    def verify(self, state: AOSState, use_semantic: bool = False) -> AOSState:
        """
        根据 state.plan 与 state.execution_results 填写 state.verification_feedback。
        简单验证：检查 exit_code 是否为 0。
        若 use_semantic 为 True，则对失败步或全部步调用 LLM 做语义验证。
        返回 state；可通过 has_verification_failures(state) 判断是否存在失败。
        """
        state.current_phase = "verification"
        if not state.plan:
            return state

        for step in state.plan:
            step_id = step.get("step_id")
            key = f"step_{step_id}"
            expected = step.get("expected_outcome") or ""

            if key not in state.execution_results:
                state.verification_feedback[key] = {
                    "status": VERIFY_STATUS_FAILED,
                    "reason": "该步骤未产生执行结果（可能被拦截或未执行）",
                    "expected_outcome": expected,
                }
                continue

            res = state.execution_results[key]
            success = res.get("success", False)
            result_text = str(res.get("result", res.get("stdout", "")) or "")
            exit_code = res.get("exit_code", -1)

            # 简单验证
            if success and exit_code == 0:
                status = VERIFY_STATUS_SUCCESS
                reason = "exit_code=0，执行成功"
            else:
                status = VERIFY_STATUS_FAILED
                reason = f"exit_code={exit_code}，执行失败或异常：{result_text[:200]}"

            if use_semantic and status == VERIFY_STATUS_FAILED:
                reason = self._semantic_verify(expected, result_text, success)

            state.verification_feedback[key] = {
                "status": status,
                "reason": reason,
                "expected_outcome": expected,
            }

        return state


def has_verification_failures(state: AOSState) -> bool:
    """是否存在任一步验证失败。"""
    for v in state.verification_feedback.values():
        if isinstance(v, dict) and v.get("status") == VERIFY_STATUS_FAILED:
            return True
    return False


__all__ = ["VerificationAgent", "VERIFY_STATUS_SUCCESS", "VERIFY_STATUS_FAILED", "has_verification_failures"]
