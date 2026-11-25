# agent-service-dep-graph

Pre-start dependency check for an agent's services: declare each service's
dependencies in a registry — API key present? disk space? model available?
wallet funded above a floor? — and verify them all **before** starting
anything. Fail fast with a named missing dep instead of discovering it from
a half-up stack.

It's the startup-time counterpart to a cron pre-flight check: one asks "can
this job run?", this one asks "can this *service* run?"

## Quick start

```bash
python3 service-dep-graph.py --list          # what services are declared?
python3 service-dep-graph.py inference-worker
python3 service-dep-graph.py --all           # verify everything, exit 1 if any service is unready
```

Exit code is `0` when every dep passes, `1` otherwise — wire it into your
start script, systemd unit, or cron wrapper and don't start the service on
a non-zero exit.

Sample output:

```
📋 Service: inference-worker
----------------------------------------
✅ API key (groq): GROQ_API_KEY
✅ API key (openrouter): OPENROUTER_API_KEY
✅ Disk space: 81234MB available
❌ Model llama-3.1-8b-instant: registry missing

🔴 Missing deps — DO NOT start inference-worker
```

## The registry

Services are declared in `services.json` (a generic example ships in this
repo; the same examples are the built-in fallback if no file is found).
Point `SERVICE_REGISTRY_FILE` at your own file to override the location.

```json
{
  "inference-worker": {
    "deps": [
      {"check": "api_key", "env": "GROQ_API_KEY", "provider": "groq"},
      {"check": "disk_space", "min_mb": 500},
      {"check": "model_available", "provider": "groq", "model": "llama-3.1-8b-instant"}
    ]
  },
  "chain-jobs": {
    "deps": [
      {"check": "api_key", "env": "ALCHEMY_API_KEY", "provider": "alchemy"},
      {"check": "wallet_balance", "min_eth": 0.001}
    ]
  }
}
```

## Check types

| Check | Passes when | Notes |
| --- | --- | --- |
| `api_key` | The named env var is set, non-placeholder, and longer than 10 chars | Presence/format only — pair with a liveness checker to know the key actually works |
| `disk_space` | Free space on `/` is at least `min_mb` | |
| `model_available` | The model appears in your model registry and is not listed as deprecated | Registry file: `MODEL_REGISTRY_FILE` (default `model-registry.json`; see `model-registry.example.json`) |
| `wallet_balance` | The watched wallet's ETH balance is at least `min_eth` | Wallet comes from `WATCH_WALLET`; RPC from `RPC_URL`, or an Alchemy URL built from `ALCHEMY_API_KEY` |
| `env_var` | The named env var is set and non-placeholder | The value is never printed — not even a prefix; the var may itself be a secret |

## Configuration

| Env var | Default | Purpose |
| --- | --- | --- |
| `SERVICE_REGISTRY_FILE` | `services.json` | Service registry location |
| `MODEL_REGISTRY_FILE` | `model-registry.json` | Model registry for `model_available` |
| `WATCH_WALLET` | — | Wallet address for `wallet_balance` (never hardcoded) |
| `RPC_URL` | — | JSON-RPC endpoint for `wallet_balance` |
| `ALCHEMY_API_KEY` | — | Fallback: builds a Base-mainnet Alchemy RPC URL |

## Limits — read this first

These are **presence and threshold probes, not deep health checks.** An
`api_key` pass means a plausible-looking value is set; it does not prove the
key is alive (that's a liveness checker's job). A `model_available` pass
means the model is in *your* registry file — if the registry is stale, the
check is stale. The point is catching the dumb, common failures — missing
env var, empty disk, empty wallet, deprecated model — in one named list
before startup, not certifying the stack healthy.

## License

MIT — see `LICENSE`.
