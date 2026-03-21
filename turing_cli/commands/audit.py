"""Audit command implementation."""

import json
from pathlib import Path

from turing_cli.config.logging_config import get_logger
from turing_cli.models.audit import ScanResult, Vulnerability
from turing_cli.workflow.builder import WorkflowBuilder
from turing_cli.workflow.engine import WorkflowEngine
from turing_cli.workflow.models import ExecutionContext
from turing_cli.agents.runner import VulnAgentRunner

logger = get_logger(__name__)


def audit(
    scan_result: str,
    code_path: str,
    deliverables: str = "./deliverables",
    opencode_url: str = "http://localhost:4097",
    config_dir: str = "./config",
    max_retries: int = 3,
    concurrency: int = 5,
    parallel: bool = True,
    **kwargs,
):
    """执行漏洞分析

    Args:
        scan_result: 扫描结果文件路径
        code_path: 代码路径
        deliverables: 交付件保存目录
        opencode_url: OpenCode URL
        config_dir: 配置目录
        max_retries: 最大重试次数
        concurrency: 并发数
        parallel: 是否并行执行
        **kwargs: 其他参数
    """
    # 检查文件是否存在
    scan_path = Path(scan_result)
    if not scan_path.exists():
        print(f"错误: 扫描结果文件不存在: {scan_result}")
        return False

    code_path_obj = Path(code_path)
    if not code_path_obj.exists():
        print(f"错误: 代码路径不存在: {code_path}")
        return False

    # 加载扫描结果
    with open(scan_result) as f:
        data = json.load(f)

    vulns = data if isinstance(data, list) else data.get("vulnerabilities", [])
    result = ScanResult(vulnerabilities=vulns)

    # 创建输出目录
    deliverables_path = Path(deliverables)
    deliverables_path.mkdir(parents=True, exist_ok=True)

    print(f"加载了 {len(result.vulnerabilities)} 个漏洞")
    print(f"代码路径: {code_path}")
    print(f"交付件目录: {deliverables_path}")
    print(f"执行模式: {'并行' if parallel else '串行'} (并发数: {concurrency})")

    if parallel:
        return _run_parallel_audit(
            result.vulnerabilities,
            code_path_obj,
            deliverables_path,
            opencode_url,
            config_dir,
            max_retries,
            concurrency,
        )
    else:
        return _run_sequential_audit(
            result.vulnerabilities,
            code_path_obj,
            deliverables_path,
            opencode_url,
            config_dir,
            max_retries,
        )


def _run_parallel_audit(
    vulnerabilities: list[Vulnerability],
    code_path: Path,
    deliverables_path: Path,
    opencode_url: str,
    config_dir: str,
    max_retries: int,
    concurrency: int,
) -> bool:
    """并行执行漏洞分析"""

    # 初始化 Git
    git_mgr = _init_git(deliverables_path)
    if git_mgr:
        git_mgr.init_audit()

    # 创建共享的 Agent Runner
    runner = VulnAgentRunner(
        config_dir=Path(config_dir),
        deliverables_path=deliverables_path,
        code_path=code_path,
        opencode_url=opencode_url,
    )
    runner.init_git(deliverables_path)

    # 创建工作流
    builder = WorkflowBuilder("parallel_vuln_audit")

    with builder.parallel_group("vulnerability_analysis") as group:
        # 动态生成 Agent 列表
        group.dynamic_agents(lambda ctx: ctx.get("agent_ids", []))
        group.max_concurrency(concurrency)

    builder.on_error("retry", max_retries=max_retries)

    # 创建 agent_runner 函数
    def agent_runner_fn(agent_id: str, context: ExecutionContext) -> dict:
        """WorkflowEngine 调用的 agent_runner"""
        # 获取漏洞信息
        vulns = context.get("vulnerabilities", {})
        vuln_data = vulns.get(agent_id)

        if not vuln_data:
            return {"status": "failed", "error": f"未找到漏洞: {agent_id}"}

        # 构建上下文
        task_context = {
            "task_data": {"vulnerability": vuln_data},
            "shared_context": {
                "project_id": context.project_id,
                "code_path": str(code_path),
            },
            "max_retries": max_retries,
        }

        return runner.run(agent_id, task_context)

    # 执行工作流
    engine = WorkflowEngine(builder.build(), agent_runner=agent_runner_fn)

    # 准备执行数据
    agent_ids = {
        f"vuln-{i}": vuln.model_dump()
        for i, vuln in enumerate(vulnerabilities)
    }

    result = engine.run({
        "project_id": f"audit-{_get_timestamp()}",
        "agent_ids": list(agent_ids.keys()),
        "vulnerabilities": agent_ids,
        "code_path": str(code_path),
    })

    # 输出结果
    _print_result(result, len(vulnerabilities))

    return result.success


def _run_sequential_audit(
    vulnerabilities: list[Vulnerability],
    code_path: Path,
    deliverables_path: Path,
    opencode_url: str,
    config_dir: str,
    max_retries: int,
) -> bool:
    """串行执行漏洞分析（兼容模式）"""

    runner = VulnAgentRunner(
        config_dir=Path(config_dir),
        deliverables_path=deliverables_path,
        code_path=code_path,
        opencode_url=opencode_url,
    )
    runner.init_git(deliverables_path)

    completed = 0
    failed = 0

    for idx, vuln in enumerate(vulnerabilities):
        vuln_id = f"vuln-{idx}"
        print(f"\n[{idx + 1}/{len(vulnerabilities)}] 分析 {vuln_id}...")

        context = {
            "task_data": {"vulnerability": vuln.model_dump()},
            "shared_context": {"code_path": str(code_path)},
            "max_retries": max_retries,
        }

        result = runner.run(vuln_id, context)

        if result.get("status") == "completed":
            completed += 1
            confidence = result.get("confidence", "unknown")
            print(f"  ✓ 完成 (置信度: {confidence})")
        else:
            failed += 1
            error = result.get("error", "未知错误")
            print(f"  ✗ 失败: {error}")

    print("\n" + "=" * 50)
    print("分析完成:")
    print(f"  总数: {len(vulnerabilities)}")
    print(f"  完成: {completed}")
    print(f"  失败: {failed}")
    print(f"  结果: {deliverables_path}")

    return failed == 0


def _init_git(path: Path):
    """初始化 Git 管理器"""
    try:
        from turing_cli.git_ops.manager import GitManager
        return GitManager(path)
    except Exception as e:
        logger.warning(f"Git 初始化失败: {e}")
        return None


def _get_timestamp() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _print_result(result, total: int):
    """输出执行结果"""
    task_results = result.task_results

    completed = sum(
        1 for r in task_results.values()
        if r.get("status") == "completed"
    )
    failed = total - completed

    print("\n" + "=" * 50)
    print("分析完成:")
    print(f"  总数: {total}")
    print(f"  完成: {completed}")
    print(f"  失败: {failed}")
    print(f"  耗时: {result.execution_time:.2f}s")
    print(f"  结果: {list(result.task_results.keys())}")

    if result.error:
        print(f"  错误: {result.error}")
