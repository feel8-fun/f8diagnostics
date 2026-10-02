from __future__ import annotations

import json
import math
import socket
import time
from dataclasses import dataclass, field
from typing import Any

import msgspec
from f8pysdk.motion import SkeletonBone, SkeletonPacket, SkeletonPacketDecodeError, decode_skeleton_datagram


class VerifyInput(msgspec.Struct, frozen=True, kw_only=True, forbid_unknown_fields=True):
    bindAddress: str = '127.0.0.1'
    port: int = 39540
    timeoutMs: int = 2000
    minimumFrames: int = 1


class SimulateInput(msgspec.Struct, frozen=True, kw_only=True, forbid_unknown_fields=True):
    destination: str = '127.0.0.1'
    port: int = 39540
    durationSeconds: float | None = None
    fps: int = 30
    modelName: str = 'F8 diagnostic skeleton'


def validate_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError('port must be between 1 and 65535')


class BonePayload(msgspec.Struct, frozen=True, kw_only=True):
    name: str
    pos: tuple[float, float, float]
    rot: tuple[float, float, float, float]


class ChunkMetadata(msgspec.Struct, frozen=True, kw_only=True):
    chunkCount: int = 1
    chunkIndex: int = 0
    frameId: int = 0
    totalBoneCount: int = 0


class FramePayload(msgspec.Struct, frozen=True, kw_only=True):
    kind: str = msgspec.field(name='type')
    modelName: str
    bones: tuple[BonePayload, ...]
    stableKey: str = ''
    trailer: ChunkMetadata | None = None


@dataclass
class PendingFrame:
    chunk_count: int
    bone_count: int
    chunks: dict[int, tuple[BonePayload, ...]] = field(default_factory=dict)


class FrameVerifier:
    def __init__(self) -> None:
        self.pending: dict[tuple[str, int], PendingFrame] = {}

    def accept(self, payload: dict[str, Any]) -> str | None:
        frame = msgspec.convert(payload, type=FramePayload)
        if frame.kind != 'skeleton_binary' or not frame.modelName.strip():
            raise ValueError('payload requires skeleton_binary type and nonempty modelName')
        if len(frame.bones) > 10000:
            raise ValueError('too many bones in one packet')
        for bone in frame.bones:
            if not bone.name or any(not math.isfinite(value) for value in (*bone.pos, *bone.rot)):
                raise ValueError('bone requires a name and finite numbers')
        trailer = frame.trailer
        if trailer is None:
            return frame.modelName
        if not 1 <= trailer.chunkCount <= 1024 or not 0 <= trailer.chunkIndex < trailer.chunkCount:
            raise ValueError('invalid chunk count or index')
        if trailer.chunkCount == 1:
            return frame.modelName
        if not 0 <= trailer.totalBoneCount <= 10000:
            raise ValueError('invalid total bone count')
        key = (frame.stableKey or frame.modelName, trailer.frameId)
        if key not in self.pending:
            if len(self.pending) >= 16:
                del self.pending[next(iter(self.pending))]
            self.pending[key] = PendingFrame(trailer.chunkCount, trailer.totalBoneCount)
        pending = self.pending[key]
        if pending.chunk_count != trailer.chunkCount or pending.bone_count != trailer.totalBoneCount:
            del self.pending[key]
            raise ValueError('inconsistent chunk metadata')
        pending.chunks[trailer.chunkIndex] = frame.bones
        bone_count = sum(len(chunk) for chunk in pending.chunks.values())
        if bone_count > pending.bone_count:
            del self.pending[key]
            raise ValueError('assembled bone count exceeds totalBoneCount')
        if len(pending.chunks) < pending.chunk_count:
            return None
        del self.pending[key]
        if bone_count != pending.bone_count:
            raise ValueError('assembled bone count does not match totalBoneCount')
        return frame.modelName


def verify_stream(request: VerifyInput) -> dict[str, object]:
    validate_port(request.port)
    if not 100 <= request.timeoutMs <= 30000 or not 1 <= request.minimumFrames <= 100:
        raise ValueError('timeoutMs must be 100..30000 and minimumFrames must be 1..100')
    packets = frames = 0
    errors: list[str] = []
    names: set[str] = set()
    decoder = FrameVerifier()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
        listener.bind((request.bindAddress, request.port))
        deadline = time.monotonic() + request.timeoutMs / 1000
        while frames < request.minimumFrames:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            listener.settimeout(min(0.2, remaining))
            try:
                packet, _ = listener.recvfrom(65535)
            except TimeoutError:
                continue
            packets += 1
            try:
                name = decoder.accept(decode_skeleton_datagram(packet))
            except (SkeletonPacketDecodeError, ValueError, UnicodeDecodeError) as exc:
                if len(errors) < 8:
                    errors.append(f'{type(exc).__name__}: {exc}')
                continue
            if name is not None:
                frames += 1
                names.add(name)
    return {'bindAddress': request.bindAddress, 'port': request.port, 'packetCount': packets,
            'decodedFrameCount': frames, 'modelNames': sorted(names), 'decoderErrors': errors,
            'incompleteFrameCount': len(decoder.pending), 'verified': frames >= request.minimumFrames}


def simulate_stream(request: SimulateInput) -> dict[str, object]:
    validate_port(request.port)
    if request.durationSeconds is not None and (not math.isfinite(request.durationSeconds) or not 0 < request.durationSeconds <= 60):
        raise ValueError('durationSeconds must be greater than 0 and at most 60, or omitted to run until stopped')
    if not 1 <= request.fps <= 120:
        raise ValueError('fps must be 1..120')
    if not request.modelName.strip() or len(request.modelName) > 200:
        raise ValueError('modelName must contain 1..200 characters')
    frames = None if request.durationSeconds is None else math.ceil(request.durationSeconds * request.fps)
    started = time.monotonic()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        index = 0
        while frames is None or index < frames:
            wait = started + index / request.fps - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            offset = 0.1 * math.sin(index / request.fps * math.tau)
            packet = SkeletonPacket(model_name=request.modelName, timestamp_ms=int(time.time() * 1000), schema='f8.diagnostic',
                bones=(SkeletonBone('Root', (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)),
                       SkeletonBone('Tip', (offset, 1.0, 0.0), (1.0, 0.0, 0.0, 0.0))))
            sender.sendto(json.dumps(packet.to_payload(), allow_nan=False).encode(), (request.destination, request.port))
            index += 1
    return {'destination': request.destination, 'port': request.port, 'sentFrameCount': index,
            'fps': request.fps, 'modelName': request.modelName}
