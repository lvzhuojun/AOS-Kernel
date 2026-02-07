"""
权限网关（Layer 4）

每个 step 在进入沙箱前必须经过 verify_step(step)。
风险分级：SAFE / RISKY / DANGEROUS；
涉及 sandbox_workspace 之外路径的操作必须标记为 DANGEROUS。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.state import AOSState


class RiskLevel(str, Enum):
    SAFE = "SAFE"
    RISKY = "RISKY"
    DANGEROUS = "DANGEROUS"


# 仅读、且路径在工作区内的操作
SAFE_TOOLS = {"file_system_reader", "file_reader", "log_frequency_analyzer", "list_dir"}
# 写入、安装、网络
RISKY_KEYWORDS = ["写入", "写", "创建", "create", "write", "install", "pip", "网络", "network", "request", "curl", "wget"]
RISKY_TOOLS = {"file_writer", "code_writer", "python_interpreter"}  # 执行代码、写文件
# 删除、系统目录、执行二进制
DANGEROUS_KEYWORDS = ["删除", "remove", "rm ", "unlink", "系统目录", "system", "/etc", "/usr", "二进制", "exec", "subprocess", "shell"]
DANGEROUS_TOOLS = set()


@dataclass
class StepVerificationResult:
    """单步校验结果"""
    allowed: bool
    risk_level: RiskLevel
    reason: str
    step_id: Optional[int] = None
    step_snapshot: Optional[Dict[str, Any]] = None


class PermissionGateway:
    """
    权限网关：对 plan 中的每一步进行风险分级与放行/挂起。
    """

    def __init__(self, workspace_path: Optional[str] = None) -> None:
        self.workspace_path = (workspace_path or os.getenv("WORKSPACE_PATH") or "./sandbox_workspace").replace("\\", "/")
        self._workspace_abspath: Optional[str] = None

    def _norm_workspace(self) -> str:
        """返回工作区绝对路径（统一正斜杠）。"""
        if self._workspace_abspath is None:
            self._workspace_abspath = os.path.abspath(self.workspace_path).replace("\\", "/")
        return self._workspace_abspath

    def _path_in_workspace(self, path: str) -> bool:
        """判断 path 是否在工作区目录内。"""
        if not path or not path.strip():
            return False
        try:
            path = os.path.abspath(path.strip()).replace("\\", "/")
        except Exception:
            return False
        ws = self._norm_workspace()
        return path == ws or path.startswith(ws + "/")

    def _extract_paths_from_step(self, step: Dict[str, Any]) -> List[str]:
        """从 step 的 parameters、description、tool 中提取路径字符串，并调用 _path_in_workspace 校验。"""
        paths: List[str] = []
        desc = (step.get("description") or "") + " " + (step.get("tool") or "")
        # step 顶层显式参数
        for key in ("path", "file_path", "file", "target"):
            v = step.get(key)
            if isinstance(v, str) and v.strip():
                paths.append(v.strip())
        # step['parameters'] 中的路径（如 {"path": "D:/data/foo.txt"}）
        params = step.get("parameters")
        if isinstance(params, dict):
            for key in ("path", "file_path", "file", "target", "file_path"):
                v = params.get(key)
                if isinstance(v, str) and v.strip():
                    paths.append(v.strip())
        # description 中 Windows 风格：D:\xxx, C:\xxx, D:/xxx
        for m in re.finditer(r"(?i)[A-Za-z]:[/\\][^\s\"']+", desc):
            paths.append(m.group(0).strip())
        # description 中 Unix 绝对路径：/etc/xxx, /usr/xxx
        for m in re.finditer(r"/[a-zA-Z0-9_.-]+[/\w.-]*", desc):
            p = m.group(0).strip()
            if len(p) > 1 and not p.startswith("//"):
                paths.append(p)
        return paths

    def _has_path_outside_workspace(self, step: Dict[str, Any]) -> bool:
        """若 description/tool 涉及任意路径在工作区外，返回 True（应标为 DANGEROUS）。"""
        for raw in self._extract_paths_from_step(step):
            if not raw:
                continue
            # 相对路径（如 example.txt、script.py）视为在工作区内
            if not raw.startswith("/") and ":" not in raw[:2]:
                continue
            if not self._path_in_workspace(raw):
                return True
        return False

    def verify_step(self, step: Dict[str, Any], state: Optional[AOSState] = None) -> StepVerificationResult:
        """
        校验单步是否允许执行。
        - SAFE：放行。
        - RISKY / DANGEROUS：不允许直接执行，需用户批准；
          若传入 state，会设置 current_phase=awaiting_user_approval 并写入 error 与 memory 中的待批准信息。
        """
        step_id = step.get("step_id")
        description = (step.get("description") or "").lower()
        tool = (step.get("tool") or "").strip().lower()

        # DANGEROUS：访问 sandbox_workspace 之外的路径
        if self._has_path_outside_workspace(step):
            result = StepVerificationResult(
                allowed=False,
                risk_level=RiskLevel.DANGEROUS,
                reason="步骤涉及工作区外路径，仅允许访问 sandbox_workspace 内",
                step_id=step_id,
                step_snapshot=dict(step),
            )
            self._apply_awaiting_approval(state, result)
            return result

        # DANGEROUS：危险关键词
        for kw in DANGEROUS_KEYWORDS:
            if kw in description or kw in tool:
                result = StepVerificationResult(
                    allowed=False,
                    risk_level=RiskLevel.DANGEROUS,
                    reason=f"步骤涉及危险操作：{description or tool}",
                    step_id=step_id,
                    step_snapshot=dict(step),
                )
                self._apply_awaiting_approval(state, result)
                return result
        if tool in DANGEROUS_TOOLS:
            result = StepVerificationResult(
                allowed=False,
                risk_level=RiskLevel.DANGEROUS,
                reason=f"工具 {tool} 属于危险级别",
                step_id=step_id,
                step_snapshot=dict(step),
            )
            self._apply_awaiting_approval(state, result)
            return result

        # RISKY：写入、安装、网络、执行代码等
        for kw in RISKY_KEYWORDS:
            if kw in description or kw in tool:
                result = StepVerificationResult(
                    allowed=False,
                    risk_level=RiskLevel.RISKY,
                    reason=f"步骤涉及风险操作（写入/安装/网络）：{description or tool}",
                    step_id=step_id,
                    step_snapshot=dict(step),
                )
                self._apply_awaiting_approval(state, result)
                return result
        if tool in RISKY_TOOLS:
            result = StepVerificationResult(
                allowed=False,
                risk_level=RiskLevel.RISKY,
                reason=f"工具 {tool} 需要用户批准后执行",
                step_id=step_id,
                step_snapshot=dict(step),
            )
            self._apply_awaiting_approval(state, result)
            return result

        # SAFE：仅读且在工作区内
        if tool in SAFE_TOOLS:
            return StepVerificationResult(
                allowed=True,
                risk_level=RiskLevel.SAFE,
                reason="只读操作且限定在工作区内",
                step_id=step_id,
                step_snapshot=dict(step),
            )
        # 未识别的工具保守视为 RISKY
        result = StepVerificationResult(
            allowed=False,
            risk_level=RiskLevel.RISKY,
            reason=f"未识别的工具或操作，需要批准：{tool or description}",
            step_id=step_id,
            step_snapshot=dict(step),
        )
        self._apply_awaiting_approval(state, result)
        return result

    def _apply_awaiting_approval(self, state: Optional[AOSState], result: StepVerificationResult) -> None:
        if state is None:
            return
        state.current_phase = "awaiting_user_approval"
        state.error = result.reason
        state.memory["pending_approval_step"] = result.step_snapshot
        state.memory["pending_approval_risk"] = result.risk_level.value
        state.memory["pending_approval_step_id"] = result.step_id

    def approve_step(self, state: AOSState) -> None:
        """
        用户批准当前待执行步骤后调用。清除挂起展示信息，但保留 pending_approval_step_id，
        以便 ExecutionAgent.run() 识别“仅执行该步且跳过权限校验”。
        """
        state.current_phase = "execution"
        state.error = None
        state.memory.pop("pending_approval_step", None)
        state.memory.pop("pending_approval_risk", None)
        # 不清除 pending_approval_step_id，由 run() 在执行该步后清除


__all__ = ["PermissionGateway", "RiskLevel", "StepVerificationResult"]
