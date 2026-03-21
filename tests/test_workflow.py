from turing_cli.core.vuln_workflow import create_vuln_analysis_workflow
from turing_cli.models.audit import ScanResult


def test_create_workflow():
    result = ScanResult(vulnerabilities=[])
    workflow = create_vuln_analysis_workflow(result)
    assert workflow is not None
    assert workflow.definition.name == "vuln_analysis"
