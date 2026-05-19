#!/bin/bash
set -e

# Source environment variables
if [ -f "/var/www/bazaar/.bazaar.env" ]; then
  source "/var/www/bazaar/.bazaar.env"
fi

# Auto-execution flag (human-in-the-loop default)
export TRADIER_AUTO_EXECUTE="${TRADIER_AUTO_EXECUTE:-false}"

# Run the script
python3 "$@"