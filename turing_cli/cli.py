import click
from turing_cli.commands import audit, status, log, retry, init


@click.group()
@click.version_option()
def cli():
    """Turing CLI - 代码漏洞审计工具

    一个用于代码漏洞审计的命令行工具，支持工作流编排和 Agent 并行调度。
    """
    pass


cli.add_command(audit.audit)
cli.add_command(status.status)
cli.add_command(log.log)
cli.add_command(retry.retry)
cli.add_command(init.init_cmd, name="init")
