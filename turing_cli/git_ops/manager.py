"""Git manager for audit operations."""

import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

import git  # gitpython library

from turing_cli.config.logging_config import get_logger
from turing_cli.models.audit import Vulnerability

logger = get_logger(__name__)


class GitManager:
    """Git 操作管理器

    提供审计过程中的 Git 分支管理、提交和回滚功能。
    每个 Agent 在独立的分支上工作，完成后合并到主审计分支。
    """

    def __init__(self, repo_path: Path):
        """初始化 Git 管理器

        Args:
            repo_path: Git 仓库路径
        """
        self.repo = git.Repo(repo_path)
        self.repo_path = repo_path
        self._audit_branch: Optional[str] = None
        self._original_branch: Optional[str] = None

    def init_audit(self, audit_id: Optional[str] = None) -> str:
        """初始化审计会话，创建审计主分支

        Args:
            audit_id: 可选的审计 ID，不提供则自动生成

        Returns:
            审计主分支名称
        """
        # 保存当前分支
        self._original_branch = self.repo.active_branch.name

        # 创建审计分支
        if audit_id is None:
            audit_id = self._get_timestamp()
        branch_name = f"audit-{audit_id}"
        self._audit_branch = branch_name

        # 检查分支是否已存在
        if branch_name in [h.name for h in self.repo.heads]:
            logger.info(f"审计分支 {branch_name} 已存在，切换到该分支")
            self.repo.git.checkout(branch_name)
        else:
            self.repo.git.checkout("-b", branch_name)
            logger.info(f"创建审计分支: {branch_name}")

        return branch_name

    def create_agent_branch(self, agent_id: str) -> str:
        """为 Agent 创建独立的工作分支

        Args:
            agent_id: Agent 标识符

        Returns:
            Agent 分支名称
        """
        if self._audit_branch is None:
            raise RuntimeError("审计未初始化，请先调用 init_audit()")

        branch_name = f"agent-{agent_id}"

        # 确保在审计分支上创建
        current = self.repo.active_branch.name
        if current != self._audit_branch:
            self.repo.git.checkout(self._audit_branch)

        # 创建新分支
        self.repo.git.checkout("-b", branch_name)
        logger.info(f"创建 Agent 分支: {branch_name}")

        return branch_name

    def create_vuln_branch(self, vuln: Vulnerability) -> str:
        """为漏洞分析创建独立分支

        Args:
            vuln: 漏洞对象

        Returns:
            漏洞分析分支名称
        """
        vuln_hash = hashlib.md5(
            f"{vuln.bugClass}.{vuln.bugMethod}".encode()
        ).hexdigest()[:6]
        branch_name = f"vuln-{vuln.type.lower()}-{vuln_hash}"

        if self._audit_branch:
            self.repo.git.checkout(self._audit_branch)
        self.repo.git.checkout("-b", branch_name)

        return branch_name

    def commit_changes(self, message: str, files: Optional[list[Path]] = None):
        """提交当前更改

        Args:
            message: 提交消息
            files: 要提交的文件列表，None 则提交所有更改
        """
        if files:
            for f in files:
                self.repo.git.add(str(f))
        else:
            self.repo.git.add("-A")

        self.repo.git.commit("-m", message)
        logger.debug(f"提交更改: {message}")

    def commit_result(self, agent_id: str, *files: Path):
        """提交 Agent 执行结果

        Args:
            agent_id: Agent 标识符
            files: 结果文件路径
        """
        self.commit_changes(f"agent-{agent_id}: completed", list(files))

    def merge_agent_branch(self, agent_branch: str, delete: bool = True):
        """将 Agent 分支合并到审计主分支

        Args:
            agent_branch: Agent 分支名称
            delete: 合并后是否删除分支
        """
        if self._audit_branch is None:
            raise RuntimeError("审计未初始化")

        # 切换到审计分支
        self.repo.git.checkout(self._audit_branch)

        # 合并
        try:
            self.repo.git.merge(agent_branch, "--no-ff")
            logger.info(f"合并分支 {agent_branch} -> {self._audit_branch}")
        except git.GitCommandError as e:
            logger.error(f"合并失败: {e}")
            raise

        # 删除分支
        if delete:
            self.repo.git.branch("-D", agent_branch)
            logger.debug(f"删除分支: {agent_branch}")

    def merge_to_main(self, branch: str):
        """合并分支到审计主分支（兼容旧接口）"""
        self.merge_agent_branch(branch)

    def reset_hard(self, target: Optional[str] = None):
        """硬重置到指定状态

        Args:
            target: 重置目标（分支名、commit hash），默认为当前分支的 HEAD
        """
        if target:
            self.repo.git.reset("--hard", target)
        else:
            self.repo.git.reset("--hard", "HEAD")
        logger.info(f"重置工作目录: {target or 'HEAD'}")

    def clean_untracked(self):
        """清理未跟踪的文件"""
        self.repo.git.clean("-fd")
        logger.info("清理未跟踪文件")

    def delete_branch(self, branch_name: str, force: bool = True):
        """删除分支

        Args:
            branch_name: 分支名称
            force: 是否强制删除
        """
        branches = [h.name for h in self.repo.heads]
        if branch_name not in branches:
            logger.debug(f"分支 {branch_name} 不存在，无需删除")
            return

        # 确保不在要删除的分支上
        current = self.repo.active_branch.name
        if current == branch_name:
            target = self._audit_branch or self._original_branch or "main"
            self.repo.git.checkout(target)

        # 删除分支
        flag = "-D" if force else "-d"
        self.repo.git.branch(flag, branch_name)
        logger.info(f"删除分支: {branch_name}")

    def get_current_branch(self) -> str:
        """获取当前分支名"""
        return self.repo.active_branch.name

    def get_modified_files(self) -> list[str]:
        """获取已修改的文件列表"""
        return [item.a_path for item in self.repo.index.diff(None)]

    def get_untracked_files(self) -> list[str]:
        """获取未跟踪的文件列表"""
        return [item for item in self.repo.untracked_files]

    def stash_changes(self, message: str = ""):
        """暂存当前更改"""
        self.repo.git.stash("push", "-m", message)
        logger.debug(f"暂存更改: {message}")

    def pop_stash(self):
        """恢复暂存的更改"""
        self.repo.git.stash("pop")
        logger.debug("恢复暂存更改")

    def finish_audit(self, merge_to_original: bool = False):
        """完成审计，清理分支

        Args:
            merge_to_original: 是否合并到原始分支
        """
        if self._audit_branch is None:
            return

        if merge_to_original and self._original_branch:
            self.repo.git.checkout(self._original_branch)
            self.repo.git.merge(self._audit_branch)
            self.repo.git.branch("-D", self._audit_branch)
            logger.info(f"合并审计分支到 {self._original_branch}")
        else:
            self.repo.git.checkout(self._audit_branch)
            logger.info(f"审计完成，保持在 {self._audit_branch} 分支")

    def _get_timestamp(self) -> str:
        """生成时间戳"""
        return datetime.now().strftime("%Y%m%d-%H%M%S")
