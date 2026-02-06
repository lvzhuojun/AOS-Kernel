"""
压力测试脚本：连续 10 次运行同一 pipeline，不清缓存，用于诊断 API 稳定性与语义缓存效果。

用法（在项目根目录执行）：
  python -m tests.debug_stress_test
  或
  python tests/debug_stress_test.py

- 固定输入："在工作区创建一个 test.py 并运行"
- 每轮使用同一组 Agent 与 MemoryManager，不清理缓存，以观察 MemoryManager 对 API 调用量的削减
- 所有 API 调用（含重试/多模型）及缓存命中会写入 docs/api_diagnostics.log
"""

from __future__ import annotations

import logging
import os
import sys

# 确保项目根在 path 中（从 tests/ 运行时）
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from agents import (
    IntentParser,
    PlanningAgent,
    ExecutionAgent,
    VerificationAgent,
    RecoveryAgent,
    has_verification_failures,
)
from core.memory_manager import MemoryManager
from core.permission_gateway import PermissionGateway
from sandbox.docker_manager import DockerManager
from utils import LLMClient
from main import run_full_pipeline

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

FIXED_INPUT = "在工作区创建一个 test.py 并运行"
NUM_ITERATIONS = 10


def main() -> None:
    logger.info("=== AOS-Kernel 压力测试：连续 %d 次 pipeline，不清缓存 ===\n", NUM_ITERATIONS)

    gateway = PermissionGateway()
    docker_manager = DockerManager()
    memory_manager = MemoryManager()

    agents = {
        "intent_parser": IntentParser(memory_manager=memory_manager),
        "planner": PlanningAgent(memory_manager=memory_manager),
        "execution_agent": ExecutionAgent(
            permission_gateway=gateway,
            docker_manager=docker_manager,
        ),
        "verification_agent": VerificationAgent(),
        "recovery_agent": RecoveryAgent(memory_manager=memory_manager, max_retries=3),
    }

    try:
        for i in range(NUM_ITERATIONS):
            logger.info("--- 第 %d / %d 轮 ---", i + 1, NUM_ITERATIONS)
            state = run_full_pipeline(
                user_input=FIXED_INPUT,
                gateway=gateway,
                verbose=False,
                auto_approve=True,
                **agents,
            )
            if not state.plan:
                logger.warning("  第 %d 轮无计划，跳过记录缓存", i + 1)
            elif getattr(state, "verification_feedback", None) is not None:
                if not has_verification_failures(state) and state.plan:
                    memory_manager.record_successful_plan(state.intent, state.plan)
                    memory_manager.add_intent_to_cache(
                        FIXED_INPUT,
                        state.intent,
                        state.memory.get("constraints") or [],
                        state.memory.get("suggested_tools") or [],
                        state.memory.get("intent_confidence", 0.5),
                        state.memory.get("clarification_questions") or [],
                    )
            logger.info("  第 %d 轮完成 intent=%s\n", i + 1, (state.intent or "")[:50])
    finally:
        docker_manager.stop()
        stats = LLMClient.get_stats()
        logger.info("\n=== 压力测试结束 ===")
        logger.info("📊 累计成本统计:")
        logger.info("  - Cheap (2.0 Flash): %s 次", stats["cheap"])
        logger.info("  - Smart (2.0 Flash): %s 次", stats["smart"])
        logger.info("  - 缓存命中 (Saved): %s 次", stats["cache_hit"])
        logger.info("\n详细 API 诊断已写入: docs/api_diagnostics.log")


if __name__ == "__main__":
    main()
