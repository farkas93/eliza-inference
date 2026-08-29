import argparse
import pathlib
import sys
from core.benchmarks import (
    BENCHMARK_TYPES,
    DEFAULT_RESULTS_DIR,
    filter_records,
    ledger_path,
    read_ledger,
    render_runs_table,
)
from core.discovery import DiscoveryEngine
from core.executor import Executor
from tui.app import ElizaTUI

def main():
    parser = argparse.ArgumentParser(description="Eliza CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # 'list' command
    subparsers.add_parser("list", help="List services and profiles (Standard CLI)")

    # 'download' command
    download_parser = subparsers.add_parser("download", help="Download model artifacts for a service/profile")
    download_parser.add_argument("service", help="Service name (e.g. eliza-small, stt, tts)")
    download_parser.add_argument("--profile", "-p", default=None, help="Profile ID (default: auto-detected from service)")

    # 'benchmark' command
    benchmark_parser = subparsers.add_parser("benchmark", help="Run and inspect benchmarks")
    benchmark_sub = benchmark_parser.add_subparsers(dest="bench_command", help="Benchmark actions")

    bench_run = benchmark_sub.add_parser("run", help="Run a single benchmark type for a service")
    bench_run.add_argument("type", choices=BENCHMARK_TYPES, help="Benchmark type")
    bench_run.add_argument("service", help="Service name (e.g. eliza-medium)")
    bench_run.add_argument(
        "extra",
        nargs=argparse.REMAINDER,
        help="Extra options passed through (e.g. --profile ID, --max-tokens 512, --force)",
    )

    bench_all = benchmark_sub.add_parser("all", help="Run the standard benchmark suite")
    bench_all.add_argument("--force", action="store_true", help="Skip the model-verification guard")

    bench_compare = benchmark_sub.add_parser("compare", help="Regenerate the benchmark comparison markdown")
    bench_compare.add_argument("--results-dir", default=None, help="Results directory (default: benchmarks/results)")
    bench_compare.add_argument("--output", default=None, help="Output markdown path (default: benchmarks/RESULTS.md)")
    bench_compare.add_argument("--service", default=None, help="Only include this service")
    bench_compare.add_argument("--profile", default=None, help="Only include this profile")
    bench_compare.add_argument("--all-runs", action="store_true", help="Show every run instead of latest per profile")

    bench_list = benchmark_sub.add_parser("list", help="List recent benchmark runs from the ledger")
    bench_list.add_argument("--service", default=None, help="Filter by service")
    bench_list.add_argument("--profile", default=None, help="Filter by profile")
    bench_list.add_argument("--type", default=None, choices=BENCHMARK_TYPES, help="Filter by benchmark type")
    bench_list.add_argument("--limit", type=int, default=20, help="Max runs to show (default: 20)")
    bench_list.add_argument("--results-dir", default=None, help="Results directory (default: benchmarks/results)")

    # 'tui' command
    subparsers.add_parser("tui", help="Launch the interactive TUI")

    args = parser.parse_args()

    # Determine root directory (assume running from eliza-inference/)
    root = pathlib.Path(__file__).parent.parent.resolve()

    if args.command == "list":
        engine = DiscoveryEngine(root)
        stack = engine.discover()
        print(f"\n[+] Stack Name: {stack.name}")
        print("-" * 40)
        print(
            f"{'SERVICE':<15} | {'STATUS':<8} | {'HEALTH':<6} | {'CONFIG_PROFILE':<40} | {'LIVE_PROFILE':<40} | {'DRIFT':<5}"
        )
        print("-" * 40)
        for name, service in stack.services.items():
            live_profile = service.live_profile_id or "-"
            drift = "yes" if service.drift else "no"
            print(
                f"{name:<15} | {service.status:<8} | {service.health:<6} | {service.profile_id:<40} | {live_profile:<40} | {drift:<5}"
            )
        
        if stack.profiles:
            print(f"\n[+] Total Profiles Found: {len(stack.profiles)}")
            print("-" * 40)
            print(f"{'PROFILE ID':<40} | {'SERVICE':<15}")
            print("-" * 40)
            for pid, profile in stack.profiles.items():
                print(f"{pid:<40} | {profile.service_name:<15}")

    elif args.command == "download":
        executor = Executor(root)
        # Discover stack to find profile if not specified
        if args.profile:
            profile_id = args.profile
        else:
            engine = DiscoveryEngine(root)
            stack = engine.discover()
            svc = stack.services.get(args.service)
            if svc is None:
                print(f"Error: service '{args.service}' not found. Use --profile to specify a profile.", file=sys.stderr)
                sys.exit(1)
            profile_id = svc.live_profile_id or svc.profile_id

        print(f"Downloading model artifacts for {args.service} ({profile_id})...")
        sys.stdout.flush()
        try:
            def progress(msg: str) -> None:
                print(f"  {msg}")
                sys.stdout.flush()

            output = executor.download_model(args.service, profile_id, progress_callback=progress)
            print(f"\nDownload complete:\n{output}")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "benchmark":
        bench = getattr(args, "bench_command", None)

        def progress(msg: str) -> None:
            print(f"  {msg}")
            sys.stdout.flush()

        if bench == "run":
            executor = Executor(root)
            extra = list(args.extra) if args.extra else []
            has_profile_arg = any(
                opt == "--profile" or opt.startswith("--profile=") for opt in extra
            )
            if not has_profile_arg:
                engine = DiscoveryEngine(root)
                stack = engine.discover()
                svc = stack.services.get(args.service)
                if svc and (svc.live_profile_id or svc.profile_id):
                    profile_to_use = svc.live_profile_id or svc.profile_id
                    extra.extend(["--profile", profile_to_use])

            print(f"[+] Running {args.type} benchmark for {args.service}...")
            sys.stdout.flush()
            try:
                output = executor.run_benchmark(args.type, args.service, extra=tuple(extra), progress_callback=progress)
                if output:
                    print(f"\n{output}")
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                sys.exit(1)
        elif bench == "all":
            executor = Executor(root)
            print("[+] Running full benchmark suite (stream + memory + voice)...")
            sys.stdout.flush()
            try:
                output = executor.run_benchmark_all(force=args.force, progress_callback=progress)
                if output:
                    print(f"\n{output}")
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                sys.exit(1)
        elif bench == "compare":
            executor = Executor(root)
            print("[+] Regenerating benchmark comparison...")
            sys.stdout.flush()
            try:
                output = executor.run_benchmark_compare(
                    results_dir=args.results_dir,
                    output=args.output,
                    service=args.service,
                    profile=args.profile,
                    all_runs=args.all_runs,
                    progress_callback=progress,
                )
                if output:
                    print(f"\n{output}")
            except Exception as exc:
                print(f"Error: {exc}", file=sys.stderr)
                sys.exit(1)
        elif bench == "list":
            if args.results_dir:
                results_dir = pathlib.Path(args.results_dir)
                if not results_dir.is_absolute():
                    results_dir = root / results_dir
            else:
                results_dir = root / DEFAULT_RESULTS_DIR
            records = read_ledger(ledger_path(results_dir))
            records = filter_records(
                records,
                service=args.service,
                profile=args.profile,
                bench_type=args.type,
            )
            print(render_runs_table(records, limit=args.limit))
        else:
            benchmark_parser.print_help()
    elif args.command == "tui":
        app = ElizaTUI(root)
        app.run()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
