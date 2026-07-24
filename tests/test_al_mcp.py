import importlib.util
import datetime
import json
import os
import pathlib
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).parents[1] / "scripts" / "al_mcp.py"
SPEC = importlib.util.spec_from_file_location("al_site", SCRIPT)
al_site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(al_site)


class SiteClientTest(unittest.TestCase):
    def test_repository_uses_mcp_client_with_ui_metadata(self):
        root = pathlib.Path(__file__).parents[1]
        self.assertTrue((root / "scripts" / "al_mcp.py").is_file())
        self.assertFalse((root / "scripts" / "al_site.py").exists())
        metadata = (root / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: "AL Site"', metadata)
        self.assertIn('default_prompt: "Use $al-site ', metadata)

    def test_all_current_tools_have_unique_commands(self):
        commands = [al_site.tool_command_name(name) for name in al_site.SITE_TOOLS]
        self.assertEqual(len(commands), len(set(commands)))
        self.assertEqual("save-site-version", al_site.tool_command_name("SaveSiteVersion"))
        parser = al_site.build_parser()
        args = parser.parse_args(["get-site-events", "--arg", "site_id=example"])
        self.assertEqual("GetSiteEvents", args.site_tool)
        self.assertEqual("test-deploy-current", parser.parse_args(["test-deploy-current", "--handoff", "@handoff.json"]).action)
        self.assertEqual("created", parser.parse_args(["sites"]).relation)
        self.assertEqual("accessible", parser.parse_args(["sites", "--relation", "accessible"]).relation)
        self.assertEqual("accessible", parser.parse_args(["get", "shared", "--relation", "accessible"]).relation)
        self.assertEqual("delete-version", parser.parse_args(["delete-version", "version-1", "--confirm"]).action)

    def test_gateway_url_validation(self):
        self.assertEqual("https://gateway.example", al_site.validate_gateway_url("https://gateway.example/mcp"))
        self.assertEqual("http://127.0.0.1:8080", al_site.validate_gateway_url("http://127.0.0.1:8080"))
        with self.assertRaises(SystemExit):
            al_site.validate_gateway_url("http://gateway.example")
        with self.assertRaises(SystemExit):
            al_site.validate_gateway_url("https://gateway.example/not-mcp")

    def test_dev_gateway_is_the_default(self):
        with mock.patch.dict(os.environ, {"AL_SITE_MCP_GATEWAY_URL": ""}), mock.patch.object(
            al_site, "load_state", return_value={}
        ):
            self.assertEqual(al_site.DEFAULT_GATEWAY_URL, al_site.configured_gateway_url())

    def test_relation_shortcuts_forward_explicit_filters_and_paginate(self):
        responses = [
            {"structuredContent": {"items": [{"id": "site-1"}], "next_token": "next-1"}},
            {"structuredContent": {"items": [{"id": "site-2"}]}},
        ]
        with mock.patch("sys.argv", [
            "al_mcp.py", "sites", "--relation", "accessible", "--owner-kind", "team",
            "--owner-id", "team-1", "--phase", "Ready", "--page-size", "25",
        ]), mock.patch.object(al_site, "call_tool", side_effect=responses) as call, mock.patch.object(
            al_site, "print_json"
        ) as output:
            al_site.main()
        self.assertEqual([
            mock.call("ListSites", {"relation": "accessible", "limit": 25, "phases": ["Ready"], "owner_kind": "team", "owner_id": "team-1"}),
            mock.call("ListSites", {"relation": "accessible", "limit": 25, "phases": ["Ready"], "owner_kind": "team", "owner_id": "team-1", "next_token": "next-1"}),
        ], call.call_args_list)
        self.assertEqual(2, output.call_args.args[0]["structuredContent"]["count"])

        with mock.patch("sys.argv", ["al_mcp.py", "get", "site-1"]), mock.patch.object(
            al_site, "call_tool", return_value={}
        ) as call, mock.patch.object(al_site, "print_json"):
            al_site.main()
        call.assert_called_once_with("GetSite", {"site_id": "site-1", "relation": "created"})

    def test_argument_merge_parses_json(self):
        value = al_site.merge_call_arguments('{"site_id":"a"}', ["confirm=true", "step=2", 'users=["u"]'])
        self.assertEqual({"site_id": "a", "confirm": True, "step": 2, "users": ["u"]}, value)

    def test_identifier_arguments_remain_strings(self):
        value = al_site.merge_call_arguments("{}", ["resource_version=46302628", "site_id=123", "step=2"], ["custom=001"])
        self.assertEqual("46302628", value["resource_version"])
        self.assertEqual("123", value["site_id"])
        self.assertEqual(2, value["step"])
        self.assertEqual("001", value["custom"])

    def test_git_scp_url_is_normalized(self):
        self.assertEqual(
            "ssh://git@github.com/2B-AL/example.git",
            al_site.normalize_git_url("git@github.com:2B-AL/example.git"),
        )

    def test_local_git_requires_clean_pushed_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, GIT_AUTHOR_NAME="test", GIT_AUTHOR_EMAIL="test@example.com", GIT_COMMITTER_NAME="test", GIT_COMMITTER_EMAIL="test@example.com")
            remote = pathlib.Path(directory) / "remote.git"
            work = pathlib.Path(directory) / "work"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "init", "-b", "main", str(work)], check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "-C", str(work), "remote", "add", "origin", "file://" + str(remote)], check=True)
            (work / "index.html").write_text("ok", encoding="utf-8")
            subprocess.run(["git", "-C", str(work), "add", "index.html"], check=True)
            subprocess.run(["git", "-C", str(work), "commit", "-m", "initial"], check=True, env=env, stdout=subprocess.DEVNULL)
            # The Site contract rejects file:// sources before the remote check.
            with self.assertRaises(SystemExit):
                al_site.inspect_local_git(work)
            (work / "dirty.txt").write_text("dirty", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "not clean"):
                al_site.inspect_local_git(work, skip_remote_check=True)

    def test_tool_error_is_nonzero(self):
        with mock.patch.object(al_site, "rpc", return_value={"isError": True, "content": [{"type": "text", "text": "failed"}]}):
            with self.assertRaisesRegex(SystemExit, "failed"):
                al_site.call_tool("GetSite", {"site_id": "x"})

    def test_phase_prefers_meta(self):
        self.assertEqual("Ready", al_site.phase_of({"_meta": {"phase": "Ready"}, "structuredContent": {"status": {"phase": "Failed"}}}))

    def test_local_source_archive_applies_denylist_ignore_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("secret", encoding="utf-8")
            (root / ".env").write_text("TOKEN=hidden", encoding="utf-8")
            (root / ".env.example").write_text("TOKEN=example", encoding="utf-8")
            (root / ".alignore").write_text("ignored.txt\n", encoding="utf-8")
            (root / "ignored.txt").write_text("ignored", encoding="utf-8")
            (root / "index.html").write_text("hello", encoding="utf-8")
            first, first_summary = al_site.create_source_archive(root)
            second, second_summary = al_site.create_source_archive(root)
            try:
                self.assertEqual(first.read_bytes(), second.read_bytes())
                self.assertEqual(first_summary["transport_sha256"], second_summary["transport_sha256"])
                with tarfile.open(first, "r:gz") as archive:
                    names = set(archive.getnames())
                self.assertIn("index.html", names)
                self.assertIn(".env.example", names)
                self.assertNotIn(".env", names)
                self.assertNotIn(".git/config", names)
                self.assertNotIn("ignored.txt", names)
            finally:
                first.unlink(missing_ok=True)
                second.unlink(missing_ok=True)

    def test_local_source_rejects_high_confidence_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "credential.txt").write_text("AKIAABCDEFGHIJKLMNOP", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "credential material"):
                al_site.create_source_archive(root)

    def test_local_build_resolves_dockerfile_relative_to_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            app = root / "app"
            app.mkdir()
            (app / "Dockerfile").write_text(
                "FROM scratch\nUSER 65532:65532\n", encoding="utf-8"
            )
            result = al_site.validate_local_build(
                root, '{"mode":"dockerfile","context":"app","dockerfile":"Dockerfile"}'
            )
            self.assertEqual("app", result["context"])
            self.assertEqual("Dockerfile", result["dockerfile"])
            self.assertEqual("65532:65532", result["final_user"])

            with self.assertRaisesRegex(SystemExit, "relative to build.context"):
                al_site.validate_local_build(
                    root, '{"mode":"dockerfile","context":"app","dockerfile":"app/Dockerfile"}'
                )

    def test_local_build_rejects_named_or_root_final_user(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            dockerfile = root / "Dockerfile"
            dockerfile.write_text(
                "FROM example AS build\nUSER builder\nFROM example\nUSER nonroot:nonroot\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(SystemExit, "non-numeric USER"):
                al_site.validate_local_build(root, '{"mode":"dockerfile"}')

            dockerfile.write_text("FROM example\nUSER 0\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "root UID 0"):
                al_site.validate_local_build(root, '{"mode":"dockerfile"}')

    def test_local_build_auto_allows_railpack_fallback_without_dockerfile(self):
        with tempfile.TemporaryDirectory() as directory:
            result = al_site.validate_local_build(directory)
            self.assertEqual("", result["dockerfile"])

    def test_save_local_build_preflight_runs_before_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "Dockerfile").write_text("FROM example\nUSER nonroot\n", encoding="utf-8")
            with mock.patch.object(al_site, "post_source_archive") as upload:
                with self.assertRaisesRegex(SystemExit, "non-numeric USER"):
                    al_site.save_local_source(root, "site-1", '{"mode":"dockerfile"}')
            upload.assert_not_called()

    def test_save_local_keeps_upload_receipt_in_memory_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "index.html").write_text("hello", encoding="utf-8")
            uploaded = {
                "sourceRef": "registry.example/source@sha256:" + "a" * 64,
                "sourceBundleDigest": "sha256:" + "a" * 64,
                "receipt": "sensitive-receipt",
            }
            with mock.patch.object(al_site, "post_source_archive", return_value=uploaded), mock.patch.object(
                al_site, "selected_site_id", return_value="site-1"
            ), mock.patch.object(al_site, "plan_site_version", return_value={"structuredContent": {"valid": True}}), mock.patch.object(
                al_site, "call_tool", return_value={"_meta": {"version_id": "v1"}}
            ) as call:
                summary, plan, result = al_site.save_local_source(root, "site-1")
            arguments = call.call_args.args[1]
            self.assertEqual("sensitive-receipt", arguments["source"]["upload_receipt"])
            self.assertNotIn("receipt", summary)
            self.assertNotIn("sensitive-receipt", json.dumps({"summary": summary, "plan": plan, "result": result}))

    def test_dependency_free_static_source_selects_static_profile_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "index.html").write_text("<html></html>", encoding="utf-8")
            (root / "app.js").write_text("console.log('ok')", encoding="utf-8")
            build = al_site.normalized_local_build(root)
            self.assertEqual("static", build["mode"])
            self.assertTrue(build["path_prefix_aware"])

    def test_static_source_rejects_unverified_root_relative_asset_assertion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / "index.html").write_text('<script src="/app.js"></script>', encoding="utf-8")
            (root / "app.js").write_text("ok", encoding="utf-8")
            build = al_site.normalized_local_build(root)
            self.assertEqual("static", build["mode"])
            self.assertFalse(build["path_prefix_aware"])

    def test_source_manifest_digest_includes_file_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "index.html"
            source.write_text("first", encoding="utf-8")
            first = al_site.create_source_manifest(root)
            source.write_text("second", encoding="utf-8")
            second = al_site.create_source_manifest(root)
            self.assertNotEqual(first["digest"], second["digest"])

    def test_dependency_manifest_keeps_auto_profile(self):
        manifest = {"files": ["index.html", "package.json"]}
        self.assertEqual({}, al_site.normalized_manifest_build(manifest))

    def test_plan_profile_revision_is_pinned_into_saved_version(self):
        arguments = al_site.save_version_arguments(
            "site-1", {"type": "git", "repository": "https://example.com/repo.git", "commit_sha": "a" * 40},
            plan={"structuredContent": {"profileRevision": "static-v1"}},
        )
        self.assertEqual("static-v1", arguments["build_plan_revision"])

    def test_normalized_plan_is_the_saved_build_contract(self):
        build, runtime = al_site.normalized_inputs_from_plan({
            "structuredContent": {
                "normalizedBuild": {"mode": "Railpack", "context": ".", "pathPrefixAware": True},
                "normalizedRuntime": {"port": 8080, "healthPath": "/"},
            }
        }, {}, {})
        self.assertEqual({"mode": "railpack", "context": ".", "path_prefix_aware": True}, build)
        self.assertEqual({"port": 8080, "health_path": "/"}, runtime)

    def test_explicit_sandbox_handoff_does_not_read_site_or_sandbox_state(self):
        descriptor = {
            "schema_version": "sandbox-site-handoff/v1",
            "source_export_grant": "g" * 64,
            "sandbox_conversation_id": "sandbox-conversation",
            "source_root": "/workspace/project",
            "expires_at": "2099-01-01T00:00:00Z",
            "source_manifest": {"files": ["index.html"], "digest": "sha256:" + "a" * 64},
        }
        source = al_site.load_source_handoff(json.dumps(descriptor))
        self.assertEqual("sandbox_handoff", source["type"])
        self.assertEqual("sandbox-conversation", source["sandbox_conversation_id"])

    def test_sandbox_handoff_requires_sixty_second_safety_margin(self):
        descriptor = {
            "schema_version": "sandbox-site-handoff/v1", "source_export_grant": "g" * 64,
            "sandbox_conversation_id": "conversation", "source_root": "/workspace/project",
            "expires_at": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=30)).isoformat(),
            "source_manifest": {"digest": "sha256:" + "a" * 64},
        }
        with self.assertRaisesRegex(SystemExit, "less than 60 seconds"):
            al_site.load_source_handoff(json.dumps(descriptor))

    def test_consumed_handoff_file_is_removed_only_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            descriptor = pathlib.Path(directory) / "handoff.json"
            descriptor.write_text("{}", encoding="utf-8")
            al_site.remove_consumed_handoff_file("@" + str(descriptor))
            self.assertFalse(descriptor.exists())

    def test_public_test_site_requires_confirmation_before_mutation(self):
        capabilities = {"routing": {"recommendedCreate": {"audience": "public", "publicPublishing": True}}}
        with mock.patch.object(al_site, "platform_capabilities", return_value=capabilities), mock.patch.object(
            al_site, "call_tool"
        ) as call:
            with self.assertRaisesRegex(SystemExit, "confirm-public"):
                al_site.create_test_site("test", False)
        call.assert_not_called()

    def test_test_run_manifest_is_0600_and_tracks_exact_site_uid(self):
        with tempfile.TemporaryDirectory() as directory:
            run_id = "11111111-1111-1111-1111-111111111111"
            target = al_site.prepare_test_run_destination(pathlib.Path(directory) / "run.json", run_id)
            saved, record = al_site.new_test_run("site-test", "uid-test", "local", str(target), run_id)
            self.assertEqual(target, saved)
            self.assertEqual(0o600, saved.stat().st_mode & 0o777)
            _, loaded = al_site.load_test_run(saved)
            self.assertEqual("uid-test", loaded["site_uid"])
            self.assertEqual("site-test", record["resources"]["site"])

    def test_test_run_exists_before_site_creation_and_tracks_partial_result(self):
        with tempfile.TemporaryDirectory() as directory:
            run_id = "22222222-2222-2222-2222-222222222222"
            target, run = al_site.begin_test_run("sandbox-handoff", pathlib.Path(directory) / "run.json", run_id)
            self.assertTrue(target.exists())
            self.assertFalse(run["created_site"])
            al_site.record_created_test_site(target, run, "partial-site", "partial-uid")
            _, loaded = al_site.load_test_run(target)
            self.assertTrue(loaded["created_site"])
            self.assertEqual("partial-site", loaded["site_id"])
            self.assertEqual("partial-uid", loaded["site_uid"])

    def test_create_test_site_records_identity_before_partial_error(self):
        capabilities = {"routing": {"recommendedCreate": {"audience": "owner"}}}
        partial = {"isError": True, "content": [{"type": "text", "text": "selection failed"}], "_meta": {"site_id": "created-site", "uid": "created-uid"}}
        recorded = []
        with mock.patch.object(al_site, "platform_capabilities", return_value=capabilities), mock.patch.object(
            al_site, "call_tool_result", return_value=partial
        ):
            with self.assertRaisesRegex(SystemExit, "selection failed"):
                al_site.create_test_site("test", False, lambda result, site_id, site_uid: recorded.append((site_id, site_uid)))
        self.assertEqual([("created-site", "created-uid")], recorded)

    def test_resource_identity_falls_back_to_structured_metadata(self):
        result = {
            "structuredContent": {
                "metadata": {"name": "created-site", "uid": "created-uid"},
                "spec": {},
            }
        }
        self.assertEqual("created-site", al_site.result_meta_id(result, "site_id"))
        self.assertEqual("created-uid", al_site.result_uid(result))

    def test_resource_identity_reads_unified_resource_view(self):
        result = {"structuredContent": {"id": "site-view", "uid": "uid-view", "resource_version": "42"}}
        self.assertEqual("site-view", al_site.result_meta_id(result, "site_id"))
        self.assertEqual("uid-view", al_site.result_uid(result))
        self.assertEqual("42", al_site.result_resource_version(result))

    def test_cleanup_requires_latest_resource_version(self):
        with tempfile.TemporaryDirectory() as directory:
            target, _ = al_site.new_test_run(
                "site-test", "uid-test", "local", pathlib.Path(directory) / "run.json",
                "33333333-3333-3333-3333-333333333333",
            )
            current = {"structuredContent": {"id": "site-test", "uid": "uid-test", "resource_version": "77"}}
            with mock.patch("sys.argv", ["al_mcp.py", "cleanup-test-run", str(target), "--confirm"]), mock.patch.object(
                al_site, "call_tool", side_effect=[current, {"structuredContent": {"deleted": True}}]
            ) as call, mock.patch.object(al_site, "print_json"):
                al_site.main()
            self.assertEqual(
                mock.call("DeleteSite", {"site_id": "site-test", "confirm": True, "expected_uid": "uid-test", "resource_version": "77"}),
                call.call_args_list[1],
            )

    def test_wait_version_uses_cursor_without_restarting_work(self):
        responses = [
            {"structuredContent": {"cursor": "10", "version": {"status": {"phase": "Building", "build": {"state": "Running", "attempt": 1}}}}},
            {"structuredContent": {"cursor": "11", "terminal": True, "version": {"status": {"phase": "Ready", "build": {"state": "Succeeded", "attempt": 1}}}}},
        ]
        with mock.patch.object(al_site, "available_tool_names", return_value={"WatchSiteVersion"}), mock.patch.object(
            al_site, "call_tool", side_effect=responses
        ) as call:
            result = al_site.wait_for_version("site-1", "version-1", 30)
        self.assertEqual("Ready", al_site.phase_of(result))
        self.assertEqual("10", call.call_args_list[1].args[1]["cursor"])

    def test_wait_version_recovers_watch_transport_timeout_with_get(self):
        timeout = SystemExit(
            '{"code": -32000, "message": "context deadline exceeded '
            '(Client.Timeout exceeded while awaiting headers)"}'
        )
        ready = {"structuredContent": {"status": {"phase": "Ready"}}}
        with mock.patch.object(al_site, "available_tool_names", return_value={"WatchSiteVersion"}), mock.patch.object(
            al_site, "call_tool", side_effect=[timeout, ready]
        ) as call:
            result = al_site.wait_for_version("site-1", "version-1", 30)
        self.assertEqual("Ready", al_site.phase_of(result))
        self.assertEqual("WatchSiteVersion", call.call_args_list[0].args[0])
        self.assertEqual("GetSiteVersion", call.call_args_list[1].args[0])

    def test_public_smoke_resolves_shared_path_url_from_site(self):
        deployment = {"structuredContent": {"deployment": {"status": {"phase": "Ready"}}}}
        site = {"structuredContent": {"status": {"url": "https://site.example/sites/demo/"}}}

        class Response:
            status = 200

            def read(self, _limit):
                return b"ok"

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with mock.patch.object(al_site, "call_tool", return_value=site) as call, mock.patch.object(
            al_site.urllib.request, "urlopen", return_value=Response()
        ):
            result = al_site.smoke_public_deployment(deployment, "site-1")
        self.assertEqual("passed", result["status"])
        self.assertEqual("https://site.example/sites/demo/", result["url"])
        call.assert_called_once_with("GetSite", {"site_id": "site-1", "relation": "accessible"})

    def test_release_options_are_shared_and_build_typed_strategy(self):
        parser = al_site.build_parser()
        for command in ("release", "deploy-local", "deploy-local-git", "test-deploy-local", "test-deploy-current"):
            prefix = [command]
            if command == "release":
                prefix.append("version-1")
            elif command == "test-deploy-current":
                prefix.extend(["--handoff", "@handoff.json"])
            args = parser.parse_args(prefix + [
                "--canary", "5,25,100", "--lane-header", "X-AL-Site-Lane=beta",
                "--max-error-rate", "0.01", "--min-requests", "100",
            ])
            strategy = al_site.release_strategy_from_args(args)
            self.assertEqual("canary", strategy["type"])
            self.assertEqual([5, 25, 100], [step["percent"] for step in strategy["steps"]])
            self.assertEqual(0.01, strategy["steps"][0]["metric_gate"]["max_error_rate"])
            self.assertEqual("X-AL-Site-Lane", strategy["lanes"][0]["header"]["name"])

    def test_blue_green_wait_candidate_adds_protected_preview_lane(self):
        args = al_site.build_parser().parse_args(["release", "version-1", "--blue-green", "--wait-candidate"])
        strategy = al_site.release_strategy_from_args(args)
        self.assertEqual("signed-cookie", strategy["lanes"][0]["mode"])
        self.assertEqual("preview", strategy["lanes"][0]["name"])

    def test_delete_version_reads_and_forwards_exact_identity(self):
        current = {"structuredContent": {"metadata": {"uid": "version-uid", "resourceVersion": "77"}}}
        deleted = {"structuredContent": {"deleted": True}}
        with mock.patch("sys.argv", ["al_mcp.py", "delete-version", "version-1", "--site-id", "site-1", "--confirm"]), mock.patch.object(
            al_site, "call_tool", side_effect=[current, deleted]
        ) as call, mock.patch.object(al_site, "print_json"):
            al_site.main()
        self.assertEqual(mock.call("GetSiteVersion", {"site_id": "site-1", "version_id": "version-1"}), call.call_args_list[0])
        self.assertEqual(mock.call("DeleteSiteVersion", {
            "site_id": "site-1", "version_id": "version-1", "expected_uid": "version-uid",
            "resource_version": "77", "confirm": True,
        }), call.call_args_list[1])

    def test_wait_release_long_polls_deployment_between_status_reads(self):
        building = {"structuredContent": {"phase": "Canary", "state": "Canary", "traffic": {"candidatePercent": 5}}}
        watched = {"structuredContent": {"cursor": "44", "deployment": {"status": {"phase": "Ready"}}}}
        ready = {"structuredContent": {"phase": "Ready", "state": "Ready", "terminal": True}}
        with mock.patch.object(al_site, "available_tool_names", return_value={"GetSiteReleaseStatus", "WatchSiteDeployment"}), mock.patch.object(
            al_site, "call_tool", side_effect=[building, watched, ready]
        ) as call:
            result, paused = al_site.wait_for_release("site-1", "deployment-1", 30)
        self.assertFalse(paused)
        self.assertIs(result, ready)
        self.assertEqual("WatchSiteDeployment", call.call_args_list[1].args[0])

    def test_wait_candidate_requires_published_routing_revision(self):
        unpublished = {"structuredContent": {
            "phase": "Canary", "state": "Canary",
            "candidate": {"revisionName": "candidate-1", "upstream": "http://candidate"},
            "traffic": {"candidatePercent": 0, "routingEpoch": 7},
        }}
        published = {"structuredContent": {
            "phase": "Canary", "state": "Canary",
            "candidate": {"revisionName": "candidate-1", "upstream": "http://candidate"},
            "traffic": {"candidatePercent": 0, "routingEpoch": 7, "routingRevision": "projection-1"},
        }}
        with mock.patch.object(al_site, "available_tool_names", return_value={"GetSiteReleaseStatus"}), mock.patch.object(
            al_site, "call_tool", side_effect=[unpublished, published]
        ) as call, mock.patch.object(al_site.time, "sleep"):
            result, paused = al_site.wait_for_release("site-1", "deployment-1", 30, candidate_only=True)
        self.assertFalse(paused)
        self.assertIs(result, published)
        self.assertEqual(2, call.call_count)

    def test_resume_forwards_explicit_timeout_extension_with_current_preconditions(self):
        status = {"structuredContent": {
            "phase": "Paused", "currentStep": 2,
            "traffic": {"routingEpoch": 17},
        }}
        resumed = {"structuredContent": {"accepted": True}}
        with mock.patch("sys.argv", [
            "al_mcp.py", "resume", "deployment-1", "--site-id", "site-1", "--extend-timeout", "10m",
        ]), mock.patch.object(al_site, "call_tool", side_effect=[status, resumed]) as call, mock.patch.object(
            al_site, "print_json"
        ):
            al_site.main()
        self.assertEqual(mock.call("GetSiteReleaseStatus", {
            "site_id": "site-1", "deployment_id": "deployment-1",
        }), call.call_args_list[0])
        self.assertEqual(mock.call("ResumeSiteDeployment", {
            "site_id": "site-1", "deployment_id": "deployment-1", "expected_step": 2,
            "expected_phase": "Paused", "expected_routing_epoch": 17, "extend_timeout": "10m",
        }), call.call_args_list[1])

    def test_release_always_plans_and_pins_plan_revision(self):
        args = al_site.build_parser().parse_args(["release", "version-1", "--immediate"])
        plan = {"structuredContent": {"valid": True, "planRevision": "signed-plan"}}
        deployed = {"_meta": {"deployment_id": "deployment-1"}}
        with mock.patch.object(al_site, "available_tool_names", return_value={
            "GetSitePlatformCapabilities", "PlanSiteDeployment", "DeploySiteVersion", "GetSiteReleaseStatus",
        }), mock.patch.object(al_site, "platform_capabilities", return_value={"release": {"strategies": ["immediate"]}}), mock.patch.object(
            al_site, "call_tool", return_value=plan
        ) as planned, mock.patch.object(al_site, "call_tool_result", return_value=deployed) as release:
            returned_plan, returned_deployment = al_site.create_release(args, "site-1", "version-1")
        self.assertIs(returned_plan, plan)
        self.assertIs(returned_deployment, deployed)
        self.assertEqual("PlanSiteDeployment", planned.call_args.args[0])
        self.assertEqual("signed-plan", release.call_args.args[1]["plan_revision"])

    def test_custom_scaling_requires_complete_policy(self):
        args = al_site.build_parser().parse_args(["scaling-apply", "--profile", "custom", "--min-scale", "1"])
        with self.assertRaisesRegex(SystemExit, "custom scaling requires"):
            al_site.scaling_policy_from_args(args)

    def test_wait_deployment_uses_cursor_until_traffic_ready(self):
        responses = [
            {"structuredContent": {"cursor": "20", "deployment": {"status": {"phase": "CreatingRevision", "trafficPercent": 0}}}},
            {"structuredContent": {"cursor": "21", "terminal": True, "deployment": {"status": {"phase": "Ready", "trafficPercent": 100}}}},
        ]
        with mock.patch.object(al_site, "available_tool_names", return_value={"WatchSiteDeployment"}), mock.patch.object(
            al_site, "call_tool", side_effect=responses
        ) as call:
            result = al_site.wait_for_deployment("site-1", "deployment-1", 30)
        self.assertEqual("Ready", al_site.phase_of(result))
        self.assertEqual("20", call.call_args_list[1].args[1]["cursor"])

    def test_active_version_log_progress_is_cursor_deduplicated(self):
        response = {"structuredContent": {"cursor": "2026-07-22T12:00:00Z", "content": "vertex 1\nvertex 2"}}
        cursors = {}
        with mock.patch.object(al_site, "call_tool", return_value=response) as call:
            al_site.emit_active_version_log_progress(
                "site-1", "version-1", {"build": {"state": "Running"}}, cursors,
            )
            al_site.emit_active_version_log_progress(
                "site-1", "version-1", {"build": {"state": "Running"}}, cursors,
            )
        self.assertEqual(2, call.call_count)
        self.assertEqual("2026-07-22T12:00:00Z", cursors["build"])

    def test_direct_part_upload_never_sends_site_oauth_headers(self):
        class Response:
            status = 200
            headers = {"ETag": '"etag-1"'}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        captured = {}

        def open_request(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return Response()

        with tempfile.TemporaryDirectory() as directory:
            archive = pathlib.Path(directory) / "source.tar.gz"
            archive.write_bytes(b"archive")
            state = {"archiveBytes": 7, "partSize": 8 << 20, "partCount": 1}
            part = {
                "partNumber": 1,
                "size": 7,
                "url": "https://tos.example/object?X-Tos-Signature=secret",
                "headers": {"X-Tos-Test": "signed"},
            }
            with mock.patch.object(al_site.urllib.request, "urlopen", side_effect=open_request):
                completed = al_site.upload_one_part(archive, state, part)
        self.assertEqual('"etag-1"', completed["etag"])
        request = captured["request"]
        self.assertEqual("signed", request.get_header("X-tos-test"))
        self.assertIsNone(request.get_header("Authorization"))
        self.assertIsNone(request.get_header("X-al-conversation-id"))

    def test_upload_state_is_private_and_does_not_persist_presigned_urls(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(al_site, "STATE_DIR", pathlib.Path(directory)):
            digest = "a" * 64
            state = {
                "uploadID": "b" * 32,
                "sessionToken": "private-session",
                "archiveBytes": 7,
                "transportSHA256": digest,
                "partSize": 8 << 20,
                "partCount": 1,
                "expiresAt": "2099-01-01T00:00:00Z",
                "completedParts": {},
                "parts": [{"url": "https://tos.example/?secret"}],
            }
            al_site.save_upload_state(digest, state)
            path = al_site.upload_state_file(digest)
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("tos.example", raw)
            self.assertEqual(0o600, path.stat().st_mode & 0o777)
            self.assertEqual("private-session", al_site.load_upload_state(digest, 7)["sessionToken"])

    def test_new_upload_uses_initial_presigned_parts_and_completes(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(al_site, "STATE_DIR", pathlib.Path(directory)):
            archive = pathlib.Path(directory) / "source.tar.gz"
            archive.write_bytes(b"archive")
            digest = al_site.file_sha256(archive)
            calls = []

            def control(path, payload=None, method="POST", timeout=None):
                calls.append(path)
                if path == "/api/v1/source-bundle-uploads":
                    return {
                        "uploadID": "b" * 32,
                        "sessionToken": "session",
                        "archiveBytes": 7,
                        "transportSHA256": digest,
                        "partSize": 8 << 20,
                        "partCount": 1,
                        "expiresAt": "2099-01-01T00:00:00Z",
                        "parts": [{"partNumber": 1, "size": 7, "url": "https://tos.example/signed"}],
                    }
                if path.endswith("/status"):
                    return {"uploadID": "b" * 32, "parts": [], "completed": False}
                if path.endswith("/complete"):
                    self.assertEqual('"etag-1"', payload["parts"][0]["etag"])
                    return {
                        "sourceRef": "registry.example/source@sha256:" + "a" * 64,
                        "sourceBundleDigest": "sha256:" + "a" * 64,
                        "receipt": "receipt",
                    }
                self.fail(f"unexpected control request {path}")

            def upload(_filename, state, parts, _digest):
                self.assertEqual([1], [part["partNumber"] for part in parts])
                state["completedParts"]["1"] = {"partNumber": 1, "etag": '"etag-1"', "size": 7}

            with mock.patch.object(al_site, "post_gateway_json", side_effect=control), mock.patch.object(
                al_site, "upload_parts", side_effect=upload
            ):
                result = al_site.post_source_archive(archive)
            self.assertEqual("receipt", result["receipt"])
            self.assertNotIn("/parts", "\n".join(calls))
            self.assertFalse(al_site.upload_state_file(digest).exists())

    def test_local_commands_are_registered(self):
        parser = al_site.build_parser()
        self.assertEqual("save-local", parser.parse_args(["save-local", "."]).action)
        self.assertEqual("deploy-local", parser.parse_args(["deploy-local", "."]).action)


if __name__ == "__main__":
    unittest.main()
