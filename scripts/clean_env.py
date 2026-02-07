"""
清空实验环境：删除 memory.json 与 sandbox_workspace/ 内容，便于全新实验。

用法（在项目根目录执行）：
  python scripts/clean_env.py
  或
  python -m scripts.clean_env
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# 项目根目录 = 本文件所在目录的上一级
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    # 1. 删除 memory.json
    memory_file = _PROJECT_ROOT / "memory.json"
    if memory_file.is_file():
        memory_file.unlink()
        print(f"已删除: {memory_file}")
    else:
        print(f"无需删除（不存在）: {memory_file}")

    # 2. 清空 sandbox_workspace（与 .env 中 WORKSPACE_PATH 一致，默认 ./sandbox_workspace）
    workspace_rel = os.getenv("WORKSPACE_PATH", "sandbox_workspace").strip()
    workspace_path = (_PROJECT_ROOT / workspace_rel).resolve()
    if workspace_path.is_dir():
        for item in workspace_path.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
        print(f"已清空目录: {workspace_path}")
    else:
        if not workspace_path.exists():
            workspace_path.mkdir(parents=True, exist_ok=True)
            print(f"已创建空目录: {workspace_path}")
        else:
            print(f"路径存在但非目录，跳过: {workspace_path}")

    print("实验环境已清理，可重新运行 main.py 或交互模式进行全新实验。")


if __name__ == "__main__":
    main()
