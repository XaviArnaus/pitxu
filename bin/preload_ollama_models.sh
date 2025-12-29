#!/usr/bin/env bash

# Models to skip (embedding models, known unused, etc.)
skip_models=("nomic-embed-text:latest" "mxbai-embed-large:latest" "bge-m3:latest" "deepseek-coder-v2:16b" "deepseek-coder-v2:latest")

# Configuration
dry_run=false
only_filter=""
show_timings=true
convert_large_sizes=true  # Show GB for large models

# Handle Ctrl+C
trap 'echo; echo "🛑 Interrupted. Exiting..."; exit 1' INT

function print_help() {
  if [[ -t 1 ]]; then
    BOLD=$'\033[1m'
    BLUE=$'\033[1;34m'
    RESET=$'\033[0m'
  else
    BOLD=""
    BLUE=""
    RESET=""
  fi

  cat <<EOF
${BOLD}Usage:${RESET} $(basename "$0") [OPTIONS]

Preload Ollama models into RAM, sorted by model size (smallest first).

${BOLD}Options:${RESET}
  ${BLUE}--dry-run${RESET}         Show which models would be preloaded without actually running them
  ${BLUE}--only <keyword>${RESET}  Only preload models whose name contains the keyword
  ${BLUE}-h, --help${RESET}        Show this help message and exit

${BOLD}Skipped models:${RESET}
EOF

  for model in "${skip_models[@]}"; do
    echo "  - $model"
  done
}

# Argument parsing
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      dry_run=true
      shift
      ;;
    --only)
      if [[ -n "$2" ]]; then
        only_filter="$2"
        shift 2
      else
        echo "Error: --only requires a keyword argument" >&2
        exit 1
      fi
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      print_help >&2
      exit 1
      ;;
  esac
done

# Check for required commands
if ! command -v ollama &> /dev/null; then
  echo "Error: 'ollama' command not found. Please install Ollama first."
  exit 1
fi

# Check if Ollama is running
if ! curl --noproxy '*' --max-time 2 -s http://127.0.0.1:11434/ > /dev/null; then
  echo "❌ Ollama is not running or not reachable at http://127.0.0.1:11434/"
  exit 1
fi

echo "✅ Ollama is running."

# Helper function to format size
format_size() {
  local size_mb="$1"
  if [[ "$convert_large_sizes" == true && "$size_mb" -ge 1024 ]]; then
    echo "$(echo "scale=1; $size_mb / 1024" | bc) GB"
  else
    echo "${size_mb} MB"
  fi
}

if $dry_run; then
  echo "Dry run enabled. No models will be actually loaded."
fi

if [[ -n "$only_filter" ]]; then
  echo "Filtering models by keyword: \"$only_filter\""
fi

# Get model list and validate output
models=$(ollama list 2>/dev/null)
if [[ -z "$models" ]]; then
  echo "Error: Failed to get model list from 'ollama list'" >&2
  exit 1
fi

# Create temp file
tmpfile=$(mktemp)
header_line=$(echo "$models" | head -n 1)

# Verify we're parsing the expected format
if ! [[ "$header_line" =~ NAME.*SIZE ]]; then
  echo "Error: Unexpected output format from 'ollama list'" >&2
  echo "Expected header with NAME and SIZE columns" >&2
  exit 1
fi

# Parse and filter models
echo "$models" | tail -n +2 | while read -r line; do
  [[ -z "$line" ]] && continue

  name=$(echo "$line" | awk '{print $1}')
  size=$(echo "$line" | awk '{print $3}')
  unit=$(echo "$line" | awk '{print $4}')

  # Skip known models
  if [[ " ${skip_models[*]} " == *" $name "* ]]; then
    echo "⏭️ Skipping $name (explicitly excluded)" >&2
    continue
  fi

  # Apply --only filter if set
  if [[ -n "$only_filter" && "$name" != *"$only_filter"* ]]; then
    continue
  fi

  # Normalize size to MB
  size_mb=0
  if [[ "$unit" == "GB" ]]; then
    size_mb=$(echo "scale=0; $size * 1024 / 1" | bc 2>/dev/null || echo 0)
  elif [[ "$unit" == "MB" ]]; then
    size_mb=$(echo "scale=0; $size / 1" | bc 2>/dev/null || echo 0)
  else
    echo "Warning: Unknown size unit '$unit' for model $name" >&2
  fi

  if [[ "$size_mb" -eq 0 ]]; then
    echo "Warning: Could not determine size for $name" >&2
    size_mb=999999
  fi

  echo -e "$size_mb\t$name\t$size $unit"
done > "$tmpfile"

# Sort and preload models
preload_model() {
  local name="$1"
  local size_mb="$2"
  local size_original="$3"

  if $dry_run; then
    echo "[Dry run] Would preload $name ($size_original, $(format_size "$size_mb"))"
    return
  fi

  echo "Preloading $name ($size_original, $(format_size "$size_mb"))..."
  # shellcheck disable=SC2155
  local start=$(date +%s)

  if ! timeout 300 ollama run "$name" "Ready?" < /dev/null 2>&1; then
    echo "⚠️ Warning: Failed to load $name (timeout or error)" >&2
    return 1
  fi

  # shellcheck disable=SC2155
  local end=$(date +%s)
  if "$show_timings"; then
    echo "✅ $name done in $((end - start)) seconds."
  else
    echo "✅ $name done."
  fi
}

export -f preload_model format_size
export dry_run show_timings

# Sequential processing
while read -r size_mb name size_original; do
  preload_model "$name" "$size_mb" "$size_original"
done < <(sort -n "$tmpfile")

rm "$tmpfile"
echo "All models processed."