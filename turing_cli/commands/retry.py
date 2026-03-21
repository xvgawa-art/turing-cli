import json
from pathlib import Path
from turing_cli.models.audit import ScanResult


def retry(vuln_id=None, retry_all=False, scan_result=None):
    """重试失败的漏洞分析"""
    if retry_all:
        if not scan_result:
            print("错误: --scan-result 与 --all 一起使用时是必需的")
            return False

        # 检查扫描结果文件
        scan_path = Path(scan_result)
        if not scan_path.exists():
            print(f"错误: 扫描结果文件不存在: {scan_result}")
            return False

        with open(scan_result) as f:
            data = json.load(f)
        result = ScanResult(vulnerabilities=data)

        state_path = Path("./deliverables/.turing/state.json")
        if state_path.exists():
            with open(state_path) as f:
                state = json.load(f)

            failed = [k for k, v in state.get("vulnerabilities", {}).items() if v.get("status") == "failed"]
            print(f"Retrying {len(failed)} failed vulnerabilities...")
            return True
        else:
            print("No state file found")
            return False
    elif vuln_id:
        print(f"Retrying: {vuln_id}")
        return True
    else:
        print("错误: 指定 VULN_ID 或使用 --all")
        return False
