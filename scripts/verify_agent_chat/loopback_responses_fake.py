"""Task-owned loopback fake OpenAI Responses server (shared harness, 228-a).

Stdlib only. Binds to 127.0.0.1 on a caller-chosen port. Scenario/state are
re-read per request so a single server can serve a sequence of probes.

Serves:
  GET  /v1/models
  POST /v1/responses   (native SSE event shapes consumed by @ai-sdk/openai
                        3.x: response.created, output_item.added/done,
                        output_text.delta, reasoning_summary_part.added,
                        reasoning_summary_text.delta,
                        reasoning_summary_part.done, response.completed)

Privacy: the raw request journal is written only into the 0700 run directory
at 0600 and is ephemeral; verifiers must commit only sanitized structural
facts. Synthetic credentials only; the fake never contacts any provider.

Classification rule: a request without a non-empty ``tools`` array and
without a ``function_call_output`` input item is auxiliary (e.g. title
generation) in every scenario mode and never consumes the main turn counter.

Tool-loop gating: continuation success requires a ``function_call_output``
input item whose ``call_id`` equals a server-issued call id AND whose string
``output`` carries the run's unpredictable marker. The gated response echoes
the marker extracted from that correlated native tool result (never an
unconditional file read).

Reasoning mode: turn one emits a reasoning item at output slot 0 (synthetic
base64 encrypted_content) plus a function_call at output slot 1; the
continuation records per-item replay facts with FULL-BYTE equality against
the issued encrypted_content and exact call_id/tool_name call/output
linkage. The verifier gates the final sentinel on those facts; presence,
a short hash, or SDK tolerance alone is not correct producer proof.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.umask(0o077)

RUN = os.environ["AGENT_RESP_FAKE_RUN"]
WORKSPACE = os.environ.get("AGENT_RESP_FAKE_WORKSPACE", os.path.join(RUN, "workspace"))
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
                "token_sha256_8": hashlib.sha256(parts[1].encode()).hexdigest()[:8]
                if len(parts) == 2 else None,
            }
        elif lk in ("cookie", "proxy-authorization"):
            out[k] = {"redacted": True}
        else:
            out[k] = v
    return out


def sse(payload):
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


def _ev(resp_id, seq, etype, **fields):
    return {"type": etype, "sequence_number": seq, "response_id": resp_id, **fields}


class Handler(BaseHTTPRequestHandler):
    server_version = "SLAIFAgentRespFake/1"

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

    # -- event builders (shapes per @ai-sdk/openai 3.x consumer) ------------

    def _created(self, resp_id, model):
        return _ev(resp_id, 0, "response.created",
                   response={"id": resp_id, "object": "response",
                             "status": "in_progress",
                             "created_at": int(time.time()),
                             "model": model})

    def _message_events(self, resp_id, seq0, text):
        msg_id = "msg_fake_" + uuid.uuid4().hex[:20]
        out = [
            _ev(resp_id, seq0, "response.output_item.added", output_index=0,
                item={"type": "message", "id": msg_id}),
            _ev(resp_id, seq0 + 1, "response.output_text.delta",
                item_id=msg_id, output_index=0, content_index=0,
                delta=text),
            _ev(resp_id, seq0 + 2, "response.output_item.done", output_index=0,
                item={"type": "message", "id": msg_id, "role": "assistant",
                      "content": [{"type": "output_text", "text": text}]}),
        ]
        return out, seq0 + 3, [
            {"type": "message", "id": msg_id, "role": "assistant",
             "content": [{"type": "output_text", "text": text}]}]

    def _function_call_events(self, resp_id, seq0, call_id, name, args_obj,
                              output_index=0):
        fc_id = "fc_fake_" + uuid.uuid4().hex[:20]
        item = {"type": "function_call", "id": fc_id, "call_id": call_id,
                "name": name, "arguments": json.dumps(args_obj)}
        out = [
            _ev(resp_id, seq0, "response.output_item.added",
                output_index=output_index,
                item=item),
            _ev(resp_id, seq0 + 1, "response.output_item.done",
                output_index=output_index,
                item={**item, "status": "completed"}),
        ]
        return out, seq0 + 2, [{**item, "status": "completed"}]

    def _reasoning_events(self, resp_id, seq0):
        rs_id = "rs_fake_" + uuid.uuid4().hex[:20]
        enc = base64.b64encode(os.urandom(48)).decode()
        summary_text = "synthetic reasoning summary"
        out = [
            _ev(resp_id, seq0, "response.output_item.added", output_index=0,
                item={"type": "reasoning", "id": rs_id,
                      "encrypted_content": enc}),
            _ev(resp_id, seq0 + 1, "response.reasoning_summary_part.added",
                item_id=rs_id, output_index=0, summary_index=0,
                part={"type": "summary_text", "text": ""}),
            _ev(resp_id, seq0 + 2, "response.reasoning_summary_text.delta",
                item_id=rs_id, output_index=0, summary_index=0,
                delta=summary_text),
            _ev(resp_id, seq0 + 3, "response.reasoning_summary_part.done",
                item_id=rs_id, output_index=0, summary_index=0,
                part={"type": "summary_text", "text": summary_text}),
            _ev(resp_id, seq0 + 4, "response.output_item.done", output_index=0,
                item={"type": "reasoning", "id": rs_id,
                      "encrypted_content": enc,
                      "summary": [{"type": "summary_text",
                                   "text": summary_text}]}),
        ]
        return out, seq0 + 5, enc, [
            {"type": "reasoning", "id": rs_id, "encrypted_content": enc}]

    def _completed(self, resp_id, seq, model, usage, output_items=()):
        return _ev(resp_id, seq, "response.completed",
                   response={"id": resp_id, "object": "response",
                             "status": "completed",
                             "created_at": int(time.time()),
                             "model": model,
                             "output": list(output_items),
                             "usage": {"input_tokens": usage[0],
                                       "output_tokens": usage[1],
                                       "total_tokens": usage[0] + usage[1]}})

    def _stream(self, events):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for e in events:
            self.wfile.write(sse(e))
            self.wfile.flush()
        self.wfile.flush()

    def _nonstream(self, model, usage, output_items):
        payload = {
            "id": "resp_fake_" + uuid.uuid4().hex[:24],
            "object": "response",
            "status": "completed",
            "created_at": int(time.time()),
            "model": model,
            "output": list(output_items),
            "usage": {"input_tokens": usage[0], "output_tokens": usage[1],
                      "total_tokens": usage[0] + usage[1]},
        }
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _emit_text(self, model, stream, text, usage):
        resp_id = "resp_fake_" + uuid.uuid4().hex[:24]
        if stream:
            ev, _next, items = self._message_events(resp_id, 1, text)
            events = [self._created(resp_id, model), *ev,
                      self._completed(resp_id, _next, model, usage, items)]
            self._stream(events)
        else:
            _e, _n, items = self._message_events(resp_id, 1, text)
            self._nonstream(model, usage, items)

    # -- routes --------------------------------------------------------------

    def do_GET(self):
        if self.path == "/v1/models":
            self._journal("GET", self.path, dict(self.headers), b"")
            payload = {"object": "list", "data": [
                {"id": "agent-responses-fake-model", "object": "model",
                 "created": 1700000000, "owned_by": "agent-responses-loopback"}
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
        if self.path != "/v1/responses":
            self.send_error(404)
            return
        try:
            req = json.loads(body.decode("utf-8"))
        except Exception:
            self.send_error(400, "invalid json")
            return
        scenario = load(SCENARIO, {"mode": "text"})
        if scenario.get("stall"):
            time.sleep(3600)
            return
        if scenario.get("error_status"):
            status = int(scenario["error_status"])
            payload = json.dumps({"error": {
                "message": scenario.get("error_message",
                                        "synthetic upstream failure"),
                "type": scenario.get("error_type", "server_error"),
                "code": scenario.get("error_code"),
            }}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        model = req.get("model")
        stream = bool(req.get("stream"))
        raw_input = req.get("input")
        items = ([i for i in raw_input if isinstance(i, dict)]
                 if isinstance(raw_input, list) else [])
        has_tools = isinstance(req.get("tools"), list) and req.get("tools")
        has_fc_output = any(i.get("type") == "function_call_output"
                            for i in items)
        if not (has_tools or has_fc_output):
            with LOCK:
                st = load(STATE, {})
                st["aux_requests"] = st.get("aux_requests", 0) + 1
                save(STATE, st)
            self._emit_text(model, stream,
                            scenario.get("aux_final_text", "ok"), [4, 2])
            return
        with LOCK:
            st = load(STATE, {})
            st["main_requests"] = st.get("main_requests", 0) + 1
            n = st["main_requests"]
            save(STATE, st)
        mode = scenario.get("mode", "text")
        if mode == "toolloop":
            self._toolloop(req, model, stream, n, scenario, st, items)
        elif mode == "reasoning_continuation":
            self._reasoning(req, model, stream, n, scenario, st, items)
        else:
            self._emit_text(model, stream,
                            scenario.get("final_text", "AGENT_RESP_TEXT_OK"),
                            scenario.get("usage") or [12, 8])

    # -- scenario modes ------------------------------------------------------

    def _toolloop(self, req, model, stream, n, scenario, st, items):
        with LOCK:
            st = load(STATE, {})
        tool_turn = scenario.get("tool_turn_at", 1)
        if n == tool_turn:
            tool_name = scenario.get("tool_name", "read")
            arg_key = scenario.get("arg_key", "filePath")
            tool_file = scenario.get("tool_file", "probe.txt")
            call_id = "call_fake_" + uuid.uuid4().hex[:20]
            st["issued"] = {"call_id": call_id, "path": tool_file,
                            "tool_name": tool_name, "arg_key": arg_key}
            with LOCK:
                save(STATE, st)
            resp_id = "resp_fake_" + uuid.uuid4().hex[:24]
            if stream:
                ev, _nxt, out_items = self._function_call_events(
                    resp_id, 1, call_id, tool_name, {arg_key: tool_file})
                events = [self._created(resp_id, model), *ev,
                          self._completed(resp_id, _nxt, model,
                                          scenario.get("tool_usage") or [30, 6],
                                          out_items)]
                self._stream(events)
            else:
                _e, _n, out_items = self._function_call_events(
                    resp_id, 1, call_id, tool_name, {arg_key: tool_file})
                self._nonstream(model, scenario.get("tool_usage") or [30, 6],
                                out_items)
            return
        # Continuation: gate on the actually correlated native tool result.
        issued = st.get("issued", {})
        call_id = issued.get("call_id")
        try:
            with open(MARKER_FILE, "rb") as f:
                marker = f.read().decode("utf-8")
        except Exception:
            marker = None
        facts = {"call_id_issued": call_id is not None,
                 "fc_outputs_total": 0, "correlated_outputs": 0,
                 "marker_present": False, "marker_occurrences": 0,
                 "content_equals_marker": False,
                 "content_byte_length": None, "marker_byte_length": None}
        fc_outputs = [i for i in items
                      if i.get("type") == "function_call_output"]
        facts["fc_outputs_total"] = len(fc_outputs)
        matched = None
        for i in fc_outputs:
            if i.get("call_id") == call_id:
                matched = i
                break
        if matched is not None:
            facts["correlated_outputs"] += 1
        if marker is not None:
            facts["marker_byte_length"] = len(marker.encode("utf-8"))
        if matched is not None and marker is not None \
                and isinstance(matched.get("output"), str):
            content = matched["output"]
            facts["content_byte_length"] = len(content.encode("utf-8"))
            facts["marker_occurrences"] = content.count(marker)
            facts["marker_present"] = facts["marker_occurrences"] >= 1
            facts["content_equals_marker"] = content == marker
        st["toolloop_facts"] = facts
        st["toolloop_verified"] = (facts["correlated_outputs"] >= 1
                                   and facts["marker_present"])
        if st["toolloop_verified"]:
            _i = content.find(marker)
            text = content[_i:_i + len(marker)]
            st["final_text_source"] = "correlated_tool_result"
        else:
            text = "AGENT_RESP_TOOL_UNVERIFIED"
            st["final_text_source"] = "unverified_static"
        with LOCK:
            save(STATE, st)
        self._emit_text(model, stream, text, [40, 10])

    def _reasoning(self, req, model, stream, n, scenario, st, items):
        with LOCK:
            st = load(STATE, {})
        if n == 1:
            tool_name = scenario.get("tool_name", "read")
            arg_key = scenario.get("arg_key", "filePath")
            tool_file = scenario.get("tool_file", "probe.txt")
            call_id = "call_fake_" + uuid.uuid4().hex[:20]
            resp_id = "resp_fake_" + uuid.uuid4().hex[:24]
            created = self._created(resp_id, model)
            r_events, nxt, enc, r_items = self._reasoning_events(resp_id, 1)
            f_events, nxt2, f_items = self._function_call_events(
                resp_id, nxt, call_id, tool_name, {arg_key: tool_file},
                output_index=1)
            st["issued"] = {"call_id": call_id, "path": tool_file,
                            "tool_name": tool_name,
                            "encrypted_sha256_8":
                                hashlib.sha256(enc.encode()).hexdigest()[:8],
                            "encrypted_byte_length": len(enc),
                            "encrypted_content_issued": enc}
            with LOCK:
                save(STATE, st)
            if stream:
                events = [created, *r_events, *f_events,
                          self._completed(resp_id, nxt2, model,
                                          scenario.get("first_usage") or [30, 6],
                                          r_items + f_items)]
                self._stream(events)
            else:
                self._nonstream(model, scenario.get("first_usage") or [30, 6],
                                r_items + f_items)
            return
        # Continuation: record per-item replay facts; the verifier gates the
        # sentinel on full-byte replay + exact issued call linkage.
        issued = st.get("issued", {})
        per_item = []
        for i in items:
            f = {
                "type": i.get("type"),
                "keys_sorted": sorted(k for k in i.keys() if isinstance(k, str)),
                "id_present": i.get("id") is not None,
                "status_present": i.get("status") is not None,
            }
            t = i.get("type")
            if t == "message" or (
                    t is None and i.get("role") is not None
                    and "content" in i):
                f["role"] = i.get("role")
                c = i.get("content")
                f["content_form"] = type(c).__name__
                if isinstance(c, list):
                    f["content_part_types"] = sorted(
                        {p.get("type") for p in c if isinstance(p, dict)})
            elif t == "function_call":
                f["call_id_present"] = i.get("call_id") is not None
                f["name"] = i.get("name")
                f["arguments_present"] = i.get("arguments") is not None
                f["arguments_type"] = type(i.get("arguments")).__name__
            elif t == "function_call_output":
                f["call_id_present"] = i.get("call_id") is not None
                f["output_present"] = i.get("output") is not None
                f["output_type"] = type(i.get("output")).__name__
            elif t == "reasoning":
                enc = i.get("encrypted_content")
                f["encrypted_content_present"] = enc is not None
                if enc is not None:
                    f["encrypted_sha256_8"] = hashlib.sha256(
                        str(enc).encode()).hexdigest()[:8]
                    f["encrypted_byte_length"] = len(str(enc))
                    issued_enc = issued.get("encrypted_content_issued")
                    f["full_byte_equals_issued"] = (
                        issued_enc is not None and str(enc) == str(issued_enc))
            per_item.append(f)
        rc_facts = {
            "input_item_count": len(items),
            "input_item_types": [f["type"] for f in per_item],
            "reasoning_items": [f for f in per_item
                                if f["type"] == "reasoning"],
            "function_call_items": [f for f in per_item
                                    if f["type"] == "function_call"],
            "function_call_output_items": [f for f in per_item
                                           if f["type"] == "function_call_output"],
            "message_items": [f for f in per_item
                              if f.get("role") is not None
                              and f["type"] in (None, "message")],
            "issued_call_id_correlated": (
                issued.get("call_id") is not None
                and any(i.get("type") == "function_call"
                        and i.get("call_id") == issued.get("call_id")
                        and i.get("name") == issued.get("tool_name")
                        for i in items)
                and any(i.get("type") == "function_call_output"
                        and i.get("call_id") == issued.get("call_id")
                        for i in items)),
        }
        st["reasoning_continuation"] = rc_facts
        with LOCK:
            save(STATE, st)
        self._emit_text(model, stream,
                        scenario.get("final_text", "AGENT_RESP_REASONING_OK"),
                        scenario.get("usage") or [12, 8])


def main():
    port = int(sys.argv[1])
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"listening 127.0.0.1:{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
