# 框架重构计划 - 支持 Agent 标准执行流程

## 目标

基于架构图，重构框架以支持：
1. Agent 标准执行流程（Prepare → Execute → Validate → Retry）
2. AgentRunner 管理连接池，Agent 通过 Context 获取
3. Context 支持反馈机制和跨阶段数据传递
4. 交付件验证机制

## 设计决策

| 决策点 | 选择 |
|--------|------|
| OpenCode 连接管理 | AgentRunner 管理连接池，Agent 通过 Context 获取 |
| 验证失败反馈 | Context.set_feedback()，Agent 在 prepare_context 中处理 |
| 跨阶段数据传递 | Context 维护索引，详细数据写入交付件文件 |
| 动态 Agent | 保留扩展性，暂不实现 |

---

## 修改计划

### Phase 1: 数据模型层 (models/)

#### 1.1 新增 `models/deliverable.py`

**目的**：定义 Agent 交付件的数据结构

```python
class Deliverable(BaseModel):
    """Agent 执行交付件"""
    agent_id: str
    agent_type: str
    phase: str
    status: str  # pending, running, completed, failed, retrying
    confidence: Optional[str] = None  # confirmed, likely, unlikely, false-positive
    content: Dict[str, Any] = {}
    file_path: Optional[Path] = None
    created_at: datetime
    validated_at: Optional[datetime] = None
    validation_errors: List[str] = []
    retry_count: int = 0
```

#### 1.2 新增 `models/validation.py`

**目的**：定义验证结果

```python
class ValidationResult(BaseModel):
    """交付件验证结果"""
    is_valid: bool
    feedback: Optional[str] = None
    errors: List[str] = []
```

#### 1.3 修改 `models/audit.py`

**变更**：
- 保持现有 `Vulnerability`, `ScanResult` 不变
- 新增 `AgentResult` 类

---

### Phase 2: Agent 上下文层 (agents/)

#### 2.1 重构 `agents/context.py` (新文件)

**目的**：增强 AgentContext，支持反馈和跨阶段数据

```python
class AgentContext:
    """Agent 执行上下文"""

    def __init__(self, agent_id: str, agent_type: str, shared_context: Dict):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self._shared = shared_context
        self._local: Dict = {}
        self._feedback: Optional[str] = None
        self._retry_count: int = 0

    # === 连接获取 ===
    def get_opencode_client(self) -> "OpenCodeClient":
        """获取 OpenCode 客户端（由 AgentRunner 注入）"""
        return self._shared.get("__opencode_client__")

    def get_session_id(self) -> Optional[str]:
        """获取当前 Agent 的 Session ID"""
        sessions = self._shared.get("__sessions__", {})
        return sessions.get(self.agent_id)

    def set_session_id(self, session_id: str):
        """设置当前 Agent 的 Session ID"""
        if "__sessions__" not in self._shared:
            self._shared["__sessions__"] = {}
        self._shared["__sessions__"][self.agent_id] = session_id

    # === 跨阶段数据获取 ===
    def get_project_info(self) -> Dict:
        """获取项目信息"""
        return self._shared.get("project", {})

    def get_code_path(self) -> Path:
        """获取代码路径"""
        return Path(self._shared.get("code_path", "."))

    def get_deliverables_dir(self) -> Path:
        """获取交付件目录"""
        return Path(self._shared.get("deliverables_dir", "./deliverables"))

    def get_phase_result(self, phase: str, agent_name: str = None) -> Dict:
        """获取指定阶段的结果"""
        phase_results = self._shared.get("phase_results", {}).get(phase, {})
        if agent_name:
            return phase_results.get(agent_name, {})
        return phase_results

    def get_all_previous_results(self) -> Dict:
        """获取当前阶段之前所有结果"""
        return self._shared.get("phase_results", {})

    def set_result(self, result: Dict):
        """设置当前 Agent 的结果"""
        if "phase_results" not in self._shared:
            self._shared["phase_results"] = {}
        current_phase = self._shared.get("__current_phase__", "unknown")
        if current_phase not in self._shared["phase_results"]:
            self._shared["phase_results"][current_phase] = {}
        self._shared["phase_results"][current_phase][self.agent_id] = result

    # === 任务数据 ===
    def get_task_data(self) -> Dict:
        """获取任务特定数据"""
        return self._local.get("task_data", {})

    def set_task_data(self, data: Dict):
        """设置任务数据"""
        self._local["task_data"] = data

    def get_vulnerability(self) -> Optional["Vulnerability"]:
        """获取漏洞数据（代码审计阶段）"""
        return self._local.get("vulnerability")

    def set_vulnerability(self, vuln: "Vulnerability"):
        """设置漏洞数据"""
        self._local["vulnerability"] = vuln

    # === 反馈机制 ===
    def set_feedback(self, feedback: str):
        """设置验证反馈（验证失败时调用）"""
        self._feedback = feedback
        self._retry_count += 1

    def get_feedback(self) -> Optional[str]:
        """获取上次的验证反馈"""
        return self._feedback

    def get_retry_count(self) -> int:
        """获取重试次数"""
        return self._retry_count

    def clear_feedback(self):
        """清除反馈"""
        self._feedback = None
```

#### 2.2 重构 `agents/runner.py`

**目的**：实现模板方法模式 + 连接池管理

```python
class AgentRunner:
    """Agent 运行器 - 管理连接池和执行流程"""

    def __init__(
        self,
        opencode_url: str = "http://localhost:4097",
        max_retries: int = 3,
    ):
        self.opencode_url = opencode_url
        self.max_retries = max_retries
        self._client: Optional[OpenCodeClient] = None
        self._session_mgr: Optional[SessionManager] = None
        self._agents: Dict[str, BaseAgent] = {}

    def initialize(self):
        """初始化连接池"""
        self._client = OpenCodeClient(self.opencode_url)
        self._session_mgr = SessionManager(self._client)

    def get_client(self) -> OpenCodeClient:
        """获取 OpenCode 客户端"""
        if self._client is None:
            self.initialize()
        return self._client

    def create_session(self, agent_id: str) -> str:
        """为 Agent 创建 Session"""
        return self._session_mgr.create_agent_session(agent_id)

    def register_agent(self, agent_id: str, agent: "BaseAgent"):
        """注册 Agent 实例"""
        self._agents[agent_id] = agent

    def run(self, agent_id: str, context: AgentContext) -> AgentResult:
        """执行 Agent（模板方法）"""
        agent = self._agents.get(agent_id)
        if agent is None:
            raise ValueError(f"Unknown agent: {agent_id}")

        # 注入连接到 Context
        context._shared["__opencode_client__"] = self.get_client()
        context._shared["__sessions__"] = self._session_mgr._sessions

        # 执行 Agent 循环
        for attempt in range(self.max_retries):
            try:
                # 1. 准备上下文
                agent.prepare_context(context)

                # 2. 执行并输出
                deliverable = agent.execute(context)

                # 3. 验证
                validation = agent.validate(deliverable)

                if validation.is_valid:
                    # 保存交付件
                    self._save_deliverable(deliverable)
                    context.set_result(deliverable.to_dict())
                    return AgentResult(success=True, deliverable=deliverable)
                else:
                    # 验证失败，设置反馈
                    context.set_feedback(validation.feedback)
                    continue

            except Exception as e:
                if attempt == self.max_retries - 1:
                    return AgentResult(success=False, error=str(e))
                context.set_feedback(str(e))

        return AgentResult(success=False, error="Max retries exceeded")


class BaseAgent(ABC):
    """Agent 基类 - 子类实现具体逻辑"""

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Agent 类型标识"""
        pass

    def prepare_context(self, context: AgentContext) -> None:
        """准备上下文（可选重写）

        可以在这里：
        - 处理 feedback，调整策略
        - 获取上一阶段的结果
        - 准备 prompt 模板
        """
        feedback = context.get_feedback()
        if feedback:
            # 有反馈，说明是重试
            logger.info(f"Agent {context.agent_id} 重试 #{context.get_retry_count()}")
            logger.info(f"上次反馈: {feedback}")

    @abstractmethod
    def execute(self, context: AgentContext) -> Deliverable:
        """执行 Agent 逻辑（必须实现）"""
        pass

    def validate(self, deliverable: Deliverable) -> ValidationResult:
        """验证交付件（可选重写）"""
        return ValidationResult(is_valid=True)

    def build_prompt(self, context: AgentContext) -> str:
        """构建 prompt（可选重写）"""
        return ""
```

---

### Phase 3: 交付件验证层 (validators/)

#### 3.1 新增 `validators/__init__.py`

#### 3.2 新增 `validators/base.py`

```python
class DeliverableValidator:
    """交付件验证器基类"""

    @classmethod
    @abstractmethod
    def validate(cls, deliverable: Deliverable) -> ValidationResult:
        pass


class DefaultValidator(DeliverableValidator):
    """默认验证器"""

    @classmethod
    def validate(cls, deliverable: Deliverable) -> ValidationResult:
        required = ["status"]
        missing = [f for f in required if not deliverable.content.get(f)]

        if missing:
            return ValidationResult(
                is_valid=False,
                feedback=f"缺少必要字段: {', '.join(missing)}"
            )

        return ValidationResult(is_valid=True)
```

#### 3.3 新增 `validators/audit_validators.py`

```python
class SQLInjectionValidator(DeliverableValidator):
    """SQL 注入交付件验证器"""

    REQUIRED_FIELDS = ["vuln_type", "sink_class", "sink_method", "confidence"]

    @classmethod
    def validate(cls, deliverable: Deliverable) -> ValidationResult:
        content = deliverable.content

        # 检查必要字段
        missing = [f for f in cls.REQUIRED_FIELDS if not content.get(f)]
        if missing:
            return ValidationResult(
                is_valid=False,
                feedback=f"SQL注入分析缺少: {', '.join(missing)}"
            )

        # 检查置信度
        valid_confidences = ["confirmed", "likely", "unlikely", "false-positive"]
        if content["confidence"] not in valid_confidences:
            return ValidationResult(
                is_valid=False,
                feedback=f"无效的置信度: {content['confidence']}"
            )

        return ValidationResult(is_valid=True)


# 验证器注册表
VALIDATOR_REGISTRY: Dict[str, Type[DeliverableValidator]] = {
    "sql_injection": SQLInjectionValidator,
    # "xss": XSSValidator,
    # ...
}

def get_validator(agent_type: str) -> Type[DeliverableValidator]:
    return VALIDATOR_REGISTRY.get(agent_type, DefaultValidator)
```

---

### Phase 4: 具体 Agent 实现 (agents/builtin/)

#### 4.1 新增 `agents/builtin/__init__.py`

#### 4.2 新增 `agents/builtin/system_analysis.py`

```python
class BusinessArchitectureAgent(BaseAgent):
    """业务架构分析 Agent"""

    agent_type = "business_architecture"

    def execute(self, context: AgentContext) -> Deliverable:
        client = context.get_opencode_client()
        session_id = context.create_session(self.agent_id)

        # 构建 prompt
        prompt = self.build_prompt(context)

        # 调用 OpenCode
        response = client.chat(
            session_id=session_id,
            prompt=prompt,
            # ...
        )

        # 生成交付件
        return Deliverable(
            agent_id=context.agent_id,
            agent_type=self.agent_type,
            phase="system_analysis",
            content={"architecture": response.content, ...},
            file_path=context.get_deliverables_dir() / f"{context.agent_id}.md"
        )

    def build_prompt(self, context: AgentContext) -> str:
        return f"""分析以下项目的业务架构：

项目路径: {context.get_code_path()}
项目信息: {context.get_project_info()}

请分析：
1. 核心业务模块
2. 技术栈
3. 数据流
...
"""
```

#### 4.3 新增 `agents/builtin/threat_analysis.py`

#### 4.4 新增 `agents/builtin/code_audit.py`

```python
class SQLInjectionAgent(BaseAgent):
    """SQL 注入审计 Agent"""

    agent_type = "sql_injection"

    def prepare_context(self, context: AgentContext) -> None:
        super().prepare_context(context)

        # 获取上一阶段（威胁分析）的结果
        threat_results = context.get_phase_result("threat_analysis")
        high_risk_modules = threat_results.get("risk_assessment", {}).get("high_risk_modules", [])

        # 存储供后续使用
        context._local["high_risk_modules"] = high_risk_modules

    def execute(self, context: AgentContext) -> Deliverable:
        vuln = context.get_vulnerability()
        client = context.get_opencode_client()
        session_id = context.get_session_id() or context.create_session(self.agent_id)

        prompt = self.build_prompt(context, vuln)
        response = client.chat(session_id, prompt, ...)

        return Deliverable(
            agent_id=context.agent_id,
            agent_type=self.agent_type,
            phase="code_audit",
            content={
                "vuln_type": "sql_injection",
                "sink_class": vuln.sinkClass,
                "sink_method": vuln.sinkMethod,
                "confidence": self._parse_confidence(response),
                "analysis": response.content,
            },
            ...
        )

    def validate(self, deliverable: Deliverable) -> ValidationResult:
        return SQLInjectionValidator.validate(deliverable)
```

---

### Phase 5: 工作流集成 (workflow/)

#### 5.1 修改 `workflow/engine.py`

**变更**：
- 集成 AgentRunner
- 支持 Phase 概念
- 传递正确的 Context

```python
class WorkflowEngine:
    """工作流执行引擎"""

    def __init__(
        self,
        definition: WorkflowDefinition,
        agent_runner: AgentRunner,
        validator_factory: Callable = get_validator,
    ):
        self.definition = definition
        self.agent_runner = agent_runner
        self.validator_factory = validator_factory

    def run(self, context_data: Dict) -> WorkflowResult:
        """执行工作流"""
        shared_context = {
            "project_id": context_data.get("project_id"),
            "code_path": context_data.get("code_path"),
            "deliverables_dir": context_data.get("deliverables_dir", "./deliverables"),
            "project": context_data.get("project", {}),
            "phase_results": {},
            "__current_phase__": None,
        }

        for phase_name, groups in self.definition.phases:
            shared_context["__current_phase__"] = phase_name

            for group in groups:
                group.execute(shared_context, self._make_agent_runner())

        return WorkflowResult(...)

    def _make_agent_runner(self, shared_context: Dict) -> Callable:
        def runner(agent_id: str, agent_type: str, task_data: Dict) -> Dict:
            context = AgentContext(
                agent_id=agent_id,
                agent_type=agent_type,
                shared_context=shared_context,
            )
            context.set_task_data(task_data)

            result = self.agent_runner.run(agent_id, context)
            return result.to_dict()

        return runner
```

#### 5.2 修改 `workflow/builder.py`

**变更**：
- 新增 `phase()` 方法
- 保持现有 API 兼容

---

### Phase 6: 示例和文档

#### 6.1 更新 `examples/` 目录

- `examples/basic_workflow.py` - 基础工作流示例
- `examples/custom_agent.py` - 自定义 Agent 示例
- `examples/full_audit.py` - 完整审计工作流示例

#### 6.2 更新文档

- `docs/DEVELOPER_GUIDE.md` - 开发者指南
- `docs/AGENT_DEVELOPMENT.md` - Agent 开发指南（新）

---

## 文件变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `models/deliverable.py` | 交付件模型 |
| `models/validation.py` | 验证结果模型 |
| `agents/context.py` | Agent 上下文 |
| `agents/base.py` | Agent 基类 |
| `agents/builtin/__init__.py` | 内置 Agent 包 |
| `agents/builtin/system_analysis.py` | 系统分析 Agent |
| `agents/builtin/threat_analysis.py` | 威胁分析 Agent |
| `agents/builtin/code_audit.py` | 代码审计 Agent |
| `validators/__init__.py` | 验证器包 |
| `validators/base.py` | 验证器基类 |
| `validators/audit_validators.py` | 审计验证器 |

### 修改文件

| 文件 | 变更说明 |
|------|----------|
| `agents/runner.py` | 重构为 AgentRunner + 模板方法 |
| `agents/__init__.py` | 更新导出 |
| `models/audit.py` | 新增 AgentResult |
| `workflow/engine.py` | 集成 Phase 和 AgentRunner |
| `workflow/builder.py` | 新增 phase() 方法 |
| `workflow/groups.py` | 适配新的 Context 传递方式 |

### 删除文件

| 文件 | 说明 |
|------|------|
| `agents/runner_debug.py` | 合并到主代码或删除 |
| `core/vuln_workflow.py` | 迁移到 builtin agents |

---

## 执行顺序

```
Phase 1 (数据模型)
    ↓
Phase 2 (Agent 上下文 + Runner)
    ↓
Phase 3 (验证器)
    ↓
Phase 4 (具体 Agent)
    ↓
Phase 5 (工作流集成)
    ↓
Phase 6 (示例 + 文档)
```

---

## 测试计划

### 单元测试

- `tests/test_agent_context.py` - Context 功能测试
- `tests/test_deliverable.py` - 交付件模型测试
- `tests/test_validators.py` - 验证器测试
- `tests/test_base_agent.py` - Agent 基类测试

### 集成测试

- `tests/test_workflow_integration.py` - 工作流集成测试
- `tests/test_agent_loop.py` - Agent 执行循环测试

---

## 估算工作量

| Phase | 文件数 | 复杂度 | 预估时间 |
|-------|--------|--------|----------|
| Phase 1 | 2 | 低 | 0.5h |
| Phase 2 | 2 | 高 | 2h |
| Phase 3 | 3 | 中 | 1h |
| Phase 4 | 4 | 高 | 3h |
| Phase 5 | 3 | 高 | 2h |
| Phase 6 | 3 | 中 | 1h |
| **总计** | **17** | - | **9.5h** |
