from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from tradier_web_server import run_server


@dataclass
class TradierRuntimeConfig:
    host: str = '127.0.0.1'
    port: int = 8000

    @property
    def is_private_default(self) -> bool:
        return self.host == '127.0.0.1'

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['is_private_default'] = self.is_private_default
        return payload


def create_runtime_server(config: TradierRuntimeConfig | None = None):
    config = config or TradierRuntimeConfig()
    server = run_server(host=config.host, port=config.port)
    return {
        'kind': 'tradier.runtime_server',
        'config': config.to_dict(),
        'server': server,
    }
