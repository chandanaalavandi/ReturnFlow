"""Command-line entry point for generating and checking ReturnFlow datasets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from returnflow.export import load_export, write_exports
from returnflow.generator import SEED, generate_dataset
from returnflow.validation import validate_dataset

SCALES = {
    "starter": (300, 50, 80),
    "full": (30_000, 5_000, 8_000),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="returnflow", description="Synthetic returns workflow")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="generate and export a dataset")
    generate.add_argument("--scale", choices=tuple(SCALES), default="starter")
    generate.add_argument("--orders", type=int)
    generate.add_argument("--requests", type=int)
    generate.add_argument("--return-lines", type=int)
    generate.add_argument("--seed", type=int, default=SEED)
    generate.add_argument("--output", type=Path)
    validate = commands.add_parser("validate", help="validate an existing generated export")
    validate.add_argument("directory", type=Path)
    serve = commands.add_parser("serve", help="run the local web dashboard")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--data-dir", type=Path, default=Path("data"))
    serve.add_argument("--scale", choices=tuple(SCALES), default="starter")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "generate":
        default_orders, default_requests, default_lines = SCALES[args.scale]
        orders_count = args.orders if args.orders is not None else default_orders
        requests_count = args.requests if args.requests is not None else default_requests
        return_lines_count = args.return_lines if args.return_lines is not None else default_lines
        output = args.output or Path("data") / args.scale
        try:
            dataset = generate_dataset(orders_count, requests_count, return_lines_count, args.seed)
            manifest = write_exports(dataset, output)
        except (OSError, ValueError) as error:
            parser.error(str(error))
            return 2
        print(json.dumps({
            "output": str(output),
            "counts": manifest["counts"],
            "seed": manifest["seed"],
            "validation_passed": manifest["validation_passed"],
        }, indent=2))
        return 0

    if args.command == "serve":
        from returnflow.web import serve_dashboard

        try:
            serve_dashboard(args.host, args.port, args.data_dir, args.scale)
        except (OSError, ValueError) as error:
            parser.error(str(error))
        return 0

    try:
        dataset = load_export(args.directory)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        parser.error(f"Cannot load dataset from {args.directory}: {error}")
        return 2
    result = validate_dataset(dataset)
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
