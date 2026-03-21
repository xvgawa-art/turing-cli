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
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from turing_cli.agents.runner import AgentRunner, BaseAgent
from turing_cli.agents.context import AgentContext
from turing_cli.models.deliverable import Deliverable, DeliverableStatus, AgentResult
from turing_cli.models.validation import ValidationResult
from turing_cli.config.logging_config import get_logger

logger = get_logger(__name__)


# ============================================================
# 配置
# ============================================================

TEST_CASE_DIR = Path.home() / "test_case"
CODE_PATH = TEST_CASE_DIR / "java-sec-code"
SCAN_RESULT_PATH = TEST_CASE_DIR / "vuln_report.json"
DELIVERABLES_DIR = Path("./deliverables")

OPENCODE_URL = "http://localhost:4097"
MAX_RETRIES = 2


# ============================================================
# Agent 实现
# ============================================================


class VulnerabilityAnalysisAgent(BaseAgent):
    """漏洞分析 Agent

    分析特定类型的漏洞，输出结构化报告。
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
        """执行漏洞分析"""
        start_time = time.time()

        # 获取漏洞信息
        vuln = context.get_vulnerability() or {}

        # 获取代码路径
        code_path = context.code_path

        # 尝试获取 OpenCode 客户端
        client = context.get_opencode_client()

        if client and client.is_available():
            # 使用 OpenCode 进行分析
            result = self._analyze_with_opencode(context, client, vuln, code_path)
        else:
            # 使用模拟分析
            result = self._mock_analysis(vuln, code_path)

        return Deliverable(
            agent_id=context.agent_id,
            agent_type=self.agent_type,
            phase=context.phase,
            status=DeliverableStatus.COMPLETED,
            confidence=result.get("confidence"),
            content=result,
            execution_time=time.time() - start_time,
        )

    def _analyze_with_opencode(
        self,
        context: AgentContext,
        client,
        vuln: Dict,
        code_path: Path,
    ) -> Dict[str, Any]:
        """使用 OpenCode 进行分析"""
        # 创建或获取 Session
        session_id = context.get_session_id()
        if not session_id:
            session_id = client.create_session()
            context.set_session_id(session_id)

        # 构建 Prompt
        prompt = self._build_analysis_prompt(vuln, code_path)

        try:
            # 获取 Provider
            providers = client.get_providers()
            if not providers:
                logger.warning("未获取到可用 Provider，使用 Mock 分析")
                return self._mock_analysis(vuln, code_path)

            provider = providers[0]
            model_id = list(provider["models"].keys())[0] if provider["models"] else "default"

            # 调用 OpenCode
            response = client.chat(
                session_id=session_id,
                prompt=prompt,
                model_id=model_id,
                provider_id=provider["id"],
            )

            # 解析响应
            return self._parse_opencode_response(response)

        except Exception as e:
            logger.warning(f"OpenCode 调用失败: {e}")
            return self._mock_analysis(vuln, code_path)

    def _build_analysis_prompt(self, vuln: Dict, code_path: Path) -> str:
        """构建分析 Prompt"""
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

请分析漏洞的可利用性，并以 JSON 格式返回结果：
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
        """解析 OpenCode 响应

        Response 结构 (to_dict()):
        {
            'info': {...},
            'parts': [
                {'type': 'step-start', ...},
                {'type': 'text', 'text': '响应内容...', ...},
                {'type': 'step-finish', ...}
            ]
        }
        """
        import re

        # 尝试获取内容
        content = ""

        # 优先使用 to_dict() 方法解析结构化响应
        if hasattr(response, "to_dict") and callable(response.to_dict):
            try:
                data = response.to_dict()
                if "parts" in data and isinstance(data["parts"], list):
                    # 从 parts 中提取 type="text" 的内容
                    for part in data["parts"]:
                        if part.get("type") == "text" and "text" in part:
                            content = part["text"]
                            break
            except Exception:
                # to_dict() 失败，尝试其他方式
                pass

        # 兜底：尝试直接获取属性
        if not content:
            if hasattr(response, "content") and response.content:
                content = response.content
            elif hasattr(response, "text"):
                content = response.text
            else:
                content = str(response) if response else ""

        # 尝试提取 JSON 代码块 (```json ... ```)
        json_match = re.search(r"```json\s*\n([\s\S]*?)\n```", content)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
                result["raw_response"] = content
                return result
            except json.JSONDecodeError:
                pass

        # 如果没有找到 ```json 代码块，尝试提取任意 JSON 对象
        json_match = re.search(r"\{[\s\S]*?\}", content)
        if json_match:
            try:
                result = json.loads(json_match.group())
                result["raw_response"] = content
                return result
            except json.JSONDecodeError:
                pass

        # 无法解析 JSON，尝试提取置信度
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

    def _mock_analysis(self, vuln: Dict, code_path: Path) -> Dict[str, Any]:
        """模拟分析（OpenCode 不可用时使用）"""
        vuln_type = vuln.get("type", "Unknown")
        bug_class = vuln.get("bugClass", "N/A")
        bug_method = vuln.get("bugMethod", "N/A")
        bug_line = vuln.get("bugLine", "N/A")
        sink_class = vuln.get("sinkClass", "N/A")
        sink_method = vuln.get("sinkMethod", "N/A")

        # 根据漏洞类型设置默认置信度
        confidence_map = {
            "SQL注入": "confirmed",
            "XSS": "likely",
            "SSRF": "likely",
            "命令注入": "confirmed",
            "路径遍历": "likely",
        }
        confidence = confidence_map.get(vuln_type, "likely")

        analysis = f"""## {vuln_type} 漏洞分析报告

### 漏洞位置
- **类**: `{bug_class}`
- **方法**: `{bug_method}`
- **行号**: {bug_line}

### Sink 信息
- **Sink 类**: `{sink_class}`
- **Sink 方法**: `{sink_method}`

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
        """验证交付件"""
        content = deliverable.content

        # 检查必要字段
        required = ["confidence", "analysis"]
        missing = [f for f in required if not content.get(f)]
        if missing:
            return ValidationResult.failure(f"缺少必要字段: {', '.join(missing)}")

        # 检查置信度
        valid_confidences = ["confirmed", "likely", "unlikely", "false-positive"]
        confidence = content.get("confidence")
        if confidence not in valid_confidences:
            return ValidationResult.failure(
                f"无效的置信度: {confidence}，有效值为: {valid_confidences}"
            )

        # 检查分析内容长度
        analysis = content.get("analysis", "")
        if len(analysis) < 50:
            return ValidationResult.failure(
                f"分析内容过短（{len(analysis)} 字符），请提供更详细的分析"
            )

        return ValidationResult.success()


# ============================================================
# 主函数
# ============================================================


def main():
    """主函数"""
    print("=" * 70)
    print("代码审计工作流示例")
    print("=" * 70)

    # 1. 检查测试数据
    if not SCAN_RESULT_PATH.exists():
        print(f"错误: 扫描结果文件不存在: {SCAN_RESULT_PATH}")
        return 1

    if not CODE_PATH.exists():
        print(f"错误: 代码目录不存在: {CODE_PATH}")
        return 1

    # 2. 加载扫描结果
    with open(SCAN_RESULT_PATH, encoding="utf-8") as f:
        vulnerabilities = json.load(f)

    print(f"\n加载了 {len(vulnerabilities)} 个漏洞:")
    for i, vuln in enumerate(vulnerabilities):
        print(f"  [{i}] {vuln.get('type', 'Unknown')} - {vuln.get('bugMethod', 'N/A')}")

    # 3. 创建交付件目录
    DELIVERABLES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n交付件目录: {DELIVERABLES_DIR.absolute()}")

    # 4. 初始化 AgentRunner
    print(f"\n初始化 AgentRunner...")
    print(f"  OpenCode URL: {OPENCODE_URL}")

    runner = AgentRunner(
        opencode_url=OPENCODE_URL,
        max_retries=MAX_RETRIES,
        deliverables_dir=DELIVERABLES_DIR,
    )

    # 检查 OpenCode 是否可用
    opencode_available = False
    try:
        runner.initialize()
        client = runner.get_client()
        if client and client.is_available():
            providers = client.get_providers()
            if providers:
                print(f"  OpenCode 可用，Provider: {providers[0]['name']}")
                opencode_available = True
            else:
                print(f"  OpenCode 已连接但未获取到 Provider")
        else:
            print(f"  OpenCode 不可用，将使用 Mock 分析模式")
    except Exception as e:
        print(f"  OpenCode 初始化失败: {e}")
        print("  将使用 Mock 分析模式")

    # 5. 注册 Agent
    print("\n注册 Agent...")
    agent_ids = []

    # 漏洞类型映射
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

    # 6. 创建共享上下文
    project_id = f"audit-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    shared_context = {
        "project_id": project_id,
        "code_path": str(CODE_PATH),
        "deliverables_dir": str(DELIVERABLES_DIR),
        "phase_results": {},
    }

    print(f"\n项目 ID: {project_id}")
    print(f"代码路径: {CODE_PATH}")

    # 7. 执行工作流（并发）
    print("\n" + "=" * 70)
    print("开始执行工作流（并发模式）...")
    print("=" * 70)

    # 准备任务列表
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

    # 并发执行
    print(f"\n使用 max_workers={min(5, len(tasks))} 并发执行 {len(tasks)} 个任务...")
    results = runner.run_batch(tasks, max_workers=min(5, len(tasks)), show_progress=True)

    # 统计结果
    completed = sum(1 for r in results if r.success)
    failed = len(results) - completed

    # 保存成功的交付件
    for result in results:
        if result.success and result.deliverable:
            result.deliverable.save(DELIVERABLES_DIR / "code_audit")

    # 8. 输出详细结果
    print("\n" + "=" * 70)
    print("执行结果详情")
    print("=" * 70)
    for i, (agent_id, result, vuln) in enumerate(zip(agent_ids, results, vulnerabilities)):
        status = "✓ 成功" if result.success else "✗ 失败"
        confidence = (
            result.deliverable.confidence
            if result.deliverable and result.success
            else "-"
        )
        print(f"  [{i + 1}] {agent_id} ({vuln.get('type', 'Unknown')})")
        print(f"      状态: {status}, 置信度: {confidence}, 尝试次数: {result.attempts}")
        if not result.success and result.error:
            print(f"      错误: {result.error}")

    # 9. 输出汇总
    print("\n" + "=" * 70)
    print("工作流执行完成")
    print("=" * 70)
    print(f"  总数: {len(agent_ids)}")
    print(f"  完成: {completed}")
    print(f"  失败: {failed}")
    print(f"  交付件目录: {DELIVERABLES_DIR.absolute()}")

    # 10. 生成汇总报告
    report_path = DELIVERABLES_DIR / "summary_report.md"
    generate_summary_report(report_path, results, vulnerabilities)
    print(f"  汇总报告: {report_path}")

    return 0 if failed == 0 else 1


def generate_summary_report(
    report_path: Path,
    results: list[AgentResult],
    vulnerabilities: list[Dict],
) -> None:
    """生成汇总报告"""
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
        confidence = (
            result.deliverable.confidence
            if result.deliverable and result.success
            else "-"
        )
        location = f"{vuln.get('bugClass', '')}.{vuln.get('bugMethod', '')}"

        lines.append(
            f"| {i + 1} | {vuln.get('type', '-')} | {location} | {confidence} | {status} |"
        )

    lines.extend(["", "## 详细分析", ""])

    for i, (result, vuln) in enumerate(zip(results, vulnerabilities)):
        if result.success and result.deliverable:
            analysis = result.deliverable.content.get("analysis", "")
            lines.extend(
                [
                    f"### {i + 1}. {vuln.get('type', 'Unknown')}",
                    "",
                    analysis,
                    "",
                ]
            )

    report_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
