"""Rollback manager for handling agent failures."""

from pathlib import Path
from typing import Optional

from turing_cli.config.logging_config import get_logger
from turing_cli.git_ops.manager import GitManager

logger = get_logger(__name__)


class RollbackManager:
    """回滚管理器

    在 Agent 执行失败时，负责清理工作目录和分支，
    确保下一个 Agent 可以在干净的环境中执行。
    """

    def __init__(self, git_mgr: GitManager, deliverables_path: Optional[Path] = None):
        """初始化回滚管理器

        Args:
            git_mgr: Git 管理器实例
            deliverables_path: 交付件目录路径
        """
        self.git_mgr = git_mgr
        self.deliverables_path = deliverables_path

    def handle_failure(
        self,
        agent_id: str,
        branch_name: Optional[str] = None,
        clean_deliverables: bool = True,
        clean_untracked: bool = True,
    ):
        """处理 Agent 失败，执行完整的回滚操作

        Args:
            agent_id: Agent 标识符
            branch_name: 要删除的分支名，None 则根据 agent_id 生成
            clean_deliverables: 是否清理交付件
            clean_untracked: 是否清理未跟踪文件
        """
        logger.warning(f"Agent {agent_id} 失败，开始回滚...")

        # 1. 硬重置工作目录
        self.git_mgr.reset_hard()
        logger.info("  - 重置工作目录")

        # 2. 清理未跟踪文件
        if clean_untracked:
            self.git_mgr.clean_untracked()
            logger.info("  - 清理未跟踪文件")

        # 3. 删除分支
        if branch_name is None:
            branch_name = f"agent-{agent_id}"
        self.git_mgr.delete_branch(branch_name)
        logger.info(f"  - 删除分支: {branch_name}")

        # 4. 清理交付件
        if clean_deliverables and self.deliverables_path:
            self._cleanup_deliverables(agent_id)
            logger.info(f"  - 清理交付件: {agent_id}")

        logger.info(f"Agent {agent_id} 回滚完成")

    def handle_vuln_failure(
        self,
        vuln_id: str,
        branch_name: str,
        clean_deliverables: bool = True,
    ):
        """处理漏洞分析失败（兼容旧接口）

        Args:
            vuln_id: 漏洞 ID
            branch_name: 分支名称
            clean_deliverables: 是否清理交付件
        """
        self.handle_failure(
            agent_id=vuln_id,
            branch_name=branch_name,
            clean_deliverables=clean_deliverables,
        )

    def _cleanup_deliverables(self, agent_id: str):
        """清理 Agent 产生的交付件

        Args:
            agent_id: Agent 标识符
        """
        if not self.deliverables_path:
            return

        # 清理报告文件
        patterns = [
            f"vuln-{agent_id}-*.md",
            f"agent-{agent_id}-*.md",
            f"{agent_id}-*.md",
        ]

        for pattern in patterns:
            for report in self.deliverables_path.glob(pattern):
                try:
                    report.unlink()
                    logger.debug(f"删除文件: {report}")
                except Exception as e:
                    logger.warning(f"删除文件失败 {report}: {e}")

        # 清理状态文件
        state_dir = self.deliverables_path / ".turing"
        if state_dir.exists():
            state_file = state_dir / f"{agent_id}.json"
            if state_file.exists():
                try:
                    state_file.unlink()
                except Exception as e:
                    logger.warning(f"删除状态文件失败: {e}")

    def cleanup_failed_agent(self, agent_name: str, deliverables_path: Path):
        """清理失败 Agent 的交付件（兼容旧接口）"""
        self._cleanup_deliverables(agent_name)

    def checkpoint(self, name: str):
        """创建检查点（使用 stash）

        Args:
            name: 检查点名称
        """
        self.git_mgr.stash_changes(f"checkpoint-{name}")
        logger.debug(f"创建检查点: {name}")

    def restore_checkpoint(self, name: str):
        """恢复检查点

        Args:
            name: 检查点名称
        """
        self.git_mgr.pop_stash()
        logger.debug(f"恢复检查点: {name}")

    def get_cleanup_preview(self, agent_id: str) -> dict:
        """预览回滚将清理的内容

        Args:
            agent_id: Agent 标识符

        Returns:
            将被清理的文件和分支列表
        """
        preview = {
            "modified_files": self.git_mgr.get_modified_files(),
            "untracked_files": self.git_mgr.get_untracked_files(),
            "deliverables": [],
            "branch": f"agent-{agent_id}",
        }

        if self.deliverables_path:
            for pattern in [f"vuln-{agent_id}-*.md", f"{agent_id}-*.md"]:
                preview["deliverables"].extend(
                    list(self.deliverables_path.glob(pattern))
                )

        return preview
