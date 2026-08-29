# Profile alias mappings.
# Each line: alias|alias|alias -> canonical_profile
# Source is case statement patterns used by resolve_profile_path in common.sh.

# Prefix stripping aliases (service name prefix -> category folder)
# These are handled inline in resolve_profile_path, not here.

# Canonical alias mappings (shorthand -> full profile path)
case "$profile" in
  medium/qwen36-35b-a3b-llamacpp-256k|medium/eliza-medium-qwen36-35b-a3b-llamacpp-256k|medium/qwen36-35b-a3b-llamacpp-200k-experimental|medium/eliza-medium-qwen36-35b-a3b-llamacpp-200k-experimental) profile="medium/qwen3.6-35b-a3b-q4-llamacpp-256k" ;;
  medium/gemma4-26b-a4b-llamacpp-256k-experimental|medium/eliza-medium-gemma4-26b-a4b-llamacpp-256k-experimental) profile="medium/gemma4-26b-a4b-q4-llamacpp-256k" ;;
  medium/vllm-smoke-tinyllama|medium/eliza-medium-vllm-smoke-tinyllama) profile="medium/tinyllama-1_1b-vllm-2k" ;;
  medium/deepseek-v4-flash-ds4-256k|medium/eliza-medium-deepseek-v4-flash-ds4-256k) profile="medium/deepseek-v4-flash-ds4-256k" ;;
  medium/qwen3-coder-next-llamacpp|medium/eliza-medium-qwen3-coder-next-llamacpp) profile="medium/qwen3-coder-next-ud-q4-k-m-llamacpp-256k" ;;
  medium/qwen3-coder-next-sglang|medium/eliza-medium-qwen3-coder-next-sglang) profile="medium/qwen3-coder-next-sglang-256k" ;;
  medium/qwen3.6-27b-nvfp4-vllm|medium/eliza-medium-qwen3.6-27b-nvfp4-vllm) profile="medium/qwen3.6-27b-nvfp4-vllm-256k" ;;
  medium/qwen3.6-27b-nvfp4-sglang|medium/eliza-medium-qwen3.6-27b-nvfp4-sglang) profile="medium/qwen3.6-27b-nvfp4-sglang-256k" ;;
  medium/qwen3.8-flash-next|medium/eliza-medium-qwen3.8-flash-next|medium/qwen3.8-flash-next-llamacpp) profile="medium/qwen3.8-flash-next-llamacpp-256k" ;;
  medium/qwen3.8-27b-fp8-sglang|medium/eliza-medium-qwen3.8-27b-fp8-sglang) profile="medium/qwen3.8-27b-fp8-sglang-256k" ;;
  medium/qwen3.8-27b-ud-q4-k-xl-llamacpp|medium/eliza-medium-qwen3.8-27b-ud-q4-k-xl-llamacpp) profile="medium/qwen3.8-27b-ud-q4-k-xl-llamacpp-256k" ;;
  medium/qwen3.5-122b-a10b-nvfp4-vllm|medium/eliza-medium-qwen3.5-122b-a10b-nvfp4-vllm) profile="medium/qwen3.5-122b-a10b-nvfp4-vllm-256k" ;;
  medium/qwen3.5-122b-a10b-nvfp4-sglang|medium/eliza-medium-qwen3.5-122b-a10b-nvfp4-sglang) profile="medium/qwen3.5-122b-a10b-nvfp4-sglang-256k" ;;
  medium/qwen3.5-122b-a10b-mxfp4-sglang|medium/eliza-medium-qwen3.5-122b-a10b-mxfp4-sglang) profile="medium/qwen3.5-122b-a10b-mxfp4-moe-sglang-256k" ;;
  medium/qwen3.5-122b-a10b-nvfp4-txn545-sglang|medium/eliza-medium-qwen3.5-122b-a10b-nvfp4-txn545-sglang) profile="medium/qwen3.5-122b-a10b-nvfp4-txn545-sglang-256k" ;;
  medium/qwen3.5-122b-a10b-mxfp4-moe-llamacpp|medium/eliza-medium-qwen3.5-122b-a10b-mxfp4-moe-llamacpp) profile="medium/qwen3.5-122b-a10b-mxfp4-moe-llamacpp-256k" ;;
  small/gemma4-e2b-fast|small/eliza-small-gemma4-e2b-fast) profile="small/gemma4-e2b-q4-llamacpp-8k" ;;
  small/gemma4-e4b-quality|small/eliza-small-gemma4-e4b-quality) profile="small/gemma4-e4b-q4-llamacpp-8k" ;;
  small/gemma4-e4b-long|small/eliza-small-gemma4-e4b-long) profile="small/gemma4-e4b-q4-llamacpp-128k" ;;
  small/gemma4-12b-quality|small/eliza-small-gemma4-12b-quality) profile="small/gemma4-12b-q4-llamacpp-8k" ;;
  small/gemma4-e4b-vllm-experimental|small/eliza-small-gemma4-e4b-vllm-experimental) profile="small/gemma4-e4b-vllm-8k" ;;
  small/gemma3-4b-stable|small/eliza-small-gemma3-4b-stable) profile="small/gemma3-4b-q4-llamacpp-8k" ;;
esac
