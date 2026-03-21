import json
from pathlib import Path
from turing_cli.models.audit import Vulnerability, ScanResult, Confidence


def test_load_vulnerability():
    data = {
        "type": "SQL注入",
        "bugClass": "com.example.UserRepository",
        "bugMethod": "find",
        "bugLine": 10,
        "bugSig": "(Ljava.lang.String;)V",
        "sinkClass": "com.example.DB",
        "sinkMethod": "query",
        "sinkSig": "(Ljava.lang.String;)Ljava.sql.ResultSet;",
        "callTree": {"root": {"type": "vulnerable"}}
    }
    vuln = Vulnerability(**data)
    assert vuln.type == "SQL注入"
    assert vuln.bugClass == "com.example.UserRepository"


def test_confidence_enum():
    assert Confidence.CONFIRMED == "confirmed"
    assert Confidence.LIKELY == "likely"


def test_load_scan_result_from_fixture():
    """Test loading ScanResult from fixture file"""
    fixture_path = Path(__file__).parent / "fixtures" / "scan_result.json"
    with open(fixture_path) as f:
        data = json.load(f)

    result = ScanResult(vulnerabilities=data)
    assert len(result.vulnerabilities) == 1
    assert result.vulnerabilities[0].type == "SQL注入"
    assert result.vulnerabilities[0].bugClass == "com.example.app.repository.UserRepository"
