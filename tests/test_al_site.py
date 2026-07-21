import importlib.util
import json
import os
import pathlib
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).parents[1] / "scripts" / "al_site.py"
SPEC = importlib.util.spec_from_file_location("al_site", SCRIPT)
al_site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(al_site)


class SiteClientTest(unittest.TestCase):
    def test_all_current_tools_have_unique_commands(self):
        commands = [al_site.tool_command_name(name) for name in al_site.SITE_TOOLS]
        self.assertEqual(len(commands), len(set(commands)))
        self.assertEqual("save-site-version", al_site.tool_command_name("SaveSiteVersion"))
        parser = al_site.build_parser()
        args = parser.parse_args(["get-site-events", "--arg", "site_id=example"])
        self.assertEqual("GetSiteEvents", args.site_tool)

    def test_gateway_url_validation(self):
        self.assertEqual("https://gateway.example", al_site.validate_gateway_url("https://gateway.example/mcp"))
        self.assertEqual("http://127.0.0.1:8080", al_site.validate_gateway_url("http://127.0.0.1:8080"))
        with self.assertRaises(SystemExit):
            al_site.validate_gateway_url("http://gateway.example")
        with self.assertRaises(SystemExit):
            al_site.validate_gateway_url("https://gateway.example/not-mcp")

    def test_argument_merge_parses_json(self):
        value = al_site.merge_call_arguments('{"site_id":"a"}', ["confirm=true", "step=2", 'users=["u"]'])
        self.assertEqual({"site_id": "a", "confirm": True, "step": 2, "users": ["u"]}, value)

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
            ), mock.patch.object(al_site, "call_tool", return_value={"_meta": {"version_id": "v1"}}) as call:
                summary, result = al_site.save_local_source(root, "site-1")
            arguments = call.call_args.args[1]
            self.assertEqual("sensitive-receipt", arguments["source"]["upload_receipt"])
            self.assertNotIn("receipt", summary)
            self.assertNotIn("sensitive-receipt", json.dumps({"summary": summary, "result": result}))

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
