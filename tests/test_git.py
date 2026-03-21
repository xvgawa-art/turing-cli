import tempfile
from pathlib import Path
from turing_cli.git_ops.manager import GitManager
from turing_cli.git_ops.rollback import RollbackManager
from turing_cli.models.audit import Vulnerability


def test_git_manager_init():
    """Test GitManager initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        # Initialize a proper git repository
        import git
        git.Repo.init(tmppath)

        mgr = GitManager(tmppath)
        assert mgr is not None
        assert mgr.repo is not None
        assert mgr._audit_branch is None


def test_git_manager_init_audit():
    """Test audit initialization creates branch."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        # Initialize git repo
        import git
        git.Repo.init(tmppath)
        tmppath.joinpath("test.txt").write_text("initial commit")

        mgr = GitManager(tmppath)
        # Stage and commit initial state
        mgr.repo.git.add(".")
        mgr.repo.git.commit("-m", "initial")

        branch = mgr.init_audit()
        assert branch.startswith("audit-")
        assert mgr._audit_branch == branch
        assert mgr.repo.active_branch.name == branch


def test_git_manager_create_vuln_branch():
    """Test vulnerability branch creation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        import git
        repo = git.Repo.init(tmppath)
        tmppath.joinpath("test.txt").write_text("initial")
        repo.git.add(".")
        repo.git.commit("-m", "initial")

        mgr = GitManager(tmppath)
        mgr.init_audit()

        vuln = Vulnerability(
            type="SQL_INJECTION",
            bugClass="SqlInjectionHandler",
            bugMethod="executeQuery",
            bugLine=42,
            bugSig="executeQuery(Ljava/lang/String;)Ljava/sql/ResultSet;",
            sinkClass="Statement",
            sinkMethod="execute",
            sinkSig="execute(Ljava/lang/String;)Z",
            callTree={}
        )

        branch = mgr.create_vuln_branch(vuln)
        assert branch.startswith("vuln-sql_injection-")
        assert len(branch.split("-")[-1]) == 6  # hash length
        assert mgr.repo.active_branch.name == branch


def test_git_manager_commit_result():
    """Test committing analysis results."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        import git
        repo = git.Repo.init(tmppath)
        tmppath.joinpath("test.txt").write_text("initial")
        repo.git.add(".")
        repo.git.commit("-m", "initial")

        mgr = GitManager(tmppath)
        mgr.init_audit()

        # Create test files
        report_path = tmppath / "report.md"
        state_path = tmppath / "state.json"
        report_path.write_text("# Test Report")
        state_path.write_text('{"status": "done"}')

        mgr.commit_result("test-id", report_path, state_path)

        # Verify commit was created
        commits = list(mgr.repo.iter_commits())
        assert len(commits) == 2  # initial + our commit
        assert "agent-test-id" in commits[0].message


def test_git_manager_merge_to_main():
    """Test merging vulnerability branch to main."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        import git
        repo = git.Repo.init(tmppath)
        tmppath.joinpath("test.txt").write_text("initial")
        repo.git.add(".")
        repo.git.commit("-m", "initial")

        mgr = GitManager(tmppath)
        audit_branch = mgr.init_audit()

        # Create vuln branch
        vuln = Vulnerability(
            type="XSS",
            bugClass="XssHandler",
            bugMethod="render",
            bugLine=10,
            bugSig="render()V",
            sinkClass="Response",
            sinkMethod="write",
            sinkSig="write(Ljava/lang/String;)V",
            callTree={}
        )
        vuln_branch = mgr.create_vuln_branch(vuln)

        # Add file to vuln branch
        tmppath.joinpath("vuln.txt").write_text("vulnerability analysis")
        mgr.repo.git.add(".")
        mgr.repo.git.commit("-m", "vuln analysis")

        # Merge back to main
        mgr.merge_to_main(vuln_branch)

        # Verify we're back on main branch and vuln branch is deleted
        assert mgr.repo.active_branch.name == audit_branch
        branches = [h.name for h in mgr.repo.heads]
        assert vuln_branch not in branches


def test_git_manager_delete_branch():
    """Test branch deletion."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        import git
        repo = git.Repo.init(tmppath)
        tmppath.joinpath("test.txt").write_text("initial")
        repo.git.add(".")
        repo.git.commit("-m", "initial")

        mgr = GitManager(tmppath)
        audit_branch = mgr.init_audit()

        # Create and delete a branch
        mgr.repo.git.checkout("-b", "temp-branch")
        mgr.delete_branch("temp-branch")

        # Verify branch is deleted
        branches = [h.name for h in mgr.repo.heads]
        assert "temp-branch" not in branches
        assert mgr.repo.active_branch.name == audit_branch


def test_rollback_manager_handle_failure():
    """Test RollbackManager handles failure by deleting branch."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        import git
        repo = git.Repo.init(tmppath)
        tmppath.joinpath("test.txt").write_text("initial")
        repo.git.add(".")
        repo.git.commit("-m", "initial")

        git_mgr = GitManager(tmppath)
        git_mgr.init_audit()

        # Create a branch to delete
        git_mgr.repo.git.checkout("-b", "failed-branch")
        tmppath.joinpath("fail.txt").write_text("failed")
        git_mgr.repo.git.add(".")
        git_mgr.repo.git.commit("-m", "failed")

        # Use RollbackManager to handle failure
        rollback_mgr = RollbackManager(git_mgr)
        rollback_mgr.handle_failure(
            agent_id="test-agent",
            branch_name="failed-branch",
            clean_deliverables=False,
        )

        # Verify branch is deleted
        branches = [h.name for h in git_mgr.repo.heads]
        assert "failed-branch" not in branches


def test_rollback_manager_cleanup_deliverables():
    """Test RollbackManager cleans up deliverables."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        # Initialize git repo for GitManager
        import git
        git.Repo.init(tmppath)

        deliverables_path = tmppath / "deliverables"
        deliverables_path.mkdir()

        # Create some fake deliverables
        (deliverables_path / "vuln-sqli-abc123.md").write_text("SQL Injection report")
        (deliverables_path / "vuln-sqli-def456.md").write_text("Another SQL Injection")
        (deliverables_path / "vuln-xss-xyz789.md").write_text("XSS report")

        git_mgr = GitManager(tmppath)
        rollback_mgr = RollbackManager(git_mgr, deliverables_path)

        # Cleanup sqli agent deliverables
        rollback_mgr._cleanup_deliverables("sqli")

        # Verify sqli files are deleted
        remaining = list(deliverables_path.glob("*.md"))
        assert len(remaining) == 1
        assert remaining[0].name == "vuln-xss-xyz789.md"
