"""
AOS-Kernel 入口：理解 -> 计划 -> 权限 -> 执行 全链路集成

用法：
  python main.py           # 交互式，需人工审批
  python main.py --yes     # 自动化测试，自动批准所有操作（无需 input）

测试用例：
- Case 3: 在工作区创建 test.py 并运行（全链路；--yes 时自动审批）
"""

from __future__ import annotations

import argparse
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
from core.permission_gateway import PermissionGateway
from sandbox.docker_manager import DockerManager


def print_state_summary(title: str, state: Any) -> None:
    """打印 AOSState 关键信息"""
    print("=" * 80)
    print(title)
    print("-" * 80)
    print(f"intent: {state.intent!r}")
    print(f"current_phase: {state.current_phase!r}")
    print(f"error: {state.error!r}")
    if state.plan:
        print(f"\nplan ({len(state.plan)} steps):")
        for step in state.plan:
            print(f"  [{step.get('step_id')}] {step.get('description')} | tool: {step.get('tool')}")
    if state.execution_results:
        print("\nexecution_results:")
        for k, v in state.execution_results.items():
            res = v.get("result", v) if isinstance(v, dict) else v
            ok = v.get("success", "?") if isinstance(v, dict) else "?"
            print(f"  {k}: success={ok} -> {str(res)[:80]!r}")
    if state.verification_feedback:
        print("\nverification_feedback:")
        for k, v in state.verification_feedback.items():
            status = v.get("status", "?") if isinstance(v, dict) else "?"
            reason = (v.get("reason", "") or "")[:60] if isinstance(v, dict) else ""
            print(f"  {k}: {status} — {reason}")
    print()


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
    返回最终 state。
    """
    state = intent_parser.parse(user_input)
    if verbose:
        print_state_summary("1. 意图解析", state)

    confidence = state.memory.get("intent_confidence", 0.0)
    if confidence < 0.7:
        if verbose:
            print("置信度 < 0.7，需澄清，不进入计划与执行。")
        return state

    state = planner.plan(state)
    if verbose:
        print_state_summary("2. 计划生成", state)

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

                print("\n" + "=" * 80)
                print("⚠️  [安全拦截] 权限网关已拦截以下操作，需您批准后继续：")
                print("-" * 80)
                print(f"  步骤 [{step_id}] 风险: {risk}")
                print(f"  描述: {desc}")
                print(f"  工具: {tool}")
                print("=" * 80)

                if auto_approve:
                    print("[--yes] 自动批准，继续执行...\n")
                    gateway.approve_step(state)
                    continue
                answer = input("\n⚠️ [安全拦截] 是否批准执行该操作? (y/n): ").strip().lower()
                if answer != "y":
                    print("已拒绝，本步骤不执行。")
                    state.current_phase = "execution"
                    state.error = "用户拒绝批准该操作"
                    break
                gateway.approve_step(state)
                print("已批准，继续执行...\n")
                continue

            all_done = not state.plan or all(
                f"step_{s.get('step_id')}" in state.execution_results for s in state.plan
            )
            if verbose and state.execution_results:
                print_state_summary("3. 执行结果", state)
            if all_done:
                break

        # ---------- Layer 6: 验证 ----------
        state = verification_agent.verify(state)
        if verbose and state.verification_feedback:
            print_state_summary("4. 验证反馈", state)

        if not has_verification_failures(state):
            break

        # ---------- Layer 7: 恢复 ----------
        state, strategy = recovery_agent.recover(state)
        if verbose:
            print(f"\n[恢复层] 策略: {strategy} | 原因: {state.memory.get('recovery_reason', '')}")

        if strategy == STRATEGY_ABORT:
            break
        if strategy == STRATEGY_REPLAN:
            if verbose:
                print("  -> REPLAN：计划已更新，重新进入执行环节。\n")
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

    # 统一初始化
    gateway = PermissionGateway()
    docker_manager = DockerManager()
    execution_agent = ExecutionAgent(permission_gateway=gateway, docker_manager=docker_manager)
    verification_agent = VerificationAgent()
    recovery_agent = RecoveryAgent(max_retries=3)
    intent_parser = IntentParser()
    planner = PlanningAgent()

    try:
        if auto_approve:
            print("[运行模式] --yes 已开启，所有操作将自动批准。\n")

        # ---------- 测试用例 3：全链路集成 ----------
        print("\n" + "=" * 80)
        print("测试用例 3: 全链路集成 — 在工作区创建 test.py 并运行")
        print("=" * 80)
        input_3 = "在工作区创建一个 test.py，内容是打印 'Hello AOS-Kernel'，然后运行这个脚本。"
        state_3 = run_full_pipeline(
            input_3,
            intent_parser=intent_parser,
            planner=planner,
            execution_agent=execution_agent,
            verification_agent=verification_agent,
            recovery_agent=recovery_agent,
            gateway=gateway,
            verbose=True,
            auto_approve=auto_approve,
        )
        print("\n--- 用例 3 结束 ---")
        if state_3.execution_results:
            for k, v in state_3.execution_results.items():
                print(f"  {k}: {v}")

        # ---------- 测试用例 4：压力测试（故意失败 + 自愈 REPLAN） ----------
        print("\n" + "=" * 80)
        print("测试用例 4: 自愈 — 读取不存在的 ghost.txt，失败则创建 fixed.txt 补偿")
        print("=" * 80)
        input_4 = "读取工作区中一个不存在的文件 ghost.txt，如果读取失败，请创建一个名为 fixed.txt 的文件作为补偿。"
        state_4 = run_full_pipeline(
            input_4,
            intent_parser=intent_parser,
            planner=planner,
            execution_agent=execution_agent,
            verification_agent=verification_agent,
            recovery_agent=recovery_agent,
            gateway=gateway,
            verbose=True,
            auto_approve=auto_approve,
        )
        print("\n--- 用例 4 结束 ---")
        if state_4.execution_results:
            for k, v in state_4.execution_results.items():
                print(f"  {k}: {v}")
        if state_4.verification_feedback:
            print("verification_feedback:", state_4.verification_feedback)
    finally:
        # 程序结束时销毁常驻容器
        docker_manager.stop()
        print("\n[已清理] Docker 沙箱容器已停止并移除。")


if __name__ == "__main__":
    main()
