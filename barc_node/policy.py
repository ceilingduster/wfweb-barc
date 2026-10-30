"""Shared, deny-by-default control policy. Unknown commands never reach the rig."""
from pathlib import PurePosixPath
from urllib.parse import unquote


def safe_asset(path):
    decoded=unquote(path)
    parts=PurePosixPath(decoded).parts
    if decoded.startswith(('/', '\\')) or ':' in decoded or '%' in decoded or '\\' in decoded or '?' in decoded or '#' in decoded or any(p.startswith('.') or p.lower() in ('api','rest') for p in parts):
        return False
    return not path or path=='index.html' or decoded.endswith(('.js','.mjs','.css','.wasm','.svg','.png','.jpg','.jpeg','.gif','.ico','.woff','.woff2','.ttf','.map','.onnx','.onnx.json','-LICENSE'))

LISTENER_COMMANDS = frozenset({'getStatus', 'enableAudio'})
# Persistent/autonomous digital transmitters, server settings, power cycling,
# logbook writes and memory writes are deliberately excluded from this release.
OPERATOR_COMMANDS = LISTENER_COMMANDS | frozenset({
    'setFrequency', 'setMode', 'selectVFO', 'swapVFO', 'equalizeVFO',
    'setPTT', 'enableMic', 'setAfGain', 'setRfGain', 'setRfPower',
    'setSquelch', 'setMicGain', 'setAttenuator', 'setPreamp', 'setAntenna',
    'setNoiseBlanker', 'setNoiseReduction', 'setAGC', 'setCompressor',
    'setCompLevel', 'setMonitor', 'setMonitorGain', 'setAutoNotch',
    'setFilterWidth', 'setPBTInner', 'setPBTOuter', 'setFilterShape',
    'setFilter', 'setSplit', 'setDuplex', 'setToneMode', 'setToneFreq',
    'setTsqlFreq', 'setDtcsCode', 'setDuplexOffset', 'setSpan',
    'setScopeRef', 'setScopeSpeed', 'setScopeMode', 'setScopeEdges',
})


def allowed(command, operator=False):
    if not isinstance(command, dict) or not isinstance(command.get('cmd'), str):
        return False
    if command['cmd'] not in (OPERATOR_COMMANDS if operator else LISTENER_COMMANDS):
        return False
    if command['cmd'] in {'enableAudio', 'enableMic', 'setPTT'}:
        if type(command.get('value')) is not bool:
            return False
    return True
