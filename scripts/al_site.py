#!/usr/bin/env python3
import argparse
import concurrent.futures
import datetime
import fnmatch
import gzip
import hashlib
import http.server
import json
import os
import pathlib
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
import threading


DEFAULT_LOGIN_CALLBACK_URL = "http://127.0.0.1:8766/oauth/callback"
DEFAULT_GATEWAY_URL = "https://skr0bjcv434ri5v3bqdlq.apigateway-cn-beijing.volceapi.com"
STATE_DIR = pathlib.Path(os.environ.get("AL_SITE_STATE_DIR", "~/.al-site-mcp")).expanduser()
STATE_FILE = STATE_DIR / "state.json"

SITE_TOOLS = (
    "CreateSite", "SelectSite", "GetCurrentSite", "GetSite", "ListSites", "UpdateSite",
    "SaveSiteVersion", "GetSiteVersion", "ListSiteVersions", "DeleteSiteVersion",
    "DeploySiteVersion", "GetSiteDeployment", "ListSiteDeployments", "PromoteSiteDeployment",
    "RollbackSite", "CancelSiteDeployment", "PauseSiteDeployment", "GetSiteAccessPolicy",
    "SetSiteAccessPolicy", "SetSiteGovernance", "SubmitSiteAppeal", "SetSiteDomain",
    "ListSiteDomains", "VerifySiteDomain", "DeleteSiteDomain", "GetSiteLogs", "GetSiteEvents",
    "GetSiteMetrics", "GetSiteUsage", "AttachSiteAddonBinding", "DetachSiteAddonBinding",
    "ArchiveConversationSite", "DeleteSite",
)

MAX_SOURCE_FILES = 100000
MAX_SOURCE_BYTES = 2 << 30
MAX_SOURCE_FILE_BYTES = 256 << 20
MAX_SOURCE_PATH_BYTES = 512
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{36,255}"),
    re.compile(rb"xox[baprs]-[A-Za-z0-9-]{20,}"),
)


def load_state():
    try:
        with STATE_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(state):
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, STATE_FILE)


def validate_gateway_url(value):
    value = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlparse(value)
    if parsed.path.rstrip("/") == "/mcp":
        value = value[: -len("/mcp")]
        parsed = urllib.parse.urlparse(value)
    loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SystemExit("invalid Site MCP Gateway URL")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
        raise SystemExit("Site MCP Gateway URL must use HTTPS; HTTP is allowed only for loopback testing")
    if parsed.path not in {"", "/"}:
        raise SystemExit("Site MCP Gateway URL must be the gateway origin or end in /mcp")
    return value.rstrip("/")


def configured_gateway_url():
    value = os.environ.get("AL_SITE_MCP_GATEWAY_URL", "").strip()
    if not value:
        value = str(load_state().get("gateway_url") or "").strip()
    if not value:
        value = DEFAULT_GATEWAY_URL
    return validate_gateway_url(value)


def mcp_url():
    return configured_gateway_url() + "/mcp"


def gateway_base():
    return configured_gateway_url()


def login_callback_url():
    return os.environ.get("AL_SITE_LOGIN_CALLBACK_URL", DEFAULT_LOGIN_CALLBACK_URL).strip()


def configure_gateway(value):
    state = load_state()
    state["gateway_url"] = validate_gateway_url(value)
    save_state(state)
    return state["gateway_url"]


def cached_token():
    token = os.environ.get("AL_SITE_MCP_TOKEN", "").strip()
    if token:
        return token
    state = load_state()
    token = str(state.get("access_token") or "").strip()
    expires_at = float(state.get("expires_at") or 0)
    if token and expires_at > time.time() + 60:
        return token
    return ""


def ensure_token():
    return cached_token() or login()


def ensure_conversation_id():
    value = os.environ.get("AL_SITE_CONVERSATION_ID", "").strip()
    if value:
        return value
    state = load_state()
    value = str(state.get("conversation_id") or "").strip()
    if value:
        return value
    value = str(uuid.uuid4())
    state["conversation_id"] = value
    save_state(state)
    return value


def set_new_conversation_id():
    state = load_state()
    state["conversation_id"] = str(uuid.uuid4())
    state.pop("site_id", None)
    save_state(state)
    return state["conversation_id"]


def cache_resource_ids(result):
    if not isinstance(result, dict):
        return
    meta = result.get("_meta")
    if not isinstance(meta, dict):
        return
    state = load_state()
    changed = False
    for key in ("site_id", "version_id", "deployment_id"):
        value = str(meta.get(key) or "").strip()
        if value:
            state[key] = value
            changed = True
    if changed:
        save_state(state)


class LoginCallbackHandler(http.server.BaseHTTPRequestHandler):
    result = {}

    def log_message(self, *_args):
        return

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/oauth/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        token = params.get("access_token", [""])[0]
        expires_in = params.get("expires_in", ["3600"])[0]
        error = params.get("error", [""])[0]
        if error:
            LoginCallbackHandler.result = {"error": error}
        elif not token:
            LoginCallbackHandler.result = {"error": "missing access_token from gateway login callback"}
        else:
            LoginCallbackHandler.result = {"access_token": token, "expires_in": expires_in}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h3>AL Site login finished.</h3>"
            b"<p>You can close this tab and return to the terminal.</p></body></html>"
        )


def login():
    callback_url = login_callback_url()
    parsed_redirect = urllib.parse.urlparse(callback_url)
    if parsed_redirect.hostname not in {"localhost", "127.0.0.1"}:
        raise SystemExit("AL_SITE_LOGIN_CALLBACK_URL must be a localhost callback for CLI login")
    port = parsed_redirect.port or 8766
    LoginCallbackHandler.result = {}
    query = urllib.parse.urlencode({"redirect_after_login": callback_url})
    auth_url = gateway_base() + "/login?" + query
    server = http.server.HTTPServer((parsed_redirect.hostname, port), LoginCallbackHandler)
    server.timeout = 300
    print("Open this URL to login:", auth_url, file=sys.stderr)
    webbrowser.open(auth_url)
    deadline = time.time() + 300
    while not LoginCallbackHandler.result and time.time() < deadline:
        server.handle_request()
    server.server_close()
    if not LoginCallbackHandler.result:
        raise SystemExit("login timed out")
    if LoginCallbackHandler.result.get("error"):
        raise SystemExit("login failed: " + LoginCallbackHandler.result["error"])
    token = str(LoginCallbackHandler.result.get("access_token") or "").strip()
    try:
        expires_in = int(LoginCallbackHandler.result.get("expires_in") or 3600)
    except (TypeError, ValueError):
        expires_in = 3600
    state = load_state()
    state["access_token"] = token
    state["expires_at"] = int(time.time() + max(expires_in - 60, 60))
    save_state(state)
    print("login ok", file=sys.stderr)
    return token


def logout():
    state = load_state()
    state.pop("access_token", None)
    state.pop("expires_at", None)
    save_state(state)


def headers():
    result = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + ensure_token(),
        "X-AL-Conversation-ID": ensure_conversation_id(),
    }
    tool_call_id = os.environ.get("AL_SITE_TOOL_CALL_ID", "").strip()
    if tool_call_id:
        result["X-AL-Tool-Call-ID"] = tool_call_id
    org_id = os.environ.get("AL_SITE_ORG_ID", "").strip()
    if org_id:
        result["X-AL-Org-ID"] = org_id
    return result


def request_timeout():
    try:
        value = int(os.environ.get("AL_SITE_MCP_TIMEOUT", "180"))
    except ValueError:
        raise SystemExit("AL_SITE_MCP_TIMEOUT must be an integer")
    return max(value, 1)


def rpc(method, params=None, request_id=None):
    payload = {
        "jsonrpc": "2.0",
        "id": request_id or str(uuid.uuid4()),
        "method": method,
        "params": params or {},
    }
    request = urllib.request.Request(
        mcp_url(),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=request_timeout()) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        raise SystemExit(f"HTTP {error.code}: {body}")
    except urllib.error.URLError as error:
        raise SystemExit(f"Site MCP request failed: {error.reason}")
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as error:
        raise SystemExit(f"Site MCP returned invalid JSON: {error}")
    if parsed.get("error"):
        raise SystemExit(json.dumps(parsed["error"], ensure_ascii=False, indent=2))
    return parsed.get("result")


def post_gateway_json(path, payload=None, method="POST", timeout=None):
    request = urllib.request.Request(
        gateway_base() + path,
        data=json.dumps(payload or {}, ensure_ascii=False).encode("utf-8"),
        headers=headers(),
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout or request_timeout()) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", "replace")
        raise SystemExit(f"HTTP {error.code}: {body}")
    if not body.strip():
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"text": body}


def post_source_archive(filename):
    filename = pathlib.Path(filename)
    size = filename.stat().st_size
    digest = file_sha256(filename)
    state = load_upload_state(digest, size)
    initial_parts = []
    if state is None:
        session = post_gateway_json(
            "/api/v1/source-bundle-uploads",
            {"archiveBytes": size, "transportSHA256": digest},
        )
        initial_parts = session.get("parts", []) if isinstance(session, dict) else []
        state = validate_upload_session(session, digest, size)
        save_upload_state(digest, state)
    upload_id = state["uploadID"]
    session_token = state["sessionToken"]
    try:
        status = post_gateway_json(
            f"/api/v1/source-bundle-uploads/{upload_id}/status",
            {"sessionToken": session_token},
        )
        merge_completed_parts(state, status.get("parts", []))
        missing = [number for number in range(1, state["partCount"] + 1) if str(number) not in state["completedParts"]]
        if status.get("completed") is True and missing:
            raise SystemExit("completed source upload cannot be resumed because its local ETag state is incomplete")
        if missing:
            missing_set = set(missing)
            available = [part for part in initial_parts if isinstance(part, dict) and part.get("partNumber") in missing_set]
            if {part.get("partNumber") for part in available} != missing_set:
                refreshed = post_gateway_json(
                    f"/api/v1/source-bundle-uploads/{upload_id}/parts",
                    {"sessionToken": session_token, "partNumbers": missing},
                )
                available = refreshed.get("parts", [])
            upload_parts(filename, state, available, digest)
        completed = completed_parts_for_request(state)
        result = post_gateway_json(
            f"/api/v1/source-bundle-uploads/{upload_id}/complete",
            {"sessionToken": session_token, "parts": completed},
            timeout=source_finalize_timeout(),
        )
    except BaseException:
        # The session token and completed ETags are kept in a 0600 local file so
        # the next invocation resumes instead of re-uploading successful parts.
        save_upload_state(digest, state)
        raise
    required = ("sourceRef", "sourceBundleDigest", "receipt")
    if not isinstance(result, dict) or any(not str(result.get(key) or "").strip() for key in required):
        raise SystemExit("Site source upload response is missing sourceRef, sourceBundleDigest, or receipt")
    delete_upload_state(digest)
    return result


def file_sha256(filename):
    digest = hashlib.sha256()
    with pathlib.Path(filename).open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_finalize_timeout():
    try:
        value = int(os.environ.get("AL_SITE_SOURCE_FINALIZE_TIMEOUT", "900"))
    except ValueError:
        raise SystemExit("AL_SITE_SOURCE_FINALIZE_TIMEOUT must be an integer")
    return max(value, 1)


def upload_state_dir():
    return STATE_DIR / "uploads"


def upload_state_file(digest):
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise SystemExit("invalid local source digest")
    return upload_state_dir() / f"{digest}.json"


def load_upload_state(digest, size):
    path = upload_state_file(digest)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(state, dict) or state.get("transportSHA256") != digest or state.get("archiveBytes") != size:
        path.unlink(missing_ok=True)
        return None
    try:
        expires_at = datetime.datetime.fromisoformat(str(state["expiresAt"]).replace("Z", "+00:00")).timestamp()
    except (KeyError, TypeError, ValueError):
        path.unlink(missing_ok=True)
        return None
    if expires_at <= time.time() + 60:
        path.unlink(missing_ok=True)
        return None
    if not isinstance(state.get("completedParts"), dict):
        state["completedParts"] = {}
    return state


def save_upload_state(digest, state):
    directory = upload_state_dir()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    target = upload_state_file(digest)
    temporary = target.with_suffix(".tmp")
    safe = {
        key: state[key]
        for key in ("uploadID", "sessionToken", "archiveBytes", "transportSHA256", "partSize", "partCount", "expiresAt", "completedParts")
    }
    temporary.write_text(json.dumps(safe, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)


def delete_upload_state(digest):
    upload_state_file(digest).unlink(missing_ok=True)


def validate_upload_session(session, digest, size):
    if not isinstance(session, dict):
        raise SystemExit("Site source upload session response is invalid")
    required = ("uploadID", "sessionToken", "archiveBytes", "transportSHA256", "partSize", "partCount", "expiresAt")
    if any(session.get(key) in (None, "") for key in required):
        raise SystemExit("Site source upload session response is incomplete")
    if session["archiveBytes"] != size or session["transportSHA256"] != digest:
        raise SystemExit("Site source upload session does not match the local archive")
    if not re.fullmatch(r"[0-9a-f]{32}", str(session["uploadID"])):
        raise SystemExit("Site source upload ID is invalid")
    if not isinstance(session["partSize"], int) or not isinstance(session["partCount"], int) or session["partCount"] < 1:
        raise SystemExit("Site source upload part contract is invalid")
    state = {key: session[key] for key in required}
    state["completedParts"] = {}
    return state


def merge_completed_parts(state, parts):
    if not isinstance(parts, list):
        raise SystemExit("Site source upload status returned invalid parts")
    for part in parts:
        if not isinstance(part, dict):
            raise SystemExit("Site source upload status returned an invalid part")
        number, etag = part.get("partNumber"), str(part.get("etag") or "").strip()
        if not isinstance(number, int) or number < 1 or number > state["partCount"] or not etag:
            raise SystemExit("Site source upload status returned an invalid part")
        state["completedParts"][str(number)] = {"partNumber": number, "etag": etag, "size": part.get("size") or part_size(state, number)}


def part_size(state, number):
    offset = (number - 1) * state["partSize"]
    return min(state["partSize"], state["archiveBytes"] - offset)


def completed_parts_for_request(state):
    result = []
    for number in range(1, state["partCount"] + 1):
        part = state["completedParts"].get(str(number))
        if not part:
            raise SystemExit(f"source upload part {number} is incomplete")
        result.append({"partNumber": number, "etag": part["etag"], "size": part_size(state, number)})
    return result


def upload_parts(filename, state, parts, digest):
    if not isinstance(parts, list):
        raise SystemExit("Site source upload returned invalid presigned parts")
    expected = {number for number in range(1, state["partCount"] + 1) if str(number) not in state["completedParts"]}
    supplied = {part.get("partNumber") for part in parts if isinstance(part, dict)}
    if supplied != expected:
        raise SystemExit("Site source upload did not return every missing presigned part")
    lock = threading.Lock()
    try:
        configured_workers = int(os.environ.get("AL_SITE_UPLOAD_WORKERS", "4"))
    except ValueError:
        raise SystemExit("AL_SITE_UPLOAD_WORKERS must be an integer")
    workers = min(max(configured_workers, 1), 16, len(parts))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(upload_one_part, filename, state, part): part["partNumber"] for part in parts}
        for future in concurrent.futures.as_completed(futures):
            completed = future.result()
            with lock:
                state["completedParts"][str(completed["partNumber"])] = completed
                save_upload_state(digest, state)


def upload_one_part(filename, state, part):
    number = part.get("partNumber")
    size = part.get("size")
    url = str(part.get("url") or "")
    signed_headers = part.get("headers") or {}
    if not isinstance(number, int) or size != part_size(state, number) or not url.startswith("https://") or not isinstance(signed_headers, dict):
        raise SystemExit("Site source upload returned an invalid presigned part")
    with pathlib.Path(filename).open("rb") as source:
        source.seek((number - 1) * state["partSize"])
        data = source.read(size)
    if len(data) != size:
        raise SystemExit(f"could not read source upload part {number}")
    last_error = None
    for attempt in range(5):
        request_headers = {str(key): str(value) for key, value in signed_headers.items()}
        request_headers["Content-Length"] = str(size)
        request = urllib.request.Request(url, data=data, headers=request_headers, method="PUT")
        try:
            with urllib.request.urlopen(request, timeout=max(request_timeout(), 300)) as response:
                etag = str(response.headers.get("ETag") or "").strip()
                if response.status < 200 or response.status >= 300 or not etag:
                    raise OSError(f"unexpected HTTP {response.status} or missing ETag")
                return {"partNumber": number, "etag": etag, "size": size}
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as error:
            last_error = error
            if attempt < 4:
                time.sleep(min(2 ** attempt, 8))
    # Never include the presigned URL in errors or logs.
    raise SystemExit(f"source upload part {number} failed after retries: {type(last_error).__name__}")


def load_alignore(root):
    try:
        content = (root / ".alignore").read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except (OSError, UnicodeError) as error:
        raise SystemExit(f"could not read .alignore: {error}")
    rules = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:]
        directory_only = line.endswith("/")
        pattern = line.lstrip("/").rstrip("/")
        if pattern:
            rules.append((pattern, negated, directory_only))
    return rules


def ignore_rule_matches(pattern, relative, is_directory, directory_only):
    if directory_only and relative == pattern and not is_directory:
        return False
    if fnmatch.fnmatchcase(relative, pattern):
        return True
    if "/" in pattern:
        return relative == pattern or relative.startswith(pattern + "/")
    return any(fnmatch.fnmatchcase(component, pattern) for component in relative.split("/"))


def ignored_by_alignore(rules, relative, is_directory):
    ignored = False
    for pattern, negated, directory_only in rules:
        if ignore_rule_matches(pattern, relative, is_directory, directory_only):
            ignored = not negated
    return ignored


def denied_source_path(relative):
    components = relative.split("/")
    for component in components:
        if component in {".git", ".svn", ".hg", ".ssh", ".aws", ".kube"}:
            return True
        if component == ".env" or (
            component.startswith(".env.") and component not in {".env.example", ".env.sample", ".env.template"}
        ):
            return True
    for prefix in (
        ".al/runtime/", ".config/lark-cli/", ".openai/auth", ".docker/config.json", ".netrc", ".npmrc", ".pypirc",
    ):
        if relative == prefix.rstrip("/") or relative.startswith(prefix):
            return True
    return False


def scan_source_file(path):
    try:
        with path.open("rb") as source:
            sample = source.read(8 << 20)
    except OSError as error:
        raise SystemExit(f"could not read source file {path}: {error}")
    if any(pattern.search(sample) for pattern in SECRET_PATTERNS):
        raise SystemExit(f"high-confidence credential material detected in source file: {path}")


def validate_source_symlink(root, path, relative):
    try:
        target = os.readlink(path)
    except OSError as error:
        raise SystemExit(f"could not read source symlink {relative}: {error}")
    if os.path.isabs(target) or "\x00" in target:
        raise SystemExit(f"source symlink escapes the project: {relative}")
    resolved = (path.parent / target).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError:
        raise SystemExit(f"source symlink escapes the project: {relative}")
    return target.replace(os.sep, "/")


def collect_source_entries(path):
    root = pathlib.Path(path).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"local project directory does not exist: {root}")
    rules = load_alignore(root)
    entries = []
    case_paths = {}
    total_bytes = 0
    for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = pathlib.Path(current)
        names = sorted(directory_names + file_names)
        directory_names[:] = []
        for name in names:
            absolute = current_path / name
            relative = absolute.relative_to(root).as_posix()
            try:
                info = absolute.lstat()
            except OSError as error:
                raise SystemExit(f"could not inspect source path {relative}: {error}")
            is_directory = stat.S_ISDIR(info.st_mode)
            if denied_source_path(relative):
                continue
            if ignored_by_alignore(rules, relative, is_directory):
                if is_directory:
                    # Keep walking because a later negated rule may re-include
                    # a descendant, matching the server canonicalizer.
                    directory_names.append(name)
                continue
            if len(relative.encode("utf-8")) > MAX_SOURCE_PATH_BYTES or "\x00" in relative:
                raise SystemExit(f"source contains an invalid or overlong path: {relative}")
            folded = relative.lower()
            if folded in case_paths and case_paths[folded] != relative:
                raise SystemExit(f"source paths collide under case folding: {case_paths[folded]} and {relative}")
            case_paths[folded] = relative
            kind = None
            link_target = ""
            if stat.S_ISDIR(info.st_mode):
                kind = "directory"
                directory_names.append(name)
            elif stat.S_ISREG(info.st_mode):
                kind = "file"
                if info.st_size > MAX_SOURCE_FILE_BYTES:
                    raise SystemExit(f"source file exceeds the 256 MiB limit: {relative}")
                total_bytes += info.st_size
                if total_bytes > MAX_SOURCE_BYTES:
                    raise SystemExit("source exceeds the 2 GiB uncompressed limit")
                scan_source_file(absolute)
            elif stat.S_ISLNK(info.st_mode):
                kind = "symlink"
                link_target = validate_source_symlink(root, absolute, relative)
            else:
                raise SystemExit(f"source contains an unsupported file type: {relative}")
            entries.append((relative, absolute, info, kind, link_target))
            if len(entries) > MAX_SOURCE_FILES:
                raise SystemExit("source exceeds the 100000 entry limit")
    entries.sort(key=lambda item: item[0])
    return root, entries, total_bytes


def create_source_archive(path):
    root, entries, total_bytes = collect_source_entries(path)
    handle = tempfile.NamedTemporaryFile(prefix="al-site-source-", suffix=".tar.gz", delete=False)
    archive_path = pathlib.Path(handle.name)
    handle.close()
    try:
        with archive_path.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                    for relative, absolute, info, kind, link_target in entries:
                        item = tarfile.TarInfo(relative + ("/" if kind == "directory" else ""))
                        item.uid = item.gid = 0
                        item.uname = item.gname = ""
                        item.mtime = 0
                        if kind == "directory":
                            item.type, item.mode, item.size = tarfile.DIRTYPE, 0o755, 0
                            archive.addfile(item)
                        elif kind == "symlink":
                            item.type, item.mode, item.size, item.linkname = tarfile.SYMTYPE, 0o777, 0, link_target
                            archive.addfile(item)
                        else:
                            item.type = tarfile.REGTYPE
                            item.mode = 0o755 if info.st_mode & 0o111 else 0o644
                            item.size = info.st_size
                            with absolute.open("rb") as source:
                                archive.addfile(item, source)
        digest = hashlib.sha256()
        with archive_path.open("rb") as source:
            for chunk in iter(lambda: source.read(1 << 20), b""):
                digest.update(chunk)
        return archive_path, {
            "root": str(root), "entry_count": len(entries), "total_bytes": total_bytes,
            "archive_bytes": archive_path.stat().st_size, "transport_sha256": digest.hexdigest(),
        }
    except BaseException:
        archive_path.unlink(missing_ok=True)
        raise


def save_local_source(path, site_id, build_json="{}", runtime_json="{}"):
    archive, summary = create_source_archive(path)
    try:
        uploaded = post_source_archive(archive)
        source = {
            "type": "source_bundle",
            "source_bundle_ref": uploaded["sourceRef"],
            "upload_receipt": uploaded["receipt"],
        }
        arguments = save_version_arguments(site_id, source, build_json, runtime_json)
        saved = call_tool("SaveSiteVersion", arguments)
    finally:
        archive.unlink(missing_ok=True)
    # Receipt is intentionally omitted. It is caller-bound and short-lived and
    # must never enter local state, CLI output, or logs.
    summary["source_ref"] = uploaded["sourceRef"]
    summary["source_bundle_digest"] = uploaded["sourceBundleDigest"]
    return summary, saved


def archive_conversation_site():
    result = post_gateway_json("/internal/conversation-site/archive", {})
    state = load_state()
    state.pop("site_id", None)
    save_state(state)
    return result


def result_text(result):
    if not isinstance(result, dict):
        return str(result)
    parts = []
    for item in result.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
            parts.append(str(item["text"]))
    return "\n".join(parts) or json.dumps(result, ensure_ascii=False)


def call_tool(name, arguments):
    result = rpc("tools/call", {"name": name, "arguments": arguments})
    cache_resource_ids(result)
    if isinstance(result, dict) and result.get("isError"):
        raise SystemExit(result_text(result))
    return result


def load_json_object(value):
    source = str(value or "{}").strip()
    if source.startswith("@"):
        source = pathlib.Path(source[1:]).read_text(encoding="utf-8")
    try:
        parsed = json.loads(source)
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid JSON object: {error}")
    if not isinstance(parsed, dict):
        raise SystemExit("arguments must be a JSON object")
    return parsed


def parse_arg_value(value):
    raw = str(value)
    if raw.startswith("@"):
        return pathlib.Path(raw[1:]).read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def merge_call_arguments(arguments_json, arg_items):
    arguments = load_json_object(arguments_json)
    for item in arg_items or []:
        if "=" not in item:
            raise SystemExit(f"--arg must use key=value format: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise SystemExit(f"--arg key cannot be empty: {item}")
        arguments[key] = parse_arg_value(value)
    return arguments


def find_tool_definition(tools_result, name):
    for item in tools_result.get("tools", []):
        if item.get("name") == name:
            return item
    raise SystemExit(f"tool {name!r} was not found in tools/list")


def filter_tools(tools_result, keyword):
    keyword = (keyword or "").strip().lower()
    if not keyword:
        return tools_result
    result = dict(tools_result)
    result["tools"] = [
        item for item in tools_result.get("tools", [])
        if keyword in (str(item.get("name") or "") + " " + str(item.get("description") or "")).lower()
    ]
    return result


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def tool_command_name(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def selected_site_id(explicit=""):
    explicit = str(explicit or "").strip()
    if explicit:
        return explicit
    value = os.environ.get("AL_SITE_ID", "").strip()
    if value:
        return value
    state = load_state()
    value = str(state.get("site_id") or "").strip()
    if value:
        return value
    current = call_tool("GetCurrentSite", {})
    meta = current.get("_meta", {}) if isinstance(current, dict) else {}
    value = str(meta.get("site_id") or "").strip()
    if not value:
        raise SystemExit("no Site is selected; pass --site-id or run select SITE_ID")
    return value


def result_meta_id(result, key):
    meta = result.get("_meta", {}) if isinstance(result, dict) else {}
    value = str(meta.get(key) or "").strip()
    if not value:
        raise SystemExit(f"Site MCP response is missing _meta.{key}")
    return value


def phase_of(result):
    if isinstance(result, dict):
        meta = result.get("_meta")
        if isinstance(meta, dict) and meta.get("phase"):
            return str(meta["phase"])
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            status = structured.get("status")
            if isinstance(status, dict) and status.get("phase"):
                return str(status["phase"])
    return ""


def wait_for(tool, arguments, timeout_seconds, interval_seconds, success_phases, failure_phases):
    deadline = time.monotonic() + timeout_seconds
    last_phase = None
    while True:
        result = call_tool(tool, arguments)
        phase = phase_of(result)
        if phase != last_phase:
            print(f"{tool}: phase={phase or 'unknown'}", file=sys.stderr)
            last_phase = phase
        lowered = phase.lower()
        if lowered in success_phases:
            return result
        if lowered in failure_phases:
            raise SystemExit(f"{tool} reached terminal phase {phase}: {result_text(result)}")
        if time.monotonic() >= deadline:
            raise SystemExit(f"timed out waiting for {tool}; last phase={phase or 'unknown'}")
        time.sleep(interval_seconds)


def run_git(path, *args, timeout=30):
    command = ["git", "-C", str(path), *args]
    try:
        completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SystemExit(f"git command failed: {error}")
    if completed.returncode != 0:
        raise SystemExit(completed.stderr.strip() or completed.stdout.strip() or "git command failed")
    return completed.stdout.strip()


def normalize_git_url(value):
    value = value.strip()
    match = re.fullmatch(r"([^@\s]+@[^:\s]+):(.+)", value)
    if match:
        value = f"ssh://{match.group(1)}/{match.group(2)}"
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"https", "ssh"} or not parsed.hostname:
        raise SystemExit("Site Git source must use an https:// or ssh:// repository URL")
    return value


def inspect_local_git(path, remote="origin", branch="", skip_remote_check=False):
    root = pathlib.Path(path).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"local project directory does not exist: {root}")
    top = pathlib.Path(run_git(root, "rev-parse", "--show-toplevel")).resolve()
    dirty = run_git(top, "status", "--porcelain", "--untracked-files=normal")
    if dirty:
        raise SystemExit("local Git working tree is not clean; commit or remove all tracked and untracked changes")
    commit = run_git(top, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit):
        raise SystemExit("local Git HEAD is not an immutable 40-64 character commit")
    if not branch:
        branch = run_git(top, "symbolic-ref", "--quiet", "--short", "HEAD")
    repository = normalize_git_url(run_git(top, "remote", "get-url", remote))
    if not skip_remote_check:
        ref = "refs/heads/" + branch
        try:
            output = subprocess.run(
                ["git", "ls-remote", "--heads", repository, ref],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SystemExit(f"could not verify remote Git commit: {error}")
        if output.returncode != 0:
            raise SystemExit(output.stderr.strip() or "could not read remote Git branch")
        remote_commits = {line.split()[0].lower() for line in output.stdout.splitlines() if line.split()}
        if commit.lower() not in remote_commits:
            raise SystemExit(f"remote branch {branch!r} does not point at local HEAD {commit}; push the commit first")
    return {"root": str(top), "repository": repository, "commit_sha": commit, "branch": branch}


def credential_from_env(name):
    if not name:
        return ""
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"credential environment variable {name!r} is empty")
    if len(value.encode("utf-8")) > 65536:
        raise SystemExit("Git source credential exceeds the 64 KiB limit")
    return value


def save_version_arguments(site_id, source, build_json="{}", runtime_json="{}", credential_env=""):
    arguments = {"site_id": selected_site_id(site_id), "source": source}
    build = load_json_object(build_json)
    runtime = load_json_object(runtime_json)
    if build:
        arguments["build"] = build
    if runtime:
        arguments["runtime"] = runtime
    credential = credential_from_env(credential_env)
    if credential:
        arguments["source"]["credential"] = credential
    return arguments


def register_generic_tool_commands(subparsers):
    for tool in SITE_TOOLS:
        parser = subparsers.add_parser(tool_command_name(tool), help=f"Call {tool}")
        parser.set_defaults(site_tool=tool)
        parser.add_argument("--arguments", default="{}", help="JSON object or @file.json")
        parser.add_argument("--arg", action="append", default=[], help="Add one argument as key=value")


def add_site_id(parser):
    parser.add_argument("--site-id", default="", help="Use this Site instead of the cached/current Site")


def add_save_options(parser):
    add_site_id(parser)
    parser.add_argument("--build", default="{}", help="Build JSON object or @file.json")
    parser.add_argument("--runtime", default="{}", help="Runtime JSON object or @file.json")


def add_wait_options(parser, default_timeout):
    parser.add_argument("--timeout-seconds", type=int, default=default_timeout)
    parser.add_argument("--interval-seconds", type=float, default=5.0)


def build_parser():
    parser = argparse.ArgumentParser(description="AL Site MCP Gateway client")
    sub = parser.add_subparsers(dest="action", required=True)
    configure = sub.add_parser("configure")
    configure.add_argument("--gateway-url", required=True)
    sub.add_parser("config")
    sub.add_parser("login")
    sub.add_parser("login-url")
    sub.add_parser("logout")
    sub.add_parser("conversation")
    sub.add_parser("new-conversation")
    sub.add_parser("archive")
    sub.add_parser("initialize")

    tools = sub.add_parser("tools")
    tools.add_argument("--filter", default="")
    tools.add_argument("--names", action="store_true")
    describe = sub.add_parser("describe")
    describe.add_argument("tool")
    call = sub.add_parser("call")
    call.add_argument("tool")
    call.add_argument("--arguments", default="{}")
    call.add_argument("--arg", action="append", default=[])

    create = sub.add_parser("create")
    create.add_argument("display_name")
    create.add_argument("--audience", choices=("owner", "selected", "organization", "public"), default="owner")
    create.add_argument("--scaling-profile", choices=("economy", "balanced", "latency", "burst", "custom"), default="")
    create.add_argument("--runtime-class-name", default="")
    create.add_argument("--public-publishing", action="store_true")
    create.add_argument("--confirm-public", action="store_true")
    select = sub.add_parser("select")
    select.add_argument("site_id")
    sub.add_parser("current")
    sub.add_parser("sites")
    get = sub.add_parser("get")
    get.add_argument("site_id", nargs="?", default="")

    save_current = sub.add_parser("save-current")
    add_save_options(save_current)
    save_git = sub.add_parser("save-git")
    save_git.add_argument("repository")
    save_git.add_argument("commit_sha")
    save_git.add_argument("--submodules", action="store_true")
    save_git.add_argument("--credential-env", default="")
    add_save_options(save_git)
    save_oci = sub.add_parser("save-oci")
    save_oci.add_argument("image_digest")
    add_site_id(save_oci)

    for name in ("save-local", "deploy-local"):
        local = sub.add_parser(name)
        local.add_argument("path", nargs="?", default=".")
        add_save_options(local)
        if name == "deploy-local":
            add_wait_options(local, 1800)
            local.add_argument("--deployment-timeout-seconds", type=int, default=900)

    for name in ("save-local-git", "deploy-local-git"):
        local = sub.add_parser(name)
        local.add_argument("path", nargs="?", default=".")
        local.add_argument("--remote", default="origin")
        local.add_argument("--branch", default="")
        local.add_argument("--skip-remote-check", action="store_true")
        local.add_argument("--credential-env", default="")
        add_save_options(local)
        if name == "deploy-local-git":
            add_wait_options(local, 1800)
            local.add_argument("--deployment-timeout-seconds", type=int, default=900)

    version = sub.add_parser("version")
    version.add_argument("version_id")
    add_site_id(version)
    versions = sub.add_parser("versions")
    add_site_id(versions)
    wait_version = sub.add_parser("wait-version")
    wait_version.add_argument("version_id")
    add_site_id(wait_version)
    add_wait_options(wait_version, 1800)

    deploy = sub.add_parser("deploy")
    deploy.add_argument("version_id")
    add_site_id(deploy)
    deploy.add_argument("--runtime", default="{}")
    deploy.add_argument("--strategy", default="{}")
    deployment = sub.add_parser("deployment")
    deployment.add_argument("deployment_id")
    add_site_id(deployment)
    deployments = sub.add_parser("deployments")
    add_site_id(deployments)
    wait_deployment = sub.add_parser("wait-deployment")
    wait_deployment.add_argument("deployment_id")
    add_site_id(wait_deployment)
    add_wait_options(wait_deployment, 900)

    register_generic_tool_commands(sub)
    return parser


def main():
    args = build_parser().parse_args()
    if args.action == "configure":
        print(configure_gateway(args.gateway_url))
        return
    if args.action == "config":
        state = load_state()
        print_json({
            "gateway_url": os.environ.get("AL_SITE_MCP_GATEWAY_URL") or state.get("gateway_url") or DEFAULT_GATEWAY_URL,
            "conversation_id": os.environ.get("AL_SITE_CONVERSATION_ID") or state.get("conversation_id", ""),
            "site_id": os.environ.get("AL_SITE_ID") or state.get("site_id", ""),
            "has_valid_token": bool(cached_token()),
            "state_file": str(STATE_FILE),
        })
        return
    if args.action == "login":
        login()
        return
    if args.action == "login-url":
        print(gateway_base() + "/login")
        return
    if args.action == "logout":
        logout()
        print("logout ok")
        return
    if args.action == "conversation":
        print(ensure_conversation_id())
        return
    if args.action == "new-conversation":
        print(set_new_conversation_id())
        return
    if args.action == "archive":
        print_json(archive_conversation_site())
        return
    if args.action == "initialize":
        print_json(rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}}))
        return
    if args.action == "tools":
        result = filter_tools(rpc("tools/list"), args.filter)
        if args.names:
            for item in result.get("tools", []):
                print(item.get("name", ""))
        else:
            print_json(result)
        return
    if args.action == "describe":
        print_json(find_tool_definition(rpc("tools/list"), args.tool))
        return
    if args.action == "call":
        print_json(call_tool(args.tool, merge_call_arguments(args.arguments, args.arg)))
        return
    if hasattr(args, "site_tool"):
        print_json(call_tool(args.site_tool, merge_call_arguments(args.arguments, args.arg)))
        return
    if args.action == "create":
        arguments = {"display_name": args.display_name, "audience": args.audience}
        for key in ("scaling_profile", "runtime_class_name"):
            if getattr(args, key):
                arguments[key] = getattr(args, key)
        if args.public_publishing:
            arguments["public_publishing"] = True
        if args.confirm_public:
            arguments["confirm_public"] = True
        print_json(call_tool("CreateSite", arguments))
        return
    if args.action == "select":
        print_json(call_tool("SelectSite", {"site_id": args.site_id}))
        return
    if args.action == "current":
        print_json(call_tool("GetCurrentSite", {}))
        return
    if args.action == "sites":
        print_json(call_tool("ListSites", {}))
        return
    if args.action == "get":
        print_json(call_tool("GetSite", {"site_id": selected_site_id(args.site_id)}))
        return
    if args.action == "save-current":
        arguments = save_version_arguments(args.site_id, {"type": "current_conversation"}, args.build, args.runtime)
        print_json(call_tool("SaveSiteVersion", arguments))
        return
    if args.action == "save-git":
        source = {
            "type": "git", "repository": normalize_git_url(args.repository),
            "commit_sha": args.commit_sha, "submodules": args.submodules,
        }
        arguments = save_version_arguments(args.site_id, source, args.build, args.runtime, args.credential_env)
        print_json(call_tool("SaveSiteVersion", arguments))
        return
    if args.action == "save-oci":
        print_json(call_tool("SaveSiteVersion", {
            "site_id": selected_site_id(args.site_id),
            "source": {"type": "oci", "image_digest": args.image_digest},
        }))
        return
    if args.action in {"save-local", "deploy-local"}:
        local, saved = save_local_source(args.path, args.site_id, args.build, args.runtime)
        if args.action == "save-local":
            print_json({"local_source": local, "version": saved})
            return
        site_id = selected_site_id(args.site_id)
        version_id = result_meta_id(saved, "version_id")
        ready_version = wait_for(
            "GetSiteVersion", {"site_id": site_id, "version_id": version_id},
            args.timeout_seconds, args.interval_seconds, {"ready"}, {"failed"},
        )
        deployment = call_tool("DeploySiteVersion", {"site_id": site_id, "version_id": version_id})
        deployment_id = result_meta_id(deployment, "deployment_id")
        ready_deployment = wait_for(
            "GetSiteDeployment", {"site_id": site_id, "deployment_id": deployment_id},
            args.deployment_timeout_seconds, args.interval_seconds, {"ready"}, {"failed", "cancelled"},
        )
        print_json({"local_source": local, "version": ready_version, "deployment": ready_deployment})
        return
    if args.action in {"save-local-git", "deploy-local-git"}:
        local = inspect_local_git(args.path, args.remote, args.branch, args.skip_remote_check)
        source = {"type": "git", "repository": local["repository"], "commit_sha": local["commit_sha"]}
        arguments = save_version_arguments(args.site_id, source, args.build, args.runtime, args.credential_env)
        saved = call_tool("SaveSiteVersion", arguments)
        if args.action == "save-local-git":
            print_json({"local_git": local, "version": saved})
            return
        site_id = arguments["site_id"]
        version_id = result_meta_id(saved, "version_id")
        ready_version = wait_for(
            "GetSiteVersion", {"site_id": site_id, "version_id": version_id},
            args.timeout_seconds, args.interval_seconds, {"ready"}, {"failed"},
        )
        deployment = call_tool("DeploySiteVersion", {"site_id": site_id, "version_id": version_id})
        deployment_id = result_meta_id(deployment, "deployment_id")
        ready_deployment = wait_for(
            "GetSiteDeployment", {"site_id": site_id, "deployment_id": deployment_id},
            args.deployment_timeout_seconds, args.interval_seconds, {"ready"}, {"failed", "cancelled"},
        )
        print_json({
            "local_git": local, "version": ready_version,
            "deployment": ready_deployment,
        })
        return
    if args.action == "version":
        print_json(call_tool("GetSiteVersion", {"site_id": selected_site_id(args.site_id), "version_id": args.version_id}))
        return
    if args.action == "versions":
        print_json(call_tool("ListSiteVersions", {"site_id": selected_site_id(args.site_id)}))
        return
    if args.action == "wait-version":
        print_json(wait_for(
            "GetSiteVersion", {"site_id": selected_site_id(args.site_id), "version_id": args.version_id},
            args.timeout_seconds, args.interval_seconds, {"ready"}, {"failed"},
        ))
        return
    if args.action == "deploy":
        arguments = {"site_id": selected_site_id(args.site_id), "version_id": args.version_id}
        runtime, strategy = load_json_object(args.runtime), load_json_object(args.strategy)
        if runtime:
            arguments["runtime"] = runtime
        if strategy:
            arguments["strategy"] = strategy
        print_json(call_tool("DeploySiteVersion", arguments))
        return
    if args.action == "deployment":
        print_json(call_tool("GetSiteDeployment", {"site_id": selected_site_id(args.site_id), "deployment_id": args.deployment_id}))
        return
    if args.action == "deployments":
        print_json(call_tool("ListSiteDeployments", {"site_id": selected_site_id(args.site_id)}))
        return
    if args.action == "wait-deployment":
        print_json(wait_for(
            "GetSiteDeployment", {"site_id": selected_site_id(args.site_id), "deployment_id": args.deployment_id},
            args.timeout_seconds, args.interval_seconds, {"ready"}, {"failed", "cancelled"},
        ))


if __name__ == "__main__":
    main()
