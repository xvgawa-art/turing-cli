from turing_cli.models.audit import ScanResult
from turing_cli.core.workflow import WorkflowBuilder


def create_vuln_analysis_workflow(scan_result: ScanResult) -> "WorkflowEngine":
    workflow = WorkflowBuilder("vuln_analysis")

    def get_agents(ctx):
        agents = []
        for vuln in scan_result.vulnerabilities:
            vuln_id = f"{vuln.type}-{vuln.bugClass}-{vuln.bugMethod}"
            agents.append(vuln_id)
        return agents

    with workflow.parallel_group("vulnerability_analysis") as group:
        group.dynamic_agents(lambda ctx: get_agents(ctx))
        group.max_concurrency(5)

    workflow.on_error("retry", max_retries=3, backoff=1.0)

    return WorkflowEngine(workflow.build())
