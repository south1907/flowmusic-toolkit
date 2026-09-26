#!/usr/bin/env bash
set -euo pipefail

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI is required: https://cli.github.com/" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Authenticate first with: gh auth login" >&2
  exit 1
fi

repository="${1:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"

gh repo edit "$repository" \
  --add-topic chrome-extension \
  --add-topic fastapi \
  --add-topic flow-music \
  --add-topic local-api \
  --add-topic music-generation \
  --add-topic python \
  --add-topic sqlite \
  --add-topic websocket

labels=(
  "bug|d73a4a|Something is not working"
  "documentation|0075ca|Documentation improvements"
  "duplicate|cfd3d7|This issue or pull request already exists"
  "enhancement|a2eeef|New feature or improvement"
  "good first issue|7057ff|Good for first-time contributors"
  "help wanted|008672|Extra attention is needed"
  "invalid|e4e669|This does not seem valid"
  "question|d876e3|Further information is requested"
  "wontfix|ffffff|This will not be worked on"
  "needs-triage|fbca04|Needs initial review and classification"
  "api|1d76db|FastAPI service and public API"
  "browser-extension|5319e7|Chrome extension bridge"
  "dependencies|0366d6|Dependency updates"
  "github-actions|000000|GitHub Actions and automation"
  "python|3572A5|Python implementation"
  "security|b60205|Security-related change or report"
)

for definition in "${labels[@]}"; do
  IFS='|' read -r name color description <<<"$definition"
  gh label create "$name" \
    --repo "$repository" \
    --color "$color" \
    --description "$description" \
    --force
done

echo "GitHub topics and labels synchronized for $repository"

