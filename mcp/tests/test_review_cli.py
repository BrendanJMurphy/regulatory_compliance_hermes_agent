import subprocess
import sys

from compliance_mcp.audit import verify
from tests.conftest import ANALYST, APPROVER, BOTH, FRONT_OFFICE


def run(*args):
    return subprocess.run([sys.executable, "-m", "compliance_mcp.review_cli", *args], capture_output=True, text=True)


def test_four_eyes_and_approver_group(svc, env):
    d = svc.draft_create(BOTH, "policy_mapping", "t", "b")["draft_id"]
    assert "four-eyes" in run("approve", d, "--as", BOTH).stderr          # requester cannot self-approve
    assert "not a member" in run("approve", d, "--as", ANALYST).stderr    # analyst is not an approver
    assert "not a member" in run("approve", d, "--as", FRONT_OFFICE).stderr
    out = run("approve", d, "--as", APPROVER, "--note", "reviewed")
    assert out.returncode == 0 and "approved" in out.stdout
    assert svc.draft_get(ANALYST, d)["draft"]["decision"]["by"] == APPROVER
    assert "no pending draft" in run("reject", d, "--as", APPROVER).stderr
    ok, count, _ = verify(env.audit_log)
    assert ok and count >= 6
