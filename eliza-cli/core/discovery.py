import pathlib
import tomllib
from typing import Dict, List
from .models import Profile, Service, Stack

class DiscoveryEngine:
    def __init__(self, root_dir: pathlib.Path):
        self.root_dir = root_dir

    def discover(self) -> Stack:
        stack_path = self.root_dir / "configs" / "eliza-stack.toml"
        if not stack_path.exists():
            raise FileNotFoundError(f"Stack configuration not found at {stack_path}")

        with open(stack_path, "rb") as f:
            stack_data = tomllib.load(f)

        stack = Stack(name=stack_data.get("stack", {}).get("name", "unknown"))
        
        # 1. Find all available profiles
        profiles = self._discover_profiles()
        stack.profiles = profiles

        # 2. Parse services from the stack config
        services_data = stack_data.get("services", [])
        models_data = stack_data.get("models", {})

        for s_data in services_data:
            name = s_data["name"]
            profile_id = s_data["profile"]
            
            # Check if this service is also defined in models section (for public_name/actual_model)
            model_info = models_data.get(name, {})
            
            service = Service(
                name=name,
                enabled=s_data.get("enabled", True),
                profile_id=profile_id,
                health_url=s_data.get("health_url", ""),
                public_name=model_info.get("public_name"),
                actual_model=model_info.get("actual_model"),
                purpose=model_info.get("purpose"),
                base_url=model_info.get("base_url")
            )
            stack.services[name] = service

        return stack

    def _discover_profiles(self) -> Dict[str, Profile]:
        profiles = {}
        profile_dir = self.root_dir / "configs" / "profiles"
        
        if not profile_dir.exists():
            return {}

        # Walk through all .env files
        for env_path in profile_dir.rglob("*.env"):
            # Construct the profile_id (e.g., 'medium/qwen-32k')
            # relative_path: medium/qwen-32k.env -> medium/qwen-32k
            rel_path = env_path.relative_to(profile_dir)
            profile_id = str(rel_path.with_suffix("")).replace("\\", "/")
            
            profiles[profile_id] = self._parse_profile(env_path, profile_id)
            
        return profiles

    def _parse_profile(self, path: pathlib.Path, profile_id: str) -> Profile:
        data = {}
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip()] = v.strip().strip('"').strip("'")

        # Helper to cast types
        def get_int(key, default=0):
            try: return int(data.get(key, default))
            except: return default

        def get_bool(key, default=False):
            val = str(data.get(key, default)).lower()
            return val in ("true", "1", "yes", "on")

        # Determine service name from profile_id if not explicitly in .env
        # Based on common pattern: 'medium/something' -> service is 'eliza-medium'
        # Or if the .env has SERVICE_NAME="..."
        service_name = data.get("SERVICE_NAME")
        if not service_name:
            parts = profile_id.split("/")
            if len(parts) == 2:
                category = parts[0] # e.g. 'medium'
                if category in ("small", "medium"):
                    service_name = f"eliza-{category}"
                else:
                    service_name = f"eliza-{category}" # Fallback
            else:
                service_name = "unknown"

        return Profile(
            path=str(path),
            name=profile_id,
            service_name=service_name,
            backend=data.get("BACKEND", "llamacpp"),
            model_repo=data.get("MODEL_REPO", ""),
            model_dir=data.get("MODEL_DIR", ""),
            model_file=data.get("MODEL_FILE", ""),
            model_name=data.get("MODEL_NAME", ""),
            host=data.get("HOST", "0.0.0.0"),
            port=get_int("PORT", 8001),
            ctx_size=get_int("CTX_SIZE", 32768),
            batch_size=get_int("BATCH_SIZE", 1024),
            ubatch_size=get_int("UBATCH_SIZE", 1024),
            n_gpu_layers=get_int("N_GPU_LAYERS", 999),
            jinja=get_bool("JINJA", True),
            spec_type=data.get("SPEC_TYPE"),
            flash_attn=data.get("FLASH_ATTN", "auto"),
            cache_type_k=data.get("CACHE_TYPE_K", "q8_0"),
            cache_type_v=data.get("CACHE_TYPE_V", "q8_0"),
            parallel=get_int("PARALLEL", 1)
        )
