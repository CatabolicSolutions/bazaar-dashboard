import sys
sys.path.insert(0, "/var/www/bazaar")
from active_crypto_sleeve.executor import TradeApprovalGate
gate = TradeApprovalGate()
gate._write_state({"approved":False,"approved_at":None,"trade_card_id":None,"conor_message_id":None})
print("Approval cleared")
