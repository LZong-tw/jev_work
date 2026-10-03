#!/usr/bin/env bash
# Run every test in the repo. No real Jev key needed: Jev is mocked everywhere.
#   ./test.sh
# Needs Node 18+ and Python 3.8+. Browser checks (viewer, slides) run when Playwright
# with Chromium is installed, and are skipped otherwise.
set -euo pipefail
cd "$(dirname "$0")"

echo "== proxy: node --test"
(cd proxy && npm test --silent)

echo
echo "== workshop: python unittest (client, levels 1-5, level simulators, learning, proxy integration, viewer, slides)"
(cd workshop && python3 -m unittest discover -s tests)

echo
echo "All tests passed."
