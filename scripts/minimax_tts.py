#!/usr/bin/env python3
"""Generate MiniMax T2A voiceover audio for organized video scripts."""

from __future__ import annotations

import argparse
import binascii
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_ENDPOINT = "https://api.minimaxi.com/v1/t2a_v2"
ENV_KEY = "MINIMAX_API_KEY"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_default_env_files(explicit_env_file: Path | None = None) -> None:
    if explicit_env_file:
        load_dotenv(explicit_env_file)
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a MiniMax T2A voiceover from plain text."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="Text to synthesize.")
    source.add_argument("--input", type=Path, help="UTF-8 text file to synthesize.")
    parser.add_argument("--output", type=Path, required=True, help="Output audio path.")
    parser.add_argument("--api-key", help="MiniMax API key. Defaults to MINIMAX_API_KEY.")
    parser.add_argument("--env-file", type=Path, help="Optional .env file containing MINIMAX_API_KEY.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="T2A endpoint URL.")
    parser.add_argument("--model", default="speech-2.8-hd", help="MiniMax speech model.")
    parser.add_argument("--voice-id", default="Arrogant_Miss", help="Voice ID.")
    parser.add_argument("--speed", type=float, default=1.0, help="Speed, range [0.5, 2].")
    parser.add_argument("--vol", type=float, default=1.0, help="Volume, range (0, 10].")
    parser.add_argument("--pitch", type=int, default=0, help="Pitch, range [-12, 12].")
    parser.add_argument("--emotion", help="Optional voice emotion.")
    parser.add_argument("--sample-rate", type=int, default=32000, help="Audio sample rate.")
    parser.add_argument("--bitrate", type=int, default=128000, help="MP3 bitrate.")
    parser.add_argument("--format", default="mp3", help="Audio format.")
    parser.add_argument("--channel", type=int, default=1, help="Audio channel count.")
    parser.add_argument("--language-boost", default="Chinese", help="Language boost value.")
    parser.add_argument("--url-output", action="store_true", help="Ask API to return a URL.")
    parser.add_argument("--dry-run", action="store_true", help="Print request JSON only.")
    return parser.parse_args()


def read_text(args: argparse.Namespace) -> str:
    if args.text is not None:
        return args.text
    return args.input.read_text(encoding="utf-8")


def validate_args(args: argparse.Namespace, text: str) -> None:
    if not text.strip():
        raise SystemExit("Input text is empty.")
    if len(text) >= 10000:
        raise SystemExit("MiniMax T2A text must be shorter than 10000 characters.")
    if not 0.5 <= args.speed <= 2:
        raise SystemExit("--speed must be in [0.5, 2].")
    if not 0 < args.vol <= 10:
        raise SystemExit("--vol must be in (0, 10].")
    if not -12 <= args.pitch <= 12:
        raise SystemExit("--pitch must be in [-12, 12].")


def build_payload(args: argparse.Namespace, text: str) -> dict:
    voice_setting = {
        "voice_id": args.voice_id,
        "speed": args.speed,
        "vol": args.vol,
        "pitch": args.pitch,
    }
    if args.emotion:
        voice_setting["emotion"] = args.emotion

    return {
        "model": args.model,
        "text": text,
        "stream": False,
        "voice_setting": voice_setting,
        "audio_setting": {
            "sample_rate": args.sample_rate,
            "bitrate": args.bitrate,
            "format": args.format,
            "channel": args.channel,
        },
        "language_boost": args.language_boost,
        "subtitle_enable": False,
        "output_format": "url" if args.url_output else "hex",
    }


def request_t2a(endpoint: str, api_key: str, payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"MiniMax HTTP {exc.code}: {details}") from exc


def save_audio(result: dict, output: Path) -> None:
    base_resp = result.get("base_resp") or {}
    if base_resp.get("status_code") not in (None, 0):
        raise SystemExit(f"MiniMax error: {json.dumps(base_resp, ensure_ascii=False)}")

    data = result.get("data") or {}
    audio = data.get("audio")
    if not audio:
        raise SystemExit(f"No audio returned: {json.dumps(result, ensure_ascii=False)}")

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        output.write_bytes(binascii.unhexlify(audio))
    except (binascii.Error, ValueError) as exc:
        raise SystemExit("Expected hex audio. Re-run without --url-output.") from exc


def main() -> int:
    args = parse_args()
    load_default_env_files(args.env_file)
    text = read_text(args)
    validate_args(args, text)
    payload = build_payload(args, text)

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    api_key = args.api_key or os.environ.get(ENV_KEY)
    if not api_key:
        raise SystemExit("Set MINIMAX_API_KEY in the environment/.env or pass --api-key.")

    result = request_t2a(args.endpoint, api_key, payload)
    if args.url_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        save_audio(result, args.output)
        print(str(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
