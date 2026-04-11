import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from bot.main import live_executor as bot_live_executor, ETHScalper
from execution.live_executor import live_executor as exec_live_executor

bot = ETHScalper()

print(json.dumps({
    'same_object': id(bot_live_executor) == id(exec_live_executor),
    'bot_live_executor_id': id(bot_live_executor),
    'exec_live_executor_id': id(exec_live_executor),
    'bot_enabled_before': bot_live_executor.enabled,
    'exec_enabled_before': exec_live_executor.enabled,
}))

exec_live_executor.enable()

print(json.dumps({
    'same_object_after_enable': id(bot_live_executor) == id(exec_live_executor),
    'bot_enabled_after_exec_enable': bot_live_executor.enabled,
    'exec_enabled_after_exec_enable': exec_live_executor.enabled,
}))

print(json.dumps({
    'bot_enabled_final': bot_live_executor.enabled,
    'exec_enabled_final': exec_live_executor.enabled,
}))
