"""
工作流状态管理器

提供检查点的保存和加载功能，支持工作流断点恢复。
"""

import json
import os
import time
from pathlib import Path
from typing import List, Optional

from turing_cli.config.logging_config import get_logger
from turing_cli.workflow.models import ExecutionContext

logger = get_logger(__name__)

DEFAULT_CHECKPOINT_DIR = ".workflow_checkpoints"


class StateManager:
    """工作流状态管理器

    将 ExecutionContext 序列化为 JSON 文件，支持断点恢复。

    用法::

        state_manager = StateManager()
        checkpoint_id = state_manager.save_checkpoint(context)
        # ... 之后恢复
        context = state_manager.load_checkpoint(checkpoint_id)
    """

    def __init__(self, checkpoint_dir: Optional[str] = None):
        self.checkpoint_dir = Path(checkpoint_dir or DEFAULT_CHECKPOINT_DIR)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(self, context: ExecutionContext) -> str:
        """保存执行上下文到检查点文件

        Returns:
            检查点 ID（文件名）
        """
        checkpoint_id = f"{context.project_id}_{int(time.time() * 1000)}"
        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.json"

        data = {
            "project_id": context.project_id,
            "project_metadata": context.project_metadata,
            "task_results": context.task_results,
            "completed_tasks": context.completed_tasks,
            "current_task": context.current_task,
            "error": context.error,
            "_data": context._data,
        }

        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"检查点已保存: {checkpoint_id}")
        return checkpoint_id

    def load_checkpoint(self, checkpoint_id: str) -> ExecutionContext:
        """从检查点文件恢复执行上下文

        Args:
            checkpoint_id: save_checkpoint() 返回的 ID

        Raises:
            FileNotFoundError: 检查点文件不存在
        """
        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.json"

        if not checkpoint_path.exists():
            raise FileNotFoundError(f"检查点不存在: {checkpoint_id}")

        with open(checkpoint_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        context = ExecutionContext(
            project_id=data["project_id"],
            project_metadata=data.get("project_metadata", {}),
        )
        context.task_results = data.get("task_results", {})
        context.completed_tasks = data.get("completed_tasks", [])
        context.current_task = data.get("current_task", "")
        context.error = data.get("error")
        context._data = data.get("_data", {})

        logger.info(f"检查点已加载: {checkpoint_id}")
        return context

    def list_checkpoints(self, project_id: Optional[str] = None) -> List[str]:
        """列出所有检查点 ID

        Args:
            project_id: 如果指定，只返回该项目的检查点
        """
        checkpoints = []
        for f in sorted(self.checkpoint_dir.glob("*.json")):
            checkpoint_id = f.stem
            if project_id is None or checkpoint_id.startswith(f"{project_id}_"):
                checkpoints.append(checkpoint_id)
        return checkpoints

    def delete_checkpoint(self, checkpoint_id: str) -> None:
        """删除检查点文件"""
        checkpoint_path = self.checkpoint_dir / f"{checkpoint_id}.json"
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            logger.info(f"检查点已删除: {checkpoint_id}")
