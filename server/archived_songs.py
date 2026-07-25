"""Restore archived song records that are still supported by the KR client.

The 6.5.2 master fixture retains difficulty and jacket definitions for some
region-locked songs, but their MasterMusic rows were removed.  Keep the
original fixture untouched and inject the missing rows into both the JSON
model used by the local server and the protobuf payload returned to the game.
"""

import bz2
import time


GOD_KNOWS = {
    '1': 7,
    '2': 'God knows...',
    '3': 'bgm007',
    '4': 'godknows',
    '5': '하타 아키',
    '6': '코우사키 사토루',
    '7': 'anime',
    '9': '토마루 료타 (Elements Garden)',
    '10': 'godknows',
    '11': 1,
    '12': 'CiRCLE의 음악 상점에서 교환',
    '13': [
        {'1': 7, '2': 'combo_easy', '3': 'coin', '5': 5000},
        {'1': 7, '2': 'combo_expert', '3': 'coin', '5': 20000},
        {'1': 7, '2': 'combo_hard', '3': 'coin', '5': 15000},
        {'1': 7, '2': 'combo_normal', '3': 'coin', '5': 10000},
        {'1': 7, '2': 'combo_special', '3': 'coin', '5': 20000},
        {'1': 7, '2': 'full_combo_easy', '3': 'coin', '5': 10000},
        {'1': 7, '2': 'full_combo_expert', '3': 'star', '5': 50},
        {'1': 7, '2': 'full_combo_hard', '3': 'star', '5': 50},
        {'1': 7, '2': 'full_combo_normal', '3': 'coin', '5': 20000},
        {'1': 7, '2': 'full_combo_special', '3': 'star', '5': 50},
        {
            '1': 7,
            '2': 'score_rank_a',
            '3': 'practice_ticket',
            '4': 2,
            '5': 1,
        },
        {
            '1': 7,
            '2': 'score_rank_b',
            '3': 'practice_ticket',
            '4': 2,
            '5': 1,
        },
        {
            '1': 7,
            '2': 'score_rank_c',
            '3': 'practice_ticket',
            '4': 2,
            '5': 1,
        },
        {'1': 7, '2': 'score_rank_s', '3': 'star', '5': 50},
        {'1': 7, '2': 'score_rank_ss', '3': 'star', '5': 50},
    ],
    '14': 'godknows',
    '15': 1107,
    '16': 1499752800000,
    '17': 4102714800000,
    '18': 'music_shop',
    '20': '갓노우즈',
    '21': 'normal',
}


SENBONZAKURA = {
    '1': 81,
    '2': '천본앵',
    '3': 'bgm081',
    '4': '081_senbonzakura',
    '5': 'Kurousa',
    '6': 'Kurousa',
    '7': 'anime',
    '9': '후지나가 류타로 (Elements Garden)',
    '10': '천본앵',
    '11': 1,
    '12': 'CiRCLE의 음악 상점에서 교환',
    '13': [
        {'1': 81, '2': 'combo_easy', '3': 'coin', '5': 5000},
        {'1': 81, '2': 'combo_expert', '3': 'coin', '5': 20000},
        {'1': 81, '2': 'combo_hard', '3': 'coin', '5': 15000},
        {'1': 81, '2': 'combo_normal', '3': 'coin', '5': 10000},
        {'1': 81, '2': 'combo_special', '3': 'coin', '5': 20000},
        {'1': 81, '2': 'full_combo_easy', '3': 'coin', '5': 10000},
        {'1': 81, '2': 'full_combo_expert', '3': 'star', '5': 50},
        {'1': 81, '2': 'full_combo_hard', '3': 'star', '5': 50},
        {'1': 81, '2': 'full_combo_normal', '3': 'coin', '5': 20000},
        {'1': 81, '2': 'full_combo_special', '3': 'star', '5': 50},
        {
            '1': 81,
            '2': 'score_rank_a',
            '3': 'practice_ticket',
            '4': 2,
            '5': 1,
        },
        {
            '1': 81,
            '2': 'score_rank_b',
            '3': 'practice_ticket',
            '4': 2,
            '5': 1,
        },
        {
            '1': 81,
            '2': 'score_rank_c',
            '3': 'practice_ticket',
            '4': 2,
            '5': 1,
        },
        {'1': 81, '2': 'score_rank_s', '3': 'star', '5': 50},
        {'1': 81, '2': 'score_rank_ss', '3': 'star', '5': 50},
    ],
    '14': '081_senbonzakura',
    '15': 1109,
    '16': 1511092800000,
    '17': 4102714800000,
    '18': 'music_shop',
    '20': '천본앵',
    '21': 'normal',
}

ARCHIVED_SONGS = (GOD_KNOWS, SENBONZAKURA)

_MUSIC_UINT_FIELDS = {1, 11, 15, 16, 17, 19}
_ACHIEVEMENT_UINT_FIELDS = {1, 4, 5}


def enable_archived_songs(suite_master):
    """Add archived songs to the decoded suite-master dictionary once."""
    entries = suite_master['1']['1']
    existing_ids = {entry.get('1') for entry in entries}
    for song in ARCHIVED_SONGS:
        if song['1'] not in existing_ids:
            entries.append(song)
    entries.sort(key=lambda entry: entry['1'])
    return suite_master


def _encode_varint(value):
    value = int(value)
    encoded = bytearray()
    while value >= 0x80:
        encoded.append((value & 0x7f) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def _decode_varint(payload, offset):
    value = 0
    shift = 0
    while offset < len(payload):
        byte = payload[offset]
        offset += 1
        value |= (byte & 0x7f) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
        if shift >= 70:
            break
    raise ValueError('invalid protobuf varint')


def _encode_uint(field_number, value):
    return _encode_varint(field_number << 3) + _encode_varint(value)


def _encode_bytes(field_number, value):
    if isinstance(value, str):
        value = value.encode('utf-8')
    return (
        _encode_varint((field_number << 3) | 2)
        + _encode_varint(len(value))
        + value
    )


def _encode_message(fields, uint_fields):
    encoded = bytearray()
    for key in sorted(fields, key=int):
        field_number = int(key)
        value = fields[key]
        if field_number == 13:
            for achievement in value:
                encoded.extend(_encode_bytes(
                    field_number,
                    _encode_message(achievement, _ACHIEVEMENT_UINT_FIELDS),
                ))
        elif field_number in uint_fields:
            encoded.extend(_encode_uint(field_number, value))
        else:
            encoded.extend(_encode_bytes(field_number, value))
    return bytes(encoded)


def _skip_field(payload, offset, wire_type):
    if wire_type == 0:
        _, offset = _decode_varint(payload, offset)
        return offset
    if wire_type == 1:
        return offset + 8
    if wire_type == 2:
        size, offset = _decode_varint(payload, offset)
        return offset + size
    if wire_type == 5:
        return offset + 4
    raise ValueError(f'unsupported protobuf wire type: {wire_type}')


def _message_uint_field(payload, wanted_field):
    offset = 0
    while offset < len(payload):
        key, offset = _decode_varint(payload, offset)
        field_number = key >> 3
        wire_type = key & 7
        if field_number == wanted_field and wire_type == 0:
            value, _ = _decode_varint(payload, offset)
            return value
        offset = _skip_field(payload, offset, wire_type)
    return None


def _music_list_has_id(payload, music_id):
    offset = 0
    while offset < len(payload):
        key, offset = _decode_varint(payload, offset)
        field_number = key >> 3
        wire_type = key & 7
        if field_number == 1 and wire_type == 2:
            size, offset = _decode_varint(payload, offset)
            entry = payload[offset:offset + size]
            if _message_uint_field(entry, 1) == music_id:
                return True
            offset += size
        else:
            offset = _skip_field(payload, offset, wire_type)
    return False


def _message_bytes_field(payload, wanted_field):
    offset = 0
    while offset < len(payload):
        key, offset = _decode_varint(payload, offset)
        field_number = key >> 3
        wire_type = key & 7
        if field_number == wanted_field and wire_type == 2:
            size, offset = _decode_varint(payload, offset)
            return payload[offset:offset + size]
        offset = _skip_field(payload, offset, wire_type)
    return None


def _patch_limited_exchange_periods(payload, now_ms=None):
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    start_at = max(0, now_ms - 24 * 60 * 60 * 1000)
    end_at = now_ms + 30 * 24 * 60 * 60 * 1000

    offset = 0
    while offset < len(payload):
        field_start = offset
        key, offset = _decode_varint(payload, offset)
        field_number = key >> 3
        wire_type = key & 7
        if field_number == 1210 and wire_type == 2:
            size, data_start = _decode_varint(payload, offset)
            data_end = data_start + size
            period_map = payload[data_start:data_end]
            patched_period_map = bytearray()
            changed = False
            inner_offset = 0
            while inner_offset < len(period_map):
                inner_key, inner_offset = _decode_varint(
                    period_map, inner_offset
                )
                inner_field_number = inner_key >> 3
                inner_wire_type = inner_key & 7
                if inner_field_number == 1 and inner_wire_type == 2:
                    entry_size, entry_start = _decode_varint(
                        period_map, inner_offset
                    )
                    entry_end = entry_start + entry_size
                    entry = period_map[entry_start:entry_end]
                    limited_exchanges_id = _message_uint_field(entry, 1)
                    if limited_exchanges_id:
                        value = _message_bytes_field(entry, 2)
                        existing_start = (
                            _message_uint_field(value, 2)
                            if value is not None else 0
                        )
                        existing_end = (
                            _message_uint_field(value, 3)
                            if value is not None else 0
                        )
                        if not (
                            existing_start <= now_ms
                            and existing_end >= (
                                now_ms + 29 * 24 * 60 * 60 * 1000
                            )
                        ):
                            value = (
                                _encode_uint(1, limited_exchanges_id)
                                + _encode_uint(2, start_at)
                                + _encode_uint(3, end_at)
                                + _encode_uint(4, 0)
                            )
                            entry = (
                                _encode_uint(1, limited_exchanges_id)
                                + _encode_bytes(2, value)
                            )
                            changed = True
                    patched_period_map.extend(_encode_bytes(1, entry))
                    inner_offset = entry_end
                else:
                    copied_start = inner_offset
                    inner_offset = _skip_field(
                        period_map, inner_offset, inner_wire_type
                    )
                    patched_period_map.extend(
                        _encode_varint(inner_key)
                        + period_map[copied_start:inner_offset]
                    )
            if not changed:
                return payload
            return (
                payload[:field_start]
                + _encode_bytes(1210, bytes(patched_period_map))
                + payload[data_end:]
            )
        offset = _skip_field(payload, offset, wire_type)
    return payload


def _patch_suite_master(payload):
    offset = 0
    while offset < len(payload):
        field_start = offset
        key, offset = _decode_varint(payload, offset)
        field_number = key >> 3
        wire_type = key & 7
        if field_number == 1 and wire_type == 2:
            size, data_start = _decode_varint(payload, offset)
            data_end = data_start + size
            music_list = payload[data_start:data_end]
            changed = False
            for song in ARCHIVED_SONGS:
                if not _music_list_has_id(music_list, song['1']):
                    entry = _encode_message(song, _MUSIC_UINT_FIELDS)
                    music_list += _encode_bytes(1, entry)
                    changed = True
            if not changed:
                return payload
            return (
                payload[:field_start]
                + _encode_bytes(1, music_list)
                + payload[data_end:]
            )
        offset = _skip_field(payload, offset, wire_type)
    raise ValueError('suite master does not contain a music list')


def patch_suite_master_bz2(payload):
    """Inject archived songs into a bzip2-compressed SuiteMaster payload."""
    raw = _patch_suite_master(bz2.decompress(payload))
    raw = _patch_limited_exchange_periods(raw)
    return bz2.compress(raw, 9)


def suite_master_bz2_has_music(payload, music_id):
    """Return whether a compressed SuiteMaster payload contains a music ID."""
    raw = bz2.decompress(payload)
    offset = 0
    while offset < len(raw):
        key, offset = _decode_varint(raw, offset)
        field_number = key >> 3
        wire_type = key & 7
        if field_number == 1 and wire_type == 2:
            size, offset = _decode_varint(raw, offset)
            return _music_list_has_id(raw[offset:offset + size], music_id)
        offset = _skip_field(raw, offset, wire_type)
    return False


def normalize_exchange_master_dates(suite_master, now_ms=None):
    """Keep limited exchange masters visible for a local offline server."""
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    start_at = max(0, now_ms - 24 * 60 * 60 * 1000)
    end_at = now_ms + 30 * 24 * 60 * 60 * 1000
    for wrapper in suite_master.get('1210', {}).get('1', ()):
        if not isinstance(wrapper, dict):
            continue
        detail = wrapper.get('2', wrapper)
        if not isinstance(detail, dict):
            continue
        detail['2'] = start_at
        detail['3'] = end_at
    return suite_master
