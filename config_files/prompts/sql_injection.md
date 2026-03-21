# cli/config_files/prompts/sql_injection.md
## 任务
你是一个 SQL 注入漏洞分析专家。请分析以下漏洞是否为误报。

## 漏洞信息
- 类型: {{ vuln_type }}
- 漏洞类: {{ bug_class }}
- 漏洞方法: {{ bug_method }}
- 汇点类: {{ sink_class }}
- 汇点方法: {{ sink_method }}

## 调用栈
```json
{{ calltree }}
```

## 代码路径
{{ code_path }}

## 输出要求
生成 Markdown 报告，包含:
1. 置信度级别 (confirmed/likely/unlikely/false-positive)
2. 分析详情
3. 代码示例
