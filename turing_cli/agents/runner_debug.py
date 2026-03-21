import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 示例：在 VulnAgentRunner.run() 中添加日志
def run_with_logging(self, vuln_id: str, context) -> dict:
    logger.debug(f"Starting analysis for {vuln_id}")
    logger.debug(f"Context: {context}")
    
    vuln = context.get("vulnerability")
    if not vuln:
        logger.error(f"No vulnerability in context for {vuln_id}")
        return {"error": "No vulnerability in context"}
    
    logger.info(f"Analyzing {vuln.type} vulnerability")
    
    try:
        result = self.executor.execute(...)
        logger.debug(f"Executor result: {result}")
        return result
    except Exception as e:
        logger.exception(f"Error executing {vuln_id}: {e}")
        raise
