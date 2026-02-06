"""
Docker 执行器（沙箱）

- 使用常驻容器（启动一次，多次 exec）以提高速度。
- 镜像：python:3.10-slim；仅挂载 ./sandbox_workspace -> /workspace。
- 资源限制：512m 内存，0.5 CPU；单次执行 30 秒超时。
- 提供 execute_python(code) 与 execute_shell(command)。
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Optional, Tuple

# 可选依赖
try:
    import docker
    from docker.errors import DockerException, ImageNotFound, NotFound
    _DOCKER_AVAILABLE = True
except ImportError:
    _DOCKER_AVAILABLE = False
    docker = None
    DockerException = Exception
    ImageNotFound = Exception
    NotFound = Exception

from dotenv import load_dotenv
load_dotenv()

DEFAULT_IMAGE = "python:3.10-slim"
CONTAINER_WORKSPACE = "/workspace"
# 资源限制：512m 内存，0.5 CPU (nano_cpus=500_000_000)
MEM_LIMIT = "512m"
NANO_CPUS = 500_000_000
# 单次执行超时（秒），防止死循环
EXEC_TIMEOUT_SECONDS = 30


class DockerManager:
    """
    Docker 沙箱管理：常驻容器，仅挂载工作区到 /workspace。
    """

    def __init__(
        self,
        workspace_path: Optional[str] = None,
        image: Optional[str] = None,
    ) -> None:
        self.workspace_path = (workspace_path or os.getenv("WORKSPACE_PATH") or "./sandbox_workspace")
        self.image = image or os.getenv("DOCKER_IMAGE") or DEFAULT_IMAGE
        self._client = None
        self._container_id: Optional[str] = None

    def _get_client(self):
        if not _DOCKER_AVAILABLE:
            raise RuntimeError("docker 未安装，请 pip install docker")
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def ensure_container(self) -> str:
        """
        确保常驻容器在运行，若不存在则创建并启动。
        返回容器 ID。
        """
        if self._container_id:
            client = self._get_client()
            try:
                c = client.containers.get(self._container_id)
                if c.status == "running":
                    return self._container_id
            except NotFound:
                self._container_id = None
        self._start_container()
        return self._container_id  # type: ignore

    def _start_container(self) -> None:
        client = self._get_client()
        host_workspace = os.path.abspath(self.workspace_path)
        os.makedirs(host_workspace, exist_ok=True)
        container = client.containers.run(
            self.image,
            command=["sleep", "infinity"],
            detach=True,
            remove=False,
            volumes={host_workspace: {"bind": CONTAINER_WORKSPACE, "mode": "rw"}},
            working_dir=CONTAINER_WORKSPACE,
            mem_limit=MEM_LIMIT,
            nano_cpus=NANO_CPUS,
        )
        self._container_id = container.id if hasattr(container, "id") else str(container)

    def _exec_with_timeout(self, cmd: list, workdir: str = CONTAINER_WORKSPACE) -> Tuple[str, str, int]:
        """在容器内执行命令，带 30 秒超时。返回 (stdout, stderr, exit_code)。"""
        def _run() -> Tuple[str, str, int]:
            container_id = self.ensure_container()
            client = self._get_client()
            container = client.containers.get(container_id)
            exit_code, output = container.exec_run(cmd, workdir=workdir)
            out = (output or b"").decode("utf-8", errors="replace")
            return out, "", exit_code

        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(_run)
                out, err, code = future.result(timeout=EXEC_TIMEOUT_SECONDS)
                return out, err, code
        except FuturesTimeoutError:
            return "", f"执行超时（{EXEC_TIMEOUT_SECONDS} 秒）", -1

    def execute_python(self, code: str) -> Tuple[str, str, int]:
        """
        在容器内执行 Python 代码，30 秒超时。
        返回 (stdout, stderr, exit_code)。
        """
        return self._exec_with_timeout(["python", "-c", code])

    def execute_shell(self, command: str) -> Tuple[str, str, int]:
        """
        在容器内执行 shell 命令（/bin/sh -c "command"），30 秒超时。
        返回 (stdout, stderr, exit_code)。
        """
        return self._exec_with_timeout(["/bin/sh", "-c", command])

    def stop(self) -> None:
        """停止并移除常驻容器（若存在）。"""
        if not self._container_id or not _DOCKER_AVAILABLE:
            return
        try:
            client = self._get_client()
            c = client.containers.get(self._container_id)
            c.stop(timeout=5)
            c.remove()
        except Exception:
            pass
        self._container_id = None

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass


__all__ = ["DockerManager", "CONTAINER_WORKSPACE"]
