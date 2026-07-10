import argparse
import pathlib
import sys
from core.discovery import DiscoveryEngine
from tui.app import ElizaTUI

def main():
    parser = argparse.ArgumentParser(description="Eliza CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # 'list' command
    subparsers.add_parser("list", help="List services and profiles (Standard CLI)")

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

    elif args.command == "tui":
        app = ElizaTUI(root)
        app.run()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
