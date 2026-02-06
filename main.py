"""
AOS-Kernel 入口：理解 -> 计划 -> 权限 -> 执行 全链路集成

用法：
  python main.py           # 交互式，需人工审批
  python main.py --yes     # 自动化测试，自动批准所有操作（无需 input）

测试用例：
- Case 3: 在工作区创建 test.py 并运行（全链路；--yes 时自动审批）
- Case 4: 自愈场景（读取 ghost.txt 失败 -> REPLAN -> 创建 fixed.txt）
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import Any, Dict

from agents import (
    IntentParser,
    PlanningAgent,
    ExecutionAgent,
    VerificationAgent,
    has_verification_failures,
    RecoveryAgent,
    STRATEGY_REPLAN,
    STRATEGY_ABORT,
)
from core.memory_manager import MemoryManager
from core.permission_gateway import PermissionGateway
from sandbox.docker_manager import DockerManager
from utils import LLMClient

# 统一日志：分级输出，默认 INFO；可通过环境变量 LOG_LEVEL 覆盖
_LOG_LEVEL = getattr(logging, (os.getenv("LOG_LEVEL") or "INFO").upper(), logging.INFO)
logging.basicConfig(level=_LOG_LEVEL, format="%(message)s")
logger = logging.getLogger(__name__)


def _log_state_summary(title: str, state: Any) -> None:
    """以 INFO 级别输出 AOSState 关键信息。"""
    logger.info("=" * 80)
    logger.info(title)
    logger.info("-" * 80)
    logger.info("intent: %s", state.intent)
    logger.info("current_phase: %s", state.current_phase)
    logger.info("error: %s", state.error)
    if state.plan:
        logger.info("plan (%d steps):", len(state.plan))
        for step in state.plan:
            logger.info(
                "  [%s] %s | tool: %s",
                step.get("step_id"),
                step.get("description"),
                step.get("tool"),
            )
    if state.execution_results:
        logger.info("execution_results:")
        for k, v in state.execution_results.items():
            res = v.get("result", v) if isinstance(v, dict) else v
            ok = v.get("success", "?") if isinstance(v, dict) else "?"
            logger.info("  %s: success=%s -> %s", k, ok, str(res)[:80])
    if state.verification_feedback:
        logger.info("verification_feedback:")
        for k, v in state.verification_feedback.items():
            status = v.get("status", "?") if isinstance(v, dict) else "?"
            reason = (v.get("reason", "") or "")[:60] if isinstance(v, dict) else ""
            logger.info("  %s: %s — %s", k, status, reason)
    logger.info("")


def run_full_pipeline(
    user_input: str,
    intent_parser: IntentParser,
    planner: PlanningAgent,
    execution_agent: ExecutionAgent,
    verification_agent: VerificationAgent,
    recovery_agent: RecoveryAgent,
    gateway: PermissionGateway,
    verbose: bool = True,
    auto_approve: bool = False,
) -> Any:
    """
    运行全链路：理解 -> 计划 -> (执行+审批) -> 验证 -> 失败则恢复(REPLAN/ABORT) -> 必要时回执行。
    每次调用均通过 intent_parser.parse(user_input) 生成全新的 AOSState，杜绝用例间污染。
    返回最终 state。
    """
    state = intent_parser.parse(user_input)
    if verbose:
        _log_state_summary("1. 意图解析", state)

    confidence = state.memory.get("intent_confidence", 0.0)
    if confidence < 0.7:
        if verbose:
            logger.info("置信度 < 0.7，需澄清，不进入计划与执行。")
        return state

    state = planner.plan(state)
    if verbose:
        _log_state_summary("2. 计划生成", state)

    if not state.plan:
        return state

    # 自愈大循环：执行 -> 验证 -> 若失败则恢复，REPLAN 时回到执行
    while True:
        # ---------- 执行 + 审批 内循环 ----------
        while True:
            state = execution_agent.run(state)

            if state.current_phase == "awaiting_user_approval":
                pending = state.memory.get("pending_approval_step") or {}
                risk = state.memory.get("pending_approval_risk", "RISKY")
                desc = pending.get("description", "未知操作")
                tool = pending.get("tool", "?")
                step_id = pending.get("step_id", "?")

                logger.info("\n" + "=" * 80)
                logger.info("⚠️  [安全拦截] 权限网关已拦截以下操作，需您批准后继续：")
                logger.info("-" * 80)
                logger.info("  步骤 [%s] 风险: %s", step_id, risk)
                logger.info("  描述: %s", desc)
                logger.info("  工具: %s", tool)
                logger.info("=" * 80)

                if auto_approve:
                    logger.info("[--yes] 自动批准，继续执行...\n")
                    gateway.approve_step(state)
                    continue
                answer = input("\n⚠️ [安全拦截] 是否批准执行该操作? (y/n): ").strip().lower()
                if answer != "y":
                    logger.info("已拒绝，本步骤不执行。")
                    state.current_phase = "execution"
                    state.error = "用户拒绝批准该操作"
                    break
                gateway.approve_step(state)
                logger.info("已批准，继续执行...\n")
                continue

            all_done = not state.plan or all(
                f"step_{s.get('step_id')}" in state.execution_results for s in state.plan
            )
            if verbose and state.execution_results:
                _log_state_summary("3. 执行结果", state)
            if all_done:
                break

        # ---------- Layer 6: 验证 ----------
        state = verification_agent.verify(state)
        if verbose and state.verification_feedback:
            _log_state_summary("4. 验证反馈", state)

        if not has_verification_failures(state):
            break

        # ---------- Layer 7: 恢复 ----------
        state, strategy = recovery_agent.recover(state)
        if verbose:
            logger.info(
                "\n[恢复层] 策略: %s | 原因: %s",
                strategy,
                state.memory.get("recovery_reason", ""),
            )

        if strategy == STRATEGY_ABORT:
            break
        if strategy == STRATEGY_REPLAN:
            if verbose:
                logger.info("  -> REPLAN：计划已更新，重新进入执行环节。\n")
            continue
        # RETRY：此处不实现“清除失败步重试”，直接结束
        break

    return state


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AOS-Kernel 全链路：理解 -> 计划 -> 权限 -> 执行",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="自动批准所有权限拦截，无需人工 input（适用于自动化/CI 测试）",
    )
    args = parser.parse_args()
    auto_approve = args.yes

    gateway = PermissionGateway()
    docker_manager = DockerManager()
    memory_manager = MemoryManager()

    def make_fresh_agents():
        """每个用例使用全新 Agent 实例；共享 memory_manager 以支持语义缓存与经验持久化。"""
        return {
            "intent_parser": IntentParser(memory_manager=memory_manager),
            "planner": PlanningAgent(memory_manager=memory_manager),
            "execution_agent": ExecutionAgent(permission_gateway=gateway, docker_manager=docker_manager),
            "verification_agent": VerificationAgent(),
            "recovery_agent": RecoveryAgent(memory_manager=memory_manager, max_retries=3),
        }

    try:
        if auto_approve:
            logger.info("[运行模式] --yes 已开启，所有操作将自动批准。\n")

        # ---------- 测试用例 3：全链路集成 ----------
        logger.info("\n" + "=" * 80)
        logger.info("测试用例 3: 全链路集成 — 在工作区创建 test.py 并运行")
        logger.info("=" * 80)
        input_3 = "在工作区创建一个 test.py，内容是打印 'Hello AOS-Kernel'，然后运行这个脚本。"
        agents_3 = make_fresh_agents()
        state_3 = run_full_pipeline(
            user_input=input_3,
            gateway=gateway,
            verbose=True,
            auto_approve=auto_approve,
            **agents_3,
        )
        logger.info("\n--- 用例 3 结束 ---")
        if state_3.execution_results:
            for k, v in state_3.execution_results.items():
                logger.info("  %s: %s", k, v)
        if not has_verification_failures(state_3) and state_3.plan:
            memory_manager.record_successful_plan(state_3.intent, state_3.plan)
            memory_manager.add_intent_to_cache(
                input_3,
                state_3.intent,
                state_3.memory.get("constraints") or [],
                state_3.memory.get("suggested_tools") or [],
                state_3.memory.get("intent_confidence", 0.5),
                state_3.memory.get("clarification_questions") or [],
            )

        # ---------- 测试用例 4：压力测试（故意失败 + 自愈 REPLAN） ----------
        # 使用全新 Agent 与 input_4，与 Case 3 完全隔离。
        logger.info("\n" + "=" * 80)
        logger.info("测试用例 4: 自愈 — 读取不存在的 ghost.txt，失败则创建 fixed.txt 补偿")
        logger.info("=" * 80)
        input_4 = "读取工作区中一个不存在的文件 ghost.txt，如果读取失败，请创建一个名为 fixed.txt 的文件作为补偿。"
        agents_4 = make_fresh_agents()
        state_4 = run_full_pipeline(
            user_input=input_4,
            gateway=gateway,
            verbose=True,
            auto_approve=auto_approve,
            **agents_4,
        )
        logger.info("\n--- 用例 4 结束 ---")
        if state_4.execution_results:
            for k, v in state_4.execution_results.items():
                logger.info("  %s: %s", k, v)
        if state_4.verification_feedback:
            logger.info("verification_feedback: %s", state_4.verification_feedback)
        if not has_verification_failures(state_4) and state_4.plan:
            memory_manager.record_successful_plan(state_4.intent, state_4.plan)
            memory_manager.add_intent_to_cache(
                input_4,
                state_4.intent,
                state_4.memory.get("constraints") or [],
                state_4.memory.get("suggested_tools") or [],
                state_4.memory.get("intent_confidence", 0.5),
                state_4.memory.get("clarification_questions") or [],
            )
    finally:
        docker_manager.stop()
        logger.info("\n[已清理] Docker 沙箱容器已停止并移除。")
        stats = LLMClient.get_stats()
        logger.info("\n📊 本次任务成本统计:")
        logger.info("  - Cheap (2.0 Flash): %s 次", stats["cheap"])
        logger.info("  - Smart (2.0 Flash): %s 次", stats["smart"])
        if stats.get("ultra", 0) > 0:
            logger.info("  - Ultra (2.5 Flash): %s 次", stats["ultra"])
        logger.info("  - 缓存命中 (Saved): %s 次", stats["cache_hit"])


if __name__ == "__main__":
    main()
