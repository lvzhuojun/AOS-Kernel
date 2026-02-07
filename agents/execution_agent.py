"""
Execution Agent（执行层）

工作流：遍历 state.plan -> 权限网关校验 -> Docker 执行 -> 结果写入 state.execution_results。
禁止硬编码：所有文件名与内容均从 step 的 description/parameters 中动态提取，失败时由 LLM 生成代码。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from core.state import AOSState
from core.permission_gateway import PermissionGateway
from sandbox.docker_manager import DockerManager
from utils import LLMClient


# ---------- 动态提取：从 description 或 parameters 中解析文件名、内容等 ----------

def _extract_filename_from_text(text: str) -> Optional[str]:
    """
    从描述/预期结果中提取第一个出现的文件名（含扩展名）。
    匹配：hello.py, data.txt, ghost.txt, fixed.txt 等。
    """
    if not (text or "").strip():
        return None
    # 优先匹配 .py / .txt / .log 等
    m = re.search(r"(\w+\.(?:py|txt|log|json|md))\b", text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"文件\s*[：:]\s*(\w+\.\w+)|[\"'](\w+\.\w+)[\"']", text)
    if m:
        return m.group(1) or m.group(2)
    return None


def _extract_print_content_from_text(text: str) -> Optional[str]:
    """
    从描述中提取“打印内容”，如：打印 'AOS Phase 2 Ready'、内容是打印 'X'、print "Y"。
    返回用于写入文件的一行 Python 内容（如 print("AOS Phase 2 Ready")）。
    """
    if not (text or "").strip():
        return None
    # 单引号内容
    m = re.search(r"打印\s*['\"]([^'\"]+)['\"]|内容[是为]*\s*打印\s*['\"]([^'\"]+)['\"]|print\s*\(\s*['\"]([^'\"]+)['\"]", text)
    if m:
        raw = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        if raw:
            return f'print("{raw}")'
    # 双引号
    m = re.search(r"打印\s*[\"']([^\"']+)[\"']|内容[是为]*\s*打印\s*[\"']([^\"']+)[\"']", text)
    if m:
        raw = (m.group(1) or m.group(2) or "").strip()
        if raw:
            return f'print("{raw}")'
    return None


def _escape_for_write(s: str) -> str:
    """将字符串转义后放入 f.write(\"...\") 的双引号内。"""
    return (s or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class ExecutionAgent:
    """
    执行代理：按计划逐步执行，每步经权限网关校验后进入 Docker 沙箱执行。
    从 step 的 description/parameters 动态解析要执行的操作，禁止硬编码文件名。
    """

    def __init__(
        self,
        permission_gateway: Optional[PermissionGateway] = None,
        docker_manager: Optional[DockerManager] = None,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self.gateway = permission_gateway or PermissionGateway()
        self.docker = docker_manager or DockerManager()
        self._llm = llm_client

    def _llm_generate_code(self, description: str) -> Optional[str]:
        """解析失败时由 LLM 根据步骤描述生成 Python 代码（当前目录下执行）。"""
        if not description or not description.strip():
            return None
        try:
            client = self._llm or LLMClient.from_env()
            user_prompt = (
                f"根据步骤描述：'{description}'，生成一段在当前目录下执行该动作的 Python 代码。"
                "只需输出代码，不要解释。代码应可在 /workspace 当前目录直接运行。"
            )
            system_prompt = (
                "你是 AOS-Kernel 执行层。根据用户给出的步骤描述，生成唯一一段可执行的 Python 代码。"
                "不要输出 markdown 代码块标记，不要解释，只输出纯代码。"
            )
            raw = client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tier="cheap",
            )
            if not raw:
                return None
            # 去掉可能的 markdown 代码块
            code = (raw or "").strip()
            if code.startswith("```"):
                lines = code.split("\n")
                out = []
                in_block = False
                for line in lines:
                    if line.strip().startswith("```"):
                        in_block = not in_block
                        continue
                    if in_block:
                        out.append(line)
                    elif not out and "```" not in line:
                        out.append(line)
                code = "\n".join(out) if out else code
            return code.strip() or None
        except Exception:
            return None

    def _code_or_command_for_step(self, step: Dict[str, Any], state: AOSState) -> Tuple[Optional[str], Optional[str], str]:
        """
        根据 step 和 state 推断要执行的 Python code 或 shell command。
        优先从 step['description'] 或 step['parameters'] 动态提取文件名与内容；失败则调用 LLM 生成代码。
        返回 (code, command, kind)，kind 为 "python" 或 "shell"。
        """
        tool = (step.get("tool") or "").strip().lower()
        description = (step.get("description") or "").strip()
        parameters = step.get("parameters") or {}
        # 步骤中可显式携带 code / command（由上游或测试注入）
        if step.get("code"):
            return step["code"], None, "python"
        if step.get("command"):
            return None, step["command"], "shell"

        # 合并描述与参数中的文本，便于提取
        combined = " ".join([description, str(parameters)])

        # ---------- 写文件：创建/写入指定文件 ----------
        if "file_writer" in tool or "创建" in description or "write" in description.lower() or "写入" in description:
            fname = parameters.get("filename") or _extract_filename_from_text(combined) or _extract_filename_from_text(state.intent or "")
            content_line = _extract_print_content_from_text(combined) or _extract_print_content_from_text(state.intent or "")
            if content_line:
                write_content = _escape_for_write(content_line + "\n")
            else:
                write_content = _escape_for_write("# created by AOS\n")
            if fname:
                code = f'with open("{fname}", "w", encoding="utf-8") as f:\n    f.write("{write_content}")'
                return code, None, "python"
            code = self._llm_generate_code(description)
            if code:
                return code, None, "python"
            code = 'with open("output.txt", "w") as f: f.write("# created by AOS\\n")'
            return code, None, "python"

        # ---------- 运行脚本 ----------
        if "python_interpreter" in tool or "运行" in description or "run" in description.lower():
            fname = parameters.get("script") or parameters.get("filename") or _extract_filename_from_text(combined) or _extract_filename_from_text(state.intent or "")
            if fname:
                return None, f"python {fname}", "shell"
            code = self._llm_generate_code(description)
            if code:
                return code, None, "python"
            return None, "python -c \"print('no script specified')\"", "shell"

        # ---------- 读取文件 ----------
        if "file_system_reader" in tool or "file_reader" in tool or "读取" in description or "read" in description.lower():
            fname = parameters.get("filename") or _extract_filename_from_text(combined) or _extract_filename_from_text(state.intent or "")
            if fname:
                code = f'open("{fname}", encoding="utf-8").read()'
                return code, None, "python"
            code = self._llm_generate_code(description)
            if code:
                return code, None, "python"
            return 'open("unknown.txt").read()', None, "python"

        # ---------- 其他：优先 LLM 生成 ----------
        code = self._llm_generate_code(description)
        if code:
            return code, None, "python"
        return (description or "pass", None, "python")

    def run(self, state: AOSState) -> AOSState:
        """
        按 state.plan 顺序执行：权限校验 -> Docker 执行 -> 写入 execution_results。
        若某步被网关判定为 RISKY/DANGEROUS，将 state 设为 awaiting_user_approval 并返回，
        待用户批准后调用 gateway.approve_step(state) 再调用本方法继续执行。
        """
        if not state.plan:
            state.current_phase = "execution"
            return state

        if state.current_phase == "awaiting_user_approval":
            return state

        state.current_phase = "execution"
        allow_retry_failed = state.memory.pop("allow_retry_failed_steps", False)

        next_step_id = state.memory.get("pending_approval_step_id")
        just_approved = next_step_id is not None
        if just_approved:
            state.memory.pop("pending_approval_step_id", None)
            steps_to_run = [s for s in state.plan if s.get("step_id") == next_step_id]
        else:
            steps_to_run = list(state.plan)

        for step in steps_to_run:
            step_id = step.get("step_id")
            key = f"step_{step_id}"
            existing = state.execution_results.get(key)
            if existing is not None:
                if existing.get("success") is True:
                    continue
                if allow_retry_failed and existing.get("success") is False:
                    pass
                else:
                    continue
            if not just_approved:
                result = self.gateway.verify_step(step, state)
                if not result.allowed:
                    return state
            code, command, kind = self._code_or_command_for_step(step, state)
            try:
                if kind == "python" and code:
                    out, err, exit_code = self.docker.execute_python(code)
                elif kind == "shell" and command:
                    out, err, exit_code = self.docker.execute_shell(command)
                else:
                    out, err, exit_code = "", "no code/command", -1
                state.execution_results[key] = {
                    "result": out or err,
                    "stdout": out,
                    "stderr": err,
                    "exit_code": exit_code,
                    "success": exit_code == 0,
                }
            except Exception as e:
                state.execution_results[key] = {
                    "result": str(e),
                    "success": False,
                    "error": str(e),
                }
        return state


__all__ = ["ExecutionAgent"]
