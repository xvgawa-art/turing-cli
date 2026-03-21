#!/usr/bin/env python3
"""
Turing CLI - 代码漏洞审计工具

直接运行方式：
    python main.py audit <scan-result> -c <code-path> [options]
    python main.py init <name> [options]
    python main.py status
    python main.py log [options]
    python main.py retry <vuln-id> [options]
"""

import sys
import argparse
from pathlib import Path

# 添加项目根目录到 Python 路径，以支持独立运行
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入命令模块
from turing_cli.commands import audit, status, log, retry, init


def create_parser():
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="Turing CLI - 代码漏洞审计工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
    # 创建新的工作流脚手架
    python main.py init my_workflow
    python main.py init my_audit -d "审计工作流" --with-agent

    # 执行漏洞分析
    python main.py audit scan_result.json -c /path/to/code
    python main.py audit scan_result.json -c /path/to/code -d ./deliverables

    # 其他命令
    python main.py status
    python main.py log --oneline
    python main.py retry vuln-id-0
    python main.py retry --all --scan-result scan_result.json
        """
    )

    parser.add_argument('--version', action='version', version='Turing CLI 1.0.0')

    # 创建子命令解析器
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # init 命令
    init_parser = subparsers.add_parser('init', help='创建工作流脚手架')
    init_parser.add_argument('name', nargs='?', default='my_workflow', help='工作流名称')
    init_parser.add_argument('-d', '--description', default='A custom workflow', help='工作流描述')
    init_parser.add_argument('-o', '--output', default='.', help='输出目录')
    init_parser.add_argument('-a', '--with-agent', action='store_true', help='同时创建自定义 Agent 模板')

    # audit 命令
    audit_parser = subparsers.add_parser('audit', help='执行漏洞分析')
    audit_parser.add_argument('scan_result', help='扫描结果文件路径')
    audit_parser.add_argument('-c', '--code-path', required=True, help='代码路径')
    audit_parser.add_argument('-d', '--deliverables', default='./deliverables', help='交付件保存目录')
    audit_parser.add_argument('--opencode-url', default='http://localhost:4097', help='OpenCode URL')
    audit_parser.add_argument('--config-dir', default='./config', help='配置目录')
    audit_parser.add_argument('--max-retries', type=int, default=3, help='最大重试次数')
    audit_parser.add_argument('--concurrency', type=int, default=5, help='并发数')
    audit_parser.add_argument('--no-parallel', action='store_true', help='禁用并行执行')

    # status 命令
    status_parser = subparsers.add_parser('status', help='查看当前审计状态')

    # log 命令
    log_parser = subparsers.add_parser('log', help='查看审计历史')
    log_parser.add_argument('--oneline', action='store_true', help='单行显示')

    # retry 命令
    retry_parser = subparsers.add_parser('retry', help='重试失败的漏洞分析')
    retry_group = retry_parser.add_mutually_exclusive_group(required=True)
    retry_group.add_argument('vuln_id', nargs='?', help='漏洞ID')
    retry_group.add_argument('--all', action='store_true', help='重试所有失败的漏洞')
    retry_parser.add_argument('--scan-result', help='扫描结果文件路径（配合--all使用）')

    return parser


def main():
    """主函数"""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == 'init':
            return init.create_scaffold(
                project_name=args.name,
                description=args.description,
                output=args.output,
                with_agent=args.with_agent,
            )
        elif args.command == 'audit':
            audit.audit(
                scan_result=args.scan_result,
                code_path=args.code_path,
                deliverables=args.deliverables,
                opencode_url=args.opencode_url,
                config_dir=args.config_dir,
                max_retries=args.max_retries,
                concurrency=args.concurrency,
                parallel=not args.no_parallel,
            )
        elif args.command == 'status':
            status.status()
        elif args.command == 'log':
            log.log(oneline=args.oneline)
        elif args.command == 'retry':
            retry.retry(
                vuln_id=args.vuln_id,
                retry_all=args.all,
                scan_result=args.scan_result
            )
        else:
            print(f"未知命令: {args.command}", file=sys.stderr)
            return 1

        return 0

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
