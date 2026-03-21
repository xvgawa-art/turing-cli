# Turing CLI 使用示例

## 快速开始

### 1. 直接运行（推荐）

无需安装，直接运行 Python 脚本：

```bash
# 进入 CLI 目录
cd /home/icsl/turing/cli

# 查看帮助
python3 simple_main.py --help

# 执行漏洞分析
python3 simple_main.py audit scan_result.json -c /path/to/your/code

# 查看审计状态
python3 simple_main.py status

# 查看审计历史（单行格式）
python3 simple_main.py log --oneline

# 查看完整审计历史
python3 simple_main.py log

# 重试单个漏洞
python3 simple_main.py retry vuln-id-0

# 重试所有失败的漏洞
python3 simple_main.py retry --all --scan-result scan_result.json
```

### 2. 安装为系统命令（可选）

如果你想在任何位置使用 `turing` 命令：

```bash
# 进入 CLI 目录
cd /home/icsl/turing/cli

# 安装
pip install -e .

# 然后可以在任何地方使用
turing audit scan_result.json -c /path/to/your/code
turing status
turing log --oneline
turing retry vuln-id-0
```

## 详细使用说明

### audit 命令

```bash
# 基本用法
python3 simple_main.py audit scan_result.json -c /path/to/code

# 指定交付件目录
python3 simple_main.py audit scan_result.json -c /path/to/code -d ./my_results

# 指定 OpenCode 服务地址
python3 simple_main.py audit scan_result.json -c /path/to/code --opencode-url http://localhost:8097

# 设置并发和重试次数
python3 simple_main.py audit scan_result.json -c /path/to/code --concurrency 3 --max-retries 5
```

参数说明：
- `scan-result`: 扫描结果文件路径（JSON 格式）
- `-c, --code-path`: 代码根目录路径（必需）
- `-d, --deliverables`: 交付件保存目录（默认: ./deliverables）
- `--opencode-url`: OpenCode 服务地址（默认: http://localhost:4097）
- `--config-dir`: 配置文件目录（默认: ./config）
- `--max-retries`: 单个漏洞最大重试次数（默认: 3）
- `--concurrency`: 并发执行的 Agent 数量（默认: 5）

### status 命令

```bash
# 查看当前审计状态
python3 simple_main.py status
```

输出示例：
```
Audit ID: audit-12345
Start Time: 2024-01-20T10:30:00

Vulnerabilities: 10 total, 8 completed, 2 failed
```

### log 命令

```bash
# 查看完整日志
python3 simple_main.py log

# 单行显示（适合脚本处理）
python3 simple_main.py log --oneline
```

输出示例（单行格式）：
```
a1b2c3d 漏洞分析完成
e4f5g6h 重试分析完成
```

### retry 命令

```bash
# 重试单个漏洞
python3 simple_main.py retry vuln-id-0

# 重试所有失败的漏洞
python3 simple_main.py retry --all --scan-result scan_result.json
```

## 故障排除

### 1. 导入错误

如果遇到 "No module named" 错误：

```bash
# 确保在正确的目录下运行
cd /home/icsl/turing/cli

# 使用 python3 而不是 python
python3 simple_main.py --help
```

### 2. 权限错误

如果遇到权限问题：

```bash
# 给脚本执行权限
chmod +x simple_main.py

# 或者使用 python3 运行
python3 simple_main.py --help
```

### 3. 路径错误

确保所有路径都是绝对路径或相对于当前工作目录的路径：

```bash
# 使用绝对路径
python3 simple_main.py audit /absolute/path/to/scan_result.json -c /absolute/path/to/code

# 或者进入正确的目录后使用相对路径
cd /path/to/project
python3 /home/icsl/turing/cli/simple_main.py audit scan_result.json -c .
```

## 环境要求

- Python 3.8+
- Git（用于 log 命令）
- 以下 Python 包（如果通过 pip 安装）：
  - click >= 8.0.0
  - gitpython >= 3.1.0
  - pydantic >= 1.8.0
  - requests >= 2.25.0

## 与原 CLI 的区别

1. **移除了 Click 依赖**：使用标准库的 argparse 替代
2. **简化了安装**：可以直接运行 Python 脚本
3. **更清晰的错误处理**：返回明确的退出码
4. **保持了相同的功能**：所有原有功能都保留