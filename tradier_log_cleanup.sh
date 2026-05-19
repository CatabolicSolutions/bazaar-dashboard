#!/bin/bash
LOG_DIR="/home/alfred-deploy/logs"
find "$LOG_DIR" -name "tradier_*.log" -type f -mtime +7 -delete
find "$LOG_DIR" -name "tradier_cron.log" -type f -size +10M -exec truncate -s 5M {} \;
echo "Log cleanup completed at $(date)" >> "$LOG_DIR/cleanup.log"