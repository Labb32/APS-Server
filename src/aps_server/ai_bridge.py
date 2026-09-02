"""Fixed stdin/stdout bridge from official extensions to the Core AI gateway."""

from __future__ import annotations

import argparse
import json
import sys

from .ai_gateway import AIGateway, AIGatewayError, SCHEMAS
from .config import Settings


def main() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="APS internal AI gateway bridge")
    parser.add_argument("--schema", choices=sorted(SCHEMAS), required=True)
    args = parser.parse_args()
    prompt = sys.stdin.read()
    try:
        result = AIGateway(Settings()).generate(args.schema, prompt)
    except AIGatewayError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception as error:  # Keep prompts and provider payloads out of stderr.
        print(f"AI gateway internal failure: {type(error).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
