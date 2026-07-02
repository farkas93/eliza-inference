from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass(frozen=True)
class Profile:
    """Represents a single loaded .env profile."""
    path: str
    name: str  # The filename/id, e.g., 'medium/qwen3_6-27b-q4-llamacpp-32k'
    service_name: str
    backend: str
    model_repo: str
    model_dir: str
    model_file: str
    model_name: str
    host: str
    port: int
    ctx_size: int
    batch_size: int
    ubatch_size: int
    n_gpu_layers: int
    jinja: bool
    spec_type: Optional[str] = None
    flash_attn: str = "auto"
    cache_type_k: str = "q8_0"
    cache_type_v: str = "q8_0"
    parallel: int = 1

@dataclass(frozen=True)
class Service:
    """Represents an active service as configured in the stack."""
    name: str
    enabled: bool
    profile_id: str  # The profile name used in stack.toml
    health_url: str
    base_url: Optional[str] = None
    purpose: Optional[str] = None
    public_name: Optional[str] = None
    actual_model: Optional[str] = None

@dataclass
class Stack:
    """The top-level representation of the eliza-inference stack."""
    name: str
    services: Dict[str, Service] = field(default_factory=dict)
    profiles: Dict[str, Profile] = field(default_factory=dict)
