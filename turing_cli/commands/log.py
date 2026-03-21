import git
from pathlib import Path


def log(oneline=False):
    """查看审计历史"""
    try:
        repo_path = Path("./deliverables")
        if not repo_path.exists():
            print("错误: deliverables 目录不存在")
            return False

        repo = git.Repo(repo_path)
        commits = list(repo.iter_commits("main"))

        for commit in commits:
            if oneline:
                print(f"{commit.hexsha[:7]} {commit.message.strip()}")
            else:
                print(f"commit {commit.hexsha}")
                print(f"Author: {commit.author}")
                print(f"Date: {commit.committed_datetime}")
                print(f"\n    {commit.message.strip()}\n")
        return True
    except Exception as e:
        print(f"Error reading log: {e}")
        return False
