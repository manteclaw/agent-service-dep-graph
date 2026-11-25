#!/usr/bin/env python3
"""
Service Dependency Graph — Verify all deps before starting services.

Usage:
    python3 service-dep-graph.py <service_name>   # verify one service
    python3 service-dep-graph.py --all            # verify every service
    python3 service-dep-graph.py --list           # list known services

The service registry lives in services.json (see the shipped example).
Point SERVICE_REGISTRY_FILE at your own registry file to override it.
"""
import json, os, subprocess, sys

# Generic example registry — used only when no services.json is found.
# Replace with your own services; this is a starter shape, not a real stack.
EXAMPLE_REGISTRY = {
    "inference-worker": {
        "deps": [
            {"check": "api_key", "env": "GROQ_API_KEY", "provider": "groq"},
            {"check": "api_key", "env": "OPENROUTER_API_KEY", "provider": "openrouter"},
            {"check": "disk_space", "min_mb": 500},
            {"check": "model_available", "provider": "groq", "model": "llama-3.1-8b-instant"},
        ]
    },
    "chain-jobs": {
        "deps": [
            {"check": "api_key", "env": "ALCHEMY_API_KEY", "provider": "alchemy"},
            {"check": "wallet_balance", "min_eth": 0.001},
        ]
    },
    "example-agent": {
        "deps": [
            {"check": "api_key", "env": "EXAMPLE_API_KEY", "provider": "example"},
            {"check": "env_var", "env": "EXAMPLE_AGENT_ID"},
        ]
    }
}

def load_registry():
    path = os.environ.get("SERVICE_REGISTRY_FILE", "services.json")
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict) and data:
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return EXAMPLE_REGISTRY

REGISTRY = load_registry()

def check_api_key(env_var):
    val = os.environ.get(env_var, "")
    return bool(val and not val.startswith("${") and len(val) > 10)

def check_disk(min_mb):
    r = subprocess.run("df -m / | tail -1 | awk '{print $4}'", shell=True, capture_output=True, text=True)
    try:
        avail = int(r.stdout.strip())
        return avail >= min_mb, f"{avail}MB available"
    except ValueError:
        return False, "check failed"

def check_model_available(provider, model):
    registry_path = os.environ.get("MODEL_REGISTRY_FILE", "model-registry.json")
    try:
        with open(registry_path) as f:
            reg = json.load(f)
        provider_info = reg["providers"].get(provider, {})
        models = provider_info.get("models", {})
        deprecated = provider_info.get("deprecated", [])
        if model in deprecated:
            return False, f"Model {model} is deprecated"
        for cat, m in models.items():
            if m == model:
                return True, f"Model {model} found in {cat}"
        return False, f"Model {model} not in registry"
    except (FileNotFoundError, json.JSONDecodeError):
        return False, "registry missing"

def check_wallet_balance(min_eth):
    # The wallet to watch comes from the environment — never hardcoded.
    wallet = os.environ.get("WATCH_WALLET", "")
    if not wallet:
        return False, "WATCH_WALLET not set"
    rpc_url = os.environ.get("RPC_URL", "")
    if not rpc_url:
        alchemy = os.environ.get("ALCHEMY_API_KEY", "")
        if not alchemy:
            return False, "no RPC configured (set RPC_URL or ALCHEMY_API_KEY)"
        rpc_url = f"https://base-mainnet.g.alchemy.com/v2/{alchemy}"
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getBalance", "params": [wallet, "latest"]})
    r = subprocess.run(
        ["curl", "-s", "-H", "Content-Type: application/json", "-d", payload, rpc_url],
        capture_output=True, text=True
    )
    try:
        data = json.loads(r.stdout)
        balance_wei = int(data["result"], 16)
        balance_eth = balance_wei / 1e18
        return balance_eth >= min_eth, f"{balance_eth:.6f} ETH"
    except (json.JSONDecodeError, KeyError, ValueError):
        return False, "balance check failed"

def check_env_var(env_var):
    # Presence only — the value is never printed, not even a prefix: the var
    # being checked may itself be a secret.
    val = os.environ.get(env_var, "")
    ok = bool(val and not val.startswith("${"))
    return ok, "set" if ok else "not set"

def verify_service(service_name):
    config = REGISTRY.get(service_name)
    if not config:
        print(f"Unknown service: {service_name}")
        print(f"Known: {', '.join(REGISTRY.keys())}")
        return 1

    results = []
    all_pass = True

    for dep in config["deps"]:
        check_type = dep["check"]
        if check_type == "api_key":
            ok = check_api_key(dep["env"])
            results.append({"dep": f"API key ({dep['provider']})", "ok": ok, "detail": dep["env"]})
        elif check_type == "disk_space":
            ok, detail = check_disk(dep["min_mb"])
            results.append({"dep": "Disk space", "ok": ok, "detail": detail})
        elif check_type == "model_available":
            ok, detail = check_model_available(dep["provider"], dep["model"])
            results.append({"dep": f"Model {dep['model']}", "ok": ok, "detail": detail})
        elif check_type == "wallet_balance":
            ok, detail = check_wallet_balance(dep["min_eth"])
            results.append({"dep": "Wallet balance", "ok": ok, "detail": detail})
        elif check_type == "env_var":
            ok, detail = check_env_var(dep["env"])
            results.append({"dep": f"Env {dep['env']}", "ok": ok, "detail": detail})
        else:
            results.append({"dep": check_type, "ok": False, "detail": "unknown check type"})

        if not results[-1]["ok"]:
            all_pass = False

    print(f"\n📋 Service: {service_name}")
    print("-" * 40)
    for r in results:
        emoji = "✅" if r["ok"] else "❌"
        print(f"{emoji} {r['dep']}: {r['detail']}")

    if all_pass:
        print(f"\n🟢 All deps satisfied — safe to start {service_name}")
        return 0
    else:
        print(f"\n🔴 Missing deps — DO NOT start {service_name}")
        return 1

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("Usage: python3 service-dep-graph.py <service_name> | --all | --list")
        print(f"Services: {', '.join(REGISTRY.keys())}")
        return 1
    if args[0] == "--list":
        for name in REGISTRY:
            print(name)
        return 0
    if args[0] == "--all":
        rc = 0
        for name in REGISTRY:
            if verify_service(name) != 0:
                rc = 1
        return rc
    return verify_service(args[0])

if __name__ == "__main__":
    sys.exit(main())
