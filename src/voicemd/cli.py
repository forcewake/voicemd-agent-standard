from __future__ import annotations

import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path

from . import __version__
from .compiler import compile_contract
from .contract import ContractError, load_contract
from .discovery import DiscoveryError, discover_paths, find_project_root
from .evaluator import load_responses, run_cases
from .installer import InstallError, install, uninstall
from .linter import lint_text
from .server import serve
from .validator import validate_contract


def _add_contract_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--path",
        action="append",
        help="Explicit VOICE.md path. Repeat to set broad-to-specific overlays.",
    )
    parser.add_argument("--start", default=".", help="Discovery start directory (default: current).")
    parser.add_argument(
        "--no-global", action="store_true", help="Do not include ~/.config/voicemd/VOICE.md."
    )


def _load(args: argparse.Namespace):
    explicit = args.path if getattr(args, "path", None) else None
    return load_contract(
        start=Path(getattr(args, "start", ".")),
        explicit=explicit,
        include_global=not getattr(args, "no_global", False),
    )


def _template(name: str) -> str:
    return files("voicemd").joinpath(f"resources/templates/{name}.VOICE.md").read_text(
        encoding="utf-8"
    )


def cmd_init(args: argparse.Namespace) -> int:
    destination = Path(args.output).expanduser().resolve()
    if destination.is_dir():
        destination = destination / "VOICE.md"
    if destination.exists() and not args.force:
        print(f"Refusing to overwrite {destination}; pass --force.", file=sys.stderr)
        return 2
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(_template(args.mode), encoding="utf-8")
    print(destination)
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    paths = discover_paths(
        start=Path(args.start),
        explicit=args.path if args.path else None,
        include_global=not args.no_global,
    )
    if args.json:
        print(json.dumps([str(path) for path in paths], indent=2))
    else:
        if not paths:
            print("No VOICE.md found.")
            return 1
        for index, path in enumerate(paths):
            print(f"{index:02d} {path}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    contract = _load(args)
    result = validate_contract(contract, strict=args.strict)
    print(f"conformance: {result.level}")
    for source in contract.source_paths():
        print(f"source: {source}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    for error in result.errors:
        print(f"error: {error}")
    return 0 if result.ok else 1


def cmd_compile(args: argparse.Namespace) -> int:
    contract = _load(args)
    rendered = compile_contract(
        contract,
        profile=args.profile,
        audience=args.audience,
        surface=args.surface,
        tone=args.tone,
        output_format=args.format,
        compact=args.compact,
        max_chars=args.max_chars,
        include_provenance=args.provenance,
    )
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + ("\n" if not rendered.endswith("\n") else ""), encoding="utf-8")
        print(output)
    else:
        print(rendered)
    return 0


def _read_lint_input(args: argparse.Namespace) -> str:
    if args.text is not None:
        return args.text
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    return sys.stdin.read()


def cmd_lint(args: argparse.Namespace) -> int:
    contract = _load(args)
    issues = lint_text(
        contract,
        _read_lint_input(args),
        profile=args.profile,
        audience=args.audience,
        surface=args.surface,
        tone=args.tone,
    )
    if args.json:
        print(json.dumps([issue.as_dict() for issue in issues], ensure_ascii=False, indent=2))
    else:
        for issue in issues:
            evidence = f" [{issue.evidence}]" if issue.evidence else ""
            print(f"{issue.severity}: {issue.rule_id}: {issue.message}{evidence}")
        if not issues:
            print("PASS")
    return 1 if any(issue.severity == "error" for issue in issues) else 0


def cmd_test(args: argparse.Namespace) -> int:
    contract = _load(args)
    responses = load_responses(Path(args.responses)) if args.responses else {}
    results = run_cases(contract, responses=responses)
    if not results:
        print("No tests are defined in the active contract.")
        return 0
    failures = 0
    for result in results:
        if result.skipped:
            print(f"SKIP {result.case_id}: no response supplied")
        elif result.passed:
            print(f"PASS {result.case_id}")
        else:
            failures += 1
            print(f"FAIL {result.case_id}: " + "; ".join(result.failures))
    return 1 if failures else 0


def cmd_install(args: argparse.Namespace) -> int:
    results = install(
        Path(args.root),
        targets=args.target,
        mode=args.mode,
        dry_run=args.dry_run,
    )
    for path, status in results:
        print(f"{status}: {path}")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    results = uninstall(Path(args.root), targets=args.target, dry_run=args.dry_run)
    for path, status in results:
        print(f"{status}: {path}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    root = find_project_root(Path(args.start))
    failed = False
    try:
        contract = _load(args)
    except (ContractError, DiscoveryError) as exc:
        print(f"contract: FAIL: {exc}")
        contract = None
        failed = True
    if contract:
        validation = validate_contract(contract, strict=False)
        print(f"contract: {'PASS' if validation.ok else 'FAIL'} ({validation.level})")
        for source in contract.source_paths():
            print(f"  source: {source}")
        for error in validation.errors:
            print(f"  error: {error}")
            failed = True
        for warning in validation.warnings:
            print(f"  warning: {warning}")

    checks = {
        "universal skill": root / ".agents/skills/voice-contract/SKILL.md",
        "Codex/OpenCode bootstrap": root / "AGENTS.md",
        "Claude skill": root / ".claude/skills/voice-contract/SKILL.md",
        "Gemini bootstrap": root / "GEMINI.md",
        "Cursor rule": root / ".cursor/rules/voice-contract.mdc",
        "Copilot instructions": root / ".github/copilot-instructions.md",
        "Cline skill": root / ".cline/skills/voice-contract/SKILL.md",
        "Windsurf rule": root / ".windsurf/rules/voice-contract.md",
        "Aider config": root / ".aider.voice.yml",
    }
    for label, path in checks.items():
        print(f"adapter: {'present' if path.exists() else 'absent'}: {label}: {path}")
    return 1 if failed else 0


def cmd_serve(args: argparse.Namespace) -> int:
    print(f"VoiceMD sidecar listening on http://{args.host}:{args.port}", file=sys.stderr)
    serve(
        host=args.host,
        port=args.port,
        root=Path(args.start),
        path=args.path if args.path else None,
        include_global=not args.no_global,
        quiet=args.quiet,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voicemd",
        description="Compile, validate, evaluate, and integrate VOICE.md communication contracts.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a VOICE.md template.")
    init_parser.add_argument("--mode", choices=("simple", "full", "spoken"), default="simple")
    init_parser.add_argument("--output", default="VOICE.md")
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(func=cmd_init)

    discover_parser = subparsers.add_parser("discover", help="Show active VOICE.md sources.")
    _add_contract_args(discover_parser)
    discover_parser.add_argument("--json", action="store_true")
    discover_parser.set_defaults(func=cmd_discover)

    validate_parser = subparsers.add_parser("validate", help="Validate the active contract.")
    _add_contract_args(validate_parser)
    validate_parser.add_argument("--strict", action="store_true")
    validate_parser.set_defaults(func=cmd_validate)

    compile_parser = subparsers.add_parser("compile", help="Compile VOICE.md into runtime instructions.")
    _add_contract_args(compile_parser)
    compile_parser.add_argument("--profile")
    compile_parser.add_argument("--audience")
    compile_parser.add_argument("--surface")
    compile_parser.add_argument("--tone")
    compile_parser.add_argument(
        "--format",
        choices=("prompt", "json", "ascii", "nemotron", "nemotron-ascii"),
        default="prompt",
    )
    compile_parser.add_argument("--compact", action="store_true")
    compile_parser.add_argument("--max-chars", type=int)
    compile_parser.add_argument("--provenance", action="store_true")
    compile_parser.add_argument("--output", "-o")
    compile_parser.set_defaults(func=cmd_compile)

    lint_parser = subparsers.add_parser("lint", help="Lint generated text against VOICE.md.")
    _add_contract_args(lint_parser)
    lint_parser.add_argument("--text")
    lint_parser.add_argument("--file")
    lint_parser.add_argument("--profile")
    lint_parser.add_argument("--audience")
    lint_parser.add_argument("--surface")
    lint_parser.add_argument("--tone")
    lint_parser.add_argument("--json", action="store_true")
    lint_parser.set_defaults(func=cmd_lint)

    test_parser = subparsers.add_parser("test", help="Run deterministic contract test cases.")
    _add_contract_args(test_parser)
    test_parser.add_argument("--responses", help="JSONL with {id, response} model outputs.")
    test_parser.set_defaults(func=cmd_test)

    install_parser = subparsers.add_parser("install", help="Install harness adapters safely.")
    install_parser.add_argument("--root", default=".")
    install_parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="all, universal, codex, claude, gemini, cursor, copilot, cline, windsurf, opencode, aider",
    )
    install_parser.add_argument("--mode", choices=("auto", "always", "explicit"), default="auto")
    install_parser.add_argument("--dry-run", action="store_true")
    install_parser.set_defaults(func=cmd_install)

    uninstall_parser = subparsers.add_parser("uninstall", help="Remove managed harness adapters.")
    uninstall_parser.add_argument("--root", default=".")
    uninstall_parser.add_argument("--target", action="append", default=[])
    uninstall_parser.add_argument("--dry-run", action="store_true")
    uninstall_parser.set_defaults(func=cmd_uninstall)

    doctor_parser = subparsers.add_parser("doctor", help="Inspect contract and adapter health.")
    _add_contract_args(doctor_parser)
    doctor_parser.set_defaults(func=cmd_doctor)

    serve_parser = subparsers.add_parser("serve", help="Run the provider-neutral HTTP sidecar.")
    _add_contract_args(serve_parser)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--quiet", action="store_true")
    serve_parser.set_defaults(func=cmd_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ContractError, DiscoveryError, InstallError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
