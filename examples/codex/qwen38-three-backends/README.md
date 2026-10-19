# Three Qwen Codex routes: illustrative configuration

This example shows how one Codex 0.162.1 client can select three independently
configured Qwen 3.8 27B backends through a SLAIF gateway. The model names and
context limits below come from one operator deployment. They are **examples**,
not defaults or general hardware/model capabilities. No backend address,
credential, institution, or private host name is included.

| Example route | Public model selected by Codex | Backend model ID | Advertised context | Local compaction threshold |
| --- | --- | --- | ---: | ---: |
| V100 | `qwen3.8-27b-V100` | `qwen38-27b` | 245760 | 208125 |
| A100 | `qwen3.8-27b` | `qwen3.8-27b` | 262144 | 221184 |
| RTX 3090 | `qwen3.8-27b-rtx3090` | `qwen3.8-27b` | 100000 | 80000 |

The three corresponding Codex profiles are opt-in, exact server-owned registry
entries. To use one, an operator must configure a matching Responses route
through the audited route service: public and upstream model IDs, context and
output limits, the appropriate backend adapter, the Codex profile declaration,
and the required Codex capability gates must agree. Image input also requires
`responses.image_input=true` on the route and an `image_input` grant on the
gateway key. Configure the provider's backend credential and complete pricing
separately, including explicit zero pricing when the backend is free. Then
check `slaif-gateway codex inspect --json` for READY before offering downloads.
Merely installing this example or merging its code does not create those
records or grant access. See the [operator runbook](../../../docs/runbooks/codex-qwen38.md)
for the exact route, pricing, and key prerequisites.

Copy [config.toml](config.toml) and [qwen38-models.json](qwen38-models.json)
into the same Codex home directory. In the TOML, replace
`https://gateway.example.org/v1` with your gateway's HTTPS `/v1` URL and replace
`PASTE_YOUR_GATEWAY_BEARER_KEY_HERE` with a gateway-issued key authorized for
the desired routes. Keep the filled TOML private and out of source control.
The JSON catalog contains public model names and per-model context/compaction
values; it contains no key. The default model is the example A100 route.
Select another with `codex -m qwen3.8-27b-V100` or
`codex -m qwen3.8-27b-rtx3090`, or use `-m` with `codex exec`.

For a different deployment, use its actual public and backend model IDs and
verified context/modalities. Changing the client catalog does not change the
gateway's immutable profile definitions; a new server profile and matching
route declaration require a reviewed code change. A short text, image, or tool
smoke test does not establish full-context inference or compaction support.
These example profiles retain `live_qualification=false`.
