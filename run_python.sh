#!/bin/bash
set -e

# Source environment variables
if [ -f "/var/www/bazaar/.bazaar.env" ]; then
  source "/var/www/bazaar/.bazaar.env"
fi

# Run the script
python3 "$@"