"""Game API server"""

import json
import os
import random
import struct
import time
from operator import attrgetter

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from flask import abort, Flask, Request, request, Response

from server.archived_songs import (
    enable_archived_songs,
    normalize_exchange_master_dates,
    patch_suite_master_bz2,
)
from server.pb2.ce import (
    app_pb2, server_system_pb2, suite_user_character_pb2,
    suite_user_event_story_memorial_pb2, suite_user_login_bonus_pb2,
    suite_user_friend_pb2, suite_user_mission_pb2,
    suite_user_panel_mission_pb2, suite_user_pb2,
    suite_user_change_area_item_pb2,
    suite_user_event_box_gacha_pb2, suite_user_exchanges_pb2,
    suite_user_profile_pb2,
    suite_user_update_pb2,
    suite_user_story_pb2, user_action_set_album_pb2, user_area_pb2,
    user_auth_pb2,
    user_backstage_talk_set_pb2, user_band_story_pb2,
    user_deck_api_pb2, user_event_story_memorial_pb2, user_pb2,
    user_gacha_api_pb2, user_gallery_pb2, user_live_boost_pb2,
    user_live_boost_recovery_item_pb2,
    user_event_box_gacha_pb2, user_event_exchanges_pb2,
    user_music_api_pb2, user_shoplist_api_pb2,
    user_multi_room_friend_recruitment_pb2, user_present_pb2,
    user_profile_api_pb2, user_profile_degree_pb2,
    user_profile_situation_pb2, user_story_pb2,
    user_deco_equipment_pb2
)
from server.storage import (
    AreaItemPlacementState, DECK_MEMBER_FIELDS, ResourceState, StateStore,
    StateStoreError,
    LIVE_BOOST_ITEM_MAX, LIVE_BOOST_NATURAL_MAX,
    LIVE_BOOST_RECOVERY_SECONDS, UserState, today_kst_iso,
)

app = Flask(__name__)

from flask import request
import sys

@app.before_request
def _debug_log_request():
    print(
        f"[GAME] {request.remote_addr} {request.method} {request.path} "
        f"query={request.query_string.decode(errors='ignore')}",
        file=sys.stderr,
        flush=True,
    )

_suite_master = None
_suite_master_payload = None
_action_set_master_payload = None
_action_set_album_counts = None
_area_action_set_ids = None
_suite_user = None
_state_store = StateStore()
_rng = random.SystemRandom()

_key = b'bangdreamtokakao'
_iv = b'kakaotobangdream'

_LOCAL_USER_ID = 1000000
_FINAL_EVENT_ID = 209
_EVENT_BOX_GACHA_COST_PER_SPIN = 10
_EVENT_BOX_GACHA_MAX_SPIN_COUNT = 100
_LOCAL_SITUATION_RELEASE_CUTOFF_MS = 4_102_444_800_000
_SUPPORTED_EVENT_REWARD_TYPES = frozenset({
    'coin', 'star', 'item', 'practice_ticket',
    'live_boost_recovery_item', 'gacha_ticket', 'event_item',
    'degree', 'situation', 'michelle_seal', 'star_seal',
})
_BAND_STORY_FIELDS = {
    1: 'user_poppin_party_story_list',
    2: 'user_afterglow_story_list',
    3: 'user_hello_happy_world_story_list',
    4: 'user_pastel_palettes_story_list',
    5: 'user_roselia_story_list',
    18: 'user_raise_a_suilen_story_list',
    21: 'user_morfonica_story_list',
}
_PROFILE_PUBLISH_REQUEST_FIELDS = frozenset({
    22, 23, 24, 25, 26, 27, 28, 29, 30, 32, 33, 34, 35,
})
_PROFILE_PUBLISH_NAMES = (
    'publish_total_deck_power_flg',
    'publish_band_rank_flg',
    'publish_music_cleared_flg',
    'publish_music_full_combo_flg',
    'publish_high_score_rating_flg',
    'publish_updated_at_flg',
    'publish_user_id_flg',
    'searchable_flg',
    'friend_applicable_flg',
    'publish_music_all_perfect_flg',
    'publish_deck_rank_flg',
    'publish_stage_achievement_conditions_flg',
    'publish_stage_friend_ranking_flg',
)
_BAND_IDS = (1, 2, 3, 4, 5, 18, 21)
_BAND_RANK_MISSION_BANDS = {
    22: 1,
    23: 2,
    24: 4,
    25: 5,
    26: 3,
    27: 21,
    28: 18,
}
_DECK_RATING_MISSION_BANDS = {
    29: 1,
    30: 2,
    31: 4,
    32: 5,
    33: 3,
    34: 21,
}
_ALBUM_MISSION_CHARACTERS = {
    mission_id: mission_id - 1000
    for mission_id in range(1001, 1031)
}
_HIGH_SCORE_RATING_BAND_FIELDS = {
    1: 'user_poppin_party_high_score_music_list',
    2: 'user_afterglow_high_score_music_list',
    3: 'user_pastel_palettes_high_score_music_list',
    4: 'user_hello_happy_world_high_score_music_list',
    5: 'user_roselia_high_score_music_list',
    18: 'user_raise_a_suilen_high_score_music_list',
    21: 'user_morfonica_high_score_music_list',
}
_HIGH_SCORE_PLACEHOLDER_MUSIC = {
    0: 41,
    1: 1,
    2: 11,
    3: 20,
    4: 18,
    5: 9,
    18: 160,
    21: 255,
}
_HIGH_SCORE_RATING_LIMIT = 3
_AREA_ACTION_SET_REWARD_STAR = 10
_AREA_ACTION_SET_REFRESH_EXTRA = 0
_AREA_ACTION_SET_MAX_VISIBLE = 15
_BAND_RANK_EXP_PER_LEVEL = 100
_DECK_RATING_ATTRIBUTES = ('powerful', 'happy', 'pure', 'cool')
_DEFAULT_DECK_MEMBER_IDS = (1, 13, 17, 9, 5)
_DECK_RATING_THRESHOLDS = (
    (240_000, 'ss', 4, 240_000, 999_999),
    (210_000, 's', 3, 210_000, 239_999),
    (180_000, 'a', 2, 180_000, 209_999),
    (120_000, 'b', 1, 120_000, 179_999),
    (1, 'c', 0, 1, 119_999),
)


def _effective_user_id(user_id: int) -> int:
    """Map client-side placeholder IDs to the local account.

    Some KR client requests emitted from edit screens use ``0`` in the path
    even after the local user has been loaded.  The private server is a
    single-account environment, so treating that placeholder as the local user
    avoids rejecting legitimate UI actions.
    """
    return _LOCAL_USER_ID if user_id == 0 else user_id


def _load_suite_master():
    global _suite_master
    if _suite_master is None:
        with open('server/responses/suite_master.json', 'rb') as f:
            _suite_master = json.loads(f.read())
        enable_archived_songs(_suite_master)
        normalize_exchange_master_dates(_suite_master)
    return _suite_master


def _load_action_set_master_payload():
    global _action_set_master_payload
    if _action_set_master_payload is None:
        with open('server/responses/jp/7.0.0.110/master_action_set_map.json',
                  'rb') as f:
            _action_set_master_payload = json.loads(f.read())
    return _action_set_master_payload


def _action_set_character_ids(value):
    if isinstance(value, list):
        return tuple(
            character_id for character_id in value
            if isinstance(character_id, int)
        )
    if isinstance(value, int):
        return (value,)
    return ()


def _album_action_set_rows(character_id):
    rows = []
    for master in _load_suite_master().get('14', {}).get('1', []):
        action_set_id = master.get('1', 0)
        if action_set_id >= 90000:
            continue
        data = master.get('2', {})
        if character_id in _action_set_character_ids(data.get('3')):
            rows.append(master)
    return rows


def _album_action_set_counts():
    global _action_set_album_counts
    if _action_set_album_counts is not None:
        return _action_set_album_counts
    counts: dict[int, set[int]] = {}
    for master in _load_suite_master().get('14', {}).get('1', []):
        action_set_id = master.get('1', 0)
        if action_set_id >= 90000:
            continue
        for character_id in _action_set_character_ids(
                master.get('2', {}).get('3')):
            counts.setdefault(character_id, set()).add(action_set_id)
    _action_set_album_counts = {
        character_id: len(action_set_ids)
        for character_id, action_set_ids in counts.items()
    }
    return _action_set_album_counts


def _area_action_set_candidates():
    global _area_action_set_ids
    if _area_action_set_ids is not None:
        return _area_action_set_ids
    by_area: dict[int, list[int]] = {}
    for master in _load_suite_master().get('14', {}).get('1', []):
        action_set_id = master.get('1', 0)
        if action_set_id >= 90000:
            continue
        area_id = master.get('2', {}).get('2', 0)
        if not area_id:
            continue
        by_area.setdefault(area_id, []).append(action_set_id)
    _area_action_set_ids = {
        area_id: tuple(sorted(dict.fromkeys(action_set_ids)))
        for area_id, action_set_ids in by_area.items()
    }
    return _area_action_set_ids


def _is_apk_cached_area_action_set_id(action_set_id):
    # 900xx/990xx entries in the bundled area fixture are placeholder/sample
    # talks that are present in the server-side master snapshot but not in the
    # 6.5.2 APK cache.  Returning them makes the client show the "new data"
    # title-return dialog when opening the area map.
    return action_set_id < 90000


def _float32_from_master(value):
    if isinstance(value, float):
        return value
    return struct.unpack('<f', struct.pack('<I', value))[0]


def _add_final_event_story(response, suite_master):
    """Restore event 209, which is absent from the bundled memorial fixture."""
    event_wrapper = suite_master.get('101', {}).get('1', {})
    memorial_wrapper = suite_master.get('1161', {}).get('1', {})
    if (event_wrapper.get('1') != _FINAL_EVENT_ID
            or memorial_wrapper.get('1') != _FINAL_EVENT_ID):
        return response

    event_data = event_wrapper['2']
    if _FINAL_EVENT_ID not in response.past_event_map.entries:
        event = response.past_event_map.entries[_FINAL_EVENT_ID]
        event.event_id = event_data['1']
        event.event_type = event_data['2']
        event.event_name = event_data['3']
        event.asset_bundle_name = event_data['4']
        event.start_at = event_data['5']
        event.end_at = event_data['6']
        event.enable_flg = bool(event_data['7'])
        event.public_start_at = event_data['8']
        event.public_end_at = event_data['9']
        event.distribution_start_at = event_data['10']
        event.distribution_end_at = event_data['11']
        event.bgm_asset_bundle_name = event_data['12']
        event.bgm_file_name = event_data['13']
        event.aggregate_end_at = event_data['14']
        event.event_exchanges_end_at = event_data['15']

    memorial_data = memorial_wrapper['2']
    if _FINAL_EVENT_ID not in response.past_event_story_map.entries:
        story_list = response.past_event_story_map.entries[_FINAL_EVENT_ID]
        for story_data in memorial_data['4']:
            story = story_list.entries.add()
            story.event_id = story_data['1']
            story.seq = story_data['2']
            story.caption = story_data['3']
            story.title = story_data['4']
            story.synopsis = story_data['5']
            story.scenario_id = story_data['6']
            story.cover_image = story_data['7']
            story.background_image = story_data['8']
            story.release_pt = story_data['9']
            story.release_conditions = story_data['10']
            if '11' in story_data:
                story.band_story_id = story_data['11']
            story.background_image_id = story_data['12']

    if _FINAL_EVENT_ID not in response.past_event_character_list_map.entries:
        character_list = (response.past_event_character_list_map
                          .entries[_FINAL_EVENT_ID])
        for character_data in memorial_data['3']:
            character = character_list.entries.add()
            character.event_id = character_data['1']
            character.character_id = character_data['2']
            character.percent = _float32_from_master(character_data['3'])
            character.seq = character_data['4']

    return response


def _load_event_story_memorial_response():
    with open('server/responses/user_event_story_memorial_response.binpb',
              'rb') as f:
        response = (user_event_story_memorial_pb2
                    .UserEventStoryMemorialResponse.FromString(f.read()))
    return _add_final_event_story(response, _load_suite_master())


def _copy_deck(target, deck):
    target.deck_id = deck.deck_id
    target.deck_name = deck.deck_name
    target.leader = deck.leader
    target.member1 = deck.member1
    target.member2 = deck.member2
    target.member3 = deck.member3
    target.member4 = deck.member4
    target.deck_type = deck.deck_type


def _populate_deck_state(response, state: UserState):
    response.user.user_gamedata.main_deck = state.main_deck
    response.ClearField('user_deck_map')
    response.ClearField('user_deck_list')
    for deck in state.decks:
        if deck.deck_type == 'normal':
            _copy_deck(response.user_deck_map.entries[deck.deck_id], deck)
        _copy_deck(response.user_deck_list.entries.add(), deck)


def _populate_gallery_state(response, state: UserState):
    response.ClearField('user_gallery_list')
    for gallery in state.galleries:
        entry = response.user_gallery_list.entries.add()
        entry.situation_id = gallery.situation_id
        entry.illust = gallery.illust
        entry.seq = gallery.seq


def _default_costume_id(character_id):
    return character_id + 1332


def _copy_user_character(target, user_id, character_id, costume_id):
    target.user_id = user_id
    target.character_id = character_id
    target.costume_id = costume_id


def _message_has_field(target, field_name):
    return field_name in target.DESCRIPTOR.fields_by_name


def _deck_member_ids(deck):
    return (
        deck.leader, deck.member1, deck.member2, deck.member3, deck.member4
    )


def _populate_user_gamedata(target, state: UserState):
    target.user_id = state.user_id
    target.rank = state.rank
    target.exp = state.exp
    target.main_deck = state.main_deck
    target.coin = state.coin
    target.paid_star = state.paid_star
    target.free_star = state.free_star
    target.seal = state.michelle_seal
    target.pooled_exp = 0
    target.total_exp = state.total_exp
    target.next_exp = state.next_exp
    profile = state.profile
    target.degree = profile.degree
    target.publish_total_deck_power_flg = (
        profile.publish_total_deck_power_flg
    )
    target.publish_band_rank_flg = profile.publish_band_rank_flg
    target.publish_music_cleared_flg = profile.publish_music_cleared_flg
    target.publish_music_full_combo_flg = (
        profile.publish_music_full_combo_flg
    )
    target.publish_high_score_rating_flg = (
        profile.publish_high_score_rating_flg
    )
    target.publish_updated_at_flg = profile.publish_updated_at_flg
    target.unknown_bool_19 = profile.publish_user_id_flg
    target.unknown_bool_20 = profile.searchable_flg
    target.unknown_bool_21 = profile.friend_applicable_flg
    target.publish_music_all_perfect_flg = (
        profile.publish_music_all_perfect_flg
    )
    target.publish_deck_rank_flg = profile.publish_deck_rank_flg
    target.publish_stage_achievement_conditions_flg = (
        profile.publish_stage_achievement_conditions_flg
    )
    target.publish_stage_friend_ranking_flg = (
        profile.publish_stage_friend_ranking_flg
    )


def _populate_user_registration(target, state: UserState):
    target.user_id = state.user_id
    target.hash = 'ffffffff-ffff-ffff-ffff-ffffffffffff'
    target.user_name = state.profile.user_name
    target.client_version = '6.5.0-SNAPSHOT'
    target.platform = 'Android'
    target.device_model = 'samsung SM-S908N'
    target.operating_system = (
        'Android OS 9 / API-28 (PQ3A.190705.003/G9700FXXU1APFO)'
    )
    target.birth_month = state.profile.birth_month
    target.tutorial_status = 'end'
    target.introduction = state.profile.introduction
    target.unknown_string = 'standard'
    target.tutorial_ended_at = 1517886000000
    target.kakao_id = '900000000000'
    target.kakao_guest_flg = '0'


def _populate_profile_suite_state(response, state: UserState):
    profile = state.profile
    situation = response.user_profile_situation
    situation.user_id = state.user_id
    situation.situation_id = profile.situation_id
    situation.illust = profile.illust
    situation.view_profile_situation_status = (
        profile.view_profile_situation_status
    )

    response.ClearField('user_profile_degree_map')
    for profile_degree_type, degree_id in (
        ('first', profile.degree_id_first),
        ('second', profile.degree_id_second),
    ):
        if not degree_id:
            continue
        degree = response.user_profile_degree_map.entries[profile_degree_type]
        degree.user_id = state.user_id
        degree.profile_degree_type = profile_degree_type
        degree.degree_id = degree_id


def _populate_deco_equipment(target, state: UserState):
    equipment = state.deco_equipment
    target.user_id = state.user_id
    for name in (
        'deco_frame_id',
        'deco_pins_id1',
        'deco_pins_id2',
        'deco_pins_id3',
        'deco_pins_id4',
        'deco_pins_id5',
    ):
        setattr(target, name, getattr(equipment, name))


def _populate_user_gamedata_defaults(target, user_id):
    target.user_id = user_id
    target.rank = 38
    target.exp = 1980
    target.seal = 0
    target.degree = 100
    target.publish_total_deck_power_flg = 0
    target.publish_band_rank_flg = 0
    target.publish_music_cleared_flg = 0
    target.publish_music_full_combo_flg = 0
    target.publish_high_score_rating_flg = 0
    target.pooled_exp = 0
    target.total_exp = 261900
    target.next_exp = 11380
    target.publish_updated_at_flg = 1
    target.unknown_bool_19 = 0
    target.unknown_bool_20 = 1
    target.unknown_bool_21 = 1
    target.start_dash_login_bonus_receive_flg = 1
    target.publish_music_all_perfect_flg = 0
    target.publish_deck_rank_flg = 0
    target.publish_stage_achievement_conditions_flg = 0
    target.publish_stage_friend_ranking_flg = 1


def _populate_updated_user(response, state: UserState):
    cached = _cached_suite_user(state.user_id)
    if cached is not None and response is not cached:
        response.user.CopyFrom(cached.user)
    elif cached is None:
        _populate_user_gamedata_defaults(
            response.user.user_gamedata, state.user_id
        )
    _populate_user_gamedata(response.user.user_gamedata, state)


def _populate_gacha_ticket_state(response, state: UserState):
    response.ClearField('user_gacha_ticket_list')
    for ticket in state.gacha_tickets:
        entry = response.user_gacha_ticket_list.entries.add()
        entry.user_id = state.user_id
        entry.gacha_ticket_id = ticket.gacha_ticket_id
        entry.quantity = ticket.quantity


def _populate_inventory_state(response, state: UserState):
    response.ClearField('user_item_list')
    for item in state.items:
        entry = response.user_item_list.entries.add()
        entry.user_id = state.user_id
        entry.item_id = item.item_id
        entry.quantity = item.quantity

    response.ClearField('user_practice_ticket_list')
    for ticket in state.practice_tickets:
        entry = response.user_practice_ticket_list.entries.add()
        entry.user_id = state.user_id
        entry.practice_ticket_id = ticket.practice_ticket_id
        entry.quantity = ticket.quantity

    response.ClearField('user_live_boost_recovery_item_list')
    for item in state.live_boost_recovery_items:
        entry = response.user_live_boost_recovery_item_list.entries.add()
        entry.user_id = state.user_id
        entry.live_boost_recovery_item_id = (
            item.live_boost_recovery_item_id
        )
        entry.quantity = item.quantity

    if _message_has_field(response, 'user_star_seal'):
        response.user_star_seal.amount = state.star_seal


def _populate_event_state(response, state: UserState):
    response.ClearField('user_event_item_list')
    event_item_rows = {
        item.event_item_id: item.quantity
        for item in state.event_items
    }
    for event_item_id, quantity in tuple(event_item_rows.items()):
        if not _event_master(event_item_id):
            continue
        master_event_item_id = _master_event_item_id(event_item_id)
        if master_event_item_id != event_item_id:
            event_item_rows.setdefault(master_event_item_id, quantity)
    for item in state.event_items:
        if event_item_rows.get(item.event_item_id, 0) != item.quantity:
            continue
        entry = response.user_event_item_list.entries.add()
        entry.user_id = state.user_id
        entry.event_item_id = item.event_item_id
        entry.quantity = item.quantity
    for event_item_id, quantity in sorted(event_item_rows.items()):
        if any(item.event_item_id == event_item_id for item in state.event_items):
            continue
        entry = response.user_event_item_list.entries.add()
        entry.user_id = state.user_id
        entry.event_item_id = event_item_id
        entry.quantity = quantity

    response.ClearField('current_user_event_music_scores_map')
    for score in state.event_music_scores:
        entry = (
            response.current_user_event_music_scores_map
            .entries[score.event_id].entries.add()
        )
        entry.user_id = state.user_id
        entry.event_id = score.event_id
        entry.music_id = score.music_id
        entry.music_difficulty = score.music_difficulty
        entry.solo_high_score = score.solo_high_score
        entry.max_combo = score.max_combo
        entry.clear_status = score.clear_status
        entry.solo_score_rank = _score_rank_for_music(
            score.music_id,
            score.music_difficulty,
            score.solo_high_score,
            fallback=score.solo_score_rank,
        )

    response.ClearField('current_user_event_music_achievements_map')
    for achievement in state.event_music_achievements:
        entry = (
            response.current_user_event_music_achievements_map
            .entries[achievement.event_id].entries.add()
        )
        entry.user_id = state.user_id
        entry.event_id = achievement.event_id
        entry.music_id = achievement.music_id
        entry.achievement_type = achievement.achievement_type
        entry.live_type = achievement.live_type


def _ensure_event_item_entry(response, state: UserState, requested_event_id=0):
    if not _message_has_field(response, 'user_event_item_list'):
        return
    event_id = _current_event_id(state, requested_event_id)
    event_item_id = _master_event_item_id(event_id)
    if not event_item_id:
        return
    if any(
            item.event_item_id == event_item_id
            for item in response.user_event_item_list.entries):
        return
    entry = response.user_event_item_list.entries.add()
    entry.user_id = state.user_id
    entry.event_item_id = event_item_id
    entry.quantity = 0


def _current_event_id(state: UserState, requested_event_id=0):
    if requested_event_id:
        return requested_event_id
    if state.event_items:
        event_item_id = state.event_items[-1].event_item_id
        return _event_id_for_event_item_id(event_item_id) or event_item_id
    return _FINAL_EVENT_ID


def _event_master(event_id):
    wrapper = _load_suite_master().get('101', {}).get('1', {})
    if wrapper.get('1') == event_id:
        return wrapper.get('2', {})
    return {}


def _event_exchange_details(event_id):
    details = _load_suite_master().get('203', {}).get('1', [])
    return tuple(
        detail for detail in details
        if isinstance(detail, dict) and _master_uint(detail, '1') == event_id
    )


def _event_exchange_detail(event_id, seq):
    return next(
        (
            detail for detail in _event_exchange_details(event_id)
            if _master_uint(detail, '2') == seq
        ),
        None,
    )


def _event_exchange_limit(detail):
    if not isinstance(detail, dict) or '8' not in detail:
        return None
    return _master_uint(detail, '8')


def _event_exchange_remain(detail, exchanged_count):
    limit = _event_exchange_limit(detail)
    if limit is None:
        return 999_999
    return max(0, limit - exchanged_count)


def _resource_from_event_exchange_detail(detail):
    resource_type = str(detail.get('4', '') or '').strip()
    if resource_type not in _SUPPORTED_EVENT_REWARD_TYPES:
        return None
    quantity = _master_uint(detail, '6')
    if not quantity:
        return None
    return ResourceState(resource_type, _master_uint(detail, '5'), quantity)


def _event_story_details(event_id):
    wrapper = _load_suite_master().get('1161', {}).get('1', {})
    if wrapper.get('1') != event_id:
        return ()
    event_story_data = wrapper.get('2', {}).get('4', [])
    return tuple(
        detail for detail in event_story_data
        if isinstance(detail, dict)
    )


def _event_story_detail(event_id, seq):
    return next(
        (
            detail for detail in _event_story_details(event_id)
            if _master_uint(detail, '2') == seq
        ),
        None,
    )


def _event_story_rewards(event_id, seq):
    detail = _event_story_detail(event_id, seq)
    if detail is None:
        return ()
    return tuple(
        resource
        for resource in (
            _resource_from_event_story_reward(reward_detail)
            for reward_detail in detail.get('101', [])
        )
        if resource is not None
    )


def _resource_from_event_story_reward(detail):
    if not isinstance(detail, dict):
        return None
    resource_type = str(detail.get('4', '') or '').strip()
    if resource_type not in _SUPPORTED_EVENT_REWARD_TYPES:
        return None
    quantity = _master_uint(detail, '6')
    if not quantity:
        return None
    return ResourceState(resource_type, _master_uint(detail, '5'), quantity)


def _master_event_item_id(event_id):
    for wrapper in _load_suite_master().get('204', {}).get('1', []):
        detail = wrapper.get('2') if isinstance(wrapper, dict) else None
        if isinstance(detail, dict) and _master_uint(detail, '2') == event_id:
            return _master_uint(detail, '1')
    return event_id


def _event_id_for_event_item_id(event_item_id):
    for wrapper in _load_suite_master().get('204', {}).get('1', []):
        detail = wrapper.get('2') if isinstance(wrapper, dict) else None
        if isinstance(detail, dict) and _master_uint(detail, '1') == event_item_id:
            return _master_uint(detail, '2')
    return 0


def _event_item_id_for_user_event(state: UserState, event_id):
    master_event_item_id = _master_event_item_id(event_id)
    available_ids = {item.event_item_id for item in state.event_items}
    if master_event_item_id in available_ids:
        return master_event_item_id
    if event_id in available_ids:
        return event_id
    return master_event_item_id or event_id


def _populate_event_exchange_state(
        response, state: UserState, requested_event_id=0):
    if not _message_has_field(response, 'user_event_exchanges_list'):
        return
    response.ClearField('user_event_exchanges_list')
    event_id = _current_event_id(state, requested_event_id)
    exchange_details = _event_exchange_details(event_id)
    exchange_counts = _state_store.get_event_exchange_counts(
        state.user_id, event_id
    )
    if not exchange_details:
        entry = response.user_event_exchanges_list.entries.add()
        entry.user_id = state.user_id
        entry.event_id = event_id
        entry.seq = 1
        entry.remain = 999
        entry.reset_at = 0
        return

    for index, detail in enumerate(exchange_details, start=1):
        entry = response.user_event_exchanges_list.entries.add()
        entry.user_id = state.user_id
        entry.event_id = event_id
        entry.seq = _master_uint(detail, '2', index)
        entry.remain = _event_exchange_remain(
            detail, exchange_counts.get(entry.seq, 0)
        )
        entry.reset_at = 0


def _populate_event_box_gacha_state(
        response, state: UserState, requested_event_id=0):
    if not _message_has_field(response, 'current_user_event_box_gacha_map'):
        return
    response.ClearField('current_user_event_box_gacha_map')
    event_id = _current_event_id(state, requested_event_id)
    box_gacha = response.current_user_event_box_gacha_map.entries[event_id]
    box_gacha.user_id = state.user_id
    box_gacha.event_box_gacha_id = event_id
    box_gacha.round = 1
    remain = box_gacha.remains.add()
    remain.seq = 1
    remain.remain_count = 999
    box_gacha.pickup_remain.seq = 1
    box_gacha.pickup_remain.remain_count = 1

    if _message_has_field(response, 'user_event_box_gacha_spin_settings'):
        response.user_event_box_gacha_spin_settings.lump_spin_flg = False
        response.user_event_box_gacha_spin_settings.auto_stop_flg = False


def _master_uint(detail, key, default=0):
    try:
        value = detail.get(key, default)
        if value is None:
            return default
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _event_box_gacha_details(event_box_gacha_id):
    event_data = _event_master(event_box_gacha_id) or _event_master(
        _FINAL_EVENT_ID
    )
    details = event_data.get('102', [])
    return tuple(detail for detail in details if isinstance(detail, dict))


def _event_item_id_for_box_gacha(event_box_gacha_id, details):
    if details:
        event_id = _master_uint(details[0], '2', 0)
        if event_id:
            return event_id
    return event_box_gacha_id or _FINAL_EVENT_ID


def _copy_master_event_box_gacha_detail(target, detail):
    target.event_box_gacha_id = _master_uint(detail, '1')
    target.round = _master_uint(detail, '2')
    target.seq = _master_uint(detail, '3')
    target.count = _master_uint(detail, '4')
    target.resource_type = str(detail.get('5', '') or '')
    target.resource_id = _master_uint(detail, '6')
    target.resource_quantity = _master_uint(detail, '7')
    target.pickup_flag = bool(_master_uint(detail, '8'))


def _select_event_box_gacha_drop_details(details, spin_count):
    if not details or spin_count <= 0:
        return ()
    return tuple(details[index % len(details)] for index in range(spin_count))


def _resource_from_event_box_gacha_detail(detail):
    resource_type = str(detail.get('5', '') or '').strip()
    if resource_type not in _SUPPORTED_EVENT_REWARD_TYPES:
        return None
    quantity = _master_uint(detail, '7')
    if not quantity:
        return None
    return ResourceState(resource_type, _master_uint(detail, '6'), quantity)


def _event_item_quantity(state: UserState, event_item_id):
    for item in state.event_items:
        if item.event_item_id == event_item_id:
            return max(0, item.quantity)
    return 0


def _master_resource(detail):
    if not isinstance(detail, dict):
        return None
    resource_type = str(detail.get('1', '') or '').strip()
    if resource_type not in _SUPPORTED_EVENT_REWARD_TYPES:
        return None
    quantity = _master_uint(detail, '3') or _master_uint(detail, '5')
    if not quantity:
        return None
    return ResourceState(resource_type, _master_uint(detail, '2'), quantity)


def _exchange_details():
    return tuple(
        item.get('2', item)
        for item in _load_suite_master().get('1200', {}).get('1', [])
        if isinstance(item, dict)
    )


def _exchange_detail(exchanges_id):
    return next(
        (
            detail for detail in _exchange_details()
            if _master_uint(detail, '1') == exchanges_id
        ),
        None,
    )


def _exchange_limit(detail):
    if not isinstance(detail, dict):
        return None
    resource_type = str(detail.get('4', '') or '').strip()
    if resource_type == 'situation':
        return 1
    return None


def _exchange_remain(detail, exchanged_count):
    limit = _exchange_limit(detail)
    if limit is None:
        return 999_999
    return max(0, limit - exchanged_count)


def _resource_from_exchange_detail(detail):
    if not isinstance(detail, dict):
        return None
    resource_type = str(detail.get('4', '') or '').strip()
    if resource_type not in _SUPPORTED_EVENT_REWARD_TYPES:
        return None
    quantity = _master_uint(detail, '6')
    if not quantity:
        return None
    return ResourceState(resource_type, _master_uint(detail, '5'), quantity)


def _exchange_cost(detail):
    return _master_uint(detail, '7')


def _limited_exchange_periods():
    periods = {}
    for item in _load_suite_master().get('1210', {}).get('1', ()):
        if not isinstance(item, dict):
            continue
        detail = item.get('2', item)
        if not isinstance(detail, dict):
            continue
        limited_exchanges_id = _master_uint(detail, '1')
        if not limited_exchanges_id:
            continue
        periods[limited_exchanges_id] = detail
    return periods


def _limited_exchange_detail_groups():
    groups = {}
    for item in _load_suite_master().get('1211', {}).get('1', ()):
        if not isinstance(item, dict):
            continue
        limited_exchanges_id = _master_uint(item, '1')
        wrapper = item.get('2', {})
        details = wrapper.get('1', ()) if isinstance(wrapper, dict) else ()
        if not limited_exchanges_id or not isinstance(details, list):
            continue
        groups[limited_exchanges_id] = tuple(
            detail for detail in details if isinstance(detail, dict)
        )
    return groups


def _populate_limited_exchange_state(response, state: UserState):
    if not _message_has_field(response, 'user_limited_exchanges_list'):
        return
    response.ClearField('user_limited_exchanges_list')
    periods = _limited_exchange_periods()
    detail_groups = _limited_exchange_detail_groups()
    if not periods or not detail_groups:
        return

    now_ms = int(time.time() * 1000)
    default_reset_at = now_ms + 30 * 24 * 60 * 60 * 1000
    for limited_exchanges_id, details in detail_groups.items():
        period = periods.get(limited_exchanges_id, {})
        reset_at = max(_master_uint(period, '3'), default_reset_at)
        for detail in details:
            limited_exchanges_detail_id = _master_uint(detail, '2')
            if not limited_exchanges_detail_id:
                continue
            entry = response.user_limited_exchanges_list.entries.add()
            entry.user_id = state.user_id
            entry.limited_exchanges_id = limited_exchanges_id
            entry.limited_exchanges_detail_id = limited_exchanges_detail_id
            entry.remain = 1
            entry.reset_at = reset_at


def _populate_exchange_state(response, state: UserState):
    if not _message_has_field(response, 'user_exchanges_list'):
        return
    response.ClearField('user_exchanges_list')
    exchanged_counts = {
        entry.exchanges_id: max(0, entry.exchanged_count)
        for entry in state.exchanges
    }
    for detail in _exchange_details():
        exchanges_id = _master_uint(detail, '1')
        if not exchanges_id:
            continue
        entry = response.user_exchanges_list.entries.add()
        entry.user_id = state.user_id
        entry.exchanges_id = exchanges_id
        entry.remain = _exchange_remain(
            detail, exchanged_counts.get(exchanges_id, 0)
        )
        entry.reset_at = _master_uint(detail, '8')


def _active_miracle_ticket_exchange_masters():
    now_ms = int(time.time() * 1000)
    active = []
    for item in _load_suite_master().get('73', {}).get('1', ()):
        if not isinstance(item, dict):
            continue
        detail = item.get('2', item)
        if not isinstance(detail, dict):
            continue
        exchange_id = _master_uint(detail, '1')
        ticket_id = _master_uint(detail, '2')
        if not exchange_id or not ticket_id:
            continue
        start_at = _master_uint(detail, '6')
        end_at = _master_uint(detail, '7')
        if start_at and start_at > now_ms:
            continue
        exchange_type = str(detail.get('3', '') or '')
        if exchange_type == 'fixed_end' and end_at and end_at < now_ms:
            continue
        if exchange_type == 'fixed_end' and not end_at:
            continue
        if exchange_type and exchange_type not in {
                'fixed_end', 'variable_end', 'rookie_variable_end'}:
            continue
        duration_minutes = _master_uint(detail, '8') or 43200
        active.append((exchange_id, ticket_id, duration_minutes))
    return tuple(active)


def _populate_exchange_selection_state(response, state: UserState):
    if not _message_has_field(response, 'user_miracle_ticket_map'):
        return
    active_ticket_exchanges = _active_miracle_ticket_exchange_masters()
    if not response.user_miracle_ticket_map.entries and not active_ticket_exchanges:
        ticket = response.user_miracle_ticket_map.entries[4]
        ticket.user_id = state.user_id
        ticket.miracle_ticket_id = 4
        ticket.quantity = 1
        ticket.exchange_end_at = (int(time.time()) + 86400 * 30) * 1000

    now_ms = int(time.time() * 1000)
    for exchange_id, ticket_id, duration_minutes in active_ticket_exchanges:
        ticket = response.user_miracle_ticket_map.entries[ticket_id]
        ticket.user_id = state.user_id
        ticket.miracle_ticket_id = ticket_id
        ticket.quantity = max(1, ticket.quantity)
        exchange_end_at = now_ms + duration_minutes * 60 * 1000
        ticket.exchange_end_at = max(ticket.exchange_end_at, exchange_end_at)
        if _message_has_field(response, 'user_miracle_ticket_exchanges_map'):
            exchange = response.user_miracle_ticket_exchanges_map.entries[
                ticket_id
            ]
            exchange.user_id = state.user_id
            exchange.miracle_ticket_id = ticket_id
            exchange.user_miracle_ticket_exchange_count_map.entries[
                exchange_id
            ] = exchange.user_miracle_ticket_exchange_count_map.entries.get(
                exchange_id, 0
            )

    if _message_has_field(response, 'user_miracle_ticket_exchanges_map'):
        for ticket_id in list(response.user_miracle_ticket_map.entries):
            exchange = response.user_miracle_ticket_exchanges_map.entries[
                ticket_id
            ]
            exchange.user_id = state.user_id
            exchange.miracle_ticket_id = ticket_id

    if _message_has_field(
            response, 'user_not_have_view_exchanges_miracle_ticket_id_list'):
        response.user_not_have_view_exchanges_miracle_ticket_id_list.SetInParent()


def _panel_mission_masters():
    master = _load_suite_master().get('700', {}).get('1', {})
    if isinstance(master, dict):
        return (master,)
    if isinstance(master, list):
        return tuple(
            item.get('2', item) for item in master if isinstance(item, dict)
        )
    return ()


def _panel_mission_master(panel_mission_id):
    return next(
        (
            item for item in _panel_mission_masters()
            if _master_uint(item, '1') == panel_mission_id
        ),
        None,
    )


def _panel_mission_boards(panel_mission_id):
    master = _panel_mission_master(panel_mission_id)
    if master is None:
        return ()
    details = master.get('2', {}).get('6', [])
    return tuple(item for item in details if isinstance(item, dict))


def _panel_board(panel_mission_id, board_seq):
    return next(
        (
            board for board in _panel_mission_boards(panel_mission_id)
            if _master_uint(board, '1') == board_seq
        ),
        None,
    )


def _panel_board_reward(panel_mission_id, board_seq):
    board = _panel_board(panel_mission_id, board_seq)
    if board is None:
        return None
    return _master_resource(board.get('2', {}).get('1', {}))


def _panel_board_panel_seqs(panel_mission_id, board_seq):
    board = _panel_board(panel_mission_id, board_seq)
    panels = [] if board is None else board.get('2', {}).get('2', [])
    return tuple(
        _master_uint(panel, '1')
        for panel in panels
        if isinstance(panel, dict) and _master_uint(panel, '1')
    )


def _panel_board_state_map(state: UserState, panel_mission_id):
    return {
        board.board_seq: board.reward_received
        for board in state.panel_missions
        if board.panel_mission_id == panel_mission_id
    }


def _next_panel_reward_board(state: UserState, panel_mission_id):
    received_map = _panel_board_state_map(state, panel_mission_id)
    for board in _panel_mission_boards(panel_mission_id):
        board_seq = _master_uint(board, '1')
        if board_seq and not received_map.get(board_seq, False):
            return board_seq
    return 0


def _populate_panel_mission_state(response, state: UserState):
    if not _message_has_field(response, 'user_panel_mission_list'):
        return
    response.ClearField('user_panel_mission_list')
    for master in _panel_mission_masters():
        panel_mission_id = _master_uint(master, '1')
        if not panel_mission_id:
            continue
        mission = response.user_panel_mission_list.entries.add()
        mission.panel_mission_id = panel_mission_id
        received_map = _panel_board_state_map(state, panel_mission_id)
        for board in master.get('2', {}).get('6', []):
            if not isinstance(board, dict):
                continue
            board_seq = _master_uint(board, '1')
            if not board_seq:
                continue
            board_status = (
                'end' if received_map.get(board_seq, False) else 'complete'
            )
            board_entry = mission.user_panel_mission_board_list.add()
            board_entry.panel_seq = board_seq
            board_entry.mission_progress_type = board_status
            for panel in board.get('2', {}).get('2', []):
                if not isinstance(panel, dict):
                    continue
                panel_seq = _master_uint(panel, '1')
                if not panel_seq:
                    continue
                panel_entry = board_entry.user_panel_mission_panel_list.add()
                panel_entry.panel_seq = panel_seq
                panel_entry.progress = _master_uint(
                    panel.get('2', {}), '4', 1
                )
                panel_entry.mission_progress_type = board_status


def _populate_area_item_state(response, state: UserState):
    response.ClearField('user_area_item_map')
    for item in state.area_items:
        entry = response.user_area_item_map.entries[item.area_item_id]
        entry.user_id = state.user_id
        entry.area_item_id = item.area_item_id
        entry.area_item_category = item.area_item_category
        entry.level = item.level


def _populate_login_bonus_state(response, state: UserState):
    response.ClearField('user_login_bonus_map')
    for bonus in state.login_bonuses:
        if bonus.last_received_on == today_kst_iso():
            continue
        entry = response.user_login_bonus_map.entries[bonus.login_bonus_id]
        entry.user_id = state.user_id
        entry.login_bonus_id = bonus.login_bonus_id
        entry.days = bonus.days


def _populate_user_live_boost(target, state: UserState):
    now = int(time.time())
    target.user_id = state.user_id
    target.live_boost = state.live_boost
    target.server_date = now * 1000
    if state.live_boost < LIVE_BOOST_NATURAL_MAX:
        target.recover_at = (
            state.live_boost_updated_at + LIVE_BOOST_RECOVERY_SECONDS
        ) * 1000
    else:
        target.recover_at = 0
    target.live_boost_bonus_type = 'default'


def _populate_live_boost_use_limit_state(response):
    if _message_has_field(response, 'user_live_boost_use_bonus_limit_list'):
        response.user_live_boost_use_bonus_limit_list.SetInParent()
    if not _message_has_field(response, 'user_live_boost_use_full'):
        return
    # The 6.5.x client treats "full consume" (10 live boosts at once) as a
    # daily-limited option when this state is absent or stale.  The local server
    # intentionally allows repeated 10-boost solo lives, so always return a
    # fresh zero-count state after suite refreshes and live-result updates.
    response.user_live_boost_use_full.daily_use_full_count = 0
    response.user_live_boost_use_full.reset_time = (
        int(time.time() * 1000) + 24 * 60 * 60 * 1000
    )


def _populate_enabled_area_items(response, state: UserState):
    if not hasattr(response, 'enabled_user_area_items'):
        return
    response.ClearField('enabled_user_area_items')
    owned_by_category = {
        item.area_item_category: item for item in state.area_items
    }
    for placement in state.area_item_placements:
        entry = response.enabled_user_area_items.entries.add()
        entry.user_id = state.user_id
        entry.area_item_id = placement.area_item_id
        entry.area_item_category = placement.area_item_category
        owned = owned_by_category.get(placement.area_item_category)
        entry.level = owned.level if owned is not None else 1


def _populate_mission_state(response, state: UserState):
    response.ClearField('user_mission_map')
    for mission in state.missions:
        entry = response.user_mission_map.entries[
            mission.mission_id
        ].entries.add()
        entry.user_id = state.user_id
        entry.mission_id = mission.mission_id
        entry.seq = mission.seq
        entry.progress = mission.progress
        entry.mission_progress_type = mission.mission_progress_type
        entry.mission_group_id = mission.mission_group_id
    response.user_mission_map.limited_last_updated_at = int(
        time.time() * 1000
    )


def _master_band_rank_max(band_id):
    rows = next(
        (
            wrapper.get('2', {}).get('2', [])
            for wrapper in _load_suite_master().get('70', {}).get('1', [])
            if wrapper.get('1') == band_id
        ),
        [],
    )
    if isinstance(rows, dict):
        rows = [rows]
    return max((row.get('2', 1) for row in rows), default=1)


def _computed_band_rank(state: UserState, band_id):
    # The local suite exposes every released band story as read and owns the
    # full released member pool.  Mirror that all-content fixture by using the
    # highest rank represented in the bundled band-rank master table.
    return _master_band_rank_max(band_id)


def _copy_band_rank(target, state: UserState, band_id, add_exp=0):
    band_rank = _computed_band_rank(state, band_id)
    max_rank = _master_band_rank_max(band_id)
    target.user_id = state.user_id
    target.band_id = band_id
    target.band_rank = band_rank
    target.exp = 0
    target.add_exp = add_exp
    target.pooled_exp = 0
    target.total_exp = max(0, band_rank - 1) * _BAND_RANK_EXP_PER_LEVEL
    target.next_exp = 0 if band_rank >= max_rank else _BAND_RANK_EXP_PER_LEVEL


def _populate_band_rank_state(response, state: UserState):
    if not _message_has_field(response, 'user_band_rank_map'):
        return
    response.ClearField('user_band_rank_map')
    for band_id in _BAND_IDS:
        _copy_band_rank(response.user_band_rank_map.entries[band_id],
                        state, band_id)


def _populate_resource_list(target, resources):
    target.ClearField('entries')
    for value in resources:
        entry = target.entries.add()
        entry.resource_type = value.resource_type
        entry.resource_id = value.resource_id
        entry.quantity = value.quantity
        entry.lb_bonus = value.lb_bonus


def _populate_degree_state(response, state: UserState):
    if not _message_has_field(response, 'user_degree_map'):
        return
    response.ClearField('user_degree_map')
    for degree_id in state.degrees:
        entry = response.user_degree_map.entries[degree_id]
        entry.user_id = state.user_id
        entry.degree_id = degree_id


def _populate_present_count(response, state: UserState):
    response.user_resource_count.present = len(state.presents)


def _populate_user_situation(
        target, user_id, master_situation, duplicate_count=0):
    data = master_situation['2']
    target.user_id = user_id
    target.situation_id = master_situation['1']
    target.level = data['11'] + (data['15']['3'] if '15' in data else 0)
    target.exp = 0
    target.created_at = data['17']
    target.add_exp = 0
    target.training_status = 'done' if '15' in data else 'not_doing'
    target.duplicate_count = duplicate_count
    target.illust = 'after_training' if '15' in data else 'normal'
    target.skill_exp = 0
    target.skill_level = 5


def _populate_owned_situation_state(response, state: UserState):
    if not _message_has_field(response, 'user_situation_map'):
        return
    duplicate_counts = {
        item.situation_id: item.duplicate_count
        for item in state.situation_duplicates
    }
    response.ClearField('user_situation_map')
    for master_situation in _load_suite_master()['4']['1']:
        if master_situation['2'].get('17', 0) >= _LOCAL_SITUATION_RELEASE_CUTOFF_MS:
            continue
        _populate_user_situation(
            response.user_situation_map.entries[master_situation['1']],
            state.user_id,
            master_situation,
            duplicate_counts.get(master_situation['1'], 0),
        )


def _populate_character_costume_state(response, state: UserState):
    response.ClearField('user_character_map')
    costume_overrides = {
        costume.character_id: costume.costume_id
        for costume in state.character_costumes
    }
    for character_id in range(1, 36):
        _copy_user_character(
            response.user_character_map.entries[character_id],
            state.user_id,
            character_id,
            costume_overrides.get(character_id, _default_costume_id(character_id)),
        )


def _populate_empty_friend_detail(detail):
    detail.application_map.SetInParent()
    detail.approval_map.SetInParent()
    detail.friend_map.SetInParent()
    detail.application_limit = 50
    detail.approval_limit = 50
    detail.friend_limit = 50


def _populate_live_state(response, state: UserState):
    _populate_updated_user(response, state)
    _populate_owned_situation_state(response, state)
    _populate_character_costume_state(response, state)
    _populate_inventory_state(response, state)
    _populate_event_state(response, state)
    _populate_exchange_state(response, state)
    _populate_exchange_selection_state(response, state)
    _populate_limited_exchange_state(response, state)
    _populate_event_exchange_state(response, state)
    _populate_event_box_gacha_state(response, state)
    _populate_area_item_state(response, state)
    _populate_degree_state(response, state)
    _populate_login_bonus_state(response, state)
    _populate_enabled_area_items(response, state)
    _populate_mission_state(response, state)
    _populate_panel_mission_state(response, state)
    _populate_band_rank_state(response, state)
    _populate_user_live_boost(response.user_live_boost, state)
    _populate_live_boost_use_limit_state(response)
    _populate_high_score_rating(response, state)
    _populate_band_deck_rating(response, state)

    response.ClearField('user_music_score_map')
    for score in state.music_scores:
        entry = response.user_music_score_map.entries[score.music_id].entries.add()
        entry.user_id = state.user_id
        entry.music_id = score.music_id
        entry.music_difficulty = score.music_difficulty
        entry.solo_high_score = score.solo_high_score
        entry.max_combo = score.max_combo
        entry.solo_score_rank = _score_rank_for_music(
            score.music_id,
            score.music_difficulty,
            score.solo_high_score,
            fallback=score.solo_score_rank,
        )
        entry.clear_status = score.clear_status

    response.ClearField('user_music_achievement_map')
    for achievement in state.music_achievements:
        entry = (response.user_music_achievement_map
                 .entries[achievement.music_id].entries.add())
        entry.user_id = state.user_id
        entry.music_id = achievement.music_id
        entry.achievement_type = achievement.achievement_type


def _cached_suite_user(user_id):
    if (_suite_user is not None
            and _suite_user.user.user_registration.user_id == user_id):
        return _suite_user
    return None


def _sync_cached_deck_state(user_id, state):
    cached = _cached_suite_user(user_id)
    if cached is not None:
        _populate_deck_state(cached, state)
        _populate_owned_situation_state(cached, state)
        _populate_band_deck_rating(cached, state)


def _sync_cached_gallery_state(user_id, state):
    cached = _cached_suite_user(user_id)
    if cached is not None:
        _populate_gallery_state(cached, state)


def _sync_cached_character_costume_state(user_id, state):
    cached = _cached_suite_user(user_id)
    if cached is None:
        return
    overrides = {
        item.character_id: item.costume_id
        for item in state.character_costumes
    }
    for character_id, character in cached.user_character_map.entries.items():
        character.costume_id = overrides.get(
            character_id, _default_costume_id(character_id)
        )


def _sync_cached_live_state(user_id, state):
    cached = _cached_suite_user(user_id)
    if cached is not None:
        _populate_live_state(cached, state)


def _sync_cached_gacha_state(user_id, state):
    cached = _cached_suite_user(user_id)
    if cached is None:
        return
    _populate_user_gamedata(cached.user.user_gamedata, state)
    _populate_character_costume_state(cached, state)
    _populate_owned_situation_state(cached, state)
    _populate_gacha_ticket_state(cached, state)
    _populate_inventory_state(cached, state)
    _populate_present_count(cached, state)
    _populate_high_score_rating(cached, state)
    _populate_band_deck_rating(cached, state)
    duplicate_counts = {
        item.situation_id: item.duplicate_count
        for item in state.situation_duplicates
    }
    situation_master = _situation_master_map()
    for situation_id, duplicate_count in duplicate_counts.items():
        master_situation = situation_master.get(situation_id)
        if master_situation is not None:
            _populate_user_situation(
                cached.user_situation_map.entries[situation_id],
                state.user_id,
                master_situation,
                duplicate_count,
            )
        elif situation_id in cached.user_situation_map.entries:
            cached.user_situation_map.entries[
                situation_id
            ].duplicate_count = duplicate_count


def _sync_cached_area_item_state(user_id, state):
    cached = _cached_suite_user(user_id)
    if cached is None:
        return
    _populate_user_gamedata(cached.user.user_gamedata, state)
    _populate_inventory_state(cached, state)
    _populate_area_item_state(cached, state)
    _populate_enabled_area_items(cached, state)
    _populate_band_deck_rating(cached, state)


def _sync_cached_profile_state(user_id, state):
    cached = _cached_suite_user(user_id)
    if cached is None:
        return
    _populate_user_registration(cached.user.user_registration, state)
    _populate_user_gamedata(cached.user.user_gamedata, state)
    _populate_profile_suite_state(cached, state)


def _sync_cached_deco_equipment(user_id, state):
    cached = _cached_suite_user(user_id)
    if cached is not None:
        _populate_deco_equipment(cached.user_deco_equipment, state)


def _protobuf_field_numbers(payload):
    """Read top-level protobuf field numbers without assuming one body type."""
    fields = set()
    offset = 0
    size = len(payload)

    def read_varint(position):
        value = 0
        shift = 0
        while position < size and shift < 70:
            byte = payload[position]
            position += 1
            value |= (byte & 0x7f) << shift
            if not byte & 0x80:
                return value, position
            shift += 7
        abort(400, description='malformed protobuf request')

    while offset < size:
        key, offset = read_varint(offset)
        field_number = key >> 3
        wire_type = key & 7
        if not field_number:
            abort(400, description='malformed protobuf request')
        fields.add(field_number)
        if wire_type == 0:
            _, offset = read_varint(offset)
        elif wire_type == 1:
            offset += 8
        elif wire_type == 2:
            length, offset = read_varint(offset)
            offset += length
        elif wire_type == 5:
            offset += 4
        else:
            abort(400, description='unsupported protobuf wire type')
        if offset > size:
            abort(400, description='truncated protobuf request')
    return fields


def _master_gacha(gacha_id):
    suite_master = _load_suite_master()
    return next(
        (entry['2'] for entry in suite_master['7']['1']
         if entry['1'] == gacha_id),
        None,
    )


def _master_music(music_id):
    return next(
        (entry for entry in _load_suite_master()['1']['1']
         if entry['1'] == music_id),
        None,
    )


def _master_situation(situation_id):
    return next(
        (entry for entry in _load_suite_master()['4']['1']
         if entry['1'] == situation_id),
        None,
    )


def _populate_user_profile(target, state: UserState):
    profile = state.profile
    target.user_id = state.user_id
    target.user_name = profile.user_name
    target.rank = state.rank
    target.degree = profile.degree
    target.introduction = profile.introduction
    for name in (
        'publish_total_deck_power_flg',
        'publish_band_rank_flg',
        'publish_music_cleared_flg',
        'publish_music_full_combo_flg',
        'publish_high_score_rating_flg',
        'publish_user_id_flg',
        'searchable_flg',
        'publish_updated_at_flg',
        'friend_applicable_flg',
        'publish_music_all_perfect_flg',
        'publish_deck_rank_flg',
        'publish_stage_achievement_conditions_flg',
        'publish_stage_friend_ranking_flg',
    ):
        setattr(target, name, getattr(profile, name))

    main_deck = next(
        (deck for deck in state.decks
         if deck.deck_type == 'normal' and deck.deck_id == state.main_deck),
        None,
    )
    duplicate_counts = {
        item.situation_id: item.duplicate_count
        for item in state.situation_duplicates
    }
    if main_deck is not None:
        _copy_deck(target.main_user_deck, main_deck)
        for situation_id in (
            main_deck.leader,
            main_deck.member1,
            main_deck.member2,
            main_deck.member3,
            main_deck.member4,
        ):
            master = _master_situation(situation_id)
            if master is None:
                continue
            _populate_user_situation(
                target.main_deck_user_situations.entries.add(),
                state.user_id,
                master,
                duplicate_counts.get(situation_id, 0),
            )

    _populate_enabled_area_items(target, state)

    # The profile controller assumes all of these reference-type resources
    # exist, even when a local account has no matching scores yet.  Emit
    # stable placeholders and computed local ratings so the client can
    # iterate them without hitting protobuf-net null arrays.
    for band_id in _BAND_IDS:
        target.band_rank_map.entries[band_id] = _computed_band_rank(
            state, band_id
        )
    target.cleared_music_count_map.SetInParent()
    target.full_combo_music_count_map.SetInParent()
    _populate_high_score_rating(target, state)
    target.user_twitter.SetInParent()
    target.all_perfect_music_count_map.SetInParent()
    _populate_profile_deck_total_rating(target, state)
    target.stage_challenge_achievement_conditions_map.SetInParent()

    situation = target.user_profile_situation
    situation.user_id = state.user_id
    situation.situation_id = profile.situation_id
    situation.illust = profile.illust
    situation.view_profile_situation_status = (
        profile.view_profile_situation_status
    )
    for profile_degree_type, degree_id in (
        ('first', profile.degree_id_first),
        ('second', profile.degree_id_second),
    ):
        if not degree_id:
            continue
        degree = target.user_profile_degree_map.entries[profile_degree_type]
        degree.user_id = state.user_id
        degree.profile_degree_type = profile_degree_type
        degree.degree_id = degree_id
    target.search_success_flg = True


def _master_area_item(area_item_id):
    return next(
        (entry['2'] for entry in _load_suite_master()['9']['1']
         if entry['1'] == area_item_id),
        None,
    )


def _master_login_bonus(login_bonus_id):
    return next(
        (entry['2'] for entry in _load_suite_master()['41']['1']
         if entry['1'] == login_bonus_id),
        None,
    )


def _master_live_boost_recovery_amount(recovery_item_id):
    master = next(
        (
            entry['2'] for entry in _load_suite_master().get('58', {}).get('1', [])
            if entry['1'] == recovery_item_id
        ),
        None,
    )
    if master is None:
        return 10
    return master.get('4', 10)


def _login_bonus_cycle_length(master_login_bonus):
    rewards = master_login_bonus.get('7', [])
    if isinstance(rewards, dict):
        rewards = [rewards]
    return max((reward.get('2', 0) for reward in rewards), default=0)


def _login_bonus_rewards(master_login_bonus, day):
    rewards = master_login_bonus.get('7', [])
    if isinstance(rewards, dict):
        rewards = [rewards]
    return tuple(
        ResourceState(
            resource_type=reward.get('3', ''),
            resource_id=reward.get('4', 0),
            quantity=reward.get('5', 0),
            lb_bonus=reward.get('7', 0),
        )
        for reward in rewards
        if reward.get('2') == day
    )


def _master_shoplist(shop_list_id):
    return next(
        (entry['2'] for entry in _load_suite_master()['13']['1']
         if entry['1'] == shop_list_id),
        None,
    )


def _master_shop_item_costs(master_shoplist):
    entries = master_shoplist.get('7', {}).get('1', [])
    if isinstance(entries, dict):
        entries = [entries]
    return tuple(
        ResourceState(
            resource_type=entry['2'],
            resource_id=entry.get('1', 0),
            quantity=entry.get('3', 0),
            lb_bonus=entry.get('4', 0),
        )
        for entry in entries
        if entry.get('3', 0)
    )


def _area_shop_item_unlocked(master_shoplist, state: UserState):
    now = int(time.time() * 1000)
    if master_shoplist.get('11', 0) > now:
        return False
    if master_shoplist.get('12', now + 1) < now:
        return False
    conditions = master_shoplist.get('10', {}).get('1', [])
    if isinstance(conditions, dict):
        conditions = [conditions]
    for condition in conditions:
        band_id = condition.get('1', 0)
        required_band_rank = condition.get('2', 0)
        if band_id in _BAND_IDS and required_band_rank:
            if _computed_band_rank(state, band_id) < required_band_rank:
                return False
            continue
        # Unknown local condition types are treated as satisfied: the bundled
        # fixture already exposes released stories and content as available.
    return True


def _area_shop_rows(state: UserState, shop_id):
    area_items = {
        entry['1']: entry['2']
        for entry in _load_suite_master()['9']['1']
    }
    by_category = {}
    for wrapper in _load_suite_master()['13']['1']:
        master = wrapper['2']
        if master.get('2') != shop_id:
            continue
        area_item = area_items.get(master.get('5'))
        if area_item is None or area_item.get('3', 0) < 1:
            continue
        by_category.setdefault(area_item['2'], []).append(
            (area_item['3'], master, area_item)
        )

    owned = {item.area_item_category: item for item in state.area_items}
    rows = []
    for category, candidates in by_category.items():
        candidates.sort(key=lambda value: value[0])
        current = owned.get(category)
        if current is None:
            _level, target_master, target_area_item = candidates[0]
            status = (
                'purchase' if _area_shop_item_unlocked(target_master, state)
                else 'not_have'
            )
        else:
            next_entry = next(
                (value for value in candidates
                 if value[0] == current.level + 1),
                None,
            )
            if next_entry is None:
                current_entry = next(
                    (value for value in candidates
                     if value[2]['1'] == current.area_item_id),
                    None,
                )
                if current_entry is None:
                    continue
                _level, target_master, target_area_item = current_entry
                status = 'sold_out'
            else:
                _level, target_master, target_area_item = next_entry
                status = (
                    'upgrade' if _area_shop_item_unlocked(target_master, state)
                    else 'not_have'
                )
        rows.append((target_master, target_area_item, status))
    return sorted(rows, key=lambda value: (value[0].get('4', 0), value[1]['2']))


def _copy_user_shoplist(target, user_id, master, area_item, status):
    target.user_id = user_id
    target.shop_id = master['2']
    target.area_item_id = area_item['1']
    target.area_item_category = area_item['2']
    target.area_item_level = area_item['3']
    target.status = status
    target.shop_category = master.get('3', '')
    target.seq = master.get('4', 0)
    target.amount = master.get('6', 0)
    target.shop_list_id = master['1']


def _populate_user_shoplist(target, state, shop_id):
    target.ClearField('entries')
    for master, area_item, status in _area_shop_rows(state, shop_id):
        _copy_user_shoplist(
            target.entries.add(), state.user_id,
            master, area_item, status,
        )


def _populate_area_backstage_state(response):
    if response.backstage.entries or response.user_lottery_selected_backstage_talk_set_map.entries:
        return
    if os.environ.get('KRDORI_DYNAMIC_BACKSTAGE', '').lower() not in {
            '1', 'true', 'yes'}:
        return
    talk_sets_by_seq = {}
    for wrapper in _load_suite_master().get('96', {}).get('1', []):
        data = wrapper.get('2', {})
        lottery_seq = data.get('11', 0)
        if not lottery_seq:
            continue
        talk_sets_by_seq.setdefault(lottery_seq, []).append(wrapper['1'])
    if not talk_sets_by_seq:
        return

    response.ClearField('backstage')
    response.ClearField('user_lottery_selected_backstage_talk_set_map')
    response.backstage.is_force_move_backstage = False

    for lottery_seq in sorted(talk_sets_by_seq):
        talk_set_ids = sorted(talk_sets_by_seq[lottery_seq])[:30]
        lottery_array = (
            response.user_lottery_selected_backstage_talk_set_map
            .entries[lottery_seq]
        )
        for offset in range(0, len(talk_set_ids), 3):
            selected = user_backstage_talk_set_pb2.UserBackstageTalkSetList()
            for talk_set_id in talk_set_ids[offset:offset + 3]:
                entry = selected.entries.add()
                entry.backstage_talk_set_id = talk_set_id
                entry.lottery_seq = lottery_seq
            lottery_array.entries.add().CopyFrom(selected)
            if lottery_seq == 13:
                response.backstage.entries.add().CopyFrom(selected)

    if not response.backstage.entries:
        first_seq = sorted(talk_sets_by_seq)[0]
        response.backstage.entries.extend(
            response.user_lottery_selected_backstage_talk_set_map
            .entries[first_seq].entries
        )


def _populate_backstage_talk_read_history(response):
    response.ClearField('user_backstage_talk_set_read_history_map')
    for master in _load_suite_master().get('96', {}).get('1', []):
        response.user_backstage_talk_set_read_history_map.entries[
            master['1']
        ] = 'already_read'


def _backstage_talk_set_map_response():
    with open('server/responses/user_area.binpb', 'rb') as f:
        area_response = user_area_pb2.UserArea.FromString(f.read())
    _populate_area_backstage_state(area_response)
    response = user_backstage_talk_set_pb2.UserLotterySelectedBackstageTalkSetMap()
    response.CopyFrom(
        area_response.user_lottery_selected_backstage_talk_set_map
    )
    return response


def _user_area_response_from_state(state: UserState):
    with open('server/responses/user_area.binpb', 'rb') as f:
        response = user_area_pb2.UserArea.FromString(f.read())
    action_set_status = {
        action_set.action_set_id: action_set.status
        for action_set in state.action_sets
    }
    for area in response.user_area_map.entries.values():
        base_action_sets = [
            (action_set.action_set_id, action_set.status)
            for action_set in area.action_sets
            if _is_apk_cached_area_action_set_id(action_set.action_set_id)
        ]
        area.ClearField('action_sets')
        for action_set_id, status in base_action_sets:
            action_set = area.action_sets.add()
            action_set.action_set_id = action_set_id
            action_set.status = status
        base_count = len(area.action_sets)
        read_count = 0
        existing_action_set_ids = set()
        for action_set in area.action_sets:
            existing_action_set_ids.add(action_set.action_set_id)
            if action_set.status == 'can_not_read':
                continue
            status = action_set_status.get(action_set.action_set_id)
            if status:
                action_set.status = status
            if action_set.status == 'already_read':
                read_count += 1
        if base_count and read_count and _AREA_ACTION_SET_REFRESH_EXTRA:
            target_count = min(
                _AREA_ACTION_SET_MAX_VISIBLE,
                base_count + min(read_count, _AREA_ACTION_SET_REFRESH_EXTRA),
            )
            for action_set_id in _area_action_set_candidates().get(
                    area.area_id, ()):
                if len(area.action_sets) >= target_count:
                    break
                if action_set_id in existing_action_set_ids:
                    continue
                action_set = area.action_sets.add()
                action_set.action_set_id = action_set_id
                action_set.status = action_set_status.get(
                    action_set_id, 'unread'
                )
                existing_action_set_ids.add(action_set_id)
        area.ClearField('area_item_ids')
    for placement in state.area_item_placements:
        area = response.user_area_map.entries[placement.area_id]
        area.area_id = placement.area_id
        area.area_item_ids.append(placement.area_item_id)
    response.user_season.season_id = 0
    response.user_season.ClearField('season_special_id_list')
    response.user_season.ClearField('area_season_special_id_map')
    _populate_area_backstage_state(response)
    return response


def _area_change_response_from_state(state: UserState):
    area_response = _user_area_response_from_state(state)
    response = (
        suite_user_change_area_item_pb2.SuiteUserChangeAreaItemResponse()
    )
    _populate_area_item_state(response.update_resources, state)
    _populate_enabled_area_items(response.update_resources, state)
    for area_id in sorted(area_response.user_area_map.entries):
        response.user_area_list.entries.add().CopyFrom(
            area_response.user_area_map.entries[area_id]
        )
    return response


def _find_area_action_set(state: UserState, action_set_id, area_id=None):
    area_response = _user_area_response_from_state(state)
    area_entries = area_response.user_area_map.entries
    if area_id is not None:
        area = area_entries.get(area_id)
        if area is None:
            return None, None
        areas = (area,)
    else:
        areas = tuple(area_entries.values())
    for area in areas:
        for action_set in area.action_sets:
            if action_set.action_set_id == action_set_id:
                return area, action_set
    return None, None


def _recommended_area_item_placements(state: UserState):
    candidates = []
    for item in state.area_items:
        master = _master_area_item(item.area_item_id)
        if master is None:
            continue
        candidates.append((item, master))

    candidates.sort(
        key=lambda value: (
            value[1].get('5', 0),
            str(value[1].get('6', '')),
            value[0].area_item_category,
            value[0].area_item_id,
        )
    )
    placements = []
    for item, master in candidates:
        area_id = master.get('5', 0)
        if not area_id:
            continue
        placements.append(AreaItemPlacementState(
            area_item_id=item.area_item_id,
            area_item_category=item.area_item_category,
            area_id=area_id,
        ))
    return placements


def _master_music_difficulty(music_id, music_difficulty):
    difficulty = (music_difficulty or 'normal').strip().lower()
    return next(
        (entry for entry in _load_suite_master()['2']['1']
         if entry['1'] == music_id and entry['2'] == difficulty),
        None,
    )


def _score_rank_for_music(
        music_id, music_difficulty, score, fallback='d'):
    """Match LiveScoreRankUtility.FindRankFromScore in the KR 6.5.2 client."""
    difficulty = _master_music_difficulty(music_id, music_difficulty)
    if difficulty is None:
        return fallback if fallback in {'d', 'c', 'b', 'a', 's', 'ss'} else 'd'
    for rank, field in (
            ('ss', '10'), ('s', '6'), ('a', '7'), ('b', '8'), ('c', '9')):
        if score >= difficulty.get(field, 0):
            return rank
    return 'd'


def _music_band_id(music_id):
    music = _master_music(music_id)
    if music is None:
        return 0
    return music.get('11', 0)


def _high_score_rating_value(score):
    if score <= 0:
        return 0
    return max(score // 1000, 1)


def _add_high_score_rating_entry(target, music_id, difficulty, rating):
    entry = target.entries.add()
    entry.music_id = music_id
    entry.difficulty = difficulty or 'expert'
    entry.rating = rating
    return entry


def _populate_high_score_rating(target, state: UserState):
    if not _message_has_field(target, 'user_high_score_rating'):
        return

    target.ClearField('user_high_score_rating')
    if _message_has_field(target, 'user_high_score_music_rating_map'):
        target.ClearField('user_high_score_music_rating_map')

    best_by_music = {}
    for score in state.music_scores:
        rating = _high_score_rating_value(score.solo_high_score)
        current = best_by_music.get(score.music_id)
        if current is None or rating > current[2]:
            best_by_music[score.music_id] = (
                score.music_difficulty or 'expert',
                score.solo_high_score,
                rating,
            )

    grouped = {band_id: [] for band_id in _BAND_IDS}
    grouped[0] = []
    for music_id, (difficulty, _score, rating) in best_by_music.items():
        band_id = _music_band_id(music_id)
        if band_id not in grouped:
            band_id = 0
        grouped[band_id].append((rating, music_id, difficulty))
        if _message_has_field(target, 'user_high_score_music_rating_map'):
            rating_entry = target.user_high_score_music_rating_map.entries[
                music_id
            ]
            rating_entry.music_id = music_id
            rating_entry.difficulty = difficulty
            rating_entry.rating = rating

    for band_id, field_name in _HIGH_SCORE_RATING_BAND_FIELDS.items():
        high_score_list = getattr(target.user_high_score_rating, field_name)
        rows = sorted(grouped[band_id], reverse=True)
        if not rows:
            _add_high_score_rating_entry(
                high_score_list,
                _HIGH_SCORE_PLACEHOLDER_MUSIC[band_id],
                'expert',
                0,
            )
            continue
        for rating, music_id, difficulty in rows[:_HIGH_SCORE_RATING_LIMIT]:
            _add_high_score_rating_entry(
                high_score_list, music_id, difficulty, rating
            )

    other_list = (
        target.user_high_score_rating.user_other_high_score_music_list
    )
    other_rows = sorted(grouped[0], reverse=True)
    if not other_rows:
        _add_high_score_rating_entry(
            other_list,
            _HIGH_SCORE_PLACEHOLDER_MUSIC[0],
            'expert',
            0,
        )
    else:
        for rating, music_id, difficulty in other_rows[:_HIGH_SCORE_RATING_LIMIT]:
            _add_high_score_rating_entry(
                other_list, music_id, difficulty, rating
            )


def _situation_master_map():
    return {entry['1']: entry for entry in _load_suite_master()['4']['1']}


def _released_situation_master(situation_id):
    master = _situation_master_map().get(situation_id)
    if master is None:
        return None
    if master['2'].get('17', 0) >= _LOCAL_SITUATION_RELEASE_CUTOFF_MS:
        return None
    return master


def _situation_character_id(situation_id):
    master = _released_situation_master(situation_id)
    if master is None:
        return 0
    return master['2'].get('2', 0)


def _fallback_deck_situation(used_situations, used_characters):
    for situation_id in _DEFAULT_DECK_MEMBER_IDS:
        character_id = _situation_character_id(situation_id)
        if (character_id and situation_id not in used_situations
                and character_id not in used_characters):
            return situation_id

    for master in _load_suite_master()['4']['1']:
        situation_id = master['1']
        if situation_id in used_situations:
            continue
        if master['2'].get('17', 0) >= _LOCAL_SITUATION_RELEASE_CUTOFF_MS:
            continue
        character_id = master['2'].get('2', 0)
        if character_id and character_id not in used_characters:
            return situation_id
    return 0


def _normalize_deck_member_ids(member_ids):
    normalized = []
    used_situations = set()
    used_characters = set()
    for raw_situation_id in member_ids:
        situation_id = int(raw_situation_id or 0)
        character_id = _situation_character_id(situation_id)
        if (not character_id or situation_id in used_situations
                or character_id in used_characters):
            situation_id = _fallback_deck_situation(
                used_situations, used_characters
            )
            character_id = _situation_character_id(situation_id)
        normalized.append(situation_id)
        if situation_id:
            used_situations.add(situation_id)
        if character_id:
            used_characters.add(character_id)
    return tuple(normalized)


def _normalize_deck_changes(current_deck, changes):
    if current_deck is None:
        current_members = _DEFAULT_DECK_MEMBER_IDS
    else:
        current_members = tuple(
            getattr(current_deck, field) for field in DECK_MEMBER_FIELDS
        )

    requested_members = tuple(
        changes.get(field, current_members[index])
        for index, field in enumerate(DECK_MEMBER_FIELDS)
    )
    normalized_members = _normalize_deck_member_ids(requested_members)
    normalized = dict(changes)
    for field, situation_id in zip(DECK_MEMBER_FIELDS, normalized_members):
        normalized[field] = situation_id
    return normalized


def _situation_base_score(master_situation):
    parameter_rows = master_situation['2'].get('8', [])
    if not parameter_rows:
        return 0
    row = max(parameter_rows, key=lambda item: item.get('1', 0))['2']
    return row.get('3', 0) + row.get('4', 0) + row.get('5', 0)


def _area_item_rate_percent(master_area_item):
    if master_area_item.get('11') != 'rate':
        return 0.0
    values = []
    for field_name in ('8', '9', '10'):
        raw = master_area_item.get(field_name, 0)
        if raw:
            values.append(_float32_from_master(raw))
    return max(values, default=0.0)


def _area_item_bonus_by_band_attribute(state: UserState):
    bonuses = {}
    for item in state.area_items:
        master = _master_area_item(item.area_item_id)
        if master is None:
            continue
        band_id = master.get('16', 0)
        if band_id not in _BAND_IDS:
            continue
        rate_percent = _area_item_rate_percent(master)
        if rate_percent <= 0:
            continue
        attributes = master.get('12', _DECK_RATING_ATTRIBUTES)
        if isinstance(attributes, str):
            attributes = [attributes]
        for attribute in attributes:
            if attribute not in _DECK_RATING_ATTRIBUTES:
                continue
            bonuses[(band_id, attribute)] = (
                bonuses.get((band_id, attribute), 0.0) + rate_percent
            )
    return bonuses


def _apply_area_item_bonus(score, bonus_percent):
    if score <= 0 or bonus_percent <= 0:
        return score
    return int(round(score * (1.0 + (bonus_percent / 100.0))))


def _deck_rating_bounds(score):
    for threshold, rank, level, lower, upper in _DECK_RATING_THRESHOLDS:
        if score >= threshold:
            return rank, level, lower, upper
    return 'c', 0, 0, _DECK_RATING_THRESHOLDS[-1][4]


def _copy_deck_rating(target, attribute, situation_ids, score):
    target.attribute = attribute
    for field_name, situation_id in zip(
            ('leader', 'member1', 'member2', 'member3', 'member4'),
            situation_ids):
        setattr(target, field_name, situation_id)
    rank, level, lower, upper = _deck_rating_bounds(score)
    target.rank = rank
    target.score = score
    target.level = level
    target.lower_rating = lower
    target.upper_rating = upper


def _copy_total_rating(target, score):
    rank, level, lower, upper = _deck_rating_bounds(score // 4 if score else 0)
    target.rank = rank
    target.score = score
    target.level = level
    target.lower_rating = lower * 4 if lower else 0
    target.upper_rating = upper * 4


def _best_band_attribute_decks(state: UserState):
    """Build stable band-deck ratings from cards plus owned area items."""
    best_by_character = {}
    now_ms = int(time.time() * 1000)
    for master in _load_suite_master()['4']['1']:
        data = master['2']
        if data.get('17', 0) > now_ms:
            continue
        band_id = _band_id_for_character(data.get('2', 0))
        attribute = data.get('5', '')
        if band_id not in _BAND_IDS or attribute not in _DECK_RATING_ATTRIBUTES:
            continue
        key = (band_id, attribute, data['2'])
        score = _situation_base_score(master)
        current = best_by_character.get(key)
        if current is None or score > current[0]:
            best_by_character[key] = (score, master['1'])

    by_band_attribute = {}
    for (band_id, attribute, _character_id), row in best_by_character.items():
        by_band_attribute.setdefault((band_id, attribute), []).append(row)

    decks = {}
    for band_id in _BAND_IDS:
        for attribute in _DECK_RATING_ATTRIBUTES:
            candidates = sorted(
                by_band_attribute.get((band_id, attribute), ()),
                reverse=True,
            )
            if len(candidates) < 5:
                fallback = []
                for (fallback_band_id, _attribute), rows in (
                        by_band_attribute.items()):
                    if fallback_band_id == band_id:
                        fallback.extend(rows)
                seen = {situation_id for _score, situation_id in candidates}
                candidates.extend(
                    row for row in sorted(fallback, reverse=True)
                    if row[1] not in seen
                )
            chosen = candidates[:5]
            if not chosen:
                continue
            score = sum(row[0] for row in chosen)
            situation_ids = [row[1] for row in chosen]
            while len(situation_ids) < 5:
                situation_ids.append(0)
            decks.setdefault(band_id, []).append(
                (attribute, tuple(situation_ids), score)
            )
    bonuses = _area_item_bonus_by_band_attribute(state)
    if not bonuses:
        return decks
    return {
        band_id: [
            (
                attribute,
                situation_ids,
                _apply_area_item_bonus(
                    score, bonuses.get((band_id, attribute), 0.0)
                ),
            )
            for attribute, situation_ids, score in deck_rows
        ]
        for band_id, deck_rows in decks.items()
    }


def _populate_band_deck_rating(target, state: UserState):
    if not _message_has_field(target, 'user_band_deck_rating_map'):
        return
    target.ClearField('user_band_deck_rating_map')
    for band_id, deck_rows in _best_band_attribute_decks(state).items():
        band_rating = target.user_band_deck_rating_map.entries[band_id]
        total_score = 0
        for attribute, situation_ids, score in deck_rows:
            total_score += score
            _copy_deck_rating(
                band_rating.deck_rating.add(), attribute, situation_ids, score
            )
        _copy_total_rating(band_rating.total_rating, total_score)
    if _message_has_field(target, 'updated_band_deck_rank_list'):
        target.updated_band_deck_rank_list.SetInParent()


def _populate_profile_deck_total_rating(target, state: UserState):
    if not _message_has_field(target, 'user_deck_total_rating_map'):
        return
    target.ClearField('user_deck_total_rating_map')
    for band_id, deck_rows in _best_band_attribute_decks(state).items():
        total_score = sum(score for _attribute, _situations, score in deck_rows)
        _copy_total_rating(
            target.user_deck_total_rating_map.entries[band_id],
            total_score,
        )


def _recognized_mission_progress(state: UserState):
    progress = {
        mission_id: _computed_band_rank(state, band_id)
        for mission_id, band_id in _BAND_RANK_MISSION_BANDS.items()
    }
    band_deck_rows = _best_band_attribute_decks(state)
    for mission_id, band_id in _DECK_RATING_MISSION_BANDS.items():
        total_score = sum(
            score
            for _attribute, _situations, score
            in band_deck_rows.get(band_id, ())
        )
        # Mission master stores deck-rank thresholds at 10x the displayed
        # total rating value used by UserBandDeckRating.
        progress[mission_id] = total_score * 10
    album_counts = _album_action_set_counts()
    for mission_id, character_id in _ALBUM_MISSION_CHARACTERS.items():
        progress[mission_id] = album_counts.get(character_id, 0)
    return progress


def _sync_recognized_missions(user_id, state: UserState | None = None):
    effective_user_id = _effective_user_id(user_id)
    if state is None:
        state = _state_or_400(
            _state_store.get_user_state, effective_user_id
        )
    return _state_or_400(
        _state_store.sync_mission_progress,
        effective_user_id,
        _recognized_mission_progress(state),
    )


def _populate_deck_member_situations(target, state: UserState):
    if not _message_has_field(target, 'user_situation_map'):
        return
    master_situations = _situation_master_map()
    duplicate_counts = {
        entry.situation_id: entry.duplicate_count
        for entry in state.situation_duplicates
    }
    for deck in state.decks:
        for situation_id in _deck_member_ids(deck):
            master = master_situations.get(situation_id)
            if master is None:
                continue
            _populate_user_situation(
                target.user_situation_map.entries[situation_id],
                state.user_id,
                master,
                duplicate_counts.get(situation_id, 0),
            )


def _music_achievement_rewards(music_id, achievement_types):
    music = _master_music(music_id)
    if music is None:
        return ()
    wanted = set(achievement_types)
    return tuple(
        ResourceState(
            reward['3'],
            reward.get('4', 0),
            reward['5'],
        )
        for reward in music.get('13', [])
        if reward.get('2') in wanted
    )


def _band_id_for_character(character_id):
    if 1 <= character_id <= 25:
        return ((character_id - 1) // 5) + 1
    if 26 <= character_id <= 30:
        return 18
    if 31 <= character_id <= 35:
        return 21
    return None


def _populate_live_result_progression(response, state):
    """Return complete result rows even after the in-memory suite cache resets."""
    deck = next(
        (entry for entry in state.decks
         if entry.deck_type == 'normal' and entry.deck_id == state.main_deck),
        None,
    )
    if deck is None:
        return

    master_situations = {
        entry['1']: entry
        for entry in _load_suite_master()['4']['1']
    }
    duplicate_counts = {
        entry.situation_id: entry.duplicate_count
        for entry in state.situation_duplicates
    }
    situation_ids = (
        deck.leader, deck.member1, deck.member2, deck.member3, deck.member4
    )
    band_ids = set()
    for situation_id in situation_ids:
        master = master_situations.get(situation_id)
        if master is None:
            continue
        situation = response.user_situation_list.entries.add()
        _populate_user_situation(
            situation,
            state.user_id,
            master,
            duplicate_counts.get(situation_id, 0),
        )
        response.update_resources.user_situation_map.entries[
            situation_id
        ].CopyFrom(situation)
        band_id = _band_id_for_character(master['2']['2'])
        if band_id is not None:
            band_ids.add(band_id)

    for band_id in sorted(band_ids):
        band_rank = response.user_band_rank_list.entries.add()
        _copy_band_rank(band_rank, state, band_id)
        response.update_resources.user_band_rank_map.entries[
            band_id
        ].CopyFrom(band_rank)


def _master_mission_reward(mission_id, seq):
    for group in _load_suite_master().get('500', {}).get('1', []):
        missions = group.get('13', {}).get('1', [])
        for mission in missions:
            if mission.get('1') != mission_id:
                continue
            details = mission.get('18', {}).get('1', [])
            if isinstance(details, dict):
                details = [details]
            for index, detail in enumerate(details):
                if detail.get('2') != seq:
                    continue
                reward = detail.get('12')
                if not reward:
                    return None
                next_target = (
                    details[index + 1].get('5')
                    if index + 1 < len(details) else None
                )
                return (
                    group['1'],
                    ResourceState(
                        reward['4'], reward.get('5', 0), reward['6']
                    ),
                    next_target,
                )
    return None


def _draw_gacha_situations(gacha, count, guarantee_three_star=False):
    pool = gacha.get('6', [])
    rates = []
    for rate in gacha.get('7', []):
        rarity = rate['2']
        weight = _float32_from_master(rate['3'])
        if weight > 0 and any(item['2'] == rarity for item in pool):
            rates.append((rarity, weight))
    if not rates or not pool:
        raise StateStoreError('gacha master has no drawable situations')

    def draw(minimum_rarity=0):
        eligible_rates = [item for item in rates if item[0] >= minimum_rarity]
        if not eligible_rates:
            raise StateStoreError('gacha guarantee has no matching situations')
        rarity = _rng.choices(
            [item[0] for item in eligible_rates],
            weights=[item[1] for item in eligible_rates],
            k=1,
        )[0]
        candidates = [item for item in pool if item['2'] == rarity]
        return _rng.choices(
            candidates,
            weights=[max(item.get('4', 0), 1) for item in candidates],
            k=1,
        )[0]

    results = [draw() for _ in range(count)]
    if guarantee_three_star and not any(item['2'] >= 3 for item in results):
        results[-1] = draw(3)
    return tuple(item['3'] for item in results)


def _gacha_duplicate_michelle_seal_rewards(gacha, results):
    if not results:
        return ()
    rarity_by_situation_id = {
        item.get('3'): item.get('2', 0)
        for item in gacha.get('6', [])
        if isinstance(item, dict)
    }
    seal_by_rarity = {
        1: 1,
        2: 5,
        3: 25,
        4: 100,
        5: 100,
    }
    total = 0
    for result in results:
        rarity = max(0, int(rarity_by_situation_id.get(
            result.situation_id, 0
        ) or 0))
        total += seal_by_rarity.get(rarity, 0)
    if not total:
        return ()
    return (ResourceState('michelle_seal', 0, total),)


def _state_or_400(callback, *args, **kwargs):
    try:
        return callback(*args, **kwargs)
    except StateStoreError as error:
        abort(400, description=str(error))


def encrypt(data: bytes) -> bytes:
    cipher = AES.new(_key, AES.MODE_CBC, iv=_iv)
    return cipher.encrypt(pad(data, AES.block_size, 'x923'))


def decrypt(data: bytes) -> bytes:
    cipher = AES.new(_key, AES.MODE_CBC, iv=_iv)
    decrypted = cipher.decrypt(data)
    padded_bytes = decrypted[-1]
    return decrypted[:-padded_bytes]


class GameRequest(Request):
    @property
    def data(self) -> bytes:
        if not super().data:
            return None
        return decrypt(super().data)


app.request_class = GameRequest


@app.after_request
def encrypt_response(response: Response) -> Response:
    if response.response:
        combined = bytearray()
        for b in response.response:
            combined.extend(b)
        encrypted = encrypt(bytes(combined))
        response.response = [encrypted]
        response.content_length = len(encrypted)
        response.content_type = 'application/octet-stream'
    return response


@app.post('/api/user/')
def post_user_api():
    i = user_pb2.UserPostRequest.FromString(request.data)
    state = _state_or_400(_state_store.get_user_state, 1000000)
    o = user_pb2.UserRegistration()
    _populate_user_registration(o, state)
    o.client_version = i.client_version
    o.platform = i.platform
    o.device_model = i.device_model
    o.operating_system = i.operating_system
    o.kakao_id = i.kakao_id
    o.kakao_guest_flg = i.kakao_guest_flg
    return o.SerializeToString()


@app.put('/api/user/<int:user_id>/auth/prepare')
def prepare_user_auth_api(user_id):
    o = user_auth_pb2.UserAuthPrepareResponse()
    o.api_key = 'A'*39
    o.nonce = 'A'*64
    o.need_check = True
    return o.SerializeToString()


@app.put('/api/user/<int:user_id>/auth')
def user_auth_api(user_id):
    return b''


@app.get('/api/application')
def get_app_api():
    o = app_pb2.AppGetResponse()
    o.client_version = '6.5.0-SNAPSHOT'
    # Match the data version stored in the 6.5.2 APK/client cache.  If this
    # differs, the title flow tries to fetch AssetBundleInfo from the CDN.
    o.data_version = os.environ.get('KRDORI_DATA_VERSION', '6.5.0.0')
    o.app_status = 'available'
    o.client_status = 'snapshot'
    o.schema = 'amaterasu'
    o.gacha = 'available'
    o.multi_live = 'available'
    o.star_shop = 'available'
    o.master_data_version = '6.5.47'
    o.photon_app_id = '4ddacf66-3d97-4cfa-ae56-1d92a6cb849b'
    return o.SerializeToString()


@app.get('/api/suite/master')
def get_suite_master_api():
    global _suite_master_payload
    if _suite_master_payload is None:
        with open('server/responses/suite_master.bz2', 'rb') as f:
            _suite_master_payload = patch_suite_master_bz2(f.read())
    return _suite_master_payload, 200, [('X-Encoding', 'bzip2')]


@app.get('/api/suite/user/<int:user_id>')
def suite_user_api(user_id):
    global _suite_master, _suite_user

    effective_user_id = _effective_user_id(user_id)
    _suite_master = _load_suite_master()
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    state = _sync_recognized_missions(effective_user_id, state)
    duplicate_counts = {
        item.situation_id: item.duplicate_count
        for item in state.situation_duplicates
    }

    o = suite_user_pb2.SuiteUserGetResponse()

    r = o.user.user_registration
    _populate_user_registration(r, state)
    g = o.user.user_gamedata
    _populate_user_gamedata_defaults(g, effective_user_id)
    _populate_user_gamedata(g, state)

    for i in range(1, 36):
        c = o.user_character_map.entries[i]
        c.user_id = effective_user_id
        c.character_id = i
        c.costume_id = _default_costume_id(i)

    for m in _suite_master['4']['1']:   # MasterCharacterSituationMap
        if m['2']['17'] < 4102444800000:
            _populate_user_situation(
                o.user_situation_map.entries[m['1']],
                effective_user_id,
                m,
                duplicate_counts.get(m['1'], 0),
            )

    d = o.user_deck_map.entries[1]
    d.deck_id = 1
    d.deck_name = '밴드1'
    d.leader = 1
    d.member1 = 13
    d.member2 = 17
    d.member3 = 9
    d.member4 = 5
    d.deck_type = 'normal'

    ss = []
    for m in _suite_master['21']['1']:  # MasterMainStoryMap
        s = user_story_pb2.UserMainStory()
        s.user_id = effective_user_id
        s.story_id = m['1']
        s.status = 'already_read'
        ss.append(s)
    o.user_main_story_list.entries.extend(
        sorted(ss, key=attrgetter('story_id'), reverse=True))

    for i in range(1, 10):
        b = o.user_bonds_list.entries.add()
        b.user_id = effective_user_id
        b.bonds_id = i
        b.level = 1
        b.bonds = (i+1) * 5

    for i in [1, 2, 3, 4, 5, 18, 21]:
        r = o.user_band_rank_map.entries[i]
        r.user_id = effective_user_id
        r.band_id = i
        r.band_rank = 1
        r.exp = 0
        r.add_exp = 0
        r.pooled_exp = 0
        r.total_exp = 0
        r.next_exp = 400

    def build_band_story_list_from_master(field_number):
        ss = []
        for m in _suite_master[str(field_number)]['1']:
            s = user_band_story_pb2.UserBandStory()
            s.user_id = user_id
            s.band_story_id = m['1']
            s.band_id = m['2']['2']
            s.status = 'already_read'
            s.seq = m['2']['3']
            ss.append(s)
        return sorted(ss, key=attrgetter('seq'), reverse=True)

    o.user_poppin_party_story_list.entries.extend(
        build_band_story_list_from_master(22))  # masterPoppinPartyStoryMap

    o.user_afterglow_story_list.entries.extend(
        build_band_story_list_from_master(23))  # masterAfterglowStoryMap

    o.user_pastel_palettes_story_list.entries.extend(
        build_band_story_list_from_master(24))  # masterPastelPalettesStoryMap

    o.user_hello_happy_world_story_list.entries.extend(
        build_band_story_list_from_master(25))  # masterHelloHappyWorldStoryMap

    o.user_roselia_story_list.entries.extend(
        build_band_story_list_from_master(26))  # masterRoseliaStoryMap

    ls = o.user_commons_live2d_map.entries['event_box_gacha_top_first'].entries
    l = ls.add()
    l.live2d_id = 3131
    l.live2d_category = 'event_box_gacha_top_first'
    ls = o.user_commons_live2d_map.entries['live_menu'].entries
    for i in [10, 11, 12,
              22, 23, 24,
              34, 35, 36,
              46, 47, 48,
              58, 59, 60,
              7217, 7218, 7219,     # Related to seasons
              7251, 7252, 7253,
              7285, 7286, 7287,
              7319, 7320, 7321,
              7352, 7353, 7354]:
        l = ls.add()
        l.live2d_id = i
        l.live2d_category = 'live_menu'
    ls = o.user_commons_live2d_map.entries['mission'].entries
    for i in range(3126, 3131):
        l = ls.add()
        l.live2d_id = i
        l.live2d_category = 'mission'
    ls = o.user_commons_live2d_map.entries['login_bonus'].entries
    for i in [7, 8, 9,
              19, 20, 21,
              31, 32, 33,
              43, 44, 45,
              55, 56, 57,
              9557, 9558, 9559,     # Related to seasons
              9591, 9592, 9593,
              9625, 9626, 9627,
              9659, 9660, 9661,
              9692, 9693, 9694]:
        l = ls.add()
        l.live2d_id = i
        l.live2d_category = 'login_bonus'
    ls = o.user_commons_live2d_map.entries['story_menu'].entries
    for i in [1, 2, 3,
              14, 15,
              25, 26, 27,
              37, 38, 39,
              49, 50, 51,
              8387, 8388, 8389,     # Related to seasons
              8421, 8422, 8423,
              8455, 8456, 8457,
              8489, 8490, 8491,
              8522, 8523, 8524]:
        l = ls.add()
        l.live2d_id = i
        l.live2d_category = 'story_menu'
    ls = o.user_commons_live2d_map.entries['event_box_gacha_top'].entries
    for i in range(3132, 3135):
        l = ls.add()
        l.live2d_id = i
        l.live2d_category = 'event_box_gacha_top'
    ls = o.user_commons_live2d_map.entries['event_box_gacha_after'].entries
    for i in range(3142, 3145):
        l = ls.add()
        l.live2d_id = i
        l.live2d_category = 'event_box_gacha_after'
    ls = o.user_commons_live2d_map.entries['band_menu'].entries
    for i in [4, 5, 6,
              16, 17, 18,
              28, 29, 30,
              40, 41, 42,
              52, 53, 54,
              6047, 6048, 6049,     # Related to seasons
              6081, 6082, 6083,
              6115, 6116, 6117,
              6149, 6150, 6151,
              6182, 6183, 6184]:
        l = ls.add()
        l.live2d_id = i
        l.live2d_category = 'band_menu'
    ls = o.user_commons_live2d_map.entries['birthday_page'].entries
    for i in [10711, 10712, 10713,
              10745, 10746, 10747,
              10779, 10780, 10781,
              10782, 10783, 10784,
              10813, 10814, 10815,
              10847, 10848, 10849,
              10862, 10863, 10864]:
        l = ls.add()
        l.live2d_id = i
        l.live2d_category = 'birthday_page'
    ls = o.user_commons_live2d_map.entries['event_box_gacha_before'].entries
    for i in range(3136, 3139):
        l = ls.add()
        l.live2d_id = i
        l.live2d_category = 'event_box_gacha_before'
    ls = o.user_commons_live2d_map.entries['event_box_gacha_after_win'].entries
    for i in range(3140, 3142):
        l = ls.add()
        l.live2d_id = i
        l.live2d_category = 'event_box_gacha_after_win'

    for m in _suite_master['4']['1']:   # masterCharacterSituationMap
        if '14' not in m['2']:
            continue
        for me in m['2']['14']['1']:    # episodes
            e = o.user_episode_map.entries[me['1']]
            e.user_id = user_id
            e.episode_id = me['1']
            e.episode_status = 'already_read'

    for m in _suite_master['1']['1']:   # MasterMusicListGetResponse
        i = o.user_music_inventory_list.entries.add()
        i.user_id = user_id
        i.music_id = m['1']
        i.seq = 1
        i.has_mv = m['1'] in (
            v['1'] for v in _suite_master['109']['1']
        )   # MasterMusicVideoListMap
        i.is_favorite = False

    for m in _suite_master['31']['1']:  # MasterCostumeMap
        c = o.user_costume_map.entries[m['1']]
        c.user_id = user_id
        c.costume_id = m['1']

    for i in [4, 5, 6,
              11, 12, 13,
              18, 19, 20,
              25, 26, 27,
              32, 33, 34,
              39, 40, 41,
              46, 47, 48,
              53, 54, 55,
              61, 62,
              67, 68, 69]:
        t = o.user_after_live_talk_list_map.entries['success'].entries.add()
        t.after_live_talk_id = i
        t.after_live_talk_type = 'success'
    for i in [7, 14, 21, 28, 35,
              42, 49, 56, 63, 70]:
        t = o.user_after_live_talk_list_map.entries['failure'].entries.add()
        t.after_live_talk_id = i
        t.after_live_talk_type = 'failure'
    for i in [1, 2, 3,
              8, 9, 10,
              15, 16, 17,
              22, 23, 24,
              29, 30, 31,
              36, 37, 38,
              43, 44, 45,
              50, 51, 52,
              57, 58, 59,
              64, 65, 66]:
        t = (o.user_after_live_talk_list_map.entries['great_success'].entries
             .add())
        t.after_live_talk_id = i
        t.after_live_talk_type = 'great_success'

    o.user_resource_count.present = 0

    b = o.user_live_boost
    b.user_id = user_id
    b.live_boost = 10
    b.server_date = int(time.time()*1000)
    b.live_boost_bonus_type = 'default'

    for i in range(1, 20):
        s = o.user_area_status_map.entries[i]
        s.user_id = user_id
        s.area_id = i

    b = o.user_login_bonus_map.entries[1]
    b.user_id = user_id
    b.login_bonus_id = 1
    b.days = 5

    b = o.user_home_banner_list.entries.add()
    b.home_banner_id = 1283
    b = o.user_home_banner_list.entries.add()
    b.home_banner_id = 1437
    b = o.user_home_banner_list.entries.add()
    b.home_banner_id = 1480
    b = o.user_home_banner_list.entries.add()
    b.home_banner_id = 1482

    for m in _suite_master['46']['1']:  # MasterStampMap
        s = o.user_stamp_map.entries[m['1']]
        s.user_id = user_id
        s.stamp_id = m['1']
        s.seq = m['2']['2']

    for i in [100, 101, 102, 103, 104, 105, 111, 112]:
        d = o.user_degree_map.entries[i]
        d.user_id = user_id
        d.degree_id = i
    _populate_degree_state(o, state)

    for c, ls in [
        (1, [1, 2, 3, 4, 5,
             4374, 4375, 4376,
             9000, 9001, 9002]),
        (2, [6, 7, 8, 9, 10,
             4408, 4409, 4410,
             9003, 9004, 9005]),
        (3, [11, 12, 13, 14, 15,
             4442, 4443, 4444,
             9006, 9007, 9008]),
        (4, [16, 17, 18, 19, 20,
             4476, 4477, 4478,
             9009, 9010, 9011]),
        (5, [21, 22, 23, 24, 25,
             4509, 4510, 4511,
             9012, 9013, 9014]),
        (6, [26, 27, 28, 29, 30,
             4542, 4543, 4544,
             9015, 9016, 9017]),
        (7, [31, 32, 33, 34, 35,
             4575, 4576, 4577,
             9018, 9019, 9020]),
        (8, [36, 37, 38, 39, 40,
             4608, 4609, 4610,
             9021, 9022, 9023]),
        (9, [41, 42, 43, 44, 45,
             4641, 4642, 4643,
             9024, 9025, 9026]),
        (10, [46, 47, 48, 49, 50,
              4674, 4675, 4676,
              9027, 9028, 9029]),
        (11, [51, 52, 53, 54, 55,
              5209, 5210, 5211,
              9030, 9031, 9032]),
        (12, [56, 57, 58, 59, 60,
              5243, 5244, 5245,
              9033, 9034, 9035]),
        (13, [61, 62, 63, 64, 65,
              5277, 5278, 5279,
              9036, 9037, 9038]),
        (14, [66, 67, 68, 69, 70,
              5310, 5311, 5312,
              9039, 9040, 9041]),
        (15, [71, 72, 73, 74, 75,
              5343, 5344, 5345,
              9042, 9043, 9044]),
        (16, [76, 77, 78, 79, 80,
              5038, 5039, 5040,
              9045, 9046, 9047]),
        (17, [81, 82, 83, 84, 85,
              5073, 5074, 5075,
              9048, 9049, 9050]),
        (18, [86, 87, 88, 89, 90,
              5107, 5108, 5109,
              9051, 9052, 9053]),
        (19, [91, 92, 94, 95,
              5142, 5143, 5144,
              9054, 9055, 9056]),
        (20, [96, 97, 98, 99, 100,
              5176, 5177, 5178,
              9057, 9058, 9059]),
        (21, [101, 103, 104, 105,
              4707, 4708, 4709,
              9060, 9061, 9062]),
        (22, [106, 107, 108, 109, 110,
              4740, 4741, 4742,
              9063, 9064, 9065]),
        (23, [111, 112, 114, 115,
              4774, 4775, 4776,
              9066, 9067, 9068]),
        (24, [116, 117, 118, 119, 120,
              4807, 4808, 4809,
              9069, 9070, 9071]),
        (25, [121, 123, 124, 125,
              4840, 4841, 4842,
              9072, 9073, 9074]),
        (26, [3755, 3756, 3757, 3758, 3759,
              3920, 3921, 3922,
              5377, 5378, 5379]),
        (27, [3760, 3761, 3762, 3763, 3764,
              3923, 3924, 3925,
              5410, 5411, 5412]),
        (28, [3765, 3766, 3767, 3768, 3769,
              3926, 3927, 3928,
              5443, 5444, 5445]),
        (29, [3770, 3771, 3772, 3773, 3774,
              3929, 3930, 3931,
              5476, 5477, 5478]),
        (30, [3775, 3776, 3777, 3778, 3779,
              3932, 3933, 3934,
              5509, 5510, 5511]),
        (31, [3935, 3936, 3937, 3938, 3939,
              4083, 4084, 4085,
              4873, 4874, 4875]),
        (32, [3965, 3966, 3967, 3968, 3969,
              4086, 4087, 4088,
              4906, 4907, 4908]),
        (33, [3994, 3995, 3996, 3997, 3998,
              4089, 4090, 4091,
              4939, 4940, 4941]),
        (34, [4024, 4025, 4026, 4027, 4028,
              4092, 4093, 4094,
              4972, 4973, 4974]),
        (35, [4054, 4055, 4056, 4057, 4058,
              4095, 4096, 4097,
              5005, 5006, 5007])
    ]:
        for l in ls:
            e = o.user_character_profile_live2d_map.entries[c].entries.add()
            e.character_id = c
            e.live2d_id = l

    s = o.user_generic_story_map.entries[34]
    s.user_id = user_id
    s.generic_story_id = 34
    s.status = 'unread'

    o.user_season.season_id = 0
    o.user_season.ClearField('season_special_id_list')
    o.user_season.ClearField('area_season_special_id_map')

    m = _load_event_story_memorial_response()
    for k, v in m.past_event_story_map.entries.items():
        sm = o.user_event_story_memorial_map.entries[k]
        sm.event_id = k
        for e in v.entries:
            s = sm.user_event_story_list.entries.add()
            s.user_id = user_id
            s.event_id = k
            s.seq = e.seq
            s.status = 'already_read'
        sm.is_exist_un_read_story = False
        sm.is_locked = False

    o.user_released_bonds_id_list.entries.extend(range(1, 66))
    o.user_released_bonds_id_list.entries.extend(range(148, 158))
    o.user_released_bonds_id_list.entries.extend(range(169, 179))
    o.user_released_bonds_id_list.entries.extend(range(180, 197))

    t = o.user_miracle_ticket_map.entries[4]
    t.user_id = user_id
    t.miracle_ticket_id = 4
    t.quantity = 1
    t.exchange_end_at = (int(time.time())+86400*30) * 1000

    for m in _suite_master['30']['1']:  # MasterMusicShopMap
        s = o.user_music_shop_map.entries[m['2']['2']].entries.add()
        s.user_id = user_id
        s.music_shop_id = m['1']
        s.shop_id = m['2']['2']
        s.shop_category = m['2']['3']
        s.music_id = m['2']['5']
        s.status = 'sold_out'
        s.seq = m['2']['4']

    for m in _suite_master['96']['1']:  # MasterBackstageTalkSetMap
        o.user_backstage_talk_set_read_history_map.entries[m['1']] = (
            'already_read')

    o.user_friend_relation_detail.application_limit = 50
    o.user_friend_relation_detail.approval_limit = 50
    o.user_friend_relation_detail.friend_limit = 50

    _populate_profile_suite_state(o, state)

    i = o.user_deco_frame_inventory_map.entries[1]
    i.user_id = user_id
    i.deco_frame_id = 1
    i.level = 1

    for i in [310, 320, 330, 340, 350]:
        p = o.user_deco_pins_inventory_map.entries[i]
        p.user_id = user_id
        p.deco_pins_id = i
        p.quantity = 1

    _populate_deco_equipment(o.user_deco_equipment, state)

    for m in _suite_master['109']['1']:     # MasterMusicVideoListMap
        if isinstance(m['2']['1'], list):
            for v in m['2']['1']:
                i = (o.user_music_video_list_map
                     .user_music_video_inventory_list_map.entries[m['1']]
                     .entries.add())
                i.user_id = user_id
                i.music_id = m['1']
                i.seq = v['6']
        else:
            i = (o.user_music_video_list_map
                 .user_music_video_inventory_list_map.entries[m['1']]
                 .entries.add())
            i.user_id = user_id
            i.music_id = m['1']
            i.seq = m['2']['1']['6']

    o.user_event_box_gacha_spin_settings.lump_spin_flg = False
    o.user_event_box_gacha_spin_settings.auto_stop_flg = False

    o.user_morfonica_story_list.entries.extend(
        build_band_story_list_from_master(401))     # masterMorfonicaStoryMap

    o.user_raise_a_suilen_story_list.entries.extend(
        build_band_story_list_from_master(402))     # masterRaiseASuilenStoryMap

    o.user_comeback_status.comeback_gacha_id = 0

    for i in [1, 2, 7, 8, 10, 11, 13, 14, 16, 17]:
        s = o.user_digest_story_list.entries.add()
        s.user_id = user_id
        s.digest_story_id = i
        s.status = 'unread'

    o.user_receivable_present_location_list.location_list.append(
        'countdown_page')

    d = o.user_deck_list.entries.add()
    d.deck_id = 1
    d.deck_name = '밴드1'
    d.leader = 1
    d.member1 = 13
    d.member2 = 17
    d.member3 = 9
    d.member4 = 5
    d.deck_type = 'normal'

    for i, as_ in [
        (1, [('powerful', 9, 1430, 0, 37642),
             ('happy', 1428, 17, 0, 41546),
             ('pure', 1, 1431, 0, 37793),
             ('cool', 1427, 1429, 5, 71008)]),
        (2, [('powerful', 1432, 0, 0, 27494),
             ('happy', 1433, 0, 0, 33697),
             ('pure', 1436, 1434, 0, 57784),
             ('cool', 1435, 0, 0, 27492)]),
        (3, [('powerful', 1439, 1438, 0, 50766),
             ('happy', 1437, 0, 0, 33694),
             ('pure', 1441, 0, 0, 24089),
             ('cool', 1440, 0, 0, 33696)]),
        (4, [('powerful', 1444, 1445, 0, 51582),
             ('happy', 1446, 0, 0, 26679),
             ('pure', 1442, 0, 0, 33694),
             ('cool', 1443, 0, 0, 27491)]),
        (5, [('powerful', 1448, 0, 0, 33697),
             ('happy', 1451, 0, 0, 26677),
             ('pure', 1450, 1447, 0, 48179),
             ('cool', 1449, 0, 0, 27492)]),
        (21, [('powerful', 1453, 0, 0, 33697),
              ('happy', 1454, 0, 0, 27491),
              ('pure', 1456, 0, 0, 26676),
              ('cool', 1455, 1452, 0, 61191)])
    ]:
        b = o.user_band_deck_rating_map.entries[i]
        for a, l, m1, m2, s in as_:
            d = b.deck_rating.add()
            d.attribute = a
            d.leader = l
            if m1:
                d.member1 = m1
            if m2:
                d.member2 = m2
            d.rank = 'c'
            d.score = s
            d.level = 0
            d.lower_rating = 1
            d.upper_rating = 400_000
        t = b.total_rating
        t.rank = 'c'
        t.score = sum(a[4] for a in as_)
        t.level = 0
        t.lower_rating = 1
        t.upper_rating = 1_600_000

    o.user_auto_live.daily_auto_live_use_count = 0
    o.user_auto_live.reset_time = int(time.time()*1000)

    o.user_monthly_mission.mission_season_id = 0
    o.user_monthly_mission.live_point = 0
    o.user_monthly_mission.is_purchase_premium_mission_pass = False

    _populate_deck_state(o, state)
    _populate_gallery_state(o, state)
    _populate_character_costume_state(o, state)
    _populate_live_state(o, state)
    _populate_gacha_ticket_state(o, state)
    _populate_present_count(o, state)

    # with open('suite_user_get_response.txtpb', 'w', encoding='utf-8') as f:
    #     f.write(str(o))
    _suite_user = o
    return o.SerializeToString()


@app.put('/api/suite/user/<int:user_id>/gacha/<int:gacha_id>')
def put_user_gacha_api(user_id, gacha_id):
    effective_user_id = _effective_user_id(user_id)
    payload = user_gacha_api_pb2.UserGachaRequest.FromString(request.data or b'')
    if payload.gacha_id and payload.gacha_id != gacha_id:
        abort(400, description='request gacha_id does not match the URL')

    gacha = _master_gacha(gacha_id)
    if gacha is None:
        abort(404, description=f'unknown gacha_id: {gacha_id}')
    payment = next(
        (item for item in gacha.get('8', [])
         if item['4'] == payload.payment_method_id),
        None,
    )
    if payment is None:
        app.logger.warning(
            'Unknown gacha payment: gacha_id=%s band_id=%s '
            'payment_method_id=%s body=%s',
            payload.gacha_id,
            payload.band_id,
            payload.payment_method_id,
            (request.data or b'').hex(),
        )
        abort(
            400,
            description=(
                f'unknown payment_method_id: {payload.payment_method_id}'
            ),
        )
    if payment['2'] not in {'free_star', 'normal_ticket'}:
        abort(400, description=f'unsupported gacha payment: {payment["2"]}')

    draw_count = payment['5']
    situation_ids = _state_or_400(
        _draw_gacha_situations,
        gacha,
        draw_count,
        payment['6'] == 'over_the_3_star_once',
    )
    draw_state = _state_or_400(
        _state_store.draw_gacha,
        effective_user_id,
        gacha_id,
        payment['4'],
        payment['9'],
        situation_ids,
        payment['6'] == 'once_a_day',
        payment['2'],
        payment.get('3', 0),
    )
    extra_rewards = _gacha_duplicate_michelle_seal_rewards(
        gacha, draw_state.results
    )
    update_state = draw_state.user
    if extra_rewards:
        update_state = _state_or_400(
            _state_store.grant_resources,
            effective_user_id,
            extra_rewards,
        )
    _sync_cached_gacha_state(effective_user_id, update_state)

    response = user_gacha_api_pb2.SuiteUserGachaResponse()
    _populate_resource_list(response.gacha_results.extras, extra_rewards)
    for result in draw_state.results:
        entry = response.gacha_results.entries.add()
        entry.situation_id = result.situation_id
        # The local suite initially exposes every member, so a draw is a
        # duplicate and is_first_get is deliberately false.
        entry.is_first_get = False

    _populate_live_state(response.update_resources, update_state)
    _populate_gacha_ticket_state(response.update_resources, update_state)
    _populate_present_count(response.update_resources, update_state)
    situation_master = {
        entry['1']: entry for entry in _load_suite_master()['4']['1']
    }
    for result in draw_state.results:
        master_situation = situation_master.get(result.situation_id)
        if master_situation is None:
            abort(
                500,
                description=f'missing situation master: {result.situation_id}',
            )
        _populate_user_situation(
            response.update_resources.user_situation_map.entries[
                result.situation_id
            ],
            effective_user_id,
            master_situation,
            result.duplicate_count,
        )
    return response.SerializeToString()


@app.get('/api/user/<int:user_id>/', strict_slashes=False)
def get_user_api(user_id):
    if request.data:
        user_pb2.UserGetRequest.FromString(request.data)
    cached = _cached_suite_user(user_id)
    if cached is not None:
        return cached.user.SerializeToString()

    state = _state_or_400(_state_store.get_user_state, user_id)
    o = user_pb2.UserGetResponse()
    _populate_user_registration(o.user_registration, state)
    _populate_user_gamedata(o.user_gamedata, state)
    return o.SerializeToString()


@app.route(
    '/api/user/<int:user_id>/profile/<int:target_user_id>',
    methods=['GET', 'PUT'],
)
def get_user_profile_api(user_id, target_user_id):
    state = _state_or_400(
        _state_store.get_user_state, target_user_id
    )
    o = user_profile_api_pb2.UserProfile()
    _populate_user_profile(o, state)
    return o.SerializeToString()


@app.route(
    '/api/user/<int:user_id>/profile/search/<int:target_user_id>',
    methods=['GET', 'PUT'],
)
def search_user_profile_api(user_id, target_user_id):
    state = _state_or_400(
        _state_store.get_user_state, target_user_id
    )
    o = user_profile_api_pb2.UserProfileSearchResponse()
    _populate_user_profile(o.user_profile, state)
    o.search_success_flg = True
    return o.SerializeToString()


@app.put('/api/suite/user/<int:user_id>/profile/degree')
def put_user_profile_degree_api(user_id):
    i = user_profile_degree_pb2.UserProfileDegreeRequest.FromString(
        request.data or b''
    )
    state = _state_or_400(
        _state_store.set_profile_degrees,
        user_id,
        i.degree_id_first,
        i.degree_id_second,
    )
    _sync_cached_profile_state(user_id, state)
    o = suite_user_profile_pb2.UserSettingProfileDegree()
    _populate_profile_suite_state(o.update_resources, state)
    return o.SerializeToString()


@app.put('/api/suite/user/<int:user_id>/profile/situation')
def put_user_profile_situation_api(user_id):
    i = user_profile_situation_pb2.UserProfileSituationRequest.FromString(
        request.data or b''
    )
    if _master_situation(i.situation_id) is None:
        abort(400, description=f'unknown situation: {i.situation_id}')
    state = _state_or_400(
        _state_store.set_profile_situation,
        user_id,
        i.situation_id,
        i.illust,
        i.view_profile_situation_status,
    )
    _sync_cached_profile_state(user_id, state)
    o = suite_user_profile_pb2.UserSettingProfileSituation()
    _populate_profile_suite_state(o.update_resources, state)
    return o.SerializeToString()


@app.put('/api/suite/user/<int:user_id>/deco/equip')
def put_user_deco_equipment_api(user_id):
    i = user_deco_equipment_pb2.UserDecoEquipmentRequestBody.FromString(
        request.data or b''
    )
    pin_ids = tuple(
        getattr(i, name) if i.HasField(name) else 0
        for name in (
            'deco_pins_id1',
            'deco_pins_id2',
            'deco_pins_id3',
            'deco_pins_id4',
            'deco_pins_id5',
        )
    )
    state = _state_or_400(
        _state_store.set_deco_equipment,
        user_id,
        i.deco_frame_id,
        *pin_ids,
    )
    _sync_cached_deco_equipment(user_id, state)
    o = suite_user_update_pb2.SuiteUserUpdateResponse()
    _populate_deco_equipment(
        o.update_resources.user_deco_equipment,
        state,
    )
    return o.SerializeToString()


@app.route('/api/suite/user/<int:user_id>/deck/<int:deck_id>',
           methods=['POST', 'PUT'])
def edit_user_deck_api(user_id, deck_id):
    effective_user_id = _effective_user_id(user_id)
    i = user_deck_api_pb2.EditUserDeckRequest.FromString(request.data or b'')
    deck_type = i.deck_type or 'normal'
    changes = {}
    if i.deck_name:
        changes['deck_name'] = i.deck_name
    for field in DECK_MEMBER_FIELDS:
        if i.HasField(field):
            changes[field] = getattr(i, field)

    current_state = _state_or_400(
        _state_store.get_user_state, effective_user_id
    )
    current_deck = next(
        (
            deck for deck in current_state.decks
            if deck.deck_type == deck_type and deck.deck_id == deck_id
        ),
        None,
    )
    changes = _normalize_deck_changes(current_deck, changes)
    _, state = _state_or_400(
        _state_store.upsert_deck,
        effective_user_id,
        deck_id,
        deck_type,
        changes,
    )
    _sync_cached_deck_state(effective_user_id, state)

    o = user_deck_api_pb2.EditUserDeckResponse()
    _populate_deck_state(o.update_resources, state)
    _populate_owned_situation_state(o.update_resources, state)
    _populate_character_costume_state(o.update_resources, state)
    _populate_band_deck_rating(o.update_resources, state)
    return o.SerializeToString()


@app.delete('/api/suite/user/<int:user_id>/deck/<int:deck_id>'
            '/type/<string:deck_type>')
@app.delete('/api/suite/user/<int:user_id>/deck/<int:deck_id>')
def delete_user_deck_api(user_id, deck_id, deck_type='normal'):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(
        _state_store.delete_deck, effective_user_id, deck_id, deck_type
    )
    _sync_cached_deck_state(effective_user_id, state)
    o = suite_user_pb2.SuiteUserGetResponse()
    _populate_deck_state(o, state)
    _populate_owned_situation_state(o, state)
    _populate_character_costume_state(o, state)
    _populate_band_deck_rating(o, state)
    return o.SerializeToString()


@app.get('/api/user/<int:user_id>/deck.map')
def get_user_deck_map_api(user_id):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    decks = [deck for deck in state.decks if deck.deck_type == 'normal']
    try:
        offset = max(int(request.args.get('offset', 0)), 0)
        limit_value = request.args.get('limit')
        limit = max(int(limit_value), 0) if limit_value is not None else None
    except ValueError:
        abort(400, description='offset and limit must be integers')
    decks = decks[offset:] if limit is None else decks[offset:offset + limit]

    o = user_deck_api_pb2.UserDeckMapGetResponse()
    for deck in decks:
        _copy_deck(o.entries[deck.deck_id], deck)
    return o.SerializeToString()


@app.put('/api/suite/user/<int:user_id>/gallery')
def put_user_gallery_api(user_id):
    i = user_gallery_pb2.UserGallery.FromString(request.data or b'')
    state = _state_or_400(
        _state_store.upsert_gallery,
        user_id,
        i.situation_id,
        i.illust,
        i.seq,
    )
    _sync_cached_gallery_state(user_id, state)
    o = suite_user_pb2.SuiteUserGetResponse()
    _populate_gallery_state(o, state)
    return o.SerializeToString()


@app.delete('/api/suite/user/<int:user_id>/gallery')
def delete_user_gallery_api(user_id):
    state = _state_or_400(_state_store.clear_gallery, user_id)
    _sync_cached_gallery_state(user_id, state)
    o = suite_user_pb2.SuiteUserGetResponse()
    _populate_gallery_state(o, state)
    return o.SerializeToString()


def _set_main_deck(user_id):
    effective_user_id = _effective_user_id(user_id)
    i = user_pb2.UserPutRequest.FromString(request.data or b'')
    if not i.main_deck:
        abort(400, description='main_deck is required')
    state = _state_or_400(
        _state_store.set_main_deck, effective_user_id, i.main_deck
    )
    _sync_cached_deck_state(effective_user_id, state)
    return state


@app.put('/api/user/<int:user_id>/maindeck')
def put_user_main_deck_api(user_id):
    _set_main_deck(user_id)
    return b''


@app.put('/api/user/<int:user_id>', strict_slashes=False)
def put_user_profile_api(user_id):
    payload = request.data or b''
    field_numbers = _protobuf_field_numbers(payload)
    if field_numbers & _PROFILE_PUBLISH_REQUEST_FIELDS:
        i = user_pb2.UserProfilePublishConfigPutRequest.FromString(payload)
        state = _state_or_400(
            _state_store.update_profile_publish_config,
            user_id,
            {name: bool(getattr(i, name)) for name in _PROFILE_PUBLISH_NAMES},
        )
        _sync_cached_profile_state(user_id, state)
        return b''

    i = user_pb2.UserPutRequest.FromString(payload)
    identity = {}
    if 3 in field_numbers:
        identity['user_name'] = i.user_name
    if 16 in field_numbers:
        identity['birth_month'] = i.birth_month
    if 18 in field_numbers:
        identity['introduction'] = i.introduction
    if 19 in field_numbers:
        identity['degree'] = i.degree

    state = None
    if identity:
        state = _state_or_400(
            _state_store.update_profile_identity,
            user_id,
            **identity,
        )
    if 12 in field_numbers:
        state = _state_or_400(
            _state_store.set_main_deck, user_id, i.main_deck
        )
        _sync_cached_deck_state(user_id, state)
    if state is None:
        abort(400, description='unsupported user update')
    _sync_cached_profile_state(user_id, state)
    return b''


@app.put('/api/user/<int:user_id>/maindeck/nomissionprogress')
def put_user_main_deck_no_mission_api(user_id):
    _set_main_deck(user_id)
    o = user_pb2.UserMainDeckResponse()
    cached = _cached_suite_user(user_id)
    if cached is not None:
        o.user_commons_live2d_map.CopyFrom(cached.user_commons_live2d_map)
    return o.SerializeToString()


@app.route('/api/user/<int:user_id>/music/<int:music_id>',
           methods=['POST', 'PUT'])
def preprocess_user_music_api(user_id, music_id):
    effective_user_id = _effective_user_id(user_id)
    i = user_music_api_pb2.UserMusicPreProcessRequest.FromString(
        request.data or b''
    )
    state = _state_or_400(
        _state_store.start_live,
        effective_user_id,
        music_id,
        i.live_type or 'free_live',
        i.live_boost_use_count,
        i.event_id,
    )
    _sync_cached_live_state(effective_user_id, state)
    return b''


@app.route('/api/suite/user/<int:user_id>/music/<int:music_id>',
           methods=['POST', 'PUT'])
def clear_user_music_api(user_id, music_id):
    effective_user_id = _effective_user_id(user_id)
    i = user_music_api_pb2.UserMusicRequest.FromString(request.data or b'')
    before_clear = _state_or_400(_state_store.get_user_state, effective_user_id)
    music_difficulty = StateStore._normalize_music_difficulty(
        i.music_difficulty
    )
    previous_high_score = max(
        (
            score.solo_high_score
            for score in before_clear.music_scores
            if (score.music_id == music_id
                and score.music_difficulty == music_difficulty)
        ),
        default=0,
    )
    score_rank = _score_rank_for_music(
        music_id,
        music_difficulty,
        max(i.score, previous_high_score),
        fallback=StateStore._normalize_score_rank(i.clear_rank),
    )
    result = _state_or_400(
        _state_store.clear_live,
        effective_user_id,
        music_id,
        music_difficulty,
        score_rank,
        i.score,
        i.combo,
        i.clear_status,
        i.perfect_count,
        i.total_notes_count,
        i.event_id,
    )
    achievement_rewards = _music_achievement_rewards(
        music_id, result.new_achievement_types
    )
    state = result.user
    if achievement_rewards:
        state = _state_or_400(
            _state_store.grant_resources,
            effective_user_id,
            achievement_rewards,
        )
    state = _sync_recognized_missions(effective_user_id, state)
    _sync_cached_live_state(effective_user_id, state)

    o = user_music_api_pb2.SuiteUserMusic()
    _populate_live_state(o.update_resources, state)
    _populate_resource_list(o.drops, result.drops)
    o.newly_opened_contents.SetInParent()
    _populate_live_result_progression(o, state)
    _populate_resource_list(o.achievement_rewards, achievement_rewards)
    o.updated_band_deck_rank_list.SetInParent()
    o.lb_bonus = result.live_boost_bonus
    o.lb_use_count = result.live_boost_use_count
    o.solo_score_rank = result.score.solo_score_rank
    o.live_point = result.live_point
    o.user_music_achievement_map.CopyFrom(
        o.update_resources.user_music_achievement_map
    )
    # The 6.5.2 client dereferences limitedDrops before it builds the normal
    # drop result.  An empty-but-present message is therefore required.
    o.limited_drops.SetInParent()
    return o.SerializeToString()


@app.route('/api/suite/user/<int:user_id>/music/<int:music_id>/practice',
           methods=['POST', 'PUT'])
def clear_user_music_practice_api(user_id, music_id):
    effective_user_id = _effective_user_id(user_id)
    i = user_music_api_pb2.UserMusicPracticeRequest.FromString(
        request.data or b''
    )
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    o = user_music_api_pb2.SuiteUserMusicPractice()
    _populate_live_state(o.update_resources, state)
    o.solo_score_rank = (
        _score_rank_for_music(music_id, i.music_difficulty, i.score)
        if i.score else ''
    )
    return o.SerializeToString()


@app.route('/api/user/<int:user_id>/music/<int:music_id>/retry',
           methods=['POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/music/<int:music_id>/retry',
           methods=['POST', 'PUT'])
@app.route('/api/user/<int:user_id>/music/<int:music_id>/restart',
           methods=['POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/music/<int:music_id>/restart',
           methods=['POST', 'PUT'])
def retry_user_music_api(user_id, music_id):
    effective_user_id = _effective_user_id(user_id)
    user_music_api_pb2.RetryRequest.FromString(request.data or b'')
    state = _state_or_400(_state_store.retry_live, effective_user_id, music_id)
    _sync_cached_live_state(effective_user_id, state)
    return b''


@app.route('/api/user/<int:user_id>/music/retire', methods=['POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/music/retire',
           methods=['POST', 'PUT'])
@app.route('/api/user/<int:user_id>/music/giveup', methods=['POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/music/giveup',
           methods=['POST', 'PUT'])
@app.route('/api/user/<int:user_id>/music/<int:music_id>/retire',
           methods=['POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/music/<int:music_id>/retire',
           methods=['POST', 'PUT'])
@app.route('/api/user/<int:user_id>/music/<int:music_id>/giveup',
           methods=['POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/music/<int:music_id>/giveup',
           methods=['POST', 'PUT'])
@app.route('/api/user/<int:user_id>/music/<int:music_id>/give-up',
           methods=['POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/music/<int:music_id>/give-up',
           methods=['POST', 'PUT'])
@app.route('/api/user/<int:user_id>/music/<int:music_id>/abort',
           methods=['POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/music/<int:music_id>/abort',
           methods=['POST', 'PUT'])
@app.route('/api/user/<int:user_id>/music/<int:music_id>/cancel',
           methods=['POST', 'PUT', 'DELETE'])
@app.route('/api/suite/user/<int:user_id>/music/<int:music_id>/cancel',
           methods=['POST', 'PUT', 'DELETE'])
def abandon_user_music_api(user_id, music_id=None):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(
        _state_store.abandon_live, effective_user_id, music_id
    )
    _sync_cached_live_state(effective_user_id, state)
    response = suite_user_update_pb2.SuiteUserUpdateResponse()
    _populate_live_state(response.update_resources, state)
    return response.SerializeToString()


@app.put('/api/user/<int:user_id>/music/<int:music_id>/continue')
def continue_user_music_api(user_id, music_id):
    effective_user_id = _effective_user_id(user_id)
    i = user_music_api_pb2.UserMusicContinueRequest.FromString(
        request.data or b''
    )
    state = _state_or_400(
        _state_store.continue_live,
        effective_user_id,
        music_id,
        i.continue_count,
    )
    _sync_cached_live_state(effective_user_id, state)
    o = user_music_api_pb2.UserMusicContinueResponse()
    cached = _cached_suite_user(effective_user_id)
    if cached is not None:
        o.user_gamedata.CopyFrom(cached.user.user_gamedata)
    else:
        _populate_user_gamedata_defaults(o.user_gamedata, effective_user_id)
    _populate_user_gamedata(o.user_gamedata, state)
    o.continue_hash = 'local'
    return o.SerializeToString()


@app.get('/api/user/<int:user_id>/liveboost')
def get_user_live_boost_api(user_id):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    o = user_live_boost_pb2.UserLiveBoost()
    _populate_user_live_boost(o, state)
    return o.SerializeToString()


@app.put('/api/suite/user/<int:user_id>/liveboostrecoveryitem')
def recover_user_live_boost_api(user_id):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    payload = request.data or b''
    recovery_requests = []
    if payload:
        item = (
            user_live_boost_recovery_item_pb2
            .UserLiveBoostRecoveryItem
            .FromString(payload)
        )
        if item.live_boost_recovery_item_id or item.quantity:
            recovery_requests.append((
                item.live_boost_recovery_item_id,
                item.quantity or 1,
            ))
        else:
            item_list = (
                user_live_boost_recovery_item_pb2
                .UserLiveBoostRecoveryItemList
                .FromString(payload)
            )
            recovery_requests.extend(
                (
                    entry.live_boost_recovery_item_id,
                    entry.quantity or 1,
                )
                for entry in item_list.entries
            )
    if not recovery_requests:
        fallback_id = (
            state.live_boost_recovery_items[0].live_boost_recovery_item_id
            if state.live_boost_recovery_items else 0
        )
        recovery_requests.append((fallback_id, 1))

    for recovery_item_id, recovery_item_count in recovery_requests:
        if not recovery_item_id and state.live_boost_recovery_items:
            recovery_item_id = (
                state.live_boost_recovery_items[0]
                .live_boost_recovery_item_id
            )
        state = _state_or_400(
            _state_store.recover_live_boost,
            effective_user_id,
            recovery_item_id,
            _master_live_boost_recovery_amount(recovery_item_id),
            recovery_item_count,
        )
        if state.live_boost >= LIVE_BOOST_ITEM_MAX:
            break
    _sync_cached_live_state(effective_user_id, state)

    response = suite_user_update_pb2.SuiteUserUpdateResponse()
    _populate_live_state(response.update_resources, state)
    return response.SerializeToString()


@app.get('/api/suite/user/<int:user_id>/friend/relation')
def get_user_friend_relation_api(user_id):
    o = suite_user_friend_pb2.SuiteUserFriendRelationResponse()
    relation = o.update_resources.user_friend_relation_detail
    cached = _cached_suite_user(user_id)
    if cached is not None:
        relation.CopyFrom(cached.user_friend_relation_detail)
    else:
        _populate_empty_friend_detail(relation)
    return o.SerializeToString()


@app.get('/api/suite/user/<int:user_id>/friend/<string:friend_state>')
def get_user_friend_api(user_id, friend_state):
    if friend_state not in {'application', 'approval', 'friend'}:
        abort(404, description=f'unknown friend state: {friend_state}')
    o = suite_user_friend_pb2.SuiteUserFriendTopResponse()
    _populate_empty_friend_detail(o.user_friend_detail)
    relation = o.update_resources.user_friend_relation_detail
    cached = _cached_suite_user(user_id)
    if cached is not None:
        relation.CopyFrom(cached.user_friend_relation_detail)
    else:
        _populate_empty_friend_detail(relation)
    return o.SerializeToString()


@app.get('/api/user/<int:user_id>/present')
def get_user_present_api(user_id):
    effective_user_id = _effective_user_id(user_id)
    try:
        start = max(int(request.args.get('start', 0)), 0)
        limit = max(int(request.args.get('limit', 100)), 0)
    except ValueError:
        abort(400, description='start and limit must be integers')
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    limit = min(limit, 100)
    return _serialize_present_list(
        effective_user_id,
        state.presents,
        start,
        limit,
    )


@app.get('/api/user/<int:user_id>/presenthistory')
def get_user_present_history_api(user_id):
    effective_user_id = _effective_user_id(user_id)
    try:
        start = max(int(request.args.get('start', 0)), 0)
        limit = max(int(request.args.get('limit', 100)), 0)
    except ValueError:
        abort(400, description='start and limit must be integers')
    history = _state_or_400(
        _state_store.list_present_history,
        effective_user_id,
    )
    limit = min(limit, 100)
    return _serialize_present_list(effective_user_id, history, start, limit)


def _serialize_present_list(effective_user_id, all_presents, start, limit):
    presents = all_presents[start:start + limit]
    o = user_present_pb2.UserPresentList()
    for present in presents:
        entry = o.entries.add()
        entry.present_id = present.present_id
        entry.user_id = effective_user_id
        entry.resource_type = present.resource_type
        entry.resource_id = present.resource_id
        entry.quantity = present.quantity
        entry.reason = present.reason
        if present.expired_at is not None:
            entry.expired_at = present.expired_at
        entry.created_at = present.created_at
    o.pagination.start = start
    o.pagination.limit = limit
    o.pagination.record = len(all_presents)
    return o.SerializeToString()


@app.route('/api/suite/user/<int:user_id>/present', methods=['POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/present/acceptall',
           methods=['POST', 'PUT'])
def receive_user_present_api(user_id):
    effective_user_id = _effective_user_id(user_id)
    payload = user_present_pb2.UserPresentList.FromString(request.data or b'')
    receipt = _state_or_400(
        _state_store.receive_presents,
        effective_user_id,
        [entry.present_id for entry in payload.entries],
    )
    _sync_cached_gacha_state(effective_user_id, receipt.user)

    response = user_present_pb2.ObtainPresentResponse()
    _populate_updated_user(response.update_resources, receipt.user)
    _populate_gacha_ticket_state(response.update_resources, receipt.user)
    _populate_inventory_state(response.update_resources, receipt.user)
    _populate_present_count(response.update_resources, receipt.user)
    for present in receipt.presents:
        resource = response.resources.entries.add()
        resource.resource_id = present.resource_id
        resource.resource_type = present.resource_type
        resource.quantity = present.quantity
    response.newly_opened_contents.SetInParent()
    return response.SerializeToString()


@app.route('/api/suite/user/<int:user_id>/present/<int:present_id>',
           methods=['POST', 'PUT'])
def receive_single_user_present_api(user_id, present_id):
    effective_user_id = _effective_user_id(user_id)
    receipt = _state_or_400(
        _state_store.receive_presents,
        effective_user_id,
        [present_id],
    )
    _sync_cached_gacha_state(effective_user_id, receipt.user)

    response = user_present_pb2.ObtainPresentResponse()
    _populate_updated_user(response.update_resources, receipt.user)
    _populate_gacha_ticket_state(response.update_resources, receipt.user)
    _populate_inventory_state(response.update_resources, receipt.user)
    _populate_present_count(response.update_resources, receipt.user)
    for present in receipt.presents:
        resource = response.resources.entries.add()
        resource.resource_id = present.resource_id
        resource.resource_type = present.resource_type
        resource.quantity = present.quantity
    response.newly_opened_contents.SetInParent()
    return response.SerializeToString()


@app.get('/api/user/<int:user_id>/multiroomfriendrecruitment')
def get_multi_room_friend_recruitment_api(user_id):
    o = (user_multi_room_friend_recruitment_pb2
         .UserMultiRoomFriendRecruitmentLiveTopResponse())
    return o.SerializeToString()


@app.route('/api/suite/user/<int:user_id>/mission/init',
           methods=['GET', 'POST', 'PUT'])
def initialize_user_mission_api(user_id):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    state = _sync_recognized_missions(effective_user_id, state)
    response = suite_user_pb2.SuiteUserGetResponse()
    _populate_mission_state(response, state)
    return response.user_mission_map.SerializeToString()


@app.route('/api/suite/user/<int:user_id>/mission/clear/',
           defaults={'mission_type': ''}, methods=['POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/mission/clear/<path:mission_type>',
           methods=['POST', 'PUT'])
def clear_user_mission_api(user_id, mission_type):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(
        _state_store.sync_missions, effective_user_id, mission_type
    )
    state = _sync_recognized_missions(effective_user_id, state)
    response = suite_user_mission_pb2.MissionClear()
    _populate_mission_state(response.update_resources, state)
    return response.SerializeToString()


@app.route('/api/suite/user/<int:user_id>/mission/'
           '<int:mission_id>/<int:seq>/reward', methods=['POST', 'PUT'])
def receive_user_mission_reward_api(user_id, mission_id, seq):
    effective_user_id = _effective_user_id(user_id)
    _sync_recognized_missions(effective_user_id)
    master = _master_mission_reward(mission_id, seq)
    if master is None:
        abort(404, description='mission reward master was not found')
    _group_id, reward, next_target = master
    result = _state_or_400(
        _state_store.claim_mission_reward,
        effective_user_id,
        mission_id,
        seq,
        (reward,),
        next_target,
    )
    _sync_cached_live_state(effective_user_id, result.user)
    response = suite_user_mission_pb2.MissionReward()
    _populate_live_state(response.update_resources, result.user)
    _populate_resource_list(response.mission_reward_list, result.rewards)
    return response.SerializeToString()


@app.route('/api/suite/user/<int:user_id>/mission/bulk/reward/'
           '<string:group_type>', methods=['POST', 'PUT'])
def receive_user_mission_bulk_reward_api(user_id, group_type):
    effective_user_id = _effective_user_id(user_id)
    group_ids = {
        'normal': 101,
        'album': 201,
        'limited': 0,
        'ex_mission': 301,
        'countdown': 0,
    }
    try:
        group_id = int(group_type)
    except ValueError:
        group_id = group_ids.get(group_type.lower(), 0)
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    state = _sync_recognized_missions(effective_user_id, state)
    all_rewards = []
    for mission in tuple(state.missions):
        if (mission.mission_group_id != group_id
                or mission.mission_progress_type != 'complete'):
            continue
        master = _master_mission_reward(mission.mission_id, mission.seq)
        if master is None:
            continue
        _master_group, reward, next_target = master
        claimed = _state_or_400(
            _state_store.claim_mission_reward,
            effective_user_id,
            mission.mission_id,
            mission.seq,
            (reward,),
            next_target,
        )
        state = claimed.user
        all_rewards.extend(claimed.rewards)
    _sync_cached_live_state(effective_user_id, state)
    response = suite_user_mission_pb2.MissionReward()
    _populate_live_state(response.update_resources, state)
    _populate_resource_list(response.mission_reward_list, all_rewards)
    return response.SerializeToString()


@app.post('/api/suite/user/<int:user_id>/mission/panel/'
          '<int:panel_mission_id>/reward')
def receive_panel_mission_reward_api(user_id, panel_mission_id):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    board_seq = 0
    if request.data:
        try:
            payload = (
                suite_user_panel_mission_pb2.PanelMissionClearInfo
                .FromString(request.data)
            )
            board_seq = payload.board_seq
        except Exception:
            board_seq = 0
    if not board_seq:
        board_seq = _next_panel_reward_board(state, panel_mission_id)

    rewards = ()
    if board_seq:
        reward = _panel_board_reward(panel_mission_id, board_seq)
        if reward is not None:
            rewards = (reward,)
        result = _state_or_400(
            _state_store.claim_panel_mission_reward,
            effective_user_id,
            panel_mission_id,
            board_seq,
            rewards,
        )
        state = result.user
        rewards = result.rewards

    _sync_cached_live_state(effective_user_id, state)
    o = suite_user_panel_mission_pb2.SuitePanelMissionReward()
    _populate_live_state(o.update_resources, state)
    o.current_clear_info.panel_mission_id = panel_mission_id
    o.current_clear_info.board_seq = board_seq
    o.current_clear_info.panel_seq_list.extend(
        _panel_board_panel_seqs(panel_mission_id, board_seq)
    )
    _populate_resource_list(o.current_clear_info.reward_list, rewards)

    next_board_seq = _next_panel_reward_board(state, panel_mission_id)
    if next_board_seq:
        o.next_board_clear_info.panel_mission_id = panel_mission_id
        o.next_board_clear_info.board_seq = next_board_seq
        o.next_board_clear_info.panel_seq_list.extend(
            _panel_board_panel_seqs(panel_mission_id, next_board_seq)
        )
    else:
        o.next_board_clear_info.SetInParent()
    _populate_resource_list(o.board_complete_reward_list, rewards)
    return o.SerializeToString()


def _claim_login_bonus(user_id, login_bonus_id):
    state = _state_or_400(_state_store.get_user_state, user_id)
    current_bonus = next(
        (
            bonus for bonus in state.login_bonuses
            if bonus.login_bonus_id == login_bonus_id
        ),
        None,
    )
    current_day = current_bonus.days if current_bonus is not None else 1
    master = _master_login_bonus(login_bonus_id)
    if master is None:
        abort(404, description=f'unknown login_bonus_id: {login_bonus_id}')
    cycle_length = _login_bonus_cycle_length(master)
    if not cycle_length:
        abort(404, description='login bonus has no rewards')
    reward_day = ((current_day - 1) % cycle_length) + 1
    return _state_or_400(
        _state_store.receive_login_bonus,
        user_id,
        login_bonus_id,
        _login_bonus_rewards(master, reward_day),
        cycle_length,
    )


@app.put('/api/suite/user/<int:user_id>/loginbonus/acceptall')
def suite_login_bonus_accept_all_api(user_id):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    received_today = today_kst_iso()
    for bonus in tuple(state.login_bonuses):
        if bonus.last_received_on == received_today:
            continue
        result = _claim_login_bonus(effective_user_id, bonus.login_bonus_id)
        state = result.user
    _sync_cached_live_state(effective_user_id, state)

    o = suite_user_login_bonus_pb2.SuiteUserLoginBonusAcceptAllResponse()
    _populate_live_state(o.update_resources, state)
    return o.SerializeToString()


@app.get('/api/system/application')
def get_server_system_api():
    o = server_system_pb2.ServerSystem()
    o.server_date = int(time.time()*1000)
    o.time_zone_raw_offset = 32_400_000
    return o.SerializeToString()


@app.get('/api/cleanupinfo')
def get_cleanup_info_api():
    with open('server/responses/cleanup_info.binpb', 'rb') as f:
        o = f.read()
    return o


def _event_suite_response_message(user_id, event_id=0, state=None):
    effective_user_id = _effective_user_id(user_id)
    if state is None:
        state = _state_or_400(_state_store.get_user_state, effective_user_id)
    response = suite_user_pb2.SuiteUserGetResponse()
    _populate_live_state(response, state)
    _populate_deck_state(response, state)
    _populate_deck_member_situations(response, state)
    _populate_event_exchange_state(response, state, event_id)
    _populate_event_box_gacha_state(response, state, event_id)
    _ensure_event_item_entry(response, state, event_id)
    return response


def _event_suite_response(user_id, event_id=0):
    response = _event_suite_response_message(user_id, event_id)
    return response.SerializeToString()


def _exchange_suite_response(user_id, state=None):
    effective_user_id = _effective_user_id(user_id)
    if state is None:
        state = _state_or_400(_state_store.get_user_state, effective_user_id)
    response = suite_user_pb2.SuiteUserGetResponse()
    cached = _cached_suite_user(effective_user_id)
    if cached is not None:
        response.CopyFrom(cached)
    _populate_live_state(response, state)
    _populate_deck_state(response, state)
    _populate_deck_member_situations(response, state)
    return response


@app.route('/api/suite/user/<int:user_id>/exchange',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/exchanges',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/exchange/top',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/exchanges/top',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/user/<int:user_id>/exchange',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/user/<int:user_id>/exchanges',
           methods=['GET', 'POST', 'PUT'])
def suite_exchange_top_api(user_id):
    return _exchange_suite_response(user_id).SerializeToString()


@app.route('/api/suite/user/<int:user_id>/exchange/<int:exchanges_id>',
           methods=['POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/exchanges/<int:exchanges_id>',
           methods=['POST', 'PUT'])
@app.route('/api/user/<int:user_id>/exchange/<int:exchanges_id>',
           methods=['POST', 'PUT'])
@app.route('/api/user/<int:user_id>/exchanges/<int:exchanges_id>',
           methods=['POST', 'PUT'])
def suite_exchange_action_api(user_id, exchanges_id):
    effective_user_id = _effective_user_id(user_id)
    requested_count = 1
    if request.data:
        payload = user_event_exchanges_pb2.UserEventExchangesRequest.FromString(
            request.data
        )
        requested_count = payload.count or 1

    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    detail = _exchange_detail(exchanges_id)
    result = None
    if detail is not None:
        reward = _resource_from_exchange_detail(detail)
        if reward is not None:
            result = _state_or_400(
                _state_store.purchase_exchange,
                effective_user_id,
                exchanges_id,
                _exchange_cost(detail),
                [reward],
                requested_count,
                _exchange_limit(detail),
            )
            state = result.user

    _sync_cached_live_state(effective_user_id, state)
    response = suite_user_exchanges_pb2.SuiteUserExchanges()
    response.update_resources.CopyFrom(
        _exchange_suite_response(user_id, state)
    )
    exchanged_count = 0 if result is None else result.total_exchanged_count
    exchange = response.user_exchanges
    exchange.user_id = effective_user_id
    exchange.exchanges_id = exchanges_id
    exchange.remain = (
        999_999 if detail is None
        else _exchange_remain(detail, exchanged_count)
    )
    exchange.reset_at = 0 if detail is None else _master_uint(detail, '8')
    return response.SerializeToString()


@app.route('/api/suite/user/<int:user_id>/event/top',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/event/<int:event_id>/top',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/user/<int:user_id>/event/top',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/user/<int:user_id>/event/<int:event_id>/top',
           methods=['GET', 'POST', 'PUT'])
def suite_event_top_api(user_id, event_id=0):
    return _event_suite_response(user_id, event_id)


@app.route('/api/suite/user/<int:user_id>/event/exchange',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/event/exchanges',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/event/<int:event_id>/exchange',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/event/<int:event_id>/exchanges',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/user/<int:user_id>/event/exchange',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/user/<int:user_id>/event/<int:event_id>/exchange',
           methods=['GET', 'POST', 'PUT'])
def suite_event_exchange_api(user_id, event_id=0):
    return _event_suite_response(user_id, event_id)


@app.route('/api/suite/user/<int:user_id>/event/boxgacha',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/event/box_gacha',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/event/<int:event_id>/boxgacha',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/event/<int:event_id>/box_gacha',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/event/<int:event_id>/boxgacha/spin',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/user/<int:user_id>/event/boxgacha',
           methods=['GET', 'POST', 'PUT'])
@app.route('/api/user/<int:user_id>/event/<int:event_id>/boxgacha',
           methods=['GET', 'POST', 'PUT'])
def suite_event_box_gacha_api(user_id, event_id=0):
    return _event_suite_response(user_id, event_id)


@app.route('/api/suite/user/<int:user_id>/eventboxgacha/top',
           methods=['GET', 'POST', 'PUT'])
def suite_event_box_gacha_top_api(user_id):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    payload = user_event_box_gacha_pb2.EventBoxGachaTopRequest.FromString(
        request.data or b''
    )
    event_box_gacha_id = (
        payload.event_box_gacha_id or _current_event_id(state)
    )
    response = suite_user_event_box_gacha_pb2.SuiteEventBoxGachaTopResponse()
    response.update_resources.CopyFrom(
        _event_suite_response_message(user_id, event_box_gacha_id, state)
    )
    response.event_box_gacha_top_response.event_box_gacha_id = (
        event_box_gacha_id
    )
    response.event_box_gacha_top_response.first_flg = False
    return response.SerializeToString()


@app.route('/api/suite/user/<int:user_id>/eventboxgacha/spin',
           methods=['POST', 'PUT'])
def suite_event_box_gacha_spin_api(user_id):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    payload = user_event_box_gacha_pb2.EventBoxGachaSpinRequest.FromString(
        request.data or b''
    )
    event_box_gacha_id = (
        payload.event_box_gacha_id or _current_event_id(state)
    )
    requested_spin_count = min(
        payload.spin_count,
        _EVENT_BOX_GACHA_MAX_SPIN_COUNT,
    )
    details = _event_box_gacha_details(event_box_gacha_id)
    box_gacha_event_id = _event_item_id_for_box_gacha(
        event_box_gacha_id, details
    )
    event_item_id = _event_item_id_for_user_event(state, box_gacha_event_id)
    event_item_cost = requested_spin_count * _EVENT_BOX_GACHA_COST_PER_SPIN
    actual_spin_count = 0
    selected_details = ()
    if (requested_spin_count and details
            and _event_item_quantity(state, event_item_id) >= event_item_cost):
        actual_spin_count = requested_spin_count
        selected_details = _select_event_box_gacha_drop_details(
            details, actual_spin_count
        )
        rewards = tuple(
            resource
            for resource in (
                _resource_from_event_box_gacha_detail(detail)
                for detail in selected_details
            )
            if resource is not None
        )
        state = _state_or_400(
            _state_store.spend_event_item_and_grant_resources,
            effective_user_id,
            event_item_id,
            event_item_cost,
            rewards,
        )

    response = suite_user_event_box_gacha_pb2.SuiteEventBoxGachaSpinResponse()
    response.update_resources.CopyFrom(
        _event_suite_response_message(user_id, event_box_gacha_id, state)
    )
    spin_response = response.event_box_gacha_spin_response
    for detail in selected_details:
        _copy_master_event_box_gacha_detail(spin_response.drop_details.add(),
                                            detail)
    spin_response.auto_reset_flg = False
    spin_response.auto_stop_flg = False
    spin_response.spin_count = actual_spin_count
    return response.SerializeToString()


@app.route('/api/suite/user/<int:user_id>/eventboxgacha/reset/'
           '<int:event_box_gacha_id>',
           methods=['POST', 'PUT'])
def suite_event_box_gacha_reset_api(user_id, event_box_gacha_id):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    response = suite_user_event_box_gacha_pb2.SuiteEventBoxGachaResetResponse()
    response.update_resources.CopyFrom(
        _event_suite_response_message(user_id, event_box_gacha_id, state)
    )
    return response.SerializeToString()


@app.route('/api/user/<int:user_id>/eventboxgacha/settings',
           methods=['GET', 'POST', 'PUT'])
def user_event_box_gacha_settings_api(user_id):
    settings = user_event_box_gacha_pb2.UserEventBoxGachaSpinSettings()
    if request.data:
        settings.ParseFromString(request.data)
    return settings.SerializeToString()


@app.route('/api/suite/user/<int:user_id>/eventexchanges/'
           '<int:event_id>/<int:seq>',
           methods=['POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/eventexchange/'
           '<int:event_id>/<int:seq>',
           methods=['POST', 'PUT'])
@app.route('/api/user/<int:user_id>/eventexchanges/'
           '<int:event_id>/<int:seq>',
           methods=['POST', 'PUT'])
def suite_event_exchanges_action_api(user_id, event_id, seq):
    effective_user_id = _effective_user_id(user_id)
    requested_count = 1
    if request.data:
        payload = user_event_exchanges_pb2.UserEventExchangesRequest.FromString(
            request.data
        )
        requested_count = payload.count or 1
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    detail = _event_exchange_detail(event_id, seq)
    result = None
    if detail is not None:
        reward = _resource_from_event_exchange_detail(detail)
        if reward is not None:
            result = _state_or_400(
                _state_store.purchase_event_exchange,
                effective_user_id,
                event_id,
                seq,
                _event_item_id_for_user_event(state, event_id),
                _master_uint(detail, '7'),
                [reward],
                requested_count,
                _event_exchange_limit(detail),
            )
            state = result.user
    response = suite_user_exchanges_pb2.SuiteUserExchanges()
    response.update_resources.CopyFrom(
        _event_suite_response_message(user_id, event_id, state)
    )
    exchanged_count = 0 if result is None else result.total_exchanged_count
    exchange = response.user_exchanges
    exchange.user_id = effective_user_id
    exchange.exchanges_id = seq
    exchange.remain = (
        999_999 if detail is None
        else _event_exchange_remain(detail, exchanged_count)
    )
    exchange.reset_at = 0
    return response.SerializeToString()


def _event_story_read_response(user_id, event_id, seq):
    effective_user_id = _effective_user_id(user_id)
    rewards = _event_story_rewards(event_id, seq)
    result = _state_or_400(
        _state_store.read_event_story,
        effective_user_id,
        event_id,
        seq,
        rewards,
    )
    _sync_cached_live_state(effective_user_id, result.user)

    response = suite_user_event_story_memorial_pb2.SuiteReadStoryResponse()
    response.update_resources.CopyFrom(
        _event_suite_response_message(user_id, event_id, result.user)
    )
    read_response = response.user_story_event_read_story_response
    read_story = read_response.read_user_event_story
    read_story.user_id = effective_user_id
    read_story.event_id = event_id
    read_story.seq = seq
    read_story.status = 'already_read'
    _populate_resource_list(read_response.rewards, result.rewards)
    read_response.newly_opened_contents.SetInParent()

    next_story = _event_story_detail(event_id, seq + 1)
    if next_story is not None:
        read_response.recommend_story_id = seq + 1
        read_response.recommend_story_type = 'event'
    return response


@app.route('/api/suite/user/<int:user_id>/eventstory/'
           '<int:event_id>/<int:seq>',
           methods=['POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/eventstory/'
           '<int:event_id>/<int:seq>/read',
           methods=['POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/event/<int:event_id>/story/'
           '<int:seq>',
           methods=['POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/event/<int:event_id>/story/'
           '<int:seq>/read',
           methods=['POST', 'PUT'])
@app.route('/api/suite/user/<int:user_id>/story/event/'
           '<int:event_id>/<int:seq>',
           methods=['POST', 'PUT'])
def suite_event_story_read_api(user_id, event_id, seq):
    return _event_story_read_response(
        user_id, event_id, seq
    ).SerializeToString()


@app.route('/api/user/<int:user_id>/eventstory/<int:event_id>/<int:seq>',
           methods=['POST', 'PUT'])
@app.route('/api/user/<int:user_id>/eventstory/'
           '<int:event_id>/<int:seq>/read',
           methods=['POST', 'PUT'])
@app.route('/api/user/<int:user_id>/event/<int:event_id>/story/<int:seq>',
           methods=['POST', 'PUT'])
@app.route('/api/user/<int:user_id>/event/<int:event_id>/story/'
           '<int:seq>/read',
           methods=['POST', 'PUT'])
def user_event_story_read_api(user_id, event_id, seq):
    return (
        _event_story_read_response(user_id, event_id, seq)
        .user_story_event_read_story_response
        .SerializeToString()
    )


@app.get('/api/suite/user/<int:user_id>/area')
def get_user_area_character_api(user_id):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    return _user_area_response_from_state(state).SerializeToString()


@app.get('/api/user/<int:user_id>/area')
def get_user_area_character_alias_api(user_id):
    return get_user_area_character_api(user_id)


@app.route(
    '/api/suite/user/<int:user_id>/area/<int:area_id>/actionset/'
    '<int:action_set_id>',
    methods=['POST', 'PUT'],
)
@app.route(
    '/api/suite/user/<int:user_id>/area/<int:area_id>/actionset/'
    '<int:action_set_id>/read',
    methods=['POST', 'PUT'],
)
@app.route(
    '/api/user/<int:user_id>/area/<int:area_id>/actionset/'
    '<int:action_set_id>',
    methods=['POST', 'PUT'],
)
@app.route(
    '/api/suite/user/<int:user_id>/area/actionset/<int:action_set_id>',
    methods=['POST', 'PUT'],
)
@app.route(
    '/api/user/<int:user_id>/area/actionset/<int:action_set_id>',
    methods=['POST', 'PUT'],
)
@app.route(
    '/api/suite/user/<int:user_id>/actionset/<int:action_set_id>',
    methods=['POST', 'PUT'],
)
@app.route(
    '/api/suite/user/<int:user_id>/actionset/<int:action_set_id>/read',
    methods=['POST', 'PUT'],
)
@app.route(
    '/api/user/<int:user_id>/actionset/<int:action_set_id>',
    methods=['POST', 'PUT'],
)
def read_user_area_action_set_api(user_id, action_set_id, area_id=None):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    _area, action_set = _find_area_action_set(state, action_set_id, area_id)
    if action_set is None:
        abort(404, description='area action set was not found')
    if action_set.status == 'can_not_read':
        abort(400, description='area action set is not readable yet')

    result = _state_or_400(
        _state_store.read_action_set,
        effective_user_id,
        action_set_id,
        (ResourceState('star', 0, _AREA_ACTION_SET_REWARD_STAR),),
    )
    state = _sync_recognized_missions(effective_user_id, result.user)
    _sync_cached_live_state(effective_user_id, state)

    response = suite_user_pb2.SuiteUserGetResponse()
    _populate_live_state(response, state)
    return response.SerializeToString()


@app.get('/api/user/<int:user_id>/shop/<int:shop_id>/list')
def get_user_area_shop_list_api(user_id, shop_id):
    effective_user_id = _effective_user_id(user_id)
    if request.data:
        payload = user_shoplist_api_pb2.UserShoplistRequest.FromString(
            request.data
        )
        if payload.user_id and payload.user_id not in (
                user_id, effective_user_id):
            abort(400, description='request user_id does not match the URL')
        if payload.shop_id and payload.shop_id != shop_id:
            abort(400, description='request shop_id does not match the URL')
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    response = user_shoplist_api_pb2.UserShoplistResponse()
    _populate_user_shoplist(response, state, shop_id)
    return response.SerializeToString()


@app.route(
    '/api/suite/user/<int:user_id>/shop/<int:shop_id>/list/<int:shop_list_id>',
    methods=['POST', 'PUT'],
)
def purchase_user_area_shop_item_api(user_id, shop_id, shop_list_id):
    effective_user_id = _effective_user_id(user_id)
    if request.data:
        user_shoplist_api_pb2.UserAreaItemRequest.FromString(request.data)
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    target = next(
        (
            (master, area_item, status)
            for master, area_item, status in _area_shop_rows(state, shop_id)
            if master['1'] == shop_list_id
        ),
        None,
    )
    if target is None:
        abort(400, description='shop list is not the current purchase target')
    master, area_item, status = target
    expected_status = 'upgrade' if request.method == 'PUT' else 'purchase'
    if status != expected_status:
        abort(400, description=f'area item is not available for {expected_status}')

    result = _state_or_400(
        _state_store.purchase_area_item,
        effective_user_id,
        area_item['1'],
        area_item['2'],
        area_item['3'],
        area_item['5'],
        master.get('6', 0),
        _master_shop_item_costs(master),
        upgrade=(request.method == 'PUT'),
    )
    state = _sync_recognized_missions(effective_user_id, result.user)
    _sync_cached_area_item_state(effective_user_id, state)

    response = user_shoplist_api_pb2.SuiteUserShoplistResponse()
    _populate_updated_user(response.update_resources, state)
    _populate_inventory_state(response.update_resources, state)
    _populate_area_item_state(response.update_resources, state)
    _populate_enabled_area_items(response.update_resources, state)
    _populate_band_deck_rating(response.update_resources, state)
    _populate_mission_state(response.update_resources, state)
    _populate_user_shoplist(response.user_shop_list, state, shop_id)
    response.newly_opened_contents.SetInParent()
    response.updated_band_deck_rank_list.SetInParent()
    return response.SerializeToString()


@app.put('/api/suite/user/<int:user_id>/area')
def put_user_area_items_api(user_id):
    effective_user_id = _effective_user_id(user_id)
    payload = user_area_pb2.PutAreaItemRequestBody.FromString(
        request.data or b''
    )
    current = _state_or_400(_state_store.get_user_state, effective_user_id)
    owned = {item.area_item_id: item for item in current.area_items}
    placements = []
    for area_item_id in payload.area_item_id_list:
        item = owned.get(area_item_id)
        master = _master_area_item(area_item_id)
        if item is None or master is None:
            abort(400, description=f'area item is not owned: {area_item_id}')
        placements.append(AreaItemPlacementState(
            area_item_id=area_item_id,
            area_item_category=item.area_item_category,
            area_id=master['5'],
        ))
    state = _state_or_400(
        _state_store.put_area_items, effective_user_id, placements
    )
    _sync_cached_area_item_state(effective_user_id, state)
    return _area_change_response_from_state(state).SerializeToString()


@app.put('/api/suite/user/<int:user_id>/area/item/recommended')
def put_recommended_user_area_items_api(user_id):
    effective_user_id = _effective_user_id(user_id)
    current = _state_or_400(_state_store.get_user_state, effective_user_id)
    state = _state_or_400(
        _state_store.put_area_items,
        effective_user_id,
        _recommended_area_item_placements(current),
    )
    _sync_cached_area_item_state(effective_user_id, state)
    return _area_change_response_from_state(state).SerializeToString()


@app.put(
    '/api/suite/user/<int:user_id>/area/<int:area_id>/item/<int:area_item_id>'
)
def put_single_user_area_item_api(user_id, area_id, area_item_id):
    effective_user_id = _effective_user_id(user_id)
    if request.data:
        user_shoplist_api_pb2.UserAreaItemRequest.FromString(request.data)
    current = _state_or_400(_state_store.get_user_state, effective_user_id)
    owned = next(
        (item for item in current.area_items
         if item.area_item_id == area_item_id),
        None,
    )
    master = _master_area_item(area_item_id)
    if owned is None or master is None:
        abort(400, description=f'area item is not owned: {area_item_id}')
    if master['5'] != area_id:
        abort(400, description='area item does not belong to the target area')

    # A spawn point can contain only one object.  Installing a new object at
    # that point sends the previous one back to inventory.
    target_spawn_point = master.get('6', '')
    placements = []
    for placement in current.area_item_placements:
        placed_master = _master_area_item(placement.area_item_id)
        if placement.area_item_category == owned.area_item_category:
            continue
        if (placement.area_id == area_id and placed_master is not None
                and placed_master.get('6', '') == target_spawn_point):
            continue
        placements.append(placement)
    placements.append(AreaItemPlacementState(
        area_item_id=area_item_id,
        area_item_category=owned.area_item_category,
        area_id=area_id,
    ))
    state = _state_or_400(
        _state_store.put_area_items, effective_user_id, placements
    )
    _sync_cached_area_item_state(effective_user_id, state)
    return _area_change_response_from_state(state).SerializeToString()


@app.put('/api/suite/user/<int:user_id>/loginbonus/<int:login_bonus_id>/watch')
@app.put('/api/suite/user/<int:user_id>/loginbonus/<int:login_bonus_id>')
def suite_login_bonus_api(user_id, login_bonus_id):
    effective_user_id = _effective_user_id(user_id)
    result = _claim_login_bonus(effective_user_id, login_bonus_id)
    _sync_cached_live_state(effective_user_id, result.user)

    o = suite_user_login_bonus_pb2.SuiteUserLoginBonus()
    _populate_live_state(o.update_resources, result.user)
    _populate_resource_list(o.accept_response.player_resources, result.rewards)
    _populate_resource_list(o.accept_response.granted_bonus, result.rewards)
    return o.SerializeToString()


@app.get('/api/user/<int:user_id>/bandstory/<int:band_id>')
def user_band_story_api(user_id, band_id):
    o = user_band_story_pb2.UserBandStoryList()
    field = _BAND_STORY_FIELDS.get(band_id)
    cached = _cached_suite_user(user_id)
    if field is None:
        abort(404, description=f'unknown band_id: {band_id}')
    if cached is None:
        abort(409, description='suite user state has not been loaded')
    o.CopyFrom(getattr(cached, field))
    return o.SerializeToString()


@app.post('/api/suite/user/<int:user_id>/bandstory/<int:band_id>'
          '/id/<int:band_story_id>')
def post_suite_user_band_story_api(user_id, band_id, band_story_id):
    field = _BAND_STORY_FIELDS.get(band_id)
    if field is None:
        abort(404, description=f'unknown band_id: {band_id}')
    cached = _cached_suite_user(user_id)
    if cached is None:
        abort(409, description='suite user state has not been loaded')

    story_list = getattr(cached, field)
    for story in story_list.entries:
        if story.band_story_id == band_story_id:
            story.status = 'already_read'
            break
    else:
        abort(404, description=f'unknown band_story_id: {band_story_id}')
    _state_or_400(
        _state_store.read_band_story, user_id, band_id, band_story_id
    )

    o = suite_user_story_pb2.SuiteUserBandStoryResponse()
    o.user_band_story_list.CopyFrom(story_list)
    getattr(o.update_resources, field).CopyFrom(story_list)
    o.rewards.SetInParent()
    o.newly_opened_contents.SetInParent()
    return o.SerializeToString()


@app.post('/api/user/<int:user_id>/logging/playstory')
def post_logging_play_story_api(user_id):
    return b''


@app.post('/api/user/<int:user_id>/musicvideo/watching/<int:music_id>'
          '/<int:seq>')
def post_music_video_watching_api(user_id, music_id, seq):
    return b''


@app.get('/api/user/<int:user_id>/actionset/album/<int:character_id>')
def get_user_action_set_album_api(user_id, character_id):
    _effective_user_id(user_id)
    o = user_action_set_album_pb2.UserActionSetAlbumMap()
    action_set_metadata = _load_action_set_master_payload()

    for master in _album_action_set_rows(character_id):
        action_set_id = master['1']
        metadata = action_set_metadata.get(str(action_set_id), {})
        action_set = o.entries[action_set_id]
        action_set.action_set_id = action_set_id
        action_set.balloon_text = master.get('2', {}).get('11', '')
        action_set.is_memorial = (
            metadata.get('startSeason') == 'season_1'
            and 'endSeason' in metadata
        )

    return o.SerializeToString()


@app.get('/api/user/<int:user_id>/backstagetalkset/readhistory')
def get_user_backstage_talk_set_read_history_map_api(user_id):
    o = user_backstage_talk_set_pb2.UserBackstageTalkSetReadHistoryMap()
    for m in _load_suite_master()['96']['1']:  # MasterBackstageTalkSetMap
        o.entries[m['1']] = 'already_read'
    return o.SerializeToString()


@app.get('/api/user/<int:user_id>/backstagetalkset/map')
@app.get('/api/suite/user/<int:user_id>/backstagetalkset/map')
@app.get('/api/user/<int:user_id>/backstagetalkset')
def get_user_backstage_talk_set_map_api(user_id):
    _effective_user_id(user_id)
    return _backstage_talk_set_map_response().SerializeToString()


@app.route(
    '/api/suite/user/<int:user_id>/backstagetalkset/'
    '<int:backstage_talk_set_id>',
    methods=['POST', 'PUT'],
)
def post_user_backstage_talk_set_api(user_id, backstage_talk_set_id):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(_state_store.get_user_state, effective_user_id)
    response = suite_user_pb2.SuiteUserGetResponse()
    _populate_live_state(response, state)
    _populate_backstage_talk_read_history(response)

    cached = _cached_suite_user(effective_user_id)
    if cached is not None:
        _populate_backstage_talk_read_history(cached)
    return response.SerializeToString()


@app.get('/api/user/<int:user_id>/memorialstory')
def get_user_memorial_story_api(user_id):
    o = _load_event_story_memorial_response()

    o.ClearField('user_event_story_memorial_map')
    for k, v in o.past_event_story_map.entries.items():
        m = o.user_event_story_memorial_map.entries[k]
        m.event_id = k
        for e in v.entries:
            s = m.user_event_story_list.entries.add()
            s.user_id = user_id
            s.event_id = k
            s.seq = e.seq
            s.status = 'already_read'
        m.is_exist_un_read_story = False
        m.is_locked = False

    return o.SerializeToString()


@app.post('/api/suite/user/<int:user_id>/memorialstory/<int:event_id>'
          '/<int:seq>')
def post_user_memorial_story_api(user_id, event_id, seq):
    o = suite_user_event_story_memorial_pb2.SuiteReadStoryResponse()

    o.update_resources.user_event_story_memorial_map.CopyFrom(
        _suite_user.user_event_story_memorial_map)

    r = o.user_story_event_read_story_response
    s = r.read_user_event_story
    s.user_id = user_id
    s.event_id = event_id
    s.seq = seq
    s.status = 'already_read'

    r.rewards.SetInParent()
    r.newly_opened_contents.SetInParent()

    return o.SerializeToString()


@app.route('/api/suite/user/<int:user_id>/character/<int:character_id>'
           '/costume/<int:costume_id>', methods=['POST', 'PUT'])
def put_user_character_api(user_id, character_id, costume_id):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(
        _state_store.set_character_costume,
        effective_user_id,
        character_id,
        costume_id,
    )
    _sync_cached_character_costume_state(effective_user_id, state)
    response_costume_id = (
        _default_costume_id(character_id) if costume_id == 0 else costume_id
    )
    o = suite_user_character_pb2.SuiteUserCharacter()
    _copy_user_character(
        o.user_character, effective_user_id, character_id, response_costume_id
    )
    _copy_user_character(
        o.update_resources.user_character_map.entries[character_id],
        effective_user_id,
        character_id,
        response_costume_id,
    )
    return o.SerializeToString()


@app.delete('/api/suite/user/<int:user_id>/character/<int:character_id>'
            '/costume')
def delete_user_character_api(user_id, character_id):
    effective_user_id = _effective_user_id(user_id)
    state = _state_or_400(
        _state_store.clear_character_costume, effective_user_id, character_id
    )
    _sync_cached_character_costume_state(effective_user_id, state)
    costume_id = _default_costume_id(character_id)
    o = suite_user_character_pb2.SuiteUserCharacter()
    _copy_user_character(
        o.user_character, effective_user_id, character_id, costume_id
    )
    _copy_user_character(
        o.update_resources.user_character_map.entries[character_id],
        effective_user_id,
        character_id,
        costume_id,
    )
    return o.SerializeToString()


@app.post('/api/suite/user/<int:user_id>/mainstory/<int:main_story_id>')
def post_user_main_story_api(user_id, main_story_id):
    cached = _cached_suite_user(user_id)
    if cached is None:
        abort(409, description='suite user state has not been loaded')
    for story in cached.user_main_story_list.entries:
        if story.story_id == main_story_id:
            story.status = 'already_read'
            break
    else:
        abort(404, description=f'unknown main_story_id: {main_story_id}')
    _state_or_400(_state_store.read_main_story, user_id, main_story_id)

    o = suite_user_story_pb2.SuiteUserMainStoryResponse()
    o.update_resources.user_main_story_list.CopyFrom(
        cached.user_main_story_list
    )
    o.user_main_story_list.CopyFrom(cached.user_main_story_list)
    o.rewards.SetInParent()
    o.newly_opened_contents.SetInParent()
    return o.SerializeToString()


def start(port):
    print(f'Running game server on port {port}...')
    app.run(host='0.0.0.0', port=port, debug=False)

