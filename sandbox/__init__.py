"""
AOS-Kernel 沙箱模块
提供 Docker 执行环境封装，确保代码执行的安全性
"""

from .docker_manager import DockerManager, CONTAINER_WORKSPACE

__all__ = ["DockerManager", "CONTAINER_WORKSPACE"]
