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

Events are standard-shaped: ``type`` + ``sequence_number`` + per-event
fields only, with no artificial top-level ``response_id``; the response id
appears only inside the ``response`` objects of ``response.created`` /
``response.completed``. If the pinned client consumes these events without
error, the client consumes standards-shaped SSE (the Gateway validator is
not relaxed by this change; the proof is client-side consumption).

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

Assistant-tool mode: turn one emits an assistant text message at output slot
0 plus a function_call at output slot 1; the continuation gates on the
correlated native tool result (same marker rule as toolloop) and records
what the SDK kept or dropped of the turn-1 assistant message (item shapes
plus an exact lead-text replay predicate; no raw text retained).

Visible-reasoning mode: turn one emits a reasoning item carrying a visible
summary plus a per-scenario ``encrypted_content`` state (absent / null /
empty string) and a function_call; the continuation records the replayed
``encrypted_content`` state, call/output linkage, and the final tool/text
outcome. These variants are observation probes only: they are NOT
encrypted-ownership passes and grant no opaque authority; the full-cipher
gate remains required for the encrypted ``reasoning_continuation`` case.

Compaction mode (228-b, fake-only): turn one emits a function_call carrying
synthetic overflow usage (labelled usage_is_synthetic_trigger) so the pinned
native client triggers its own CLIENT-SIDE compaction on loopback. The
summary request is recognized by the source-backed buildPrompt marker and
answered with a safe synthetic template-shaped summary (content is never
persisted); the continuation records the observed input-item order and
indices and gates the final sentinel on the source-backed literals
(compaction-part user text present, byte-exact issued summary, continue
text, zero function_call_output, tools present). This proves pinned-client
behavior only; it is not a Gateway/provider pass.

Auxiliary requests (no tools, no function_call_output) additionally record
sanitized structural facts (top-level fields, model, stream/store, field
presence, input form) into state so default-title behavior can be reported.

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


# 228-b compaction mode: source-backed literals from pinned OpenCode 1.19.3
# (core/src/session/compaction.ts:161 buildPrompt marker; session/compaction.ts:531
# autocontinue text; message-v2.ts:241 compaction-part user text).
COMPACTION_MARKER = "Here is the conversation so far:"
COMPACTION_USER_TEXT = "What did we do so far?"
CONTINUE_TEXT = ("Continue if you have next steps, or stop and ask for "
                 "clarification if you are unsure how to proceed.")
DEFAULT_COMPACTION_SUMMARY = (
    "## Objective\n"
    "- Verify the pinned OpenCode client-side compaction round-trip on an "
    "owned loopback fake.\n"
    "## Important Details\n"
    "- Synthetic overflow trigger; no real provider content is involved.\n"
    "## Work State\n"
    "### Completed\n"
    "- Compaction request received and summarized by the fake.\n"
    "### Active\n"
    "- Awaiting the continuation turn.\n"
    "## Next Move\n"
    "- Reply with the final sentinel and stop.\n"
    "## Relevant Files\n"
    "- probe.txt")


def _item_text(item):
    """Plain text of an input item (content str or text-bearing parts)."""
    if not isinstance(item, dict):
        return ""
    content = item.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content
                       if isinstance(p, dict)
                       and isinstance(p.get("text"), str))
    if isinstance(item.get("text"), str):
        return item["text"]
    return ""


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
    # Standard shape: type + sequence_number + per-event fields only; the
    # response id lives inside the created/completed `response` objects.
    return {"type": etype, "sequence_number": seq, **fields}


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
                item={"type": "message", "id": msg_id,
                      "status": "in_progress", "role": "assistant",
                      "content": []}),
            _ev(resp_id, seq0 + 1, "response.output_text.delta",
                item_id=msg_id, output_index=0, content_index=0,
                delta=text),
            _ev(resp_id, seq0 + 2, "response.output_item.done", output_index=0,
                item={"type": "message", "id": msg_id, "role": "assistant",
                      "status": "completed",
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
            if scenario.get("mode") == "compaction" \
                    and COMPACTION_MARKER in "\n".join(
                        _item_text(i) for i in items):
                # R2: the native client-side compaction summary request
                # (buildPrompt, core compaction.ts). Record its safe shape;
                # never persist its content.
                tools_val = req.get("tools")
                if tools_val is None:
                    tools_form = "absent"
                elif isinstance(tools_val, list) and not tools_val:
                    tools_form = "empty_list"
                elif isinstance(tools_val, dict) and not tools_val:
                    tools_form = "empty_dict"
                elif isinstance(tools_val, list):
                    tools_form = f"list_{len(tools_val)}"
                else:
                    tools_form = type(tools_val).__name__
                system_val = req.get("system")
                if system_val is None:
                    system_form = "absent"
                elif isinstance(system_val, str):
                    system_form = "string"
                elif isinstance(system_val, list) and not system_val:
                    system_form = "empty_list"
                elif isinstance(system_val, list):
                    system_form = f"list_{len(system_val)}"
                else:
                    system_form = type(system_val).__name__
                summary = scenario.get(
                    "summary_text", DEFAULT_COMPACTION_SUMMARY)
                with LOCK:
                    st = load(STATE, {})
                    st["aux_requests"] = st.get("aux_requests", 0) + 1
                    st["compaction_request_seen"] = True
                    st["compaction_request_facts"] = {
                        "top_level_fields": sorted(
                            k for k in req.keys()
                            if isinstance(k, str)),
                        "model": model,
                        "stream": stream,
                        "store": req.get("store"),
                        "tools_form": tools_form,
                        "system_form": system_form,
                        "input_form": (type(raw_input).__name__
                                       if raw_input is not None
                                       else "absent"),
                        "input_item_count": len(items),
                        "input_item_types": sorted(
                            str(i.get("type")) for i in items),
                        "input_item_roles": sorted({
                            str(i.get("role")) for i in items
                            if i.get("role") is not None}),
                        "max_output_tokens": req.get("max_output_tokens"),
                        "tool_choice_present": "tool_choice" in req,
                        "include_present": "include" in req,
                        "reasoning_present": "reasoning" in req,
                        "marker_present": True,
                    }
                    st["issued_summary"] = summary
                    save(STATE, st)
                self._emit_text(model, stream, summary,
                                scenario.get("summary_usage") or [300, 200])
                return
            input_form = (type(raw_input).__name__
                          if raw_input is not None else "absent")
            with LOCK:
                st = load(STATE, {})
                st["aux_requests"] = st.get("aux_requests", 0) + 1
                st.setdefault("aux_request_facts", []).append({
                    "top_level_fields": sorted(
                        k for k in req.keys() if isinstance(k, str)),
                    "model": model,
                    "stream": stream,
                    "store": req.get("store"),
                    "max_output_tokens_present": "max_output_tokens" in req,
                    "tool_choice_present": "tool_choice" in req,
                    "include_present": "include" in req,
                    "reasoning_present": "reasoning" in req,
                    "input_form": input_form,
                })
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
        elif mode == "assistant_tool":
            self._assistant_tool(req, model, stream, n, scenario, st, items)
        elif mode == "reasoning_visible":
            self._reasoning_visible(req, model, stream, n, scenario, st, items)
        elif mode == "compaction":
            self._compaction(req, model, stream, n, scenario, st, items)
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

    # -- compaction mode (228-b) ---------------------------------------------
    def _compaction(self, req, model, stream, n, scenario, st, items):
        with LOCK:
            st = load(STATE, {})
        if n == 1:
            # R1: tool call carrying synthetic overflow usage; the native
            # client halts the stream at step-finish (overflow detected)
            # and never executes the tool, so no function_call_output is
            # ever expected back.
            tool_name = scenario.get("tool_name", "read")
            arg_key = scenario.get("arg_key", "filePath")
            tool_file = scenario.get("tool_file", "probe.txt")
            call_id = "call_fake_" + uuid.uuid4().hex[:20]
            usage = list(scenario.get("overflow_usage") or [225000, 2000])
            st["compaction_r1_facts"] = {
                "call_id": call_id,
                "tool_name": tool_name,
                "usage_emitted": usage,
                "usage_is_synthetic_trigger": True,
            }
            with LOCK:
                save(STATE, st)
            resp_id = "resp_fake_" + uuid.uuid4().hex[:24]
            if stream:
                ev, _nxt, out_items = self._function_call_events(
                    resp_id, 1, call_id, tool_name, {arg_key: tool_file})
                events = [self._created(resp_id, model), *ev,
                          self._completed(resp_id, _nxt, model, usage,
                                          out_items)]
                self._stream(events)
            else:
                _e, _n, out_items = self._function_call_events(
                    resp_id, 1, call_id, tool_name, {arg_key: tool_file})
                self._nonstream(model, usage, out_items)
            return
        # n >= 2: continuation after the compaction round-trip. Source
        # (message-v2.ts:536-590 filterCompacted) orders the model input
        # [compaction-user, summary, ...retained tail..., continue-user];
        # record the actual shape and gate the source-backed literals.
        prompt = scenario.get("original_prompt")
        issued_summary = st.get("issued_summary")
        user_items = [i for i in items if i.get("role") == "user"]
        assistant_items = [i for i in items if i.get("role") == "assistant"]
        first_user_text = _item_text(user_items[0]) if user_items else None
        compaction_user_index = None
        for idx in range(len(items)):
            if items[idx].get("role") == "user" \
                    and _item_text(items[idx]) == COMPACTION_USER_TEXT:
                compaction_user_index = idx
                break
        summary_index = None
        for idx, i in enumerate(items):
            if i.get("role") == "assistant" \
                    and _item_text(i) == issued_summary:
                summary_index = idx
                break
        continue_index = None
        for idx in range(len(items) - 1, -1, -1):
            if items[idx].get("role") == "user" \
                    and _item_text(items[idx]) == CONTINUE_TEXT:
                continue_index = idx
                break
        fc_outputs = sum(1 for i in items
                         if i.get("type") == "function_call_output")
        tools = req.get("tools")
        facts = {
            "request_index": n,
            "stream": stream,
            "store": req.get("store"),
            "tools_count": (len(tools) if isinstance(tools, list) else None),
            "input_item_count": len(items),
            "input_item_types": [str(i.get("type")) for i in items],
            "input_item_roles": [
                (str(i.get("role")) if i.get("role") is not None else None)
                for i in items],
            "user_item_count": len(user_items),
            "assistant_item_count": len(assistant_items),
            "fc_outputs_total": fc_outputs,
            "compaction_user_item_index": compaction_user_index,
            "summary_item_index_byte_exact": summary_index,
            "continue_user_item_index": continue_index,
            "order_compaction_user_before_summary": (
                compaction_user_index is not None
                and summary_index is not None
                and compaction_user_index < summary_index),
            "order_summary_before_continue": (
                summary_index is not None
                and continue_index is not None
                and summary_index < continue_index),
            "first_user_text_equals_original_prompt": (
                prompt is not None and first_user_text == prompt),
            "first_user_text_length": (
                len(first_user_text) if first_user_text is not None
                else None),
        }
        verified = (
            compaction_user_index is not None
            and summary_index is not None
            and continue_index is not None
            and facts["order_compaction_user_before_summary"] is True
            and facts["order_summary_before_continue"] is True
            and fc_outputs == 0
            and isinstance(tools, list) and len(tools) >= 1
            and st.get("compaction_request_seen") is True)
        st["compaction_continuation_facts"] = facts
        st["compaction_verified"] = verified
        if verified:
            text = scenario.get("final_text", "AGENT_RESP_COMPACTION_OK")
            st["final_text_source"] = "static_sentinel"
        else:
            text = "AGENT_RESP_COMPACTION_UNVERIFIED"
            st["final_text_source"] = "unverified_static"
        with LOCK:
            save(STATE, st)
        self._emit_text(model, stream, text,
                        scenario.get("final_usage") or [40, 10])

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

    def _reasoning_events_visible(self, resp_id, seq0, cipher_state):
        rs_id = "rs_fake_" + uuid.uuid4().hex[:20]
        summary_text = "synthetic reasoning summary"
        added_item = {"type": "reasoning", "id": rs_id}
        if cipher_state == "null":
            added_item["encrypted_content"] = None
        elif cipher_state == "empty_string":
            added_item["encrypted_content"] = ""
        done_item = {**added_item,
                     "summary": [{"type": "summary_text",
                                  "text": summary_text}]}
        out = [
            _ev(resp_id, seq0, "response.output_item.added", output_index=0,
                item=added_item),
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
                item=done_item),
        ]
        return out, seq0 + 5, [done_item]

    def _assistant_tool(self, req, model, stream, n, scenario, st, items):
        with LOCK:
            st = load(STATE, {})
        if n == 1:
            tool_name = scenario.get("tool_name", "read")
            arg_key = scenario.get("arg_key", "filePath")
            tool_file = scenario.get("tool_file", "probe.txt")
            lead_text = scenario.get("lead_text", "AGENT_RESP_ASSISTANT_LEAD")
            call_id = "call_fake_" + uuid.uuid4().hex[:20]
            st["issued"] = {"call_id": call_id, "path": tool_file,
                            "tool_name": tool_name, "arg_key": arg_key,
                            "lead_text": lead_text}
            with LOCK:
                save(STATE, st)
            resp_id = "resp_fake_" + uuid.uuid4().hex[:24]
            if stream:
                m_events, nxt, m_items = self._message_events(
                    resp_id, 1, lead_text)
                f_events, nxt2, f_items = self._function_call_events(
                    resp_id, nxt, call_id, tool_name, {arg_key: tool_file},
                    output_index=1)
                events = [self._created(resp_id, model), *m_events,
                          *f_events,
                          self._completed(resp_id, nxt2, model,
                                          scenario.get("tool_usage") or [30, 6],
                                          m_items + f_items)]
                self._stream(events)
            else:
                _m, _n, m_items = self._message_events(resp_id, 1, lead_text)
                _f, _n2, f_items = self._function_call_events(
                    resp_id, 4, call_id, tool_name, {arg_key: tool_file},
                    output_index=1)
                self._nonstream(model, scenario.get("tool_usage") or [30, 6],
                                m_items + f_items)
            return
        # Continuation: gate on the correlated native tool result and record
        # what the SDK kept or dropped of the turn-1 assistant message
        # (item shapes plus an exact lead-text replay predicate only).
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
        content = None
        if matched is not None and marker is not None \
                and isinstance(matched.get("output"), str):
            content = matched["output"]
            facts["content_byte_length"] = len(content.encode("utf-8"))
            facts["marker_occurrences"] = content.count(marker)
            facts["marker_present"] = facts["marker_occurrences"] >= 1
            facts["content_equals_marker"] = content == marker
        lead_text = issued.get("lead_text")
        assistant_items = [i for i in items
                           if i.get("role") == "assistant"
                           and "content" in i]
        replayed = False
        for i in assistant_items:
            c = i.get("content")
            if isinstance(c, str):
                replayed = replayed or (lead_text is not None
                                        and c == lead_text)
            elif isinstance(c, list):
                replayed = replayed or any(
                    isinstance(p, dict) and p.get("text") == lead_text
                    for p in c)
        at_facts = dict(facts)
        at_facts.update({
            "assistant_message_items": [_item_shape(i)
                                        for i in assistant_items],
            "assistant_message_count": len(assistant_items),
            "lead_text_replayed_in_input": replayed,
        })
        st["assistant_tool_facts"] = at_facts
        st["assistant_verified"] = (facts["correlated_outputs"] >= 1
                                    and facts["marker_present"])
        if st["assistant_verified"]:
            _i = content.find(marker)
            text = content[_i:_i + len(marker)]
            st["final_text_source"] = "correlated_tool_result"
        else:
            text = "AGENT_RESP_ASSISTANT_UNVERIFIED"
            st["final_text_source"] = "unverified_static"
        with LOCK:
            save(STATE, st)
        self._emit_text(model, stream, text, [40, 10])

    def _reasoning_visible(self, req, model, stream, n, scenario, st, items):
        with LOCK:
            st = load(STATE, {})
        if n == 1:
            tool_name = scenario.get("tool_name", "read")
            arg_key = scenario.get("arg_key", "filePath")
            tool_file = scenario.get("tool_file", "probe.txt")
            cipher_state = scenario.get("cipher_state", "absent")
            emit_state = {"empty": "empty_string"}.get(
                cipher_state, cipher_state)
            call_id = "call_fake_" + uuid.uuid4().hex[:20]
            resp_id = "resp_fake_" + uuid.uuid4().hex[:24]
            created = self._created(resp_id, model)
            r_events, nxt, r_items = self._reasoning_events_visible(
                resp_id, 1, emit_state)
            f_events, nxt2, f_items = self._function_call_events(
                resp_id, nxt, call_id, tool_name, {arg_key: tool_file},
                output_index=1)
            st["issued"] = {"call_id": call_id, "path": tool_file,
                            "tool_name": tool_name,
                            "cipher_state": cipher_state}
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
        # Continuation: observation probe of the replayed encrypted_content
        # state; NOT an encrypted-ownership pass (the full-cipher gate stays
        # on the reasoning_continuation case).
        issued = st.get("issued", {})
        per_item = [_item_shape(i) for i in items]
        reasoning_items = [f for f in per_item if f["type"] == "reasoning"]
        replayed_state = (reasoning_items[0].get("encrypted_content_state")
                          if reasoning_items else None)
        expected = {"absent": "absent", "null": "null",
                    "empty": "empty_string"}.get(issued.get("cipher_state"))
        call_id = issued.get("call_id")
        try:
            with open(MARKER_FILE, "rb") as f:
                marker = f.read().decode("utf-8")
        except Exception:
            marker = None
        facts = {"fc_outputs_total": 0, "correlated_outputs": 0,
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
        content = None
        if matched is not None and marker is not None \
                and isinstance(matched.get("output"), str):
            content = matched["output"]
            facts["content_byte_length"] = len(content.encode("utf-8"))
            facts["marker_occurrences"] = content.count(marker)
            facts["marker_present"] = facts["marker_occurrences"] >= 1
            facts["content_equals_marker"] = content == marker
        rv_facts = {
            "cipher_state_issued": issued.get("cipher_state"),
            "cipher_state_replayed": replayed_state,
            "cipher_state_matches_issued":
                expected is not None and replayed_state == expected,
            "input_item_count": len(items),
            "input_item_types": [f["type"] for f in per_item],
            "reasoning_items": reasoning_items,
            "function_call_items": [f for f in per_item
                                    if f["type"] == "function_call"],
            "function_call_output_items": [f for f in per_item
                                           if f["type"] == "function_call_output"],
            "message_items": [f for f in per_item
                              if f.get("role") is not None
                              and f["type"] in (None, "message")],
            "issued_call_id_correlated": (
                call_id is not None
                and any(i.get("type") == "function_call"
                        and i.get("call_id") == call_id
                        and i.get("name") == issued.get("tool_name")
                        for i in items)
                and any(i.get("type") == "function_call_output"
                        and i.get("call_id") == call_id
                        for i in items)),
            "marker_gate": facts,
        }
        st["reasoning_visible"] = rv_facts
        st["reasoning_visible_verified"] = (facts["correlated_outputs"] >= 1
                                            and facts["marker_present"])
        if st["reasoning_visible_verified"]:
            _i = content.find(marker)
            text = content[_i:_i + len(marker)]
            st["final_text_source"] = "correlated_tool_result"
        else:
            text = "AGENT_RESP_REASONING_VISIBLE_UNVERIFIED"
            st["final_text_source"] = "unverified_static"
        with LOCK:
            save(STATE, st)
        self._emit_text(model, stream, text, [40, 10])


def _cipher_state(i):
    if "encrypted_content" not in i:
        return "absent"
    v = i["encrypted_content"]
    if v is None:
        return "null"
    if isinstance(v, str):
        return "empty_string" if v == "" else "nonempty_string"
    return "other_typed"


def _item_shape(i, issued_enc=None):
    f = {
        "type": i.get("type"),
        "keys_sorted": sorted(k for k in i.keys() if isinstance(k, str)),
        "id_present": i.get("id") is not None,
        "status_present": i.get("status") is not None,
    }
    t = i.get("type")
    if t == "message" or (t is None and i.get("role") is not None
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
        state = _cipher_state(i)
        f["encrypted_content_state"] = state
        if state == "nonempty_string":
            enc = i["encrypted_content"]
            f["encrypted_sha256_8"] = hashlib.sha256(
                enc.encode()).hexdigest()[:8]
            f["encrypted_byte_length"] = len(enc)
            f["full_byte_equals_issued"] = (
                issued_enc is not None and enc == issued_enc)
        f["summary_present"] = i.get("summary") is not None
    return f


def main():
    port = int(sys.argv[1])
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"listening 127.0.0.1:{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
