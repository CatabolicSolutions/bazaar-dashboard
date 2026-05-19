#!/usr/bin/env python3
import subprocess
import shlex
import sys

def send_discord_message(message_content, channel_id="1483025184775733319"):
    """Sends a message to the specified Discord channel using OpenClaw's message tool."""
    try:
        escaped_channel_id = shlex.quote(channel_id)
        escaped_message_content = shlex.quote(message_content)
        
        full_command_string = (
            f'openclaw message action send '
            f'target {escaped_channel_id} '
            f'message {escaped_message_content}'
        )
        
        result = subprocess.run(full_command_string, shell=True, capture_output=True, text=True, check=True)
        print(f"Discord message command executed. Stdout: {result.stdout.strip()}, Stderr: {result.stderr.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error executing Discord message command: {e}. Stderr: {e.stderr.strip()}")
        return False
    except Exception as e:
        print(f"Error preparing or executing Discord message: {e}")
        return False

if __name__ == "__main__":
    # Test message
    success = send_discord_message("Test from Tradier pipeline VPS")
    if success:
        print("Discord test succeeded")
    else:
        print("Discord test failed")
        sys.exit(1)