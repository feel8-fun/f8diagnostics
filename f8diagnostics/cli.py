from __future__ import annotations

import logging
import sys
from typing import Any

import msgspec

from .skeleton import SimulateInput, VerifyInput, simulate_stream, verify_stream


class ToolInput(msgspec.Struct, frozen=True, kw_only=True, forbid_unknown_fields=True):
    schemaVersion: str
    arguments: dict[str, Any]


def main(operation: str) -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    try:
        request = msgspec.json.decode(sys.stdin.buffer.read(65536), type=ToolInput)
        if request.schemaVersion != 'f8toolInput/1':
            raise ValueError('unsupported tool input schema')
        if operation == 'verify':
            data = verify_stream(msgspec.convert(request.arguments, type=VerifyInput))
            success = data['verified'] is True
            message = 'Skeleton stream verified' if success else 'No complete skeleton frame verified'
        elif operation == 'simulate':
            data = simulate_stream(msgspec.convert(request.arguments, type=SimulateInput))
            success = True
            message = 'Simulation finished; UDP sending does not confirm receiver delivery'
        else:
            raise ValueError('expected verify or simulate command')
        result = {'schemaVersion': 'f8toolResult/1', 'success': success, 'message': message, 'data': data}
    except Exception as exc:
        logging.exception('Skeleton diagnostic tool failed')
        result = {'schemaVersion': 'f8toolResult/1', 'success': False, 'message': f'{type(exc).__name__}: {exc}', 'data': None}
    print(msgspec.json.encode(result).decode())
