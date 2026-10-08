from __future__ import annotations

import concurrent.futures
import json
import socket
import subprocess
import sys
from threading import Event

import pytest

from f8diagnostics.skeleton import FrameVerifier, SimulateInput, VerifyInput, simulate_stream, verify_stream
from f8pysdk.motion import decode_skeleton_datagram
from f8pysdk.extension_packaging import validate_package
from pathlib import Path


def test_simulated_packets_use_sdk_skeleton_format() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
        listener.bind(('127.0.0.1', 0))
        listener.settimeout(1)
        port = listener.getsockname()[1]
        report = simulate_stream(SimulateInput(port=port, durationSeconds=0.1, fps=10))
        payload = decode_skeleton_datagram(listener.recvfrom(65535)[0])
    assert report['sentFrameCount'] == 1
    assert FrameVerifier().accept(payload) == 'F8 diagnostic skeleton'
    assert [bone['name'] for bone in payload['bones']] == ['Root', 'Tip']


def test_verification_reports_malformed_and_complete_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    ready = Event()

    class ReadySocket(socket.socket):
        def bind(self, address: tuple[str, int]) -> None:
            super().bind(address)
            ready.set()

    monkeypatch.setattr(socket, 'socket', ReadySocket)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(verify_stream, VerifyInput(port=port, timeoutMs=1000))
        assert ready.wait(timeout=1)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            sender.sendto(b'not a skeleton', ('127.0.0.1', port))
            simulate_stream(SimulateInput(port=port, durationSeconds=0.02, fps=100))
        result = future.result(timeout=2)
    assert result['verified'] is True
    assert result['decodedFrameCount'] == 1
    assert result['decoderErrors']


def test_partial_chunks_are_not_counted_as_complete_frames() -> None:
    decoder = FrameVerifier()
    base = {'type': 'skeleton_binary', 'modelName': 'fixture', 'bones': [],
            'trailer': {'chunkCount': 2, 'chunkIndex': 0, 'frameId': 1, 'totalBoneCount': 0}}
    assert decoder.accept(base) is None
    assert decoder.accept(base) is None
    assert decoder.accept({**base, 'trailer': {**base['trailer'], 'chunkIndex': 1}}) == 'fixture'
    assert not decoder.pending
    with pytest.raises(ValueError, match='finite numbers'):
        decoder.accept({'type': 'skeleton_binary', 'modelName': 'bad', 'bones': [{'name': 'root', 'pos': [float('nan'), 0, 0], 'rot': [1, 0, 0, 0]}]})


@pytest.mark.parametrize('options', [SimulateInput(durationSeconds=61), SimulateInput(fps=121), SimulateInput(port=0)])
def test_simulation_is_bounded(options: SimulateInput) -> None:
    with pytest.raises(ValueError):
        simulate_stream(options)


def test_tool_cli_reports_errors_with_protocol_result_and_traceback() -> None:
    process = subprocess.run([sys.executable, '-m', 'f8diagnostics.simulate'],
        input=json.dumps({'schemaVersion': 'f8toolInput/1', 'arguments': {'port': 0}}), text=True, capture_output=True, check=True)
    result = json.loads(process.stdout)
    assert result['schemaVersion'] == 'f8toolResult/1'
    assert result['success'] is False
    assert 'port' in result['message']
    assert 'Traceback' in process.stderr


def test_optional_tool_only_manifest() -> None:
    catalog = validate_package(Path(__file__).resolve().parents[1])
    extension = catalog.extensions[0]
    assert not catalog.preinstalled and not extension.service_classes
    assert {tool.tool_id for tool in extension.tools} == {'skeleton-verify', 'skeleton-simulate'}
    assert all(not tool.requires_confirmation for tool in extension.tools)
    assert extension.tools[1].timeout_seconds is None
    assert all(tool.allow_concurrent for tool in extension.tools)
    assert SimulateInput().durationSeconds is None
