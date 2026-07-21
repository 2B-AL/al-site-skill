#!/usr/bin/env python3
import json
import pathlib
import subprocess
import sys


EXPECTED_TOOLS = {
    "CreateSite", "SelectSite", "GetCurrentSite", "GetSite", "ListSites", "UpdateSite",
    "SaveSiteVersion", "GetSiteVersion", "ListSiteVersions", "DeleteSiteVersion",
    "DeploySiteVersion", "GetSiteDeployment", "ListSiteDeployments", "PromoteSiteDeployment",
    "RollbackSite", "CancelSiteDeployment", "PauseSiteDeployment", "GetSiteAccessPolicy",
    "SetSiteAccessPolicy", "SetSiteGovernance", "SubmitSiteAppeal", "SetSiteDomain",
    "ListSiteDomains", "VerifySiteDomain", "DeleteSiteDomain", "GetSiteLogs", "GetSiteEvents",
    "GetSiteMetrics", "GetSiteUsage", "AttachSiteAddonBinding", "DetachSiteAddonBinding",
    "ArchiveConversationSite", "DeleteSite",
}


def run(arguments):
    script = pathlib.Path(__file__).with_name("al_site.py")
    completed = subprocess.run(
        [sys.executable, str(script), *arguments], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stderr or completed.stdout)
    return completed.stdout


def main():
    tools = json.loads(run(["tools"]))
    names = {item["name"] for item in tools.get("tools", [])}
    missing = sorted(EXPECTED_TOOLS - names)
    if missing:
        raise SystemExit("missing Site MCP tools: " + ", ".join(missing))
    print(f"Site MCP tool list ok: {len(names)} tools")
    print(run(["initialize"]).strip())


if __name__ == "__main__":
    main()

