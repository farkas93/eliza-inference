import argparse
import pathlib
import sys
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
            profile_id = svc.profile_id

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

    elif args.command == "tui":
        app = ElizaTUI(root)
        app.run()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
