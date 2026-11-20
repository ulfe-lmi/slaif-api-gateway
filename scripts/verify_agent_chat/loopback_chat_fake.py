"""Task-owned loopback fake OpenAI-compatible Chat server (shared harness).

Part of the small shared loopback/client harness under scripts/verify_agent_chat/.
Stdlib only. Binds to 127.0.0.1 on a caller-chosen port. Scenario/state are
re-read per request so a single server can serve a sequence of probes.

Privacy: the raw request journal is written only into the 0700 run directory
at 0600 and is ephemeral; verifiers must commit only sanitized structural
facts. Synthetic credentials only; the fake never contacts any provider.

Classification rule: a request without a non-empty ``tools`` array and
without a ``role: tool`` message is auxiliary (e.g. title generation or
compaction summarization) in every scenario mode and never consumes the
main turn counter.

Tool-loop gating: continuation success requires a tool message whose
``tool_call_id`` equals a server-issued call id AND whose string content
carries the run's unpredictable marker. The gated response echoes the
marker extracted from that correlated native tool result (never an
unconditional file read).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.umask(0o077)

RUN = os.environ["AGENT_CHAT_FAKE_RUN"]
WORKSPACE = os.environ.get("AGENT_CHAT_FAKE_WORKSPACE", os.path.join(RUN, "workspace"))
JOURNAL = os.path.join(RUN, "run", "requests.jsonl")
SCENARIO = os.path.join(RUN, "run", "scenario.json")
STATE = os.path.join(RUN, "run", "state.json")
MARKER_FILE = os.path.join(RUN, "run", "expected_marker.bin")
LOCK = threading.RLock()


def _write_private(path: str, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def save(path, obj):
    _write_private(path, (json.dumps(obj) + "\n").encode())


def redact_headers(headers):
    out = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk == "authorization":
            parts = v.split(" ", 1)
            out[k] = {
                "redacted": True,
                "scheme": parts[0] if parts and parts[0] else None,
                "token_sha256_8": hashlib.sha256(parts[1].encode()).hexdigest()[:8] if len(parts) == 2 else None,
            }
        elif lk in ("cookie", "proxy-authorization"):
            out[k] = {"redacted": True}
        else:
            out[k] = v
    return out


def sse(payload):
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


class Handler(BaseHTTPRequestHandler):
    server_version = "SLAIFAgentChatFake/1"

    def log_message(self, fmt, *args):
        pass

    def _journal(self, method, path, headers, body_bytes):
        with LOCK:
            fd = os.open(JOURNAL, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps({
                    "ts": time.time(), "method": method, "path": path,
                    "headers": redact_headers(headers),
                    "body_bytes": len(body_bytes),
                    "body": body_bytes.decode("utf-8", "replace"),
                }, ensure_ascii=False) + "\n")

    def do_GET(self):
        if self.path == "/v1/models":
            self._journal("GET", self.path, dict(self.headers), b"")
            payload = {"object": "list", "data": [
                {"id": "agent-chat-fake-model", "object": "model",
                 "created": 1700000000, "owned_by": "agent-chat-loopback"}
            ]}
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self._journal("POST", self.path, dict(self.headers), body)
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        try:
            req = json.loads(body.decode("utf-8"))
        except Exception:
            self.send_error(400, "invalid json")
            return
        scenario = load(SCENARIO, {"mode": "text"})
        model = req.get("model")
        stream = bool(req.get("stream"))
        msgs = [m for m in req.get("messages", []) if isinstance(m, dict)]
        has_tools = isinstance(req.get("tools"), list) and req.get("tools")
        has_tool_msg = any(m.get("role") == "tool" for m in msgs)

        if scenario.get("mode") == "compact":
            if not (has_tools or has_tool_msg):
                with LOCK:
                    st = load(STATE, {})
                    st["summary_issued"] = True
                    st["aux_requests"] = st.get("aux_requests", 0) + 1
                    save(STATE, st)
                self._text(req, model, stream,
                           dict(scenario, final_text=scenario.get("summary_text", "SUMMARY"),
                                usage=[4, 2]))
                return
            with LOCK:
                st = load(STATE, {})
                st["main_requests"] = st.get("main_requests", 0) + 1
                n = st["main_requests"]
                save(STATE, st)
            self._compact_main(req, model, stream, n, scenario)
            return

        if not (has_tools or has_tool_msg):
            # Auxiliary (title, etc.): never consumes the main turn counter.
            with LOCK:
                st = load(STATE, {})
                st["aux_requests"] = st.get("aux_requests", 0) + 1
                save(STATE, st)
            if scenario.get("mode") == "toolloop":
                self._aux(req, model, stream, scenario)
                return
            self._text(req, model, stream,
                       dict(scenario, final_text=scenario.get("aux_final_text", "ok")))
            return

        with LOCK:
            st = load(STATE, {})
            st["chat_requests"] = st.get("chat_requests", 0) + 1
            n = st["chat_requests"]
            save(STATE, st)
        if scenario.get("mode") == "toolloop":
            self._toolloop(req, model, stream, n, scenario)
        else:
            self._text(req, model, stream, scenario)

    # -- response builders -------------------------------------------------

    def _usage_chunk(self, cid, model, p, c):
        return {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [],
            "usage": {"prompt_tokens": p, "completion_tokens": c, "total_tokens": p + c},
        }

    def _finish(self):
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _stream(self, chunks):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for c in chunks:
            self.wfile.write(sse(c))
            self.wfile.flush()
        self._finish()

    def _nonstream(self, message, model, usage):
        payload = {
            "id": "chatcmpl-fake-" + uuid.uuid4().hex[:24],
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": usage,
        }
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _text(self, req, model, stream, scenario):
        text = scenario.get("final_text", "AGENT_CHAT_TEXT_OK")
        p, c = (scenario.get("usage") or [12, 8])
        usage = {"prompt_tokens": p, "completion_tokens": c, "total_tokens": p + c}
        if stream:
            cid = "chatcmpl-fake-" + uuid.uuid4().hex[:24]
            base = {"id": cid, "object": "chat.completion.chunk",
                    "created": int(time.time()), "model": model}
            chunks = [
                dict(base, choices=[{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]),
                *([dict(base, choices=[{"index": 0, "delta": {"reasoning_content": scenario["reasoning_content"]}, "finish_reason": None}])]
                  if scenario.get("reasoning_content") else []),
                dict(base, choices=[{"index": 0, "delta": {"content": text}, "finish_reason": None}]),
                dict(base, choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}]),
            ]
            if isinstance(req.get("stream_options"), dict) and req["stream_options"].get("include_usage"):
                chunks.append(self._usage_chunk(cid, model, p, c))
            self._stream(chunks)
        else:
            self._nonstream({"role": "assistant", "content": text}, model, usage)

    def _aux(self, req, model, stream, scenario):
        text = scenario.get("aux_final_text", "ok")
        self._text(req, model, stream, dict(scenario, final_text=text, usage=[4, 2]))

    def _toolloop(self, req, model, stream, n, scenario):
        with LOCK:
            st = load(STATE, {})
        if n == 1:
            files = scenario.get("tool_files") or [scenario.get("tool_file", "probe.txt")]
            calls = [{"call_id": "call_fake_" + uuid.uuid4().hex[:20], "path": f}
                     for f in files]
            st["issued"] = {"call_id": calls[0]["call_id"], "path": calls[0]["path"],
                            "calls": calls}
            with LOCK:
                save(STATE, st)
            cid = "chatcmpl-fake-" + uuid.uuid4().hex[:24]
            base = {"id": cid, "object": "chat.completion.chunk",
                    "created": int(time.time()), "model": model}
            chunks = [
                dict(base, choices=[{"index": 0, "delta": {"role": "assistant", "content": None}, "finish_reason": None}]),
                dict(base, choices=[{"index": 0, "delta": {"tool_calls": [
                    {"index": i, "id": c["call_id"], "type": "function",
                     "function": {"name": "read",
                                  "arguments": json.dumps({"filePath": c["path"]})}}
                    for i, c in enumerate(calls)
                ]}, "finish_reason": None}]),
                dict(base, choices=[{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]),
            ]
            if isinstance(req.get("stream_options"), dict) and req["stream_options"].get("include_usage"):
                chunks.append(self._usage_chunk(cid, model, 30, 6))
            self._stream(chunks)
            return
        # Continuation: gate on the actually correlated native tool results.
        issued = st.get("issued", {})
        calls = issued.get("calls", [{"call_id": issued.get("call_id"),
                                      "path": issued.get("path")}])
        facts = {"calls_issued": len(calls), "tool_messages_total": 0,
                 "correlated_calls": 0, "unverified_calls": []}
        tool_msgs = [m for m in req.get("messages", [])
                     if isinstance(m, dict) and m.get("role") == "tool"]
        facts["tool_messages_total"] = len(tool_msgs)
        per_call = []
        verified_pairs = []
        for ci, c in enumerate(calls):
            idx = calls.index(c)
            mpath = (os.path.join(RUN, "run", f"expected_marker_{idx}.bin")
                     if len(calls) > 1 else MARKER_FILE)
            try:
                with open(mpath, "rb") as f:
                    marker = f.read().decode("utf-8")
            except Exception:
                marker = None
            matched = None
            for m in tool_msgs:
                if m.get("tool_call_id") == c["call_id"]:
                    matched = m
                    break
            cf = {"correlated_tool_message": matched is not None,
                  "content_type": type(matched.get("content")).__name__ if matched else None,
                  "marker_present": False, "marker_occurrences": 0,
                  "content_equals_marker": False,
                  "content_byte_length": None, "marker_byte_length": None}
            if matched is not None and marker is not None and isinstance(matched.get("content"), str):
                content = matched["content"]
                cf["marker_byte_length"] = len(marker.encode("utf-8"))
                cf["content_byte_length"] = len(content.encode("utf-8"))
                cf["marker_occurrences"] = content.count(marker)
                cf["marker_present"] = cf["marker_occurrences"] >= 1
                cf["content_equals_marker"] = content == marker
                if cf["marker_present"]:
                    verified_pairs.append((c, matched, marker))
            per_call.append(cf)
            if not (cf["correlated_tool_message"] and cf["marker_present"]):
                facts["unverified_calls"].append(c["path"])
        facts["per_call"] = per_call
        facts["correlated_calls"] = sum(1 for cf in per_call if cf["correlated_tool_message"])
        st["toolloop_facts"] = facts
        st["toolloop_verified"] = (facts["correlated_calls"] == len(calls)
                                   and not facts["unverified_calls"])
        # Echo the verified marker extracted from the correlated native tool
        # result (never an unconditional file read).
        if st["toolloop_verified"] and verified_pairs:
            _c, _m, _mk = verified_pairs[0]
            _i = _m["content"].find(_mk)
            text = _m["content"][_i:_i + len(_mk)]
            st["final_text_source"] = "correlated_tool_result"
        else:
            text = "AGENT_CHAT_TOOL_UNVERIFIED"
            st["final_text_source"] = "unverified_static"
        with LOCK:
            save(STATE, st)
        self._text(req, model, stream,
                   dict(scenario, final_text=text, usage=[40, 10]))

    def _compact_main(self, req, model, stream, n, scenario):
        if n == 1:
            p, c = scenario.get("first_usage", [1900, 100])
            self._text(req, model, stream,
                       dict(scenario, final_text=scenario.get("first_text", "STEP1-DONE"),
                            usage=[p, c]))
            return
        marker = scenario.get("summary_text", "")
        found = None
        for m in req.get("messages", []):
            if isinstance(m, dict):
                c2 = m.get("content")
                if isinstance(c2, str) and marker and marker in c2:
                    i = c2.find(marker)
                    found = c2[i:i + len(marker)]
                    break
        with LOCK:
            st = load(STATE, {})
            st["compact_verified"] = found is not None
            save(STATE, st)
        text = found if found is not None else "AGENT_CHAT_COMPACT_UNVERIFIED"
        self._text(req, model, stream,
                   dict(scenario, final_text=text, usage=[50, 10]))


def main():
    port = int(sys.argv[1])
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"listening 127.0.0.1:{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
