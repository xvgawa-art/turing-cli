#!/usr/bin/env python3
"""
完整工作流示例 - 代码审计工作流

使用 turing-cli 框架对扫描结果进行自动化分析。

使用方法:
    cd ~/turing-cli
    source venv/bin/activate
    python examples/full_audit_workflow.py

环境要求:
    - 测试数据在 ~/test_case/ 目录
    - 如需调用 OpenCode，需要 server 运行在 http://localhost:4097
    - 如需调用 MCP，需要 MCP server 运行在 python -u /opt/server.py
"""

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from turing_cli.agents.context import AgentContext
from turing_cli.agents.runner import AgentRunner, BaseAgent
from turing_cli.clients.mcp_client import MCPClient, run_mcp_tool_sync
from turing_cli.config.loader import ConfigLoader
from turing_cli.config.logging_config import get_logger
from turing_cli.mcp import AuditMCPService, MCPToolExecutionError, MCPToolRegistry
from turing_cli.mcp.executor import MCPExecutor
from turing_cli.models.deliverable import AgentResult, Deliverable, DeliverableStatus
from turing_cli.models.validation import ValidationResult

logger = get_logger(__name__)


# ============================================================
# 配置
# ============================================================

TEST_CASE_DIR = Path.home() / "test_case"
CODE_PATH = TEST_CASE_DIR / "java-sec-code"
SCAN_RESULT_PATH = TEST_CASE_DIR / "vuln_report.json"
DELIVERABLES_DIR = Path("./deliverables")
CONFIG_DIR = project_root / "config"

OPENCODE_URL = "http://localhost:4097"
MAX_RETRIES = 2

# 这里保留漏洞生成工具和 server_command 的演示配置，
# 因为当前示例里“生成漏洞报告”这一步仍然是独立裸调用。
#
# 真正给 Agent 使用的 MCP 工具注册（例如 method_source）
# 已经迁移到 config/mcp_tools.yaml，由 MCPToolRegistry 统一加载。
MCP_SERVER_COMMAND = "python -u /opt/server.py"
MCP_VULN_TOOL_NAME = "cloudbug_analyze_cloudbug_analyze"
USE_MCP = True
USE_MCP_METHOD_SOURCE = True


def _extract_json_payload(value: Any) -> Any:
    """从 MCP 返回值中提取 JSON 负载。

    MCP 工具返回值在不同实现下可能是：
    - 带 content 属性的对象
    - dict
    - list[TextContent]
    - 纯字符串

    这里做一个尽量稳健的兼容提取，避免示例代码因为返回结构差异而失效。
    """
    if hasattr(value, "content"):
        content = value.content
    elif isinstance(value, dict):
        content = value
    elif isinstance(value, list) and value:
        first_item = value[0]
        if hasattr(first_item, "text"):
            content = first_item.text
        elif hasattr(first_item, "content"):
            content = first_item.content
        else:
            content = first_item
    else:
        content = str(value)

    if isinstance(content, str):
        json_match = re.search(r"\[[\s\S]*\]", content) or re.search(r"\{[\s\S]*\}", content)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(content)
    return content


def generate_vulnerabilities_via_mcp(
    jar_path: Path,
    vulnerabilities_jar_path: Path,
    callchain_json_path: Path,
    extract_path: Path,
    output_path: Path,
) -> bool:
    """通过 MCP 工具生成漏洞报告。"""
    if not MCPClient().is_available():
        logger.error("MCP 不可用，请安装 mcp 包: pip install mcp")
        return False

    print("\n" + "=" * 70)
    print("调用 MCP 工具生成漏洞报告...")
    print("=" * 70)
    print(f"  JAR 路径: {jar_path}")
    print(f"  漏洞 JAR 路径: {vulnerabilities_jar_path}")
    print(f"  调用链 JSON 路径: {callchain_json_path}")
    print(f"  提取路径: {extract_path}")
    print(f"  输出路径: {output_path}")

    for path, name in [
        (jar_path, "JAR 文件"),
        (vulnerabilities_jar_path, "漏洞 JAR 文件"),
        (callchain_json_path, "调用链 JSON 文件"),
    ]:
        if not path.exists():
            logger.error(f"{name}不存在: {path}")
            return False

    try:
        result = run_mcp_tool_sync(
            server_command=MCP_SERVER_COMMAND,
            tool_name=MCP_VULN_TOOL_NAME,
            arguments={
                "jar_path": str(jar_path),
                "vulnerabilities_jar_path": str(vulnerabilities_jar_path),
                "callchain_json_path": str(callchain_json_path),
                "extract_path": str(extract_path),
            },
        )

        print(f"\nMCP 工具执行结果: {result}")

        content = _extract_json_payload(result)
        if isinstance(content, dict):
            vulnerabilities = [content]
        elif isinstance(content, list):
            vulnerabilities = content
        else:
            logger.error(f"无法解析漏洞数据: {type(content)}")
            return False

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(vulnerabilities, f, ensure_ascii=False, indent=2)

        print(f"\n成功生成漏洞报告: {output_path}")
        print(f"  漏洞数量: {len(vulnerabilities)}")
        return True

    except Exception as e:
        logger.error(f"调用 MCP 工具失败: {e}")
        import traceback
        traceback.print_exc()
        return False


class VulnerabilityAnalysisAgent(BaseAgent):
    """漏洞分析 Agent。

    该 Agent 的职责不是直接了解某个 MCP 工具名，
    而是通过 AgentContext 获取已经注入好的 AuditMCPService，
    然后使用高层领域接口（如 get_method_source）来拿源码上下文。

    这种写法的好处是：
    - Agent 代码不关心真实 tool_name
    - MCP server 更换实现时，Agent 不需要改
    - tool_name、描述、注册关系都集中配置化管理
    """

    def __init__(self, agent_type: str, description: str = ""):
        self._agent_type = agent_type
        self._description = description or f"{agent_type} 分析 Agent"

    @property
    def agent_type(self) -> str:
        return self._agent_type

    @property
    def description(self) -> str:
        return self._description

    def execute(self, context: AgentContext) -> Deliverable:
        """执行漏洞分析。"""
        start_time = time.time()

        vuln = context.get_vulnerability() or {}
        code_path = context.code_path
        client = context.get_opencode_client()
        mcp_service = context.get_mcp_service()

        # 先通过 MCP 获取漏洞相关的方法源码，再把这些上下文交给大模型推理。
        source_context = self._collect_source_context(vuln, code_path, mcp_service)

        if client and client.is_available():
            result = self._analyze_with_opencode(
                context,
                client,
                vuln,
                code_path,
                source_context,
            )
        else:
            result = self._mock_analysis(vuln, code_path, source_context)

        result["source_context"] = source_context

        return Deliverable(
            agent_id=context.agent_id,
            agent_type=self.agent_type,
            phase=context.phase,
            status=DeliverableStatus.COMPLETED,
            confidence=result.get("confidence"),
            content=result,
            execution_time=time.time() - start_time,
        )

    def _collect_source_context(
        self,
        vuln: Dict[str, Any],
        code_path: Path,
        mcp_service: Optional[AuditMCPService],
    ) -> Dict[str, Any]:
        """收集源码上下文。

        当前策略很简单：
        - 如果有 bugClass + bugMethod，就抓 bug 方法源码
        - 如果有 sinkClass + sinkMethod，就抓 sink 方法源码

        后续这里可以扩展成：
        - 根据漏洞类型抓不同节点
        - 结合调用链抓中间关键方法
        - 抓 source / sink / sanitizer 的组合上下文
        """
        if not mcp_service or not mcp_service.is_available() or not USE_MCP_METHOD_SOURCE:
            return {}

        collected: Dict[str, Any] = {}
        for label, class_name, method_name in self._get_source_targets(vuln):
            try:
                collected[label] = mcp_service.get_method_source(
                    class_name=class_name,
                    method_name=method_name,
                    code_path=str(code_path),
                )
            except MCPToolExecutionError as exc:
                collected[f"{label}_error"] = str(exc)
            except Exception as exc:
                collected[f"{label}_error"] = f"未预期错误: {exc}"

        return collected

    def _get_source_targets(self, vuln: Dict[str, Any]) -> list[tuple[str, str, str]]:
        """根据漏洞信息决定要抓哪些源码目标。"""
        targets: list[tuple[str, str, str]] = []
        bug_class = vuln.get("bugClass")
        bug_method = vuln.get("bugMethod")
        sink_class = vuln.get("sinkClass")
        sink_method = vuln.get("sinkMethod")

        if bug_class and bug_method:
            targets.append(("bug_method_source", bug_class, bug_method))
        if sink_class and sink_method:
            targets.append(("sink_method_source", sink_class, sink_method))
        return targets

    def _analyze_with_opencode(
        self,
        context: AgentContext,
        client,
        vuln: Dict[str, Any],
        code_path: Path,
        source_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """使用 OpenCode 进行推理分析。"""
        session_id = context.get_session_id()
        if not session_id:
            session_id = client.create_session()
            context.set_session_id(session_id)

        prompt = self._build_analysis_prompt(vuln, code_path, source_context)

        try:
            providers = client.get_providers()
            if not providers:
                logger.warning("未获取到可用 Provider，使用 Mock 分析")
                return self._mock_analysis(vuln, code_path, source_context)

            provider = providers[0]
            model_id = list(provider["models"].keys())[0] if provider["models"] else "default"

            response = client.chat(
                session_id=session_id,
                prompt=prompt,
                model_id=model_id,
                provider_id=provider["id"],
            )
            return self._parse_opencode_response(response)
        except Exception as e:
            logger.warning(f"OpenCode 调用失败: {e}")
            return self._mock_analysis(vuln, code_path, source_context)

    def _build_analysis_prompt(
        self,
        vuln: Dict[str, Any],
        code_path: Path,
        source_context: Dict[str, Any],
    ) -> str:
        """构建分析 Prompt。"""
        return f"""你是一个专业的安全审计专家，请分析以下潜在的 {self.agent_type} 漏洞。

**项目路径**: {code_path}

**漏洞信息**:
- 类型: {vuln.get('type', 'N/A')}
- Bug 类: {vuln.get('bugClass', 'N/A')}
- Bug 方法: {vuln.get('bugMethod', 'N/A')}
- Bug 行: {vuln.get('bugLine', 'N/A')}
- Sink 类: {vuln.get('sinkClass', 'N/A')}
- Sink 方法: {vuln.get('sinkMethod', 'N/A')}
- 调用链: {json.dumps(vuln.get('callTree', {}), ensure_ascii=False, indent=2)}

**通过 MCP 获取的方法源码上下文**:
{json.dumps(source_context, ensure_ascii=False, indent=2)}

请结合漏洞信息和源码上下文分析漏洞的可利用性，并以 JSON 格式返回结果：
{{
    "confidence": "confirmed|likely|unlikely|false-positive",
    "vuln_type": "{self.agent_type}",
    "sink_class": "sink 类名",
    "sink_method": "sink 方法名",
    "source": "用户输入来源",
    "analysis": "详细分析报告（Markdown 格式）",
    "recommendation": "修复建议"
}}
"""

    def _parse_opencode_response(self, response: Any) -> Dict[str, Any]:
        """解析 OpenCode 响应。"""
        content = ""

        if hasattr(response, "to_dict") and callable(response.to_dict):
            try:
                data = response.to_dict()
                if "parts" in data and isinstance(data["parts"], list):
                    for part in data["parts"]:
                        if part.get("type") == "text" and "text" in part:
                            content = part["text"]
                            break
            except Exception:
                pass

        if not content:
            if hasattr(response, "content") and response.content:
                content = response.content
            elif hasattr(response, "text"):
                content = response.text
            else:
                content = str(response) if response else ""

        json_match = re.search(r"```json\s*\n([\s\S]*?)\n```", content)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
                result["raw_response"] = content
                return result
            except json.JSONDecodeError:
                pass

        json_match = re.search(r"\{[\s\S]*?\}", content)
        if json_match:
            try:
                result = json.loads(json_match.group())
                result["raw_response"] = content
                return result
            except json.JSONDecodeError:
                pass

        confidence = "likely"
        content_lower = content.lower()
        if "confirmed" in content_lower or "已确认" in content_lower:
            confidence = "confirmed"
        elif "false-positive" in content_lower or "误报" in content_lower:
            confidence = "false-positive"
        elif "unlikely" in content_lower or "不太可能" in content_lower:
            confidence = "unlikely"

        return {
            "confidence": confidence,
            "analysis": content,
            "raw_response": content,
        }

    def _mock_analysis(
        self,
        vuln: Dict[str, Any],
        code_path: Path,
        source_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """模拟分析（OpenCode 不可用时使用）。"""
        vuln_type = vuln.get("type", "Unknown")
        bug_class = vuln.get("bugClass", "N/A")
        bug_method = vuln.get("bugMethod", "N/A")
        bug_line = vuln.get("bugLine", "N/A")
        sink_class = vuln.get("sinkClass", "N/A")
        sink_method = vuln.get("sinkMethod", "N/A")

        confidence_map = {
            "SQL注入": "confirmed",
            "XSS": "likely",
            "SSRF": "likely",
            "命令注入": "confirmed",
            "路径遍历": "likely",
        }
        confidence = confidence_map.get(vuln_type, "likely")

        source_summary = json.dumps(source_context or {}, ensure_ascii=False, indent=2)

        analysis = f"""## {vuln_type} 漏洞分析报告

### 漏洞位置
- **类**: `{bug_class}`
- **方法**: `{bug_method}`
- **行号**: {bug_line}

### Sink 信息
- **Sink 类**: `{sink_class}`
- **Sink 方法**: `{sink_method}`

### MCP 源码上下文
```json
{source_summary}
```

### 分析结论

该漏洞存在较高的可利用性。用户输入直接传递到危险的 sink 点，
没有经过有效的输入验证或过滤。

**置信度**: {confidence}

### 漏洞详情

根据调用链分析，用户可控的输入经过以下路径到达 sink 点：

1. 用户输入进入 `{bug_method}` 方法
2. 数据直接传递到 `{sink_class}.{sink_method}`
3. 未经过有效的输入验证或编码

### 修复建议

1. **输入验证**: 对用户输入进行严格的类型和格式验证
2. **参数化查询**: 使用参数化语句而非字符串拼接
3. **最小权限**: 确保数据库连接使用最小权限账户
4. **输出编码**: 对输出进行适当的编码处理
"""

        return {
            "confidence": confidence,
            "vuln_type": vuln_type,
            "sink_class": sink_class,
            "sink_method": sink_method,
            "source": "用户输入参数",
            "analysis": analysis,
            "recommendation": "实施输入验证和参数化查询",
        }

    def validate(self, deliverable: Deliverable) -> ValidationResult:
        """验证交付件。"""
        content = deliverable.content
        required = ["confidence", "analysis"]
        missing = [f for f in required if not content.get(f)]
        if missing:
            return ValidationResult.failure(f"缺少必要字段: {', '.join(missing)}")

        valid_confidences = ["confirmed", "likely", "unlikely", "false-positive"]
        confidence = content.get("confidence")
        if confidence not in valid_confidences:
            return ValidationResult.failure(
                f"无效的置信度: {confidence}，有效值为: {valid_confidences}"
            )

        analysis = content.get("analysis", "")
        if len(analysis) < 50:
            return ValidationResult.failure(
                f"分析内容过短（{len(analysis)} 字符），请提供更详细的分析"
            )

        return ValidationResult.success()


def build_audit_mcp_service(config_dir: Path, server_command: str) -> AuditMCPService:
    """从配置文件构建审计场景 MCP Service。

    这里是“配置驱动”接入的关键入口：
    1. 通过 ConfigLoader 读取 ``config/mcp_tools.yaml``
    2. 由 MCPToolRegistry.from_config(...) 构建注册表
    3. 再由 executor + service 组合成最终可注入给 AgentRunner 的服务对象

    以后新增工具时，通常只需要：
    - 在 mcp_tools.yaml 中追加工具定义
    - 在 AuditMCPService 中新增高层方法
    而不需要再改 Agent 的底层接线逻辑。
    """
    loader = ConfigLoader(config_dir)
    mcp_config = loader.load_mcp_config()
    registry = MCPToolRegistry.from_config(mcp_config)
    executor = MCPExecutor(server_command, registry)
    return AuditMCPService(server_command=server_command, executor=executor)


def main():
    print("=" * 70)
    print("代码审计工作流示例")
    print("=" * 70)

    if not CODE_PATH.exists():
        print(f"错误: 代码目录不存在: {CODE_PATH}")
        return 1

    vulnerabilities = []

    if USE_MCP:
        jar_path = TEST_CASE_DIR / "target.jar"
        vulnerabilities_jar_path = TEST_CASE_DIR / "vulnerabilities.jar"
        callchain_json_path = TEST_CASE_DIR / "callchain.json"
        extract_path = TEST_CASE_DIR / "extracted"

        success = generate_vulnerabilities_via_mcp(
            jar_path=jar_path,
            vulnerabilities_jar_path=vulnerabilities_jar_path,
            callchain_json_path=callchain_json_path,
            extract_path=extract_path,
            output_path=SCAN_RESULT_PATH,
        )

        if not success:
            print("错误: MCP 工具调用失败")
            return 1

    if not SCAN_RESULT_PATH.exists():
        print(f"错误: 扫描结果文件不存在: {SCAN_RESULT_PATH}")
        return 1

    with open(SCAN_RESULT_PATH, encoding="utf-8") as f:
        vulnerabilities = json.load(f)

    print(f"\n加载了 {len(vulnerabilities)} 个漏洞:")
    for i, vuln in enumerate(vulnerabilities):
        print(f"  [{i}] {vuln.get('type', 'Unknown')} - {vuln.get('bugMethod', 'N/A')}")

    DELIVERABLES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n交付件目录: {DELIVERABLES_DIR.absolute()}")

    print("\n初始化 AgentRunner...")
    print(f"  OpenCode URL: {OPENCODE_URL}")
    print(f"  MCP 配置目录: {CONFIG_DIR}")

    mcp_service = build_audit_mcp_service(
        config_dir=CONFIG_DIR,
        server_command=MCP_SERVER_COMMAND,
    )
    runner = AgentRunner(
        opencode_url=OPENCODE_URL,
        max_retries=MAX_RETRIES,
        deliverables_dir=DELIVERABLES_DIR,
        mcp_service=mcp_service,
    )

    try:
        runner.initialize()
        client = runner.get_client()
        if client and client.is_available():
            providers = client.get_providers()
            if providers:
                print(f"  OpenCode 可用，Provider: {providers[0]['name']}")
            else:
                print("  OpenCode 已连接但未获取到 Provider")
        else:
            print("  OpenCode 不可用，将使用 Mock 分析模式")
    except Exception as e:
        print(f"  OpenCode 初始化失败: {e}")
        print("  将使用 Mock 分析模式")

    if mcp_service.is_available() and USE_MCP_METHOD_SOURCE:
        method_source_spec = MCPToolRegistry.from_config(
            ConfigLoader(CONFIG_DIR).load_mcp_config()
        ).require("method_source")
        print(f"  MCP 方法源码工具已启用: {method_source_spec.tool_name}")
    else:
        print("  MCP 方法源码工具不可用或已禁用")

    print("\n注册 Agent...")
    agent_ids = []
    type_mapping = {
        "SQL注入": "sql_injection",
        "XSS": "xss",
        "SSRF": "ssrf",
        "命令注入": "command_injection",
        "路径遍历": "path_traversal",
    }

    for i, vuln in enumerate(vulnerabilities):
        agent_id = f"vuln-{i}"
        vuln_type = vuln.get("type", "unknown")
        agent_type = type_mapping.get(vuln_type, vuln_type.lower().replace(" ", "_"))

        agent = VulnerabilityAnalysisAgent(
            agent_type=agent_type,
            description=f"{vuln_type} 漏洞分析",
        )

        runner.register_agent(agent_id, agent)
        agent_ids.append(agent_id)
        print(f"  [{i}] {agent_id} -> {agent_type}")

    project_id = f"audit-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    shared_context = {
        "project_id": project_id,
        "code_path": str(CODE_PATH),
        "deliverables_dir": str(DELIVERABLES_DIR),
        "phase_results": {},
    }

    print(f"\n项目 ID: {project_id}")
    print(f"代码路径: {CODE_PATH}")

    print("\n" + "=" * 70)
    print("开始执行工作流（并发模式）...")
    print("=" * 70)

    tasks: list[tuple[str, AgentContext]] = []
    for agent_id, vuln in zip(agent_ids, vulnerabilities):
        print(f"准备任务: {agent_id} - {vuln.get('type', 'Unknown')}")
        context = AgentContext(
            agent_id=agent_id,
            agent_type=runner.get_agent(agent_id).agent_type,
            phase="code_audit",
            shared_context=shared_context,
        )
        context.set_vulnerability(vuln)
        tasks.append((agent_id, context))

    print(f"\n使用 max_workers={min(5, len(tasks))} 并发执行 {len(tasks)} 个任务...")
    results = runner.run_batch(tasks, max_workers=min(5, len(tasks)), show_progress=True)

    completed = sum(1 for r in results if r.success)
    failed = len(results) - completed

    for result in results:
        if result.success and result.deliverable:
            result.deliverable.save(DELIVERABLES_DIR / "code_audit")

    print("\n" + "=" * 70)
    print("执行结果详情")
    print("=" * 70)
    for i, (agent_id, result, vuln) in enumerate(zip(agent_ids, results, vulnerabilities)):
        status = "✓ 成功" if result.success else "✗ 失败"
        confidence = result.deliverable.confidence if result.deliverable and result.success else "-"
        print(f"  [{i + 1}] {agent_id} ({vuln.get('type', 'Unknown')})")
        print(f"      状态: {status}, 置信度: {confidence}, 尝试次数: {result.attempts}")
        if not result.success and result.error:
            print(f"      错误: {result.error}")

    print("\n" + "=" * 70)
    print("工作流执行完成")
    print("=" * 70)
    print(f"  总数: {len(agent_ids)}")
    print(f"  完成: {completed}")
    print(f"  失败: {failed}")
    print(f"  交付件目录: {DELIVERABLES_DIR.absolute()}")

    report_path = DELIVERABLES_DIR / "summary_report.md"
    generate_summary_report(report_path, results, vulnerabilities)
    print(f"  汇总报告: {report_path}")

    return 0 if failed == 0 else 1


def generate_summary_report(
    report_path: Path,
    results: list[AgentResult],
    vulnerabilities: list[Dict[str, Any]],
) -> None:
    """生成汇总报告。"""
    lines = [
        "# 代码审计汇总报告",
        "",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 漏洞分析结果",
        "",
        "| # | 类型 | 位置 | 置信度 | 状态 |",
        "|---|------|------|--------|------|",
    ]

    for i, (result, vuln) in enumerate(zip(results, vulnerabilities)):
        status = "✓ 完成" if result.success else "✗ 失败"
        confidence = result.deliverable.confidence if result.deliverable and result.success else "-"
        location = f"{vuln.get('bugClass', '')}.{vuln.get('bugMethod', '')}"
        lines.append(
            f"| {i + 1} | {vuln.get('type', '-')} | {location} | {confidence} | {status} |"
        )

    lines.extend(["", "## 详细分析", ""])

    for i, (result, vuln) in enumerate(zip(results, vulnerabilities)):
        if result.success and result.deliverable:
            analysis = result.deliverable.content.get("analysis", "")
            lines.extend([
                f"### {i + 1}. {vuln.get('type', 'Unknown')}",
                "",
                analysis,
                "",
            ])

    report_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
