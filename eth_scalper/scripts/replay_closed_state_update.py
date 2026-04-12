import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from types import SimpleNamespace

from state_manager import state_manager

POSITION_ID = 'pos_1_1775983277'
EXIT_TX_HASH = 'e63d35b98456a2405dcc89d1b8090b5c60b5c0edf950598ad78651e980e99d69'
EXIT_PRICE = 2218.41
EXIT_TIME = 1775983583.0288873
PNL_USD = -2.0013521370526126
PNL_PCT = -0.013521370526124727
REASON = 'timeout'

before = [p for p in state_manager.load_persisted_positions() if p.get('id') == POSITION_ID]
print(json.dumps({'before': before}, indent=2))

position = SimpleNamespace(id=POSITION_ID, exit_tx_hash=EXIT_TX_HASH)
state_manager.mark_position_closed(
    position=position,
    exit_price=EXIT_PRICE,
    exit_time=EXIT_TIME,
    pnl_usd=PNL_USD,
    pnl_pct=PNL_PCT,
    reason=REASON,
)

after = [p for p in state_manager.load_persisted_positions() if p.get('id') == POSITION_ID]
print(json.dumps({'after': after}, indent=2))
