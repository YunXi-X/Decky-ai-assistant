#!/usr/bin/env python3
import argparse
import getpass
import json
import shlex
import subprocess
from dataclasses import dataclass


SETTINGS_PATH = "$HOME/homebrew/settings/AI Chat/config.json"


@dataclass
class Preset:
    provider: str
    endpoint: str
    model: str


PRESETS = {
    "deepseek": Preset(
        provider="openai",
        endpoint="https://api.deepseek.com",
        model="deepseek-v4-flash",
    ),
    "deepseek-pro": Preset(
        provider="openai",
        endpoint="https://api.deepseek.com",
        model="deepseek-v4-pro",
    ),
    "kimi": Preset(
        provider="openai",
        endpoint="https://api.moonshot.cn/v1",
        model="kimi-k2.6",
    ),
    "kimi-code": Preset(
        provider="openai",
        endpoint="https://api.moonshot.cn/v1",
        model="kimi-k2.7-code",
    ),
    "custom": Preset(
        provider="openai",
        endpoint="",
        model="",
    ),
}


def prompt(default: str, label: str) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def build_config(args: argparse.Namespace) -> dict:
    preset = PRESETS[args.preset]
    api_key = args.api_key or getpass.getpass("API key: ").strip()
    if not api_key:
        raise SystemExit("API key cannot be empty.")

    endpoint = args.endpoint or preset.endpoint
    model = args.model or preset.model
    if args.preset == "custom":
        endpoint = prompt(endpoint, "Endpoint / base URL")
        model = prompt(model, "Model")

    return {
        "provider": preset.provider,
        "endpoint": endpoint,
        "model": model,
        "api_key": api_key,
        "system_prompt": args.system_prompt,
        "temperature": args.temperature,
        "max_history": args.max_history,
        "ragflow_chat_id": "",
        "ragflow_session_id": "",
    }


def upload_config(target: str, config: dict, restart: bool) -> None:
    payload = json.dumps(config, ensure_ascii=True, indent=2)
    remote_path = SETTINGS_PATH
    remote_dir = remote_path.rsplit("/", 1)[0]
    command = (
        f"mkdir -p {shlex.quote(remote_dir)} && "
        f"umask 077 && "
        f"cat > {shlex.quote(remote_path)}"
    )
    subprocess.run(["ssh", target, command], input=payload, text=True, check=True)

    if restart:
        subprocess.run(
            ["ssh", target, "sudo systemctl restart plugin_loader"],
            check=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Configure Decky AI Chat on a Steam Deck over SSH.",
    )
    parser.add_argument("target", help="SSH target, for example deck@192.168.1.23")
    parser.add_argument(
        "--preset",
        choices=sorted(PRESETS.keys()),
        default="deepseek",
        help="Provider preset to configure.",
    )
    parser.add_argument("--endpoint", help="Override endpoint/base URL.")
    parser.add_argument("--model", help="Override model.")
    parser.add_argument(
        "--api-key",
        help="API key. Omit this to enter it securely without shell history.",
    )
    parser.add_argument(
        "--system-prompt",
        default="You are a concise, helpful assistant running inside Steam Deck game mode.",
    )
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-history", type=int, default=16)
    parser.add_argument(
        "--no-restart",
        action="store_true",
        help="Do not restart Decky plugin_loader after writing config.",
    )
    args = parser.parse_args()

    config = build_config(args)
    upload_config(args.target, config, restart=not args.no_restart)
    print(
        f"Configured {args.preset} on {args.target}: "
        f"{config['endpoint']} / {config['model']}"
    )


if __name__ == "__main__":
    main()
