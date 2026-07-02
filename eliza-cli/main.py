import sys
import pathlib
from core.discovery import DiscoveryEngine

def main():
    # main.py is in eliza-cli/
    # eliza-cli/ is in eliza-inference/
    # eliza-inference/ is in /home/wseliza/private/
    root = pathlib.Path(__file__).parent.parent.resolve()
    print(f"[*] Searching stack in: {root}")
    
    try:
        engine = DiscoveryEngine(root)
        stack = engine.discover()
        
        print(f"\n[+] Stack Name: {stack.name}")
        print("-" * 40)
        
        print(f"{'SERVICE':<15} | {'ENABLED':<8} | {'PROFILE':<40}")
        print("-" * 40)
        for name, service in stack.services.items():
            status = "YES" if service.enabled else "NO"
            print(f"{name:<15} | {status:<8} | {service.profile_id:<40}")
            
        if stack.profiles:
            print(f"\n[+] Total Profiles Found: {len(stack.profiles)}")
            print("-" * 40)
            print(f"{'PROFILE ID':<40} | {'SERVICE':<15}")
            print("-" * 40)
            for pid, profile in stack.profiles.items():
                print(f"{pid:<40} | {profile.service_name:<15}")
        else:
            print("\n[!] No profiles found in configs/profiles/")

    except Exception as e:
        print(f"\n[!] ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
