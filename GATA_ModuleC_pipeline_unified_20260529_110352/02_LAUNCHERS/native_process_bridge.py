from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys


def quote_cmd_argument(value: str) -> str:
    if not value or any(character.isspace() for character in value):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file-path", required=True)
    parser.add_argument("--working-directory", required=True)
    parser.add_argument("--args-json-b64", required=True)
    args = parser.parse_args()

    child_args = json.loads(
        base64.b64decode(args.args_json_b64).decode("utf-8")
    )
    inherited_path = next(
        (value for key, value in os.environ.items() if key.lower() == "path"),
        "",
    )
    child_env = {
        key: value for key, value in os.environ.items() if key.lower() != "path"
    }
    child_env["PATH"] = inherited_path

    command = " ".join(
        quote_cmd_argument(value) for value in [args.file_path, *child_args]
    )
    process = subprocess.Popen(
        f'"{os.environ.get("ComSpec", "cmd.exe")}" /d /s /c "call {command}"',
        cwd=args.working_directory,
        env=child_env,
        stdout=sys.stdout.buffer,
        stderr=sys.stderr.buffer,
    )
    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
