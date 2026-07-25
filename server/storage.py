"""Persistent local state used by the game API server."""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence


SUPPORTED_DECK_TYPES = frozenset({'normal', 'medley_event'})
DECK_MEMBER_FIELDS = ('leader', 'member1', 'member2', 'member3', 'member4')
LIVE_BOOST_BONUSES = (1, 5, 6, 7, 8, 10, 12, 14, 16, 18, 20)
LIVE_BOOST_RECOVERY_SECONDS = 1800
LIVE_BOOST_NATURAL_MAX = 10
LIVE_BOOST_ITEM_MAX = 99
LIVE_RESULT_DIFFICULTIES = frozenset({
    'easy', 'normal', 'hard', 'expert', 'special',
})
LIVE_RESULT_RANKS = ('d', 'c', 'b', 'a', 's', 'ss')
LIVE_RESULT_CLEAR_STATUSES = frozenset({
    'not_clear', 'failed', 'clear', 'full_combo', 'all_perfect',
})
DEFAULT_DEGREES = (100, 101, 102, 103, 104, 105, 111, 112)
RANK_MISSION_ID = 2
RANK_MISSION_TARGETS = {
    1: 5,
    2: 10,
    3: 20,
    4: 30,
    5: 40,
    6: 50,
    7: 60,
    8: 70,
    9: 80,
    10: 90,
    11: 100,
}
BAND_RANK_MISSION_TARGETS = {
    1: 5,
    2: 10,
    3: 15,
    4: 20,
}
BAND_RANK_MISSION_IDS = frozenset(range(22, 29))
DECK_RATING_MISSION_TARGETS = {
    1: 4_000_000,
    2: 6_200_000,
    3: 8_000_000,
    4: 9_000_000,
}
DECK_RATING_MISSION_IDS = frozenset(range(29, 35))
ALBUM_MISSION_TARGETS = {
    1: 3,
    2: 10,
    3: 15,
    4: 20,
    5: 30,
    6: 40,
    7: 50,
}
ALBUM_MISSION_IDS = frozenset(range(1001, 1031))
MISSION_TARGETS_BY_ID = {
    RANK_MISSION_ID: RANK_MISSION_TARGETS,
    **{
        mission_id: BAND_RANK_MISSION_TARGETS
        for mission_id in BAND_RANK_MISSION_IDS
    },
    **{
        mission_id: DECK_RATING_MISSION_TARGETS
        for mission_id in DECK_RATING_MISSION_IDS
    },
    **{
        mission_id: ALBUM_MISSION_TARGETS
        for mission_id in ALBUM_MISSION_IDS
    },
}
KST = timezone(timedelta(hours=9))
PROFILE_PUBLISH_FIELDS = frozenset({
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
})


def today_kst_iso() -> str:
    return datetime.now(KST).date().isoformat()


def live_boost_bonus(use_count: int) -> int:
    """Return the master-data reward multiplier for a live boost count."""
    use_count = max(0, min(int(use_count), len(LIVE_BOOST_BONUSES) - 1))
    return LIVE_BOOST_BONUSES[use_count]


class StateStoreError(ValueError):
    """Raised when a requested state transition is invalid."""


@dataclass(frozen=True)
class DeckState:
    deck_id: int
    deck_name: str
    leader: int
    member1: int
    member2: int
    member3: int
    member4: int
    deck_type: str = 'normal'


@dataclass(frozen=True)
class GalleryState:
    situation_id: int
    illust: str
    seq: int


@dataclass(frozen=True)
class CharacterCostumeState:
    character_id: int
    costume_id: int


@dataclass(frozen=True)
class BandStoryReadState:
    band_id: int
    band_story_id: int


@dataclass(frozen=True)
class SituationDuplicateState:
    situation_id: int
    duplicate_count: int


@dataclass(frozen=True)
class GachaTicketState:
    gacha_ticket_id: int
    quantity: int


@dataclass(frozen=True)
class ItemState:
    item_id: int
    quantity: int


@dataclass(frozen=True)
class PracticeTicketState:
    practice_ticket_id: int
    quantity: int


@dataclass(frozen=True)
class LiveBoostRecoveryItemState:
    live_boost_recovery_item_id: int
    quantity: int


@dataclass(frozen=True)
class EventItemState:
    event_item_id: int
    quantity: int


@dataclass(frozen=True)
class ExchangeState:
    exchanges_id: int
    exchanged_count: int


@dataclass(frozen=True)
class AreaItemState:
    area_item_id: int
    area_item_category: int
    level: int


@dataclass(frozen=True)
class AreaItemPlacementState:
    area_item_id: int
    area_item_category: int
    area_id: int


@dataclass(frozen=True)
class ActionSetState:
    action_set_id: int
    status: str
    reward_received: bool


@dataclass(frozen=True)
class PanelMissionBoardState:
    panel_mission_id: int
    board_seq: int
    reward_received: bool


@dataclass(frozen=True)
class ProfileState:
    user_name: str
    introduction: str
    birth_month: str
    degree: int
    publish_total_deck_power_flg: bool
    publish_band_rank_flg: bool
    publish_music_cleared_flg: bool
    publish_music_full_combo_flg: bool
    publish_high_score_rating_flg: bool
    publish_updated_at_flg: bool
    publish_user_id_flg: bool
    searchable_flg: bool
    friend_applicable_flg: bool
    publish_music_all_perfect_flg: bool
    publish_deck_rank_flg: bool
    publish_stage_achievement_conditions_flg: bool
    publish_stage_friend_ranking_flg: bool
    situation_id: int
    illust: str
    view_profile_situation_status: str
    degree_id_first: int
    degree_id_second: int


@dataclass(frozen=True)
class DecoEquipmentState:
    deco_frame_id: int
    deco_pins_id1: int
    deco_pins_id2: int
    deco_pins_id3: int
    deco_pins_id4: int
    deco_pins_id5: int


@dataclass(frozen=True)
class MissionState:
    mission_id: int
    seq: int
    progress: int
    mission_progress_type: str
    mission_group_id: int


@dataclass(frozen=True)
class LoginBonusState:
    login_bonus_id: int
    days: int
    last_received_on: str | None


@dataclass(frozen=True)
class ResourceState:
    resource_type: str
    resource_id: int
    quantity: int
    lb_bonus: int = 0


@dataclass(frozen=True)
class PresentState:
    present_id: int
    resource_type: str
    resource_id: int
    quantity: int
    reason: str
    expired_at: int | None
    created_at: int


@dataclass(frozen=True)
class UserState:
    user_id: int
    main_deck: int
    live_boost: int
    live_boost_updated_at: int
    rank: int
    exp: int
    total_exp: int
    next_exp: int
    coin: int
    michelle_seal: int
    star_seal: int
    paid_star: int
    free_star: int
    profile: ProfileState
    deco_equipment: DecoEquipmentState
    decks: tuple[DeckState, ...]
    galleries: tuple[GalleryState, ...]
    character_costumes: tuple[CharacterCostumeState, ...]
    main_story_reads: tuple[int, ...]
    band_story_reads: tuple[BandStoryReadState, ...]
    music_scores: tuple['MusicScoreState', ...]
    music_achievements: tuple['MusicAchievementState', ...]
    event_music_scores: tuple['EventMusicScoreState', ...]
    event_music_achievements: tuple['EventMusicAchievementState', ...]
    situation_duplicates: tuple[SituationDuplicateState, ...]
    gacha_tickets: tuple[GachaTicketState, ...]
    items: tuple[ItemState, ...]
    practice_tickets: tuple[PracticeTicketState, ...]
    live_boost_recovery_items: tuple[LiveBoostRecoveryItemState, ...]
    event_items: tuple[EventItemState, ...]
    exchanges: tuple[ExchangeState, ...]
    area_items: tuple[AreaItemState, ...]
    area_item_placements: tuple[AreaItemPlacementState, ...]
    action_sets: tuple[ActionSetState, ...]
    panel_missions: tuple[PanelMissionBoardState, ...]
    degrees: tuple[int, ...]
    login_bonuses: tuple[LoginBonusState, ...]
    missions: tuple[MissionState, ...]
    presents: tuple[PresentState, ...]


@dataclass(frozen=True)
class MusicScoreState:
    music_id: int
    music_difficulty: str
    solo_high_score: int
    max_combo: int
    solo_score_rank: str
    clear_status: str


@dataclass(frozen=True)
class MusicAchievementState:
    music_id: int
    achievement_type: str


@dataclass(frozen=True)
class EventMusicScoreState:
    event_id: int
    music_id: int
    music_difficulty: str
    solo_high_score: int
    max_combo: int
    solo_score_rank: str
    clear_status: str


@dataclass(frozen=True)
class EventMusicAchievementState:
    event_id: int
    music_id: int
    achievement_type: str
    live_type: str


@dataclass(frozen=True)
class LiveClearState:
    user: UserState
    score: MusicScoreState
    event_id: int
    live_type: str
    live_point: int
    live_boost_use_count: int
    live_boost_bonus: int
    drops: tuple[ResourceState, ...]
    new_achievement_types: tuple[str, ...]


@dataclass(frozen=True)
class GachaDrawResult:
    situation_id: int
    duplicate_count: int


@dataclass(frozen=True)
class GachaDrawState:
    user: UserState
    results: tuple[GachaDrawResult, ...]


@dataclass(frozen=True)
class PresentReceiptState:
    user: UserState
    presents: tuple[PresentState, ...]


@dataclass(frozen=True)
class MissionRewardState:
    user: UserState
    mission: MissionState
    rewards: tuple[ResourceState, ...]


@dataclass(frozen=True)
class ActionSetReadState:
    user: UserState
    action_set: ActionSetState
    rewards: tuple[ResourceState, ...]


@dataclass(frozen=True)
class LoginBonusReceiptState:
    user: UserState
    login_bonus: LoginBonusState
    rewards: tuple[ResourceState, ...]
    received: bool


@dataclass(frozen=True)
class PanelMissionRewardState:
    user: UserState
    panel_mission_id: int
    board_seq: int
    rewards: tuple[ResourceState, ...]
    received: bool


@dataclass(frozen=True)
class AreaItemPurchaseState:
    user: UserState
    area_item: AreaItemState
    upgraded: bool


@dataclass(frozen=True)
class EventExchangePurchaseState:
    user: UserState
    exchanged_count: int
    total_exchanged_count: int


@dataclass(frozen=True)
class EventStoryReadReceiptState:
    user: UserState
    event_id: int
    seq: int
    rewards: tuple[ResourceState, ...]
    received: bool


@dataclass(frozen=True)
class ExchangePurchaseState:
    user: UserState
    exchanged_count: int
    total_exchanged_count: int


DEFAULT_DECK = DeckState(
    deck_id=1,
    deck_name='밴드1',
    leader=1,
    member1=13,
    member2=17,
    member3=9,
    member4=5,
)

DEFAULT_AREA_ITEMS = (
    AreaItemState(1, 1, 1),
    AreaItemState(26, 6, 1),
    AreaItemState(51, 11, 1),
    AreaItemState(76, 16, 1),
    AreaItemState(101, 21, 1),
)

DEFAULT_LOGIN_BONUSES = (
    # Start fresh local accounts at the first normal daily login bonus.
    LoginBonusState(1, 1, None),
)

DEFAULT_RANK = 400
DEFAULT_RANK_EXP = 1980
DEFAULT_TOTAL_EXP = 261900
DEFAULT_NEXT_EXP = 11380
DEFAULT_LIVE_RANK_EXP = 50
RANK_NEXT_EXP_INCREMENT = 320


def default_state_path() -> Path:
    override = os.environ.get('KRDORI_DB_PATH')
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / 'state' / 'db.sqlite3'


class StateStore:
    """Persistent store for mutable per-user state using SQLite."""

    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = Path(path) if path is not None else default_state_path()

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        connection.execute('PRAGMA journal_mode = WAL')
        self._initialize(connection)
        return connection

    @staticmethod
    def _initialize(connection) -> None:
        connection.executescript(
            '''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                main_deck INTEGER NOT NULL DEFAULT 1,
                live_boost INTEGER NOT NULL DEFAULT 10,
                live_boost_updated_at INTEGER NOT NULL DEFAULT 0,
                rank INTEGER NOT NULL DEFAULT 38,
                exp INTEGER NOT NULL DEFAULT 1980,
                total_exp INTEGER NOT NULL DEFAULT 261900,
                next_exp INTEGER NOT NULL DEFAULT 11380,
                coin INTEGER NOT NULL DEFAULT 2603500,
                seal INTEGER NOT NULL DEFAULT 0,
                star_seal INTEGER NOT NULL DEFAULT 0,
                paid_star INTEGER NOT NULL DEFAULT 0,
                free_star INTEGER NOT NULL DEFAULT 70175,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS decks (
                user_id INTEGER NOT NULL,
                deck_type TEXT NOT NULL,
                deck_id INTEGER NOT NULL,
                deck_name TEXT NOT NULL,
                leader INTEGER NOT NULL DEFAULT 0,
                member1 INTEGER NOT NULL DEFAULT 0,
                member2 INTEGER NOT NULL DEFAULT 0,
                member3 INTEGER NOT NULL DEFAULT 0,
                member4 INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, deck_type, deck_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS active_lives (
                user_id INTEGER PRIMARY KEY,
                music_id INTEGER NOT NULL,
                live_type TEXT NOT NULL,
                event_id INTEGER NOT NULL DEFAULT 0,
                live_boost_use_count INTEGER NOT NULL DEFAULT 0,
                continue_count INTEGER NOT NULL DEFAULT 0,
                started_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_galleries (
                user_id INTEGER NOT NULL,
                seq INTEGER NOT NULL,
                situation_id INTEGER NOT NULL,
                illust TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, seq),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS character_costumes (
                user_id INTEGER NOT NULL,
                character_id INTEGER NOT NULL,
                costume_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, character_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS main_story_reads (
                user_id INTEGER NOT NULL,
                story_id INTEGER NOT NULL,
                read_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, story_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS band_story_reads (
                user_id INTEGER NOT NULL,
                band_id INTEGER NOT NULL,
                band_story_id INTEGER NOT NULL,
                read_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, band_id, band_story_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS event_story_reads (
                user_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                seq INTEGER NOT NULL,
                read_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                reward_received INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, event_id, seq),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS music_scores (
                user_id INTEGER NOT NULL,
                music_id INTEGER NOT NULL,
                music_difficulty TEXT NOT NULL,
                solo_high_score INTEGER NOT NULL DEFAULT 0,
                max_combo INTEGER NOT NULL DEFAULT 0,
                solo_score_rank TEXT NOT NULL DEFAULT '',
                clear_status TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, music_id, music_difficulty),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS music_achievements (
                user_id INTEGER NOT NULL,
                music_id INTEGER NOT NULL,
                achievement_type TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, music_id, achievement_type),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_event_items (
                user_id INTEGER NOT NULL,
                event_item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, event_item_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_event_exchanges (
                user_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                seq INTEGER NOT NULL,
                exchanged_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, event_id, seq),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_exchanges (
                user_id INTEGER NOT NULL,
                exchanges_id INTEGER NOT NULL,
                exchanged_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, exchanges_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS event_music_scores (
                user_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                music_id INTEGER NOT NULL,
                music_difficulty TEXT NOT NULL,
                solo_high_score INTEGER NOT NULL DEFAULT 0,
                max_combo INTEGER NOT NULL DEFAULT 0,
                solo_score_rank TEXT NOT NULL DEFAULT '',
                clear_status TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (
                    user_id, event_id, music_id, music_difficulty
                ),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS event_music_achievements (
                user_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                music_id INTEGER NOT NULL,
                achievement_type TEXT NOT NULL,
                live_type TEXT NOT NULL DEFAULT 'free_live',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (
                    user_id, event_id, music_id, achievement_type, live_type
                ),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_situation_duplicates (
                user_id INTEGER NOT NULL,
                situation_id INTEGER NOT NULL,
                duplicate_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, situation_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS gacha_payment_history (
                user_id INTEGER NOT NULL,
                gacha_id INTEGER NOT NULL,
                payment_method_id INTEGER NOT NULL,
                used_on TEXT NOT NULL,
                used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, gacha_id, payment_method_id, used_on),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_gacha_tickets (
                user_id INTEGER NOT NULL,
                gacha_ticket_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, gacha_ticket_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_items (
                user_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, item_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_practice_tickets (
                user_id INTEGER NOT NULL,
                practice_ticket_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, practice_ticket_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_live_boost_recovery_items (
                user_id INTEGER NOT NULL,
                live_boost_recovery_item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, live_boost_recovery_item_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_degrees (
                user_id INTEGER NOT NULL,
                degree_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, degree_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_area_items (
                user_id INTEGER NOT NULL,
                area_item_category INTEGER NOT NULL,
                area_item_id INTEGER NOT NULL,
                level INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, area_item_category),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_area_item_placements (
                user_id INTEGER NOT NULL,
                area_item_category INTEGER NOT NULL,
                area_item_id INTEGER NOT NULL,
                area_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, area_item_category),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_area_state_initialized (
                user_id INTEGER PRIMARY KEY,
                initialized_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_action_sets (
                user_id INTEGER NOT NULL,
                action_set_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'unread',
                reward_received INTEGER NOT NULL DEFAULT 0,
                read_at INTEGER,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, action_set_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_panel_missions (
                user_id INTEGER NOT NULL,
                panel_mission_id INTEGER NOT NULL,
                board_seq INTEGER NOT NULL,
                reward_received INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, panel_mission_id, board_seq),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER PRIMARY KEY,
                user_name TEXT NOT NULL DEFAULT '유저',
                introduction TEXT NOT NULL DEFAULT '잘 부탁드립니다!',
                birth_month TEXT NOT NULL DEFAULT '201802',
                degree INTEGER NOT NULL DEFAULT 100,
                publish_total_deck_power_flg INTEGER NOT NULL DEFAULT 0,
                publish_band_rank_flg INTEGER NOT NULL DEFAULT 0,
                publish_music_cleared_flg INTEGER NOT NULL DEFAULT 0,
                publish_music_full_combo_flg INTEGER NOT NULL DEFAULT 0,
                publish_high_score_rating_flg INTEGER NOT NULL DEFAULT 0,
                publish_updated_at_flg INTEGER NOT NULL DEFAULT 1,
                publish_user_id_flg INTEGER NOT NULL DEFAULT 0,
                searchable_flg INTEGER NOT NULL DEFAULT 1,
                friend_applicable_flg INTEGER NOT NULL DEFAULT 1,
                publish_music_all_perfect_flg INTEGER NOT NULL DEFAULT 0,
                publish_deck_rank_flg INTEGER NOT NULL DEFAULT 0,
                publish_stage_achievement_conditions_flg INTEGER NOT NULL DEFAULT 0,
                publish_stage_friend_ranking_flg INTEGER NOT NULL DEFAULT 1,
                situation_id INTEGER NOT NULL DEFAULT 1,
                illust TEXT NOT NULL DEFAULT 'normal',
                view_profile_situation_status TEXT NOT NULL DEFAULT 'leader',
                degree_id_first INTEGER NOT NULL DEFAULT 100,
                degree_id_second INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_deco_equipment (
                user_id INTEGER PRIMARY KEY,
                deco_frame_id INTEGER NOT NULL DEFAULT 1,
                deco_pins_id1 INTEGER NOT NULL DEFAULT 0,
                deco_pins_id2 INTEGER NOT NULL DEFAULT 0,
                deco_pins_id3 INTEGER NOT NULL DEFAULT 0,
                deco_pins_id4 INTEGER NOT NULL DEFAULT 0,
                deco_pins_id5 INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_missions (
                user_id INTEGER NOT NULL,
                mission_id INTEGER NOT NULL,
                seq INTEGER NOT NULL DEFAULT 1,
                progress INTEGER NOT NULL DEFAULT 0,
                mission_progress_type TEXT NOT NULL DEFAULT 'in_progress',
                mission_group_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, mission_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS user_login_bonuses (
                user_id INTEGER NOT NULL,
                login_bonus_id INTEGER NOT NULL,
                days INTEGER NOT NULL DEFAULT 1,
                last_received_on TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, login_bonus_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS presents (
                user_id INTEGER NOT NULL,
                present_id INTEGER NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id INTEGER NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL,
                reason TEXT NOT NULL,
                expired_at INTEGER,
                created_at INTEGER NOT NULL,
                received_at INTEGER,
                PRIMARY KEY (user_id, present_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
            '''
        )
        user_columns = {
            row['name']
            for row in connection.execute('PRAGMA table_info(users)').fetchall()
        }
        if 'live_boost' not in user_columns:
            connection.execute(
                'ALTER TABLE users ADD COLUMN live_boost INTEGER NOT NULL DEFAULT 10'
            )
        if 'live_boost_updated_at' not in user_columns:
            connection.execute(
                '''
                ALTER TABLE users
                ADD COLUMN live_boost_updated_at INTEGER NOT NULL DEFAULT 0
                '''
            )
        active_live_columns = {
            row['name']
            for row in connection.execute(
                'PRAGMA table_info(active_lives)'
            ).fetchall()
        }
        if 'event_id' not in active_live_columns:
            connection.execute(
                '''
                ALTER TABLE active_lives
                ADD COLUMN event_id INTEGER NOT NULL DEFAULT 0
                '''
            )
        for column, definition in (
            ('rank', 'INTEGER NOT NULL DEFAULT 38'),
            ('exp', 'INTEGER NOT NULL DEFAULT 1980'),
            ('total_exp', 'INTEGER NOT NULL DEFAULT 261900'),
            ('next_exp', 'INTEGER NOT NULL DEFAULT 11380'),
            ('coin', 'INTEGER NOT NULL DEFAULT 2603500'),
            ('seal', 'INTEGER NOT NULL DEFAULT 0'),
            ('star_seal', 'INTEGER NOT NULL DEFAULT 0'),
            ('paid_star', 'INTEGER NOT NULL DEFAULT 0'),
            ('free_star', 'INTEGER NOT NULL DEFAULT 70175'),
        ):
            if column not in user_columns:
                connection.execute(
                    f'ALTER TABLE users ADD COLUMN {column} {definition}'
                )

    @staticmethod
    def _validate_user_id(user_id: int) -> int:
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id < 1:
            raise StateStoreError('user_id must be a positive integer')
        return user_id

    @staticmethod
    def _validate_uint32(name: str, value: object) -> int:
        if (not isinstance(value, int) or isinstance(value, bool)
                or value < 0 or value > 0xFFFFFFFF):
            raise StateStoreError(f'{name} must be an unsigned 32-bit integer')
        return value

    @staticmethod
    def _validate_deck_type(deck_type: str) -> str:
        if deck_type not in SUPPORTED_DECK_TYPES:
            raise StateStoreError(f'unsupported deck type: {deck_type!r}')
        return deck_type

    @staticmethod
    def _ensure_user(connection: sqlite3.Connection, user_id: int) -> None:
        connection.execute(
            '''
            INSERT OR IGNORE INTO users (
                user_id, main_deck, live_boost, live_boost_updated_at,
                rank, exp, total_exp, next_exp
            ) VALUES (?, ?, 10, ?, ?, ?, ?, ?)
            ''',
            (
                user_id,
                DEFAULT_DECK.deck_id,
                int(time.time()),
                DEFAULT_RANK,
                DEFAULT_RANK_EXP,
                DEFAULT_TOTAL_EXP,
                DEFAULT_NEXT_EXP,
            ),
        )
        connection.execute(
            'INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)',
            (user_id,),
        )
        connection.execute(
            'INSERT OR IGNORE INTO user_deco_equipment (user_id) VALUES (?)',
            (user_id,),
        )
        connection.executemany(
            '''
            INSERT OR IGNORE INTO user_degrees (user_id, degree_id)
            VALUES (?, ?)
            ''',
            [(user_id, degree_id) for degree_id in DEFAULT_DEGREES],
        )
        has_normal_deck = connection.execute(
            '''
            SELECT 1 FROM decks
            WHERE user_id = ? AND deck_type = 'normal'
            LIMIT 1
            ''',
            (user_id,),
        ).fetchone()
        if has_normal_deck is None:
            connection.execute(
                '''
                INSERT INTO decks (
                    user_id, deck_type, deck_id, deck_name,
                    leader, member1, member2, member3, member4
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    user_id,
                    DEFAULT_DECK.deck_type,
                    DEFAULT_DECK.deck_id,
                    DEFAULT_DECK.deck_name,
                    DEFAULT_DECK.leader,
                    DEFAULT_DECK.member1,
                    DEFAULT_DECK.member2,
                    DEFAULT_DECK.member3,
                    DEFAULT_DECK.member4,
                ),
            )
        area_state_initialized = connection.execute(
            '''
            SELECT 1 FROM user_area_state_initialized WHERE user_id = ?
            ''',
            (user_id,),
        ).fetchone()
        if area_state_initialized is None:
            connection.executemany(
                '''
                INSERT OR IGNORE INTO user_area_items (
                    user_id, area_item_category, area_item_id, level
                ) VALUES (?, ?, ?, ?)
                ''',
                [
                    (
                        user_id,
                        item.area_item_category,
                        item.area_item_id,
                        item.level,
                    )
                    for item in DEFAULT_AREA_ITEMS
                ],
            )
            connection.executemany(
                '''
                INSERT OR IGNORE INTO user_area_item_placements (
                    user_id, area_item_category, area_item_id, area_id
                ) VALUES (?, ?, ?, 4)
                ''',
                [
                    (user_id, item.area_item_category, item.area_item_id)
                    for item in DEFAULT_AREA_ITEMS
                ],
            )
            connection.execute(
                '''
            INSERT INTO user_area_state_initialized (user_id) VALUES (?)
                ''',
                (user_id,),
            )
        connection.executemany(
            '''
            INSERT OR IGNORE INTO user_login_bonuses (
                user_id, login_bonus_id, days, last_received_on
            ) VALUES (?, ?, ?, ?)
            ''',
            [
                (
                    user_id,
                    bonus.login_bonus_id,
                    bonus.days,
                    bonus.last_received_on,
                )
                for bonus in DEFAULT_LOGIN_BONUSES
            ],
        )
        connection.execute(
            '''
            INSERT OR IGNORE INTO presents (
                user_id, present_id, resource_type, resource_id, quantity,
                reason, expired_at, created_at
            ) VALUES (?, 1, 'gacha_ticket', 1, 5, ?, NULL, ?)
            ''',
            (
                user_id,
                '로컬 서버 기능 테스트 보상',
                int(time.time() * 1000),
            ),
        )
        mission_progress = {
            5: 0,
            29: 187989,
            30: 146467,
            31: 139446,
            32: 136045,
            33: 142245,
            34: 149055,
        }
        mission_ids = [2, 5, *range(22, 35), *range(1001, 1031)]
        connection.executemany(
            '''
            INSERT OR IGNORE INTO user_missions (
                user_id, mission_id, seq, progress,
                mission_progress_type, mission_group_id
            ) VALUES (?, ?, 1, ?, 'in_progress', ?)
            ''',
            [
                (
                    user_id,
                    mission_id,
                    mission_progress.get(
                        mission_id,
                        2 if 1001 <= mission_id <= 1005 else 1,
                    ),
                    201 if mission_id >= 1000 else 101,
                )
                for mission_id in mission_ids
            ],
        )
        StateStore._sync_rank_mission(connection, user_id)

    @staticmethod
    def _row_to_deck(row: sqlite3.Row) -> DeckState:
        return DeckState(
            deck_id=row['deck_id'],
            deck_name=row['deck_name'],
            leader=row['leader'],
            member1=row['member1'],
            member2=row['member2'],
            member3=row['member3'],
            member4=row['member4'],
            deck_type=row['deck_type'],
        )

    @classmethod
    def _get_user_state(
            cls, connection: sqlite3.Connection, user_id: int) -> UserState:
        cls._refresh_live_boost(connection, user_id)
        user = connection.execute(
            '''
            SELECT user_id, main_deck, live_boost, live_boost_updated_at,
                   rank, exp, total_exp, next_exp, coin, seal, star_seal,
                   paid_star, free_star
            FROM users WHERE user_id = ?
            ''',
            (user_id,),
        ).fetchone()
        profile = connection.execute(
            'SELECT * FROM user_profiles WHERE user_id = ?',
            (user_id,),
        ).fetchone()
        deco_equipment = connection.execute(
            'SELECT * FROM user_deco_equipment WHERE user_id = ?',
            (user_id,),
        ).fetchone()
        rows = connection.execute(
            '''
            SELECT deck_id, deck_name, leader, member1, member2, member3,
                   member4, deck_type
            FROM decks
            WHERE user_id = ?
            ORDER BY CASE deck_type WHEN 'normal' THEN 0 ELSE 1 END, deck_id
            ''',
            (user_id,),
        ).fetchall()
        score_rows = connection.execute(
            '''
            SELECT music_id, music_difficulty, solo_high_score, max_combo,
                   solo_score_rank, clear_status
            FROM music_scores
            WHERE user_id = ?
            ORDER BY music_id, music_difficulty
            ''',
            (user_id,),
        ).fetchall()
        gallery_rows = connection.execute(
            '''
            SELECT situation_id, illust, seq
            FROM user_galleries
            WHERE user_id = ?
            ORDER BY seq
            ''',
            (user_id,),
        ).fetchall()
        costume_rows = connection.execute(
            '''
            SELECT character_id, costume_id
            FROM character_costumes
            WHERE user_id = ?
            ORDER BY character_id
            ''',
            (user_id,),
        ).fetchall()
        main_story_rows = connection.execute(
            '''
            SELECT story_id
            FROM main_story_reads
            WHERE user_id = ?
            ORDER BY story_id
            ''',
            (user_id,),
        ).fetchall()
        band_story_rows = connection.execute(
            '''
            SELECT band_id, band_story_id
            FROM band_story_reads
            WHERE user_id = ?
            ORDER BY band_id, band_story_id
            ''',
            (user_id,),
        ).fetchall()
        achievement_rows = connection.execute(
            '''
            SELECT music_id, achievement_type
            FROM music_achievements
            WHERE user_id = ?
            ORDER BY music_id, achievement_type
            ''',
            (user_id,),
        ).fetchall()
        event_item_rows = connection.execute(
            '''
            SELECT event_item_id, quantity
            FROM user_event_items
            WHERE user_id = ? AND quantity > 0
            ORDER BY event_item_id
            ''',
            (user_id,),
        ).fetchall()
        exchange_rows = connection.execute(
            '''
            SELECT exchanges_id, exchanged_count
            FROM user_exchanges
            WHERE user_id = ?
            ORDER BY exchanges_id
            ''',
            (user_id,),
        ).fetchall()
        event_score_rows = connection.execute(
            '''
            SELECT event_id, music_id, music_difficulty, solo_high_score,
                   max_combo, solo_score_rank, clear_status
            FROM event_music_scores
            WHERE user_id = ?
            ORDER BY event_id, music_id, music_difficulty
            ''',
            (user_id,),
        ).fetchall()
        event_achievement_rows = connection.execute(
            '''
            SELECT event_id, music_id, achievement_type, live_type
            FROM event_music_achievements
            WHERE user_id = ?
            ORDER BY event_id, music_id, achievement_type, live_type
            ''',
            (user_id,),
        ).fetchall()
        duplicate_rows = connection.execute(
            '''
            SELECT situation_id, duplicate_count
            FROM user_situation_duplicates
            WHERE user_id = ?
            ORDER BY situation_id
            ''',
            (user_id,),
        ).fetchall()
        ticket_rows = connection.execute(
            '''
            SELECT gacha_ticket_id, quantity
            FROM user_gacha_tickets
            WHERE user_id = ? AND quantity > 0
            ORDER BY gacha_ticket_id
            ''',
            (user_id,),
        ).fetchall()
        item_rows = connection.execute(
            '''
            SELECT item_id, quantity
            FROM user_items
            WHERE user_id = ? AND quantity > 0
            ORDER BY item_id
            ''',
            (user_id,),
        ).fetchall()
        practice_ticket_rows = connection.execute(
            '''
            SELECT practice_ticket_id, quantity
            FROM user_practice_tickets
            WHERE user_id = ? AND quantity > 0
            ORDER BY practice_ticket_id
            ''',
            (user_id,),
        ).fetchall()
        recovery_item_rows = connection.execute(
            '''
            SELECT live_boost_recovery_item_id, quantity
            FROM user_live_boost_recovery_items
            WHERE user_id = ? AND quantity > 0
            ORDER BY live_boost_recovery_item_id
            ''',
            (user_id,),
        ).fetchall()
        degree_rows = connection.execute(
            '''
            SELECT degree_id
            FROM user_degrees
            WHERE user_id = ?
            ORDER BY degree_id
            ''',
            (user_id,),
        ).fetchall()
        area_item_rows = connection.execute(
            '''
            SELECT area_item_id, area_item_category, level
            FROM user_area_items
            WHERE user_id = ?
            ORDER BY area_item_category
            ''',
            (user_id,),
        ).fetchall()
        area_item_placement_rows = connection.execute(
            '''
            SELECT area_item_id, area_item_category, area_id
            FROM user_area_item_placements
            WHERE user_id = ?
            ORDER BY area_id, area_item_category
            ''',
            (user_id,),
        ).fetchall()
        action_set_rows = connection.execute(
            '''
            SELECT action_set_id, status, reward_received
            FROM user_action_sets
            WHERE user_id = ?
            ORDER BY action_set_id
            ''',
            (user_id,),
        ).fetchall()
        panel_mission_rows = connection.execute(
            '''
            SELECT panel_mission_id, board_seq, reward_received
            FROM user_panel_missions
            WHERE user_id = ?
            ORDER BY panel_mission_id, board_seq
            ''',
            (user_id,),
        ).fetchall()
        mission_rows = connection.execute(
            '''
            SELECT mission_id, seq, progress, mission_progress_type,
                   mission_group_id
            FROM user_missions
            WHERE user_id = ?
            ORDER BY mission_group_id, mission_id
            ''',
            (user_id,),
        ).fetchall()
        login_bonus_rows = connection.execute(
            '''
            SELECT login_bonus_id, days, last_received_on
            FROM user_login_bonuses
            WHERE user_id = ?
            ORDER BY login_bonus_id
            ''',
            (user_id,),
        ).fetchall()
        present_rows = connection.execute(
            '''
            SELECT present_id, resource_type, resource_id, quantity, reason,
                   expired_at, created_at
            FROM presents
            WHERE user_id = ? AND received_at IS NULL
              AND (expired_at IS NULL OR expired_at > ?)
            ORDER BY present_id
            ''',
            (user_id, int(time.time() * 1000)),
        ).fetchall()
        return UserState(
            user_id=user['user_id'],
            main_deck=user['main_deck'],
            live_boost=user['live_boost'],
            live_boost_updated_at=user['live_boost_updated_at'],
            rank=user['rank'],
            exp=user['exp'],
            total_exp=user['total_exp'],
            next_exp=user['next_exp'],
            coin=user['coin'],
            michelle_seal=user['seal'],
            star_seal=user['star_seal'],
            paid_star=user['paid_star'],
            free_star=user['free_star'],
            profile=ProfileState(
                user_name=profile['user_name'],
                introduction=profile['introduction'],
                birth_month=profile['birth_month'],
                degree=profile['degree'],
                publish_total_deck_power_flg=bool(
                    profile['publish_total_deck_power_flg']
                ),
                publish_band_rank_flg=bool(
                    profile['publish_band_rank_flg']
                ),
                publish_music_cleared_flg=bool(
                    profile['publish_music_cleared_flg']
                ),
                publish_music_full_combo_flg=bool(
                    profile['publish_music_full_combo_flg']
                ),
                publish_high_score_rating_flg=bool(
                    profile['publish_high_score_rating_flg']
                ),
                publish_updated_at_flg=bool(
                    profile['publish_updated_at_flg']
                ),
                publish_user_id_flg=bool(profile['publish_user_id_flg']),
                searchable_flg=bool(profile['searchable_flg']),
                friend_applicable_flg=bool(
                    profile['friend_applicable_flg']
                ),
                publish_music_all_perfect_flg=bool(
                    profile['publish_music_all_perfect_flg']
                ),
                publish_deck_rank_flg=bool(
                    profile['publish_deck_rank_flg']
                ),
                publish_stage_achievement_conditions_flg=bool(
                    profile['publish_stage_achievement_conditions_flg']
                ),
                publish_stage_friend_ranking_flg=bool(
                    profile['publish_stage_friend_ranking_flg']
                ),
                situation_id=profile['situation_id'],
                illust=profile['illust'],
                view_profile_situation_status=(
                    profile['view_profile_situation_status']
                ),
                degree_id_first=profile['degree_id_first'],
                degree_id_second=profile['degree_id_second'],
            ),
            deco_equipment=DecoEquipmentState(
                deco_frame_id=deco_equipment['deco_frame_id'],
                deco_pins_id1=deco_equipment['deco_pins_id1'],
                deco_pins_id2=deco_equipment['deco_pins_id2'],
                deco_pins_id3=deco_equipment['deco_pins_id3'],
                deco_pins_id4=deco_equipment['deco_pins_id4'],
                deco_pins_id5=deco_equipment['deco_pins_id5'],
            ),
            decks=tuple(cls._row_to_deck(row) for row in rows),
            galleries=tuple(
                GalleryState(
                    situation_id=row['situation_id'],
                    illust=row['illust'],
                    seq=row['seq'],
                )
                for row in gallery_rows
            ),
            character_costumes=tuple(
                CharacterCostumeState(
                    character_id=row['character_id'],
                    costume_id=row['costume_id'],
                )
                for row in costume_rows
            ),
            main_story_reads=tuple(row['story_id'] for row in main_story_rows),
            band_story_reads=tuple(
                BandStoryReadState(
                    band_id=row['band_id'],
                    band_story_id=row['band_story_id'],
                )
                for row in band_story_rows
            ),
            music_scores=tuple(
                MusicScoreState(
                    music_id=row['music_id'],
                    music_difficulty=row['music_difficulty'],
                    solo_high_score=row['solo_high_score'],
                    max_combo=row['max_combo'],
                    solo_score_rank=row['solo_score_rank'],
                    clear_status=row['clear_status'],
                )
                for row in score_rows
            ),
            music_achievements=tuple(
                MusicAchievementState(
                    music_id=row['music_id'],
                    achievement_type=row['achievement_type'],
                )
                for row in achievement_rows
            ),
            event_music_scores=tuple(
                EventMusicScoreState(
                    event_id=row['event_id'],
                    music_id=row['music_id'],
                    music_difficulty=row['music_difficulty'],
                    solo_high_score=row['solo_high_score'],
                    max_combo=row['max_combo'],
                    solo_score_rank=row['solo_score_rank'],
                    clear_status=row['clear_status'],
                )
                for row in event_score_rows
            ),
            event_music_achievements=tuple(
                EventMusicAchievementState(
                    event_id=row['event_id'],
                    music_id=row['music_id'],
                    achievement_type=row['achievement_type'],
                    live_type=row['live_type'],
                )
                for row in event_achievement_rows
            ),
            situation_duplicates=tuple(
                SituationDuplicateState(
                    situation_id=row['situation_id'],
                    duplicate_count=row['duplicate_count'],
                )
                for row in duplicate_rows
            ),
            gacha_tickets=tuple(
                GachaTicketState(
                    gacha_ticket_id=row['gacha_ticket_id'],
                    quantity=row['quantity'],
                )
                for row in ticket_rows
            ),
            items=tuple(
                ItemState(item_id=row['item_id'], quantity=row['quantity'])
                for row in item_rows
            ),
            practice_tickets=tuple(
                PracticeTicketState(
                    practice_ticket_id=row['practice_ticket_id'],
                    quantity=row['quantity'],
                )
                for row in practice_ticket_rows
            ),
            live_boost_recovery_items=tuple(
                LiveBoostRecoveryItemState(
                    live_boost_recovery_item_id=(
                        row['live_boost_recovery_item_id']
                    ),
                    quantity=row['quantity'],
                )
                for row in recovery_item_rows
            ),
            event_items=tuple(
                EventItemState(
                    event_item_id=row['event_item_id'],
                    quantity=row['quantity'],
                )
                for row in event_item_rows
            ),
            exchanges=tuple(
                ExchangeState(
                    exchanges_id=row['exchanges_id'],
                    exchanged_count=row['exchanged_count'],
                )
                for row in exchange_rows
            ),
            area_items=tuple(
                AreaItemState(
                    area_item_id=row['area_item_id'],
                    area_item_category=row['area_item_category'],
                    level=row['level'],
                )
                for row in area_item_rows
            ),
            area_item_placements=tuple(
                AreaItemPlacementState(
                    area_item_id=row['area_item_id'],
                    area_item_category=row['area_item_category'],
                    area_id=row['area_id'],
                )
                for row in area_item_placement_rows
            ),
            action_sets=tuple(
                ActionSetState(
                    action_set_id=row['action_set_id'],
                    status=row['status'],
                    reward_received=bool(row['reward_received']),
                )
                for row in action_set_rows
            ),
            panel_missions=tuple(
                PanelMissionBoardState(
                    panel_mission_id=row['panel_mission_id'],
                    board_seq=row['board_seq'],
                    reward_received=bool(row['reward_received']),
                )
                for row in panel_mission_rows
            ),
            degrees=tuple(row['degree_id'] for row in degree_rows),
            login_bonuses=tuple(
                LoginBonusState(
                    login_bonus_id=row['login_bonus_id'],
                    days=row['days'],
                    last_received_on=row['last_received_on'],
                )
                for row in login_bonus_rows
            ),
            missions=tuple(
                MissionState(
                    mission_id=row['mission_id'],
                    seq=row['seq'],
                    progress=row['progress'],
                    mission_progress_type=row['mission_progress_type'],
                    mission_group_id=row['mission_group_id'],
                )
                for row in mission_rows
            ),
            presents=tuple(
                PresentState(
                    present_id=row['present_id'],
                    resource_type=row['resource_type'],
                    resource_id=row['resource_id'],
                    quantity=row['quantity'],
                    reason=row['reason'],
                    expired_at=row['expired_at'],
                    created_at=row['created_at'],
                )
                for row in present_rows
            ),
        )

    @staticmethod
    def _refresh_live_boost(
            connection: sqlite3.Connection, user_id: int) -> None:
        row = connection.execute(
            '''
            SELECT live_boost, live_boost_updated_at
            FROM users WHERE user_id = ?
            ''',
            (user_id,),
        ).fetchone()
        now = int(time.time())
        if row['live_boost'] >= LIVE_BOOST_NATURAL_MAX:
            if not row['live_boost_updated_at']:
                connection.execute(
                    '''
                    UPDATE users SET live_boost_updated_at = ?
                    WHERE user_id = ?
                    ''',
                    (now, user_id),
                )
            return
        updated_at = row['live_boost_updated_at'] or now
        recovered = max(now - updated_at, 0) // LIVE_BOOST_RECOVERY_SECONDS
        if not recovered:
            return
        live_boost = min(
            row['live_boost'] + recovered,
            LIVE_BOOST_NATURAL_MAX,
        )
        next_updated_at = (
            now if live_boost >= LIVE_BOOST_NATURAL_MAX
            else updated_at + recovered * LIVE_BOOST_RECOVERY_SECONDS
        )
        connection.execute(
            '''
            UPDATE users
            SET live_boost = ?, live_boost_updated_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            ''',
            (live_boost, next_updated_at, user_id),
        )

    def get_user_state(self, user_id: int) -> UserState:
        user_id = self._validate_user_id(user_id)
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            return self._get_user_state(connection, user_id)

    def sync_missions(self, user_id: int, mission_type: str = '') -> UserState:
        user_id = self._validate_user_id(user_id)
        mission_type = (mission_type or '').strip().lower()
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            if mission_type in {'', 'live', 'normal', 'rank'}:
                self._sync_rank_mission(connection, user_id)
            return self._get_user_state(connection, user_id)

    def sync_mission_progress(
            self,
            user_id: int,
            progress_by_mission_id: Mapping[int, int],
    ) -> UserState:
        user_id = self._validate_user_id(user_id)
        normalized = {
            self._validate_uint32('mission_id', mission_id): max(
                0, self._validate_uint32('mission_progress', progress)
            )
            for mission_id, progress in progress_by_mission_id.items()
        }
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            self._sync_mission_progress_values(
                connection, user_id, normalized
            )
            return self._get_user_state(connection, user_id)

    def update_profile_identity(
            self,
            user_id: int,
            *,
            user_name: str | None = None,
            introduction: str | None = None,
            birth_month: str | None = None,
            degree: int | None = None,
    ) -> UserState:
        user_id = self._validate_user_id(user_id)
        changes: dict[str, object] = {}
        if user_name is not None:
            if not isinstance(user_name, str):
                raise StateStoreError('user_name must be a string')
            user_name = user_name.strip()
            if not user_name:
                raise StateStoreError('user_name must not be empty')
            if len(user_name) > 30:
                raise StateStoreError(
                    'user_name must not exceed 30 characters'
                )
            changes['user_name'] = user_name
        if introduction is not None:
            if not isinstance(introduction, str):
                raise StateStoreError('introduction must be a string')
            if len(introduction) > 100:
                raise StateStoreError(
                    'introduction must not exceed 100 characters'
                )
            changes['introduction'] = introduction
        if birth_month is not None:
            if (not isinstance(birth_month, str)
                    or (birth_month and (
                        len(birth_month) != 6 or not birth_month.isdecimal()
                    ))):
                raise StateStoreError(
                    'birth_month must be empty or contain six digits'
                )
            changes['birth_month'] = birth_month
        if degree is not None:
            changes['degree'] = self._validate_uint32('degree', degree)
        if not changes:
            raise StateStoreError('profile update must not be empty')

        assignments = ', '.join(f'{name} = ?' for name in changes)
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            connection.execute(
                f'''
                UPDATE user_profiles
                SET {assignments}, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                ''',
                (*changes.values(), user_id),
            )
            return self._get_user_state(connection, user_id)

    def update_profile_publish_config(
            self,
            user_id: int,
            values: Mapping[str, bool],
    ) -> UserState:
        user_id = self._validate_user_id(user_id)
        unknown_fields = set(values) - PROFILE_PUBLISH_FIELDS
        if unknown_fields:
            raise StateStoreError(
                'unknown profile publish fields: '
                + ', '.join(sorted(unknown_fields))
            )
        if not values:
            raise StateStoreError('profile publish update must not be empty')
        normalized: dict[str, int] = {}
        for name, value in values.items():
            if not isinstance(value, bool):
                raise StateStoreError(f'{name} must be a boolean')
            normalized[name] = int(value)

        assignments = ', '.join(f'{name} = ?' for name in normalized)
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            connection.execute(
                f'''
                UPDATE user_profiles
                SET {assignments}, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                ''',
                (*normalized.values(), user_id),
            )
            return self._get_user_state(connection, user_id)

    def set_profile_degrees(
            self,
            user_id: int,
            degree_id_first: int,
            degree_id_second: int,
    ) -> UserState:
        user_id = self._validate_user_id(user_id)
        degree_id_first = self._validate_uint32(
            'degree_id_first', degree_id_first
        )
        degree_id_second = self._validate_uint32(
            'degree_id_second', degree_id_second
        )
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            connection.execute(
                '''
                UPDATE user_profiles
                SET degree_id_first = ?, degree_id_second = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                ''',
                (degree_id_first, degree_id_second, user_id),
            )
            return self._get_user_state(connection, user_id)

    def set_deco_equipment(
            self,
            user_id: int,
            deco_frame_id: int,
            deco_pins_id1: int,
            deco_pins_id2: int,
            deco_pins_id3: int,
            deco_pins_id4: int,
            deco_pins_id5: int,
    ) -> UserState:
        user_id = self._validate_user_id(user_id)
        values = tuple(
            self._validate_uint32(name, value)
            for name, value in (
                ('deco_frame_id', deco_frame_id),
                ('deco_pins_id1', deco_pins_id1),
                ('deco_pins_id2', deco_pins_id2),
                ('deco_pins_id3', deco_pins_id3),
                ('deco_pins_id4', deco_pins_id4),
                ('deco_pins_id5', deco_pins_id5),
            )
        )
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            connection.execute(
                '''
                UPDATE user_deco_equipment
                SET deco_frame_id = ?, deco_pins_id1 = ?,
                    deco_pins_id2 = ?, deco_pins_id3 = ?,
                    deco_pins_id4 = ?, deco_pins_id5 = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                ''',
                (*values, user_id),
            )
            return self._get_user_state(connection, user_id)

    def set_profile_situation(
            self,
            user_id: int,
            situation_id: int,
            illust: str,
            view_profile_situation_status: str,
    ) -> UserState:
        user_id = self._validate_user_id(user_id)
        situation_id = self._validate_uint32('situation_id', situation_id)
        if situation_id == 0:
            raise StateStoreError('situation_id must be positive')
        if not isinstance(illust, str) or not illust:
            raise StateStoreError('illust must not be empty')
        if len(illust) > 50:
            raise StateStoreError('illust must not exceed 50 characters')
        if (not isinstance(view_profile_situation_status, str)
                or not view_profile_situation_status):
            raise StateStoreError(
                'view_profile_situation_status must not be empty'
            )
        if len(view_profile_situation_status) > 50:
            raise StateStoreError(
                'view_profile_situation_status must not exceed 50 characters'
            )
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            connection.execute(
                '''
                UPDATE user_profiles
                SET situation_id = ?, illust = ?,
                    view_profile_situation_status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                ''',
                (
                    situation_id,
                    illust,
                    view_profile_situation_status,
                    user_id,
                ),
            )
            return self._get_user_state(connection, user_id)

    def draw_gacha(
            self,
            user_id: int,
            gacha_id: int,
            payment_method_id: int,
            cost: int,
            situation_ids: Sequence[int],
            once_per_day: bool = False,
            payment_type: str = 'free_star',
            payment_resource_id: int = 0,
    ) -> GachaDrawState:
        user_id = self._validate_user_id(user_id)
        gacha_id = self._validate_uint32('gacha_id', gacha_id)
        payment_method_id = self._validate_uint32(
            'payment_method_id', payment_method_id
        )
        cost = self._validate_uint32('cost', cost)
        payment_resource_id = self._validate_uint32(
            'payment_resource_id', payment_resource_id
        )
        normalized_ids = tuple(
            self._validate_uint32('situation_id', value)
            for value in situation_ids
        )
        if not normalized_ids:
            raise StateStoreError('gacha result must not be empty')
        if any(value == 0 for value in normalized_ids):
            raise StateStoreError('situation_id must be positive')

        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            used_on = date.today().isoformat()
            if once_per_day:
                already_used = connection.execute(
                    '''
                    SELECT 1 FROM gacha_payment_history
                    WHERE user_id = ? AND gacha_id = ?
                      AND payment_method_id = ? AND used_on = ?
                    ''',
                    (user_id, gacha_id, payment_method_id, used_on),
                ).fetchone()
                if already_used is not None:
                    raise StateStoreError(
                        'this gacha payment method was already used today'
                    )

            if payment_type == 'free_star':
                free_star = connection.execute(
                    'SELECT free_star FROM users WHERE user_id = ?',
                    (user_id,),
                ).fetchone()['free_star']
                if free_star < cost:
                    raise StateStoreError('not enough free stars')
                connection.execute(
                    '''
                    UPDATE users
                    SET free_star = free_star - ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                    ''',
                    (cost, user_id),
                )
            elif payment_type == 'normal_ticket':
                ticket = connection.execute(
                    '''
                    SELECT quantity FROM user_gacha_tickets
                    WHERE user_id = ? AND gacha_ticket_id = ?
                    ''',
                    (user_id, payment_resource_id),
                ).fetchone()
                if ticket is None or ticket['quantity'] < cost:
                    raise StateStoreError('not enough gacha tickets')
                connection.execute(
                    '''
                    UPDATE user_gacha_tickets
                    SET quantity = quantity - ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND gacha_ticket_id = ?
                    ''',
                    (cost, user_id, payment_resource_id),
                )
            else:
                raise StateStoreError(
                    f'unsupported gacha payment: {payment_type}'
                )

            results = []
            for situation_id in normalized_ids:
                row = connection.execute(
                    '''
                    SELECT duplicate_count FROM user_situation_duplicates
                    WHERE user_id = ? AND situation_id = ?
                    ''',
                    (user_id, situation_id),
                ).fetchone()
                duplicate_count = (
                    1 if row is None else row['duplicate_count'] + 1
                )
                connection.execute(
                    '''
                    INSERT INTO user_situation_duplicates (
                        user_id, situation_id, duplicate_count
                    ) VALUES (?, ?, ?)
                    ON CONFLICT(user_id, situation_id) DO UPDATE SET
                        duplicate_count = excluded.duplicate_count,
                        updated_at = CURRENT_TIMESTAMP
                    ''',
                    (user_id, situation_id, duplicate_count),
                )
                results.append(GachaDrawResult(situation_id, duplicate_count))

            if once_per_day:
                connection.execute(
                    '''
                    INSERT INTO gacha_payment_history (
                        user_id, gacha_id, payment_method_id, used_on
                    ) VALUES (?, ?, ?, ?)
                    ''',
                    (user_id, gacha_id, payment_method_id, used_on),
                )

            return GachaDrawState(
                user=self._get_user_state(connection, user_id),
                results=tuple(results),
            )

    @classmethod
    def _normalize_resources(
            cls, resources: Sequence[ResourceState]) -> tuple[ResourceState, ...]:
        normalized = []
        for resource in resources:
            if not isinstance(resource, ResourceState):
                raise StateStoreError('resources must contain ResourceState values')
            resource_type = resource.resource_type.strip()
            if resource_type not in {
                    'coin', 'star', 'item', 'practice_ticket',
                    'live_boost_recovery_item', 'gacha_ticket',
                    'event_item', 'degree', 'situation',
                    'michelle_seal', 'star_seal'}:
                raise StateStoreError(
                    f'unsupported resource: {resource_type}'
                )
            resource_id = cls._validate_uint32(
                'resource_id', resource.resource_id
            )
            quantity = cls._validate_uint32('quantity', resource.quantity)
            lb_bonus = cls._validate_uint32('lb_bonus', resource.lb_bonus)
            if quantity == 0:
                continue
            if resource_type in {
                    'item', 'practice_ticket', 'live_boost_recovery_item',
                    'gacha_ticket', 'event_item', 'degree',
                    'situation'} and resource_id == 0:
                raise StateStoreError(
                    f'{resource_type} resource_id must be positive'
                )
            normalized.append(ResourceState(
                resource_type, resource_id, quantity, lb_bonus
            ))
        return tuple(normalized)

    @staticmethod
    def _grant_resources(
            connection: sqlite3.Connection,
            user_id: int,
            resources: Sequence[ResourceState]) -> None:
        table_config = {
            'item': ('user_items', 'item_id'),
            'practice_ticket': (
                'user_practice_tickets', 'practice_ticket_id'
            ),
            'live_boost_recovery_item': (
                'user_live_boost_recovery_items',
                'live_boost_recovery_item_id',
            ),
            'gacha_ticket': ('user_gacha_tickets', 'gacha_ticket_id'),
            'event_item': ('user_event_items', 'event_item_id'),
        }
        for resource in resources:
            if resource.resource_type == 'coin':
                connection.execute(
                    '''
                    UPDATE users SET coin = coin + ?,
                        updated_at = CURRENT_TIMESTAMP WHERE user_id = ?
                    ''',
                    (resource.quantity, user_id),
                )
            elif resource.resource_type == 'star':
                connection.execute(
                    '''
                    UPDATE users SET free_star = free_star + ?,
                        updated_at = CURRENT_TIMESTAMP WHERE user_id = ?
                    ''',
                    (resource.quantity, user_id),
                )
            elif resource.resource_type == 'michelle_seal':
                connection.execute(
                    '''
                    UPDATE users SET seal = seal + ?,
                        updated_at = CURRENT_TIMESTAMP WHERE user_id = ?
                    ''',
                    (resource.quantity, user_id),
                )
            elif resource.resource_type == 'star_seal':
                connection.execute(
                    '''
                    UPDATE users SET star_seal = star_seal + ?,
                        updated_at = CURRENT_TIMESTAMP WHERE user_id = ?
                    ''',
                    (resource.quantity, user_id),
                )
            elif resource.resource_type == 'degree':
                connection.execute(
                    '''
                    INSERT OR IGNORE INTO user_degrees (user_id, degree_id)
                    VALUES (?, ?)
                    ''',
                    (user_id, resource.resource_id),
                )
            elif resource.resource_type == 'situation':
                row = connection.execute(
                    '''
                    SELECT duplicate_count FROM user_situation_duplicates
                    WHERE user_id = ? AND situation_id = ?
                    ''',
                    (user_id, resource.resource_id),
                ).fetchone()
                duplicate_count = (
                    resource.quantity
                    if row is None
                    else row['duplicate_count'] + resource.quantity
                )
                connection.execute(
                    '''
                    INSERT INTO user_situation_duplicates (
                        user_id, situation_id, duplicate_count
                    ) VALUES (?, ?, ?)
                    ON CONFLICT(user_id, situation_id) DO UPDATE SET
                        duplicate_count = excluded.duplicate_count,
                        updated_at = CURRENT_TIMESTAMP
                    ''',
                    (user_id, resource.resource_id, duplicate_count),
                )
            else:
                table, id_column = table_config[resource.resource_type]
                connection.execute(
                    f'''
                    INSERT INTO {table} (user_id, {id_column}, quantity)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, {id_column}) DO UPDATE SET
                        quantity = quantity + excluded.quantity,
                        updated_at = CURRENT_TIMESTAMP
                    ''',
                    (user_id, resource.resource_id, resource.quantity),
                )

    @staticmethod
    def _grant_rank_exp(
            connection: sqlite3.Connection, user_id: int, add_exp: int) -> None:
        if add_exp <= 0:
            return
        row = connection.execute(
            '''
            SELECT rank, exp, total_exp, next_exp
            FROM users WHERE user_id = ?
            ''',
            (user_id,),
        ).fetchone()
        rank = row['rank']
        exp = row['exp'] + add_exp
        total_exp = row['total_exp'] + add_exp
        next_exp = row['next_exp']
        while next_exp > 0 and exp >= next_exp:
            exp -= next_exp
            rank += 1
            next_exp += RANK_NEXT_EXP_INCREMENT
        connection.execute(
            '''
            UPDATE users
            SET rank = ?, exp = ?, total_exp = ?, next_exp = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            ''',
            (rank, exp, total_exp, next_exp, user_id),
        )
        StateStore._sync_rank_mission(connection, user_id)

    @staticmethod
    def _sync_rank_mission(connection: sqlite3.Connection, user_id: int) -> None:
        user = connection.execute(
            'SELECT rank FROM users WHERE user_id = ?',
            (user_id,),
        ).fetchone()
        mission = connection.execute(
            '''
            SELECT seq, mission_progress_type
            FROM user_missions
            WHERE user_id = ? AND mission_id = ?
            ''',
            (user_id, RANK_MISSION_ID),
        ).fetchone()
        if user is None or mission is None:
            return
        if mission['mission_progress_type'] == 'end':
            return
        target = RANK_MISSION_TARGETS.get(mission['seq'])
        if target is None:
            return
        progress = user['rank']
        progress_type = (
            'complete' if progress >= target else 'in_progress'
        )
        connection.execute(
            '''
            UPDATE user_missions
            SET progress = ?, mission_progress_type = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND mission_id = ?
            ''',
            (progress, progress_type, user_id, RANK_MISSION_ID),
        )

    @staticmethod
    def _sync_mission_progress_values(
            connection: sqlite3.Connection,
            user_id: int,
            progress_by_mission_id: Mapping[int, int],
    ) -> None:
        for mission_id, progress in progress_by_mission_id.items():
            targets = MISSION_TARGETS_BY_ID.get(mission_id)
            if targets is None:
                continue
            mission = connection.execute(
                '''
                SELECT seq, mission_progress_type
                FROM user_missions
                WHERE user_id = ? AND mission_id = ?
                ''',
                (user_id, mission_id),
            ).fetchone()
            if mission is None or mission['mission_progress_type'] == 'end':
                continue
            target = targets.get(mission['seq'])
            if target is None:
                continue
            progress_type = (
                'complete' if progress >= target else 'in_progress'
            )
            connection.execute(
                '''
                UPDATE user_missions
                SET progress = ?, mission_progress_type = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND mission_id = ?
                ''',
                (progress, progress_type, user_id, mission_id),
            )

    def grant_resources(
            self,
            user_id: int,
            resources: Sequence[ResourceState],
    ) -> UserState:
        user_id = self._validate_user_id(user_id)
        normalized = self._normalize_resources(resources)
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            self._grant_resources(connection, user_id, normalized)
            return self._get_user_state(connection, user_id)

    def claim_panel_mission_reward(
            self,
            user_id: int,
            panel_mission_id: int,
            board_seq: int,
            rewards: Sequence[ResourceState],
    ) -> PanelMissionRewardState:
        user_id = self._validate_user_id(user_id)
        panel_mission_id = self._validate_uint32(
            'panel_mission_id', panel_mission_id
        )
        board_seq = self._validate_uint32('board_seq', board_seq)
        if not panel_mission_id or not board_seq:
            raise StateStoreError('panel_mission_id and board_seq must be positive')
        normalized = self._normalize_resources(rewards)

        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            row = connection.execute(
                '''
                SELECT reward_received
                FROM user_panel_missions
                WHERE user_id = ? AND panel_mission_id = ? AND board_seq = ?
                ''',
                (user_id, panel_mission_id, board_seq),
            ).fetchone()
            received = row is None or not bool(row['reward_received'])
            if received:
                self._grant_resources(connection, user_id, normalized)
            connection.execute(
                '''
                INSERT INTO user_panel_missions (
                    user_id, panel_mission_id, board_seq, reward_received
                ) VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id, panel_mission_id, board_seq)
                DO UPDATE SET
                    reward_received = 1,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (user_id, panel_mission_id, board_seq),
            )
            return PanelMissionRewardState(
                self._get_user_state(connection, user_id),
                panel_mission_id,
                board_seq,
                normalized if received else (),
                received,
            )

    def get_exchange_counts(self, user_id: int) -> dict[int, int]:
        user_id = self._validate_user_id(user_id)
        with closing(self._connect()) as connection:
            self._ensure_user(connection, user_id)
            rows = connection.execute(
                '''
                SELECT exchanges_id, exchanged_count
                FROM user_exchanges
                WHERE user_id = ?
                ''',
                (user_id,),
            ).fetchall()
        return {
            row['exchanges_id']: max(0, row['exchanged_count'])
            for row in rows
        }

    def purchase_exchange(
            self,
            user_id: int,
            exchanges_id: int,
            michelle_seal_cost_per_count: int,
            rewards_per_count: Sequence[ResourceState],
            requested_count: int,
            exchange_limit: int | None = None,
    ) -> ExchangePurchaseState:
        user_id = self._validate_user_id(user_id)
        exchanges_id = self._validate_uint32('exchanges_id', exchanges_id)
        michelle_seal_cost_per_count = self._validate_uint32(
            'michelle_seal_cost_per_count', michelle_seal_cost_per_count
        )
        requested_count = self._validate_uint32(
            'requested_count', requested_count
        )
        if exchange_limit is not None:
            exchange_limit = self._validate_uint32(
                'exchange_limit', exchange_limit
            )
        if not exchanges_id:
            raise StateStoreError('exchanges_id must be positive')
        normalized = self._normalize_resources(rewards_per_count)

        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            row = connection.execute(
                '''
                SELECT exchanged_count
                FROM user_exchanges
                WHERE user_id = ? AND exchanges_id = ?
                ''',
                (user_id, exchanges_id),
            ).fetchone()
            total_exchanged = (
                0 if row is None else max(0, row['exchanged_count'])
            )
            actual_count = requested_count
            if exchange_limit is not None:
                actual_count = min(
                    actual_count,
                    max(0, exchange_limit - total_exchanged),
                )
            if michelle_seal_cost_per_count:
                user = connection.execute(
                    'SELECT seal FROM users WHERE user_id = ?',
                    (user_id,),
                ).fetchone()
                available = 0 if user is None else max(0, user['seal'])
                actual_count = min(
                    actual_count,
                    available // michelle_seal_cost_per_count,
                )
            if actual_count <= 0:
                return ExchangePurchaseState(
                    self._get_user_state(connection, user_id),
                    0,
                    total_exchanged,
                )

            if michelle_seal_cost_per_count:
                connection.execute(
                    '''
                    UPDATE users
                    SET seal = seal - ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                    ''',
                    (michelle_seal_cost_per_count * actual_count, user_id),
                )
            rewards = tuple(
                replace(resource, quantity=resource.quantity * actual_count)
                for resource in normalized
            )
            self._grant_resources(connection, user_id, rewards)
            total_exchanged += actual_count
            connection.execute(
                '''
                INSERT INTO user_exchanges (
                    user_id, exchanges_id, exchanged_count
                ) VALUES (?, ?, ?)
                ON CONFLICT(user_id, exchanges_id) DO UPDATE SET
                    exchanged_count = excluded.exchanged_count,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (user_id, exchanges_id, total_exchanged),
            )
            return ExchangePurchaseState(
                self._get_user_state(connection, user_id),
                actual_count,
                total_exchanged,
            )

    def read_action_set(
            self,
            user_id: int,
            action_set_id: int,
            rewards: Sequence[ResourceState] = (),
    ) -> ActionSetReadState:
        """Mark an area action set as read and grant its first-read reward.

        The client exposes area conversations through ``UserActionSet.status``
        but does not provide a separate reward-received field.  Keeping a small
        server-side ledger lets the API return a stable read state while also
        making the first-read bonus idempotent.
        """
        user_id = self._validate_user_id(user_id)
        action_set_id = self._validate_uint32(
            'action_set_id', action_set_id
        )
        if action_set_id == 0:
            raise StateStoreError('action_set_id must be positive')
        normalized = self._normalize_resources(rewards)

        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            row = connection.execute(
                '''
                SELECT reward_received
                FROM user_action_sets
                WHERE user_id = ? AND action_set_id = ?
                ''',
                (user_id, action_set_id),
            ).fetchone()
            should_grant = row is None or not bool(row['reward_received'])
            if should_grant:
                self._grant_resources(connection, user_id, normalized)

            now_ms = int(time.time() * 1000)
            if row is None:
                connection.execute(
                    '''
                    INSERT INTO user_action_sets (
                        user_id, action_set_id, status, reward_received,
                        read_at
                    ) VALUES (?, ?, 'already_read', 1, ?)
                    ''',
                    (user_id, action_set_id, now_ms),
                )
            else:
                connection.execute(
                    '''
                    UPDATE user_action_sets
                    SET status = 'already_read',
                        reward_received = 1,
                        read_at = COALESCE(read_at, ?),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND action_set_id = ?
                    ''',
                    (now_ms, user_id, action_set_id),
                )

            user = self._get_user_state(connection, user_id)
            action_set = next(
                value for value in user.action_sets
                if value.action_set_id == action_set_id
            )
            return ActionSetReadState(
                user,
                action_set,
                normalized if should_grant else (),
            )

    def spend_event_item_and_grant_resources(
            self,
            user_id: int,
            event_item_id: int,
            event_item_cost: int,
            rewards: Sequence[ResourceState],
    ) -> UserState:
        """Spend event currency and grant rewards as one safe transaction.

        If the local account does not have enough event currency, the request is
        treated as a no-op and the current state is returned.  The game client
        surfaces most 4xx responses as a generic communication failure, so
        event reward APIs should prefer a valid zero-spin/zero-exchange result
        over aborting the session.
        """
        user_id = self._validate_user_id(user_id)
        event_item_id = self._validate_uint32(
            'event_item_id', event_item_id
        )
        event_item_cost = self._validate_uint32(
            'event_item_cost', event_item_cost
        )
        if event_item_cost and event_item_id == 0:
            raise StateStoreError('event_item_id must be positive')
        normalized = self._normalize_resources(rewards)

        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            if event_item_cost:
                row = connection.execute(
                    '''
                    SELECT quantity
                    FROM user_event_items
                    WHERE user_id = ? AND event_item_id = ?
                    ''',
                    (user_id, event_item_id),
                ).fetchone()
                available = 0 if row is None else max(row['quantity'], 0)
                if available < event_item_cost:
                    return self._get_user_state(connection, user_id)
                connection.execute(
                    '''
                    UPDATE user_event_items
                    SET quantity = quantity - ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND event_item_id = ?
                    ''',
                    (event_item_cost, user_id, event_item_id),
                )

            self._grant_resources(connection, user_id, normalized)
            return self._get_user_state(connection, user_id)

    def get_event_exchange_counts(
            self, user_id: int, event_id: int) -> dict[int, int]:
        user_id = self._validate_user_id(user_id)
        event_id = self._validate_uint32('event_id', event_id)
        with closing(self._connect()) as connection:
            self._ensure_user(connection, user_id)
            rows = connection.execute(
                '''
                SELECT seq, exchanged_count
                FROM user_event_exchanges
                WHERE user_id = ? AND event_id = ?
                ''',
                (user_id, event_id),
            ).fetchall()
        return {
            row['seq']: max(0, row['exchanged_count'])
            for row in rows
        }

    def purchase_event_exchange(
            self,
            user_id: int,
            event_id: int,
            seq: int,
            event_item_id: int,
            event_item_cost_per_count: int,
            rewards_per_count: Sequence[ResourceState],
            requested_count: int,
            exchange_limit: int | None = None,
    ) -> EventExchangePurchaseState:
        user_id = self._validate_user_id(user_id)
        event_id = self._validate_uint32('event_id', event_id)
        seq = self._validate_uint32('seq', seq)
        event_item_id = self._validate_uint32(
            'event_item_id', event_item_id
        )
        event_item_cost_per_count = self._validate_uint32(
            'event_item_cost_per_count', event_item_cost_per_count
        )
        requested_count = self._validate_uint32(
            'requested_count', requested_count
        )
        if exchange_limit is not None:
            exchange_limit = self._validate_uint32(
                'exchange_limit', exchange_limit
            )
        if not all((event_id, seq)):
            raise StateStoreError('event_id and seq must be positive')
        if event_item_cost_per_count and event_item_id == 0:
            raise StateStoreError('event_item_id must be positive')
        normalized = self._normalize_resources(rewards_per_count)

        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            row = connection.execute(
                '''
                SELECT exchanged_count
                FROM user_event_exchanges
                WHERE user_id = ? AND event_id = ? AND seq = ?
                ''',
                (user_id, event_id, seq),
            ).fetchone()
            total_exchanged = (
                0 if row is None else max(0, row['exchanged_count'])
            )
            actual_count = requested_count
            if exchange_limit is not None:
                actual_count = min(
                    actual_count,
                    max(0, exchange_limit - total_exchanged),
                )
            if event_item_cost_per_count:
                item = connection.execute(
                    '''
                    SELECT quantity
                    FROM user_event_items
                    WHERE user_id = ? AND event_item_id = ?
                    ''',
                    (user_id, event_item_id),
                ).fetchone()
                available = 0 if item is None else max(item['quantity'], 0)
                actual_count = min(
                    actual_count,
                    available // event_item_cost_per_count,
                )
            if actual_count <= 0:
                return EventExchangePurchaseState(
                    self._get_user_state(connection, user_id),
                    0,
                    total_exchanged,
                )

            if event_item_cost_per_count:
                connection.execute(
                    '''
                    UPDATE user_event_items
                    SET quantity = quantity - ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND event_item_id = ?
                    ''',
                    (
                        event_item_cost_per_count * actual_count,
                        user_id,
                        event_item_id,
                    ),
                )
            rewards = tuple(
                replace(resource, quantity=resource.quantity * actual_count)
                for resource in normalized
            )
            self._grant_resources(connection, user_id, rewards)
            total_exchanged += actual_count
            connection.execute(
                '''
                INSERT INTO user_event_exchanges (
                    user_id, event_id, seq, exchanged_count
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, event_id, seq) DO UPDATE SET
                    exchanged_count = excluded.exchanged_count,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (user_id, event_id, seq, total_exchanged),
            )
            return EventExchangePurchaseState(
                self._get_user_state(connection, user_id),
                actual_count,
                total_exchanged,
            )

    def recover_live_boost(
            self,
            user_id: int,
            recovery_item_id: int = 0,
            recovery_amount: int = 10,
            recovery_item_count: int = 1,
    ) -> UserState:
        user_id = self._validate_user_id(user_id)
        recovery_item_id = self._validate_uint32(
            'recovery_item_id', recovery_item_id
        )
        recovery_amount = self._validate_uint32(
            'recovery_amount', recovery_amount
        )
        recovery_item_count = self._validate_uint32(
            'recovery_item_count', recovery_item_count
        )
        if recovery_amount == 0:
            raise StateStoreError('recovery_amount must be positive')
        if recovery_item_count == 0:
            raise StateStoreError('recovery_item_count must be positive')

        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            self._refresh_live_boost(connection, user_id)
            row = connection.execute(
                '''
                SELECT live_boost, live_boost_updated_at
                FROM users WHERE user_id = ?
                ''',
                (user_id,),
            ).fetchone()
            if row['live_boost'] >= LIVE_BOOST_ITEM_MAX:
                return self._get_user_state(connection, user_id)
            if recovery_item_id == 0:
                return self._get_user_state(connection, user_id)

            needed_boost = LIVE_BOOST_ITEM_MAX - row['live_boost']
            units_fit = needed_boost // recovery_amount
            if units_fit == 0:
                return self._get_user_state(connection, user_id)
            consume_count = min(recovery_item_count, units_fit)

            if recovery_item_id:
                item = connection.execute(
                    '''
                    SELECT quantity
                    FROM user_live_boost_recovery_items
                    WHERE user_id = ? AND live_boost_recovery_item_id = ?
                    ''',
                    (user_id, recovery_item_id),
                ).fetchone()
                available = 0 if item is None else max(item['quantity'], 0)
                consume_count = min(consume_count, available)
                if not consume_count:
                    return self._get_user_state(connection, user_id)
                connection.execute(
                    '''
                    UPDATE user_live_boost_recovery_items
                    SET quantity = quantity - ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND live_boost_recovery_item_id = ?
                    ''',
                    (consume_count, user_id, recovery_item_id),
                )

            now = int(time.time())
            live_boost = min(
                row['live_boost'] + recovery_amount * consume_count,
                LIVE_BOOST_ITEM_MAX,
            )
            updated_at = (
                now if live_boost >= LIVE_BOOST_NATURAL_MAX
                else row['live_boost_updated_at'] or now
            )
            connection.execute(
                '''
                UPDATE users
                SET live_boost = ?, live_boost_updated_at = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                ''',
                (live_boost, updated_at, user_id),
            )
            return self._get_user_state(connection, user_id)

    def purchase_area_item(
            self,
            user_id: int,
            area_item_id: int,
            area_item_category: int,
            level: int,
            area_id: int,
            coin_cost: int,
            item_costs: Sequence[ResourceState],
            *,
            upgrade: bool,
    ) -> AreaItemPurchaseState:
        """Buy or upgrade one area-item category as a single transaction."""
        user_id = self._validate_user_id(user_id)
        area_item_id = self._validate_uint32(
            'area_item_id', area_item_id
        )
        area_item_category = self._validate_uint32(
            'area_item_category', area_item_category
        )
        level = self._validate_uint32('level', level)
        area_id = self._validate_uint32('area_id', area_id)
        coin_cost = self._validate_uint32('coin_cost', coin_cost)
        if not all((area_item_id, area_item_category, level, area_id)):
            raise StateStoreError('area item identifiers must be positive')

        normalized_costs = self._normalize_resources(item_costs)
        if any(cost.resource_type != 'item' for cost in normalized_costs):
            raise StateStoreError('area item costs must contain items only')
        aggregated_costs: dict[int, int] = {}
        for cost in normalized_costs:
            aggregated_costs[cost.resource_id] = (
                aggregated_costs.get(cost.resource_id, 0) + cost.quantity
            )

        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            current = connection.execute(
                '''
                SELECT area_item_id, level FROM user_area_items
                WHERE user_id = ? AND area_item_category = ?
                ''',
                (user_id, area_item_category),
            ).fetchone()
            if upgrade:
                if current is None:
                    raise StateStoreError('area item is not owned')
                if level != current['level'] + 1:
                    raise StateStoreError('area item upgrade level is invalid')
            else:
                if current is not None:
                    raise StateStoreError('area item category is already owned')
                if level != 1:
                    raise StateStoreError('a new area item must start at level 1')

            coin = connection.execute(
                'SELECT coin FROM users WHERE user_id = ?',
                (user_id,),
            ).fetchone()['coin']
            if coin < coin_cost:
                raise StateStoreError('not enough coins')
            for item_id, quantity in aggregated_costs.items():
                row = connection.execute(
                    '''
                    SELECT quantity FROM user_items
                    WHERE user_id = ? AND item_id = ?
                    ''',
                    (user_id, item_id),
                ).fetchone()
                if row is None or row['quantity'] < quantity:
                    raise StateStoreError(f'not enough item {item_id}')

            connection.execute(
                '''
                UPDATE users SET coin = coin - ?,
                    updated_at = CURRENT_TIMESTAMP WHERE user_id = ?
                ''',
                (coin_cost, user_id),
            )
            for item_id, quantity in aggregated_costs.items():
                connection.execute(
                    '''
                    UPDATE user_items SET quantity = quantity - ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND item_id = ?
                    ''',
                    (quantity, user_id, item_id),
                )
            connection.execute(
                '''
                INSERT INTO user_area_items (
                    user_id, area_item_category, area_item_id, level
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, area_item_category) DO UPDATE SET
                    area_item_id = excluded.area_item_id,
                    level = excluded.level,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (user_id, area_item_category, area_item_id, level),
            )
            connection.execute(
                '''
                UPDATE user_area_item_placements
                SET area_item_id = ?, area_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND area_item_category = ?
                ''',
                (area_item_id, area_id, user_id, area_item_category),
            )
            user = self._get_user_state(connection, user_id)
            area_item = next(
                item for item in user.area_items
                if item.area_item_category == area_item_category
            )
            return AreaItemPurchaseState(user, area_item, upgrade)

    def put_area_items(
            self,
            user_id: int,
            placements: Sequence[AreaItemPlacementState],
    ) -> UserState:
        """Replace the user's installed area items after ownership checks."""
        user_id = self._validate_user_id(user_id)
        normalized = []
        categories = set()
        for placement in placements:
            if not isinstance(placement, AreaItemPlacementState):
                raise StateStoreError(
                    'placements must contain AreaItemPlacementState values'
                )
            values = (
                self._validate_uint32(
                    'area_item_id', placement.area_item_id
                ),
                self._validate_uint32(
                    'area_item_category', placement.area_item_category
                ),
                self._validate_uint32('area_id', placement.area_id),
            )
            if not all(values):
                raise StateStoreError('area item identifiers must be positive')
            if placement.area_item_category in categories:
                raise StateStoreError('area item category is duplicated')
            categories.add(placement.area_item_category)
            normalized.append(placement)

        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            owned = {
                row['area_item_category']: row['area_item_id']
                for row in connection.execute(
                    '''
                    SELECT area_item_category, area_item_id
                    FROM user_area_items WHERE user_id = ?
                    ''',
                    (user_id,),
                ).fetchall()
            }
            for placement in normalized:
                if owned.get(placement.area_item_category) != (
                        placement.area_item_id):
                    raise StateStoreError('area item is not owned')
            connection.execute(
                'DELETE FROM user_area_item_placements WHERE user_id = ?',
                (user_id,),
            )
            connection.executemany(
                '''
                INSERT INTO user_area_item_placements (
                    user_id, area_item_category, area_item_id, area_id
                ) VALUES (?, ?, ?, ?)
                ''',
                [
                    (
                        user_id,
                        placement.area_item_category,
                        placement.area_item_id,
                        placement.area_id,
                    )
                    for placement in normalized
                ],
            )
            return self._get_user_state(connection, user_id)

    def claim_mission_reward(
            self,
            user_id: int,
            mission_id: int,
            seq: int,
            rewards: Sequence[ResourceState],
            next_target: int | None = None,
    ) -> MissionRewardState:
        user_id = self._validate_user_id(user_id)
        mission_id = self._validate_uint32('mission_id', mission_id)
        seq = self._validate_uint32('seq', seq)
        if mission_id == 0 or seq == 0:
            raise StateStoreError('mission_id and seq must be positive')
        normalized = self._normalize_resources(rewards)
        if next_target is not None:
            next_target = self._validate_uint32('next_target', next_target)
            if next_target == 0:
                raise StateStoreError('next_target must be positive')

        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            row = connection.execute(
                '''
                SELECT seq, progress, mission_progress_type, mission_group_id
                FROM user_missions
                WHERE user_id = ? AND mission_id = ?
                ''',
                (user_id, mission_id),
            ).fetchone()
            if row is None:
                raise StateStoreError('mission was not found')
            if row['seq'] != seq:
                raise StateStoreError('mission sequence does not match')
            if row['mission_progress_type'] != 'complete':
                raise StateStoreError('mission reward is not receivable')

            self._grant_resources(connection, user_id, normalized)
            if next_target is None:
                next_seq = seq
                next_progress = row['progress']
                progress_type = 'end'
            else:
                next_seq = seq + 1
                next_progress = min(row['progress'], next_target)
                progress_type = (
                    'complete' if next_progress >= next_target
                    else 'in_progress'
                )
            connection.execute(
                '''
                UPDATE user_missions
                SET seq = ?, progress = ?, mission_progress_type = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND mission_id = ?
                ''',
                (
                    next_seq, next_progress, progress_type,
                    user_id, mission_id,
                ),
            )
            user = self._get_user_state(connection, user_id)
            mission = next(
                value for value in user.missions
                if value.mission_id == mission_id
            )
            return MissionRewardState(user, mission, normalized)

    def receive_presents(
            self, user_id: int, present_ids: Sequence[int]) -> PresentReceiptState:
        user_id = self._validate_user_id(user_id)
        normalized_ids = tuple(dict.fromkeys(
            self._validate_uint32('present_id', value)
            for value in present_ids
        ))
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            if normalized_ids:
                placeholders = ','.join('?' for _ in normalized_ids)
                rows = connection.execute(
                    f'''
                    SELECT present_id, resource_type, resource_id, quantity,
                           reason, expired_at, created_at
                    FROM presents
                    WHERE user_id = ? AND received_at IS NULL
                      AND present_id IN ({placeholders})
                      AND (expired_at IS NULL OR expired_at > ?)
                    ORDER BY present_id
                    ''',
                    (user_id, *normalized_ids, int(time.time() * 1000)),
                ).fetchall()
            else:
                rows = connection.execute(
                    '''
                    SELECT present_id, resource_type, resource_id, quantity,
                           reason, expired_at, created_at
                    FROM presents
                    WHERE user_id = ? AND received_at IS NULL
                      AND (expired_at IS NULL OR expired_at > ?)
                    ORDER BY present_id
                    ''',
                    (user_id, int(time.time() * 1000)),
                ).fetchall()

            received = tuple(
                PresentState(
                    present_id=row['present_id'],
                    resource_type=row['resource_type'],
                    resource_id=row['resource_id'],
                    quantity=row['quantity'],
                    reason=row['reason'],
                    expired_at=row['expired_at'],
                    created_at=row['created_at'],
                )
                for row in rows
            )
            for present in received:
                resource = self._normalize_resources((ResourceState(
                    present.resource_type,
                    present.resource_id,
                    present.quantity,
                ),))
                self._grant_resources(connection, user_id, resource)
                connection.execute(
                    '''
                    UPDATE presents SET received_at = ?
                    WHERE user_id = ? AND present_id = ?
                    ''',
                    (int(time.time() * 1000), user_id, present.present_id),
                )

            return PresentReceiptState(
                user=self._get_user_state(connection, user_id),
                presents=received,
            )

    def list_present_history(self, user_id: int) -> tuple[PresentState, ...]:
        user_id = self._validate_user_id(user_id)
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            rows = connection.execute(
                '''
                SELECT present_id, resource_type, resource_id, quantity,
                       reason, expired_at, created_at
                FROM presents
                WHERE user_id = ? AND received_at IS NOT NULL
                ORDER BY received_at DESC, present_id DESC
                ''',
                (user_id,),
            ).fetchall()
            return tuple(
                PresentState(
                    present_id=row['present_id'],
                    resource_type=row['resource_type'],
                    resource_id=row['resource_id'],
                    quantity=row['quantity'],
                    reason=row['reason'],
                    expired_at=row['expired_at'],
                    created_at=row['created_at'],
                )
                for row in rows
            )

    def receive_login_bonus(
            self,
            user_id: int,
            login_bonus_id: int,
            rewards: Sequence[ResourceState],
            cycle_length: int,
            *,
            received_on: date | str | None = None,
    ) -> LoginBonusReceiptState:
        user_id = self._validate_user_id(user_id)
        login_bonus_id = self._validate_uint32(
            'login_bonus_id', login_bonus_id
        )
        cycle_length = self._validate_uint32('cycle_length', cycle_length)
        if login_bonus_id == 0:
            raise StateStoreError('login_bonus_id must be positive')
        if cycle_length == 0:
            raise StateStoreError('cycle_length must be positive')
        normalized = self._normalize_resources(rewards)
        if received_on is None:
            received_day = today_kst_iso()
        elif isinstance(received_on, date):
            received_day = received_on.isoformat()
        else:
            received_day = str(received_on)
        if not received_day:
            raise StateStoreError('received_on must not be empty')

        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            row = connection.execute(
                '''
                SELECT days, last_received_on
                FROM user_login_bonuses
                WHERE user_id = ? AND login_bonus_id = ?
                ''',
                (user_id, login_bonus_id),
            ).fetchone()
            if row is None:
                current_days = 1
                last_received_on = None
                connection.execute(
                    '''
                    INSERT INTO user_login_bonuses (
                        user_id, login_bonus_id, days, last_received_on
                    ) VALUES (?, ?, ?, NULL)
                    ''',
                    (user_id, login_bonus_id, current_days),
                )
            else:
                current_days = row['days']
                last_received_on = row['last_received_on']

            if last_received_on == received_day:
                user = self._get_user_state(connection, user_id)
                login_bonus = next(
                    value for value in user.login_bonuses
                    if value.login_bonus_id == login_bonus_id
                )
                return LoginBonusReceiptState(
                    user=user,
                    login_bonus=login_bonus,
                    rewards=(),
                    received=False,
                )

            self._grant_resources(connection, user_id, normalized)
            next_days = current_days + 1
            if next_days > cycle_length:
                next_days = 1
            connection.execute(
                '''
                UPDATE user_login_bonuses
                SET days = ?, last_received_on = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND login_bonus_id = ?
                ''',
                (next_days, received_day, user_id, login_bonus_id),
            )
            user = self._get_user_state(connection, user_id)
            login_bonus = next(
                value for value in user.login_bonuses
                if value.login_bonus_id == login_bonus_id
            )
            return LoginBonusReceiptState(
                user=user,
                login_bonus=login_bonus,
                rewards=normalized,
                received=True,
            )

    def upsert_deck(
            self,
            user_id: int,
            deck_id: int,
            deck_type: str,
            changes: Mapping[str, object],
    ) -> tuple[DeckState, UserState]:
        user_id = self._validate_user_id(user_id)
        deck_id = self._validate_uint32('deck_id', deck_id)
        deck_type = self._validate_deck_type(deck_type)

        unknown_fields = set(changes) - {'deck_name', *DECK_MEMBER_FIELDS}
        if unknown_fields:
            raise StateStoreError(
                f'unknown deck fields: {", ".join(sorted(unknown_fields))}'
            )

        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            if deck_id == 0:
                row = connection.execute(
                    '''
                    SELECT COALESCE(MAX(deck_id), 0) + 1 AS next_id
                    FROM decks WHERE user_id = ? AND deck_type = ?
                    ''',
                    (user_id, deck_type),
                ).fetchone()
                deck_id = row['next_id']

            row = connection.execute(
                '''
                SELECT deck_id, deck_name, leader, member1, member2, member3,
                       member4, deck_type
                FROM decks
                WHERE user_id = ? AND deck_type = ? AND deck_id = ?
                ''',
                (user_id, deck_type, deck_id),
            ).fetchone()
            current = (
                self._row_to_deck(row)
                if row is not None
                else DeckState(deck_id, f'밴드{deck_id}', 0, 0, 0, 0, 0, deck_type)
            )

            normalized: dict[str, object] = {}
            if 'deck_name' in changes:
                deck_name = changes['deck_name']
                if not isinstance(deck_name, str):
                    raise StateStoreError('deck_name must be a string')
                deck_name = deck_name.strip()
                if not deck_name:
                    raise StateStoreError('deck_name must not be empty')
                if len(deck_name) > 50:
                    raise StateStoreError('deck_name must not exceed 50 characters')
                normalized['deck_name'] = deck_name

            for field in DECK_MEMBER_FIELDS:
                if field in changes:
                    normalized[field] = self._validate_uint32(
                        field, changes[field]
                    )

            updated = replace(current, **normalized)
            connection.execute(
                '''
                INSERT INTO decks (
                    user_id, deck_type, deck_id, deck_name,
                    leader, member1, member2, member3, member4
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, deck_type, deck_id) DO UPDATE SET
                    deck_name = excluded.deck_name,
                    leader = excluded.leader,
                    member1 = excluded.member1,
                    member2 = excluded.member2,
                    member3 = excluded.member3,
                    member4 = excluded.member4,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (
                    user_id,
                    updated.deck_type,
                    updated.deck_id,
                    updated.deck_name,
                    updated.leader,
                    updated.member1,
                    updated.member2,
                    updated.member3,
                    updated.member4,
                ),
            )
            connection.execute(
                'UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                (user_id,),
            )
            return updated, self._get_user_state(connection, user_id)

    def set_main_deck(self, user_id: int, deck_id: int) -> UserState:
        user_id = self._validate_user_id(user_id)
        deck_id = self._validate_uint32('deck_id', deck_id)
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            exists = connection.execute(
                '''
                SELECT 1 FROM decks
                WHERE user_id = ? AND deck_type = 'normal' AND deck_id = ?
                ''',
                (user_id, deck_id),
            ).fetchone()
            if exists is None:
                raise StateStoreError(f'normal deck {deck_id} does not exist')
            connection.execute(
                '''
                UPDATE users
                SET main_deck = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                ''',
                (deck_id, user_id),
            )
            return self._get_user_state(connection, user_id)

    def delete_deck(
            self, user_id: int, deck_id: int, deck_type: str) -> UserState:
        user_id = self._validate_user_id(user_id)
        deck_id = self._validate_uint32('deck_id', deck_id)
        deck_type = self._validate_deck_type(deck_type)
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            existing = connection.execute(
                '''
                SELECT 1 FROM decks
                WHERE user_id = ? AND deck_type = ? AND deck_id = ?
                ''',
                (user_id, deck_type, deck_id),
            ).fetchone()
            if existing is None:
                return self._get_user_state(connection, user_id)

            if deck_type == 'normal':
                normal_count = connection.execute(
                    '''
                    SELECT COUNT(*) AS count FROM decks
                    WHERE user_id = ? AND deck_type = 'normal'
                    ''',
                    (user_id,),
                ).fetchone()['count']
                if normal_count <= 1:
                    raise StateStoreError('the last normal deck cannot be deleted')

            connection.execute(
                '''
                DELETE FROM decks
                WHERE user_id = ? AND deck_type = ? AND deck_id = ?
                ''',
                (user_id, deck_type, deck_id),
            )
            user = connection.execute(
                'SELECT main_deck FROM users WHERE user_id = ?',
                (user_id,),
            ).fetchone()
            if deck_type == 'normal' and user['main_deck'] == deck_id:
                replacement = connection.execute(
                    '''
                    SELECT MIN(deck_id) AS deck_id FROM decks
                    WHERE user_id = ? AND deck_type = 'normal'
                    ''',
                    (user_id,),
                ).fetchone()['deck_id']
                connection.execute(
                    '''
                    UPDATE users
                    SET main_deck = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                    ''',
                    (replacement, user_id),
                )
            return self._get_user_state(connection, user_id)

    def upsert_gallery(
            self,
            user_id: int,
            situation_id: int,
            illust: str,
            seq: int,
    ) -> UserState:
        user_id = self._validate_user_id(user_id)
        situation_id = self._validate_uint32('situation_id', situation_id)
        seq = self._validate_uint32('seq', seq)
        if situation_id == 0:
            raise StateStoreError('situation_id must be positive')
        if not isinstance(illust, str) or not illust.strip():
            raise StateStoreError('illust must not be empty')
        illust = illust.strip()
        if len(illust) > 50:
            raise StateStoreError('illust must not exceed 50 characters')

        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            connection.execute(
                '''
                INSERT INTO user_galleries (
                    user_id, seq, situation_id, illust
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, seq) DO UPDATE SET
                    situation_id = excluded.situation_id,
                    illust = excluded.illust,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (user_id, seq, situation_id, illust),
            )
            connection.execute(
                'UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                (user_id,),
            )
            return self._get_user_state(connection, user_id)

    def clear_gallery(self, user_id: int) -> UserState:
        user_id = self._validate_user_id(user_id)
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            connection.execute(
                'DELETE FROM user_galleries WHERE user_id = ?',
                (user_id,),
            )
            connection.execute(
                'UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                (user_id,),
            )
            return self._get_user_state(connection, user_id)

    def set_character_costume(
            self, user_id: int, character_id: int, costume_id: int) -> UserState:
        user_id = self._validate_user_id(user_id)
        character_id = self._validate_uint32('character_id', character_id)
        costume_id = self._validate_uint32('costume_id', costume_id)
        if character_id == 0:
            raise StateStoreError('character_id must be positive')
        if costume_id == 0:
            return self.clear_character_costume(user_id, character_id)
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            connection.execute(
                '''
                INSERT INTO character_costumes (
                    user_id, character_id, costume_id
                ) VALUES (?, ?, ?)
                ON CONFLICT(user_id, character_id) DO UPDATE SET
                    costume_id = excluded.costume_id,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (user_id, character_id, costume_id),
            )
            return self._get_user_state(connection, user_id)

    def clear_character_costume(
            self, user_id: int, character_id: int) -> UserState:
        user_id = self._validate_user_id(user_id)
        character_id = self._validate_uint32('character_id', character_id)
        if character_id == 0:
            raise StateStoreError('character_id must be positive')
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            connection.execute(
                '''
                DELETE FROM character_costumes
                WHERE user_id = ? AND character_id = ?
                ''',
                (user_id, character_id),
            )
            return self._get_user_state(connection, user_id)

    def read_main_story(self, user_id: int, story_id: int) -> UserState:
        user_id = self._validate_user_id(user_id)
        story_id = self._validate_uint32('story_id', story_id)
        if story_id == 0:
            raise StateStoreError('story_id must be positive')
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            connection.execute(
                '''
                INSERT OR IGNORE INTO main_story_reads (user_id, story_id)
                VALUES (?, ?)
                ''',
                (user_id, story_id),
            )
            return self._get_user_state(connection, user_id)

    def read_band_story(
            self, user_id: int, band_id: int, band_story_id: int) -> UserState:
        user_id = self._validate_user_id(user_id)
        band_id = self._validate_uint32('band_id', band_id)
        band_story_id = self._validate_uint32('band_story_id', band_story_id)
        if band_id == 0:
            raise StateStoreError('band_id must be positive')
        if band_story_id == 0:
            raise StateStoreError('band_story_id must be positive')
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            connection.execute(
                '''
                INSERT OR IGNORE INTO band_story_reads (
                    user_id, band_id, band_story_id
                ) VALUES (?, ?, ?)
                ''',
                (user_id, band_id, band_story_id),
            )
            return self._get_user_state(connection, user_id)

    def read_event_story(
            self,
            user_id: int,
            event_id: int,
            seq: int,
            rewards: Sequence[ResourceState],
    ) -> EventStoryReadReceiptState:
        user_id = self._validate_user_id(user_id)
        event_id = self._validate_uint32('event_id', event_id)
        seq = self._validate_uint32('seq', seq)
        if event_id == 0:
            raise StateStoreError('event_id must be positive')
        normalized = self._normalize_resources(rewards)

        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            row = connection.execute(
                '''
                SELECT reward_received
                FROM event_story_reads
                WHERE user_id = ? AND event_id = ? AND seq = ?
                ''',
                (user_id, event_id, seq),
            ).fetchone()
            should_grant = row is None or not bool(row['reward_received'])
            if should_grant:
                self._grant_resources(connection, user_id, normalized)

            connection.execute(
                '''
                INSERT OR IGNORE INTO event_story_reads (
                    user_id, event_id, seq, reward_received
                ) VALUES (?, ?, ?, 1)
                ''',
                (user_id, event_id, seq),
            )
            connection.execute(
                '''
                UPDATE event_story_reads
                SET reward_received = 1
                WHERE user_id = ? AND event_id = ? AND seq = ?
                    AND reward_received = 0
                ''',
                (user_id, event_id, seq),
            )
            return EventStoryReadReceiptState(
                self._get_user_state(connection, user_id),
                event_id,
                seq,
                normalized if should_grant else (),
                should_grant,
            )

    @staticmethod
    def _refund_active_live_boost(
            connection: sqlite3.Connection,
            user_id: int,
            music_id: int | None = None,
    ) -> int:
        if music_id is None:
            active = connection.execute(
                '''
                SELECT music_id, live_boost_use_count
                FROM active_lives WHERE user_id = ?
                ''',
                (user_id,),
            ).fetchone()
        else:
            active = connection.execute(
                '''
                SELECT music_id, live_boost_use_count
                FROM active_lives
                WHERE user_id = ? AND music_id = ?
                ''',
                (user_id, music_id),
            ).fetchone()
        if active is None:
            return 0

        refund_count = max(0, int(active['live_boost_use_count'] or 0))
        if refund_count:
            row = connection.execute(
                '''
                SELECT live_boost
                FROM users WHERE user_id = ?
                ''',
                (user_id,),
            ).fetchone()
            live_boost = min(
                int(row['live_boost']) + refund_count,
                LIVE_BOOST_ITEM_MAX,
            )
            connection.execute(
                '''
                UPDATE users
                SET live_boost = ?,
                    live_boost_updated_at = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                ''',
                (live_boost, int(time.time()), user_id),
            )
        connection.execute(
            'DELETE FROM active_lives WHERE user_id = ?',
            (user_id,),
        )
        return refund_count

    def start_live(
            self,
            user_id: int,
            music_id: int,
            live_type: str,
            live_boost_use_count: int,
            event_id: int = 0,
    ) -> UserState:
        user_id = self._validate_user_id(user_id)
        music_id = self._validate_uint32('music_id', music_id)
        if music_id == 0:
            raise StateStoreError('music_id must be positive')
        if not isinstance(live_type, str) or not live_type.strip():
            raise StateStoreError('live_type must not be empty')
        live_type = live_type.strip()
        if len(live_type) > 50:
            raise StateStoreError('live_type must not exceed 50 characters')
        live_boost_use_count = self._validate_uint32(
            'live_boost_use_count', live_boost_use_count
        )
        event_id = self._validate_uint32('event_id', event_id)
        if live_boost_use_count > 10:
            raise StateStoreError('live_boost_use_count must not exceed 10')

        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            self._refresh_live_boost(connection, user_id)
            # The client can re-enter live preprocessing when a live is
            # restarted from the pause/failure flow.  Settle the previous
            # active live first so the same boost is not consumed twice.
            self._refund_active_live_boost(connection, user_id)
            user = connection.execute(
                'SELECT live_boost FROM users WHERE user_id = ?',
                (user_id,),
            ).fetchone()
            if user['live_boost'] < live_boost_use_count:
                raise StateStoreError('not enough live boost')
            now = int(time.time())
            if live_boost_use_count:
                connection.execute(
                    '''
                    UPDATE users
                    SET live_boost = live_boost - ?,
                        live_boost_updated_at = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                    ''',
                    (live_boost_use_count, now, user_id),
                )
            connection.execute(
                '''
                INSERT INTO active_lives (
                    user_id, music_id, live_type, event_id,
                    live_boost_use_count,
                    continue_count, started_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    music_id = excluded.music_id,
                    live_type = excluded.live_type,
                    event_id = excluded.event_id,
                    live_boost_use_count = excluded.live_boost_use_count,
                    continue_count = 0,
                    started_at = excluded.started_at
                ''',
                (
                    user_id, music_id, live_type, event_id,
                    live_boost_use_count, now,
                ),
            )
            return self._get_user_state(connection, user_id)

    def abandon_live(
            self, user_id: int, music_id: int | None = None) -> UserState:
        user_id = self._validate_user_id(user_id)
        if music_id is not None:
            music_id = self._validate_uint32('music_id', music_id)
            if music_id == 0:
                raise StateStoreError('music_id must be positive')
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            self._refresh_live_boost(connection, user_id)
            self._refund_active_live_boost(connection, user_id, music_id)
            return self._get_user_state(connection, user_id)

    def retry_live(self, user_id: int, music_id: int) -> UserState:
        user_id = self._validate_user_id(user_id)
        music_id = self._validate_uint32('music_id', music_id)
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            active = connection.execute(
                'SELECT music_id FROM active_lives WHERE user_id = ?',
                (user_id,),
            ).fetchone()
            if active is None:
                connection.execute(
                    '''
                    INSERT INTO active_lives (
                        user_id, music_id, live_type, event_id,
                        live_boost_use_count,
                        continue_count, started_at
                    ) VALUES (?, ?, 'free_live', 0, 0, 0, ?)
                    ''',
                    (user_id, music_id, int(time.time())),
                )
            elif active['music_id'] != music_id:
                raise StateStoreError('active live uses a different music_id')
            else:
                connection.execute(
                    '''
                    UPDATE active_lives SET started_at = ? WHERE user_id = ?
                    ''',
                    (int(time.time()), user_id),
                )
            return self._get_user_state(connection, user_id)

    def continue_live(
            self, user_id: int, music_id: int, continue_count: int) -> UserState:
        user_id = self._validate_user_id(user_id)
        music_id = self._validate_uint32('music_id', music_id)
        continue_count = self._validate_uint32(
            'continue_count', continue_count
        )
        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            active = connection.execute(
                '''
                SELECT music_id, continue_count
                FROM active_lives WHERE user_id = ?
                ''',
                (user_id,),
            ).fetchone()
            if active is None or active['music_id'] != music_id:
                raise StateStoreError('matching active live was not found')
            if continue_count < active['continue_count']:
                raise StateStoreError('continue_count cannot decrease')
            additional_continues = continue_count - active['continue_count']
            cost = additional_continues * 50
            if cost:
                free_star = connection.execute(
                    'SELECT free_star FROM users WHERE user_id = ?',
                    (user_id,),
                ).fetchone()['free_star']
                if free_star < cost:
                    raise StateStoreError('not enough free_star to continue live')
                connection.execute(
                    '''
                    UPDATE users SET free_star = free_star - ?
                    WHERE user_id = ?
                    ''',
                    (cost, user_id),
                )
            connection.execute(
                '''
                UPDATE active_lives
                SET continue_count = ?, started_at = ?
                WHERE user_id = ?
                ''',
                (continue_count, int(time.time()), user_id),
            )
            return self._get_user_state(connection, user_id)

    @staticmethod
    def _clear_status_priority(clear_status: str) -> int:
        priorities = {
            '': 0,
            'not_clear': 0,
            'failed': 0,
            'clear': 1,
            'cleared': 1,
            'full_combo': 2,
            'all_perfect': 3,
        }
        return priorities.get(clear_status, 1)

    @staticmethod
    def _normalize_music_difficulty(music_difficulty: str) -> str:
        text = (
            music_difficulty.strip().lower()
            if music_difficulty else 'normal'
        )
        aliases = {
            '0': 'easy',
            '1': 'normal',
            '2': 'hard',
            '3': 'expert',
            '4': 'special',
            'ex': 'expert',
            'sp': 'special',
        }
        text = aliases.get(text, text)
        if text not in LIVE_RESULT_DIFFICULTIES:
            return 'normal'
        return text

    @staticmethod
    def _normalize_score_rank(clear_rank: str) -> str:
        text = clear_rank.strip().lower() if clear_rank else 'd'
        aliases = {
            'ss_rank': 'ss',
            's_rank': 's',
            'rank_ss': 'ss',
            'rank_s': 's',
        }
        text = aliases.get(text, text)
        if text not in LIVE_RESULT_RANKS:
            return 'd'
        return text

    @staticmethod
    def _normalize_clear_status(
            clear_status: str,
            combo: int,
            perfect_count: int,
            total_notes_count: int) -> str:
        text = clear_status.strip().lower() if clear_status else 'clear'
        aliases = {
            'cleared': 'clear',
            'live_clear': 'clear',
            'success': 'clear',
            'fail': 'failed',
            'failure': 'failed',
            'fc': 'full_combo',
            'fullcombo': 'full_combo',
            'allperfect': 'all_perfect',
            'ap': 'all_perfect',
        }
        text = aliases.get(text, text)
        if text not in LIVE_RESULT_CLEAR_STATUSES:
            text = 'clear'
        if total_notes_count and perfect_count >= total_notes_count:
            return 'all_perfect'
        if total_notes_count and combo >= total_notes_count:
            return 'full_combo'
        return text

    def clear_live(
            self,
            user_id: int,
            music_id: int,
            music_difficulty: str,
            clear_rank: str,
            score: int,
            combo: int,
            clear_status: str,
            perfect_count: int = 0,
            total_notes_count: int = 0,
            event_id: int = 0,
    ) -> LiveClearState:
        user_id = self._validate_user_id(user_id)
        music_id = self._validate_uint32('music_id', music_id)
        score = self._validate_uint32('score', score)
        combo = self._validate_uint32('combo', combo)
        perfect_count = self._validate_uint32('perfect_count', perfect_count)
        total_notes_count = self._validate_uint32(
            'total_notes_count', total_notes_count
        )
        event_id = self._validate_uint32('event_id', event_id)
        if total_notes_count:
            combo = min(combo, total_notes_count)
            perfect_count = min(perfect_count, total_notes_count)
        music_difficulty = self._normalize_music_difficulty(music_difficulty)
        clear_rank = self._normalize_score_rank(clear_rank)
        clear_status = self._normalize_clear_status(
            clear_status, combo, perfect_count, total_notes_count
        )

        with closing(self._connect()) as connection, connection:
            self._ensure_user(connection, user_id)
            active = connection.execute(
                '''
                SELECT music_id, live_type, event_id, live_boost_use_count
                FROM active_lives WHERE user_id = ?
                ''',
                (user_id,),
            ).fetchone()
            active_matches_request = (
                active is not None and active['music_id'] == music_id
            )
            live_boost_use_count = (
                active['live_boost_use_count'] if active_matches_request else 0
            )
            live_type = (
                active['live_type'] if active_matches_request else 'free_live'
            )
            if not event_id and active_matches_request:
                event_id = active['event_id']

            previous = connection.execute(
                '''
                SELECT solo_high_score, max_combo, solo_score_rank, clear_status
                FROM music_scores
                WHERE user_id = ? AND music_id = ? AND music_difficulty = ?
                ''',
                (user_id, music_id, music_difficulty),
            ).fetchone()
            solo_high_score = (
                score if previous is None else max(score, previous['solo_high_score'])
            )
            max_combo = (
                combo if previous is None else max(combo, previous['max_combo'])
            )
            rank_order = LIVE_RESULT_RANKS
            previous_rank = (
                previous['solo_score_rank'] if previous is not None else 'd'
            )
            solo_score_rank = max(
                (previous_rank, clear_rank),
                key=lambda rank: (
                    rank_order.index(rank) if rank in rank_order else 0
                ),
            )
            best_clear_status = clear_status
            if (previous is not None
                    and self._clear_status_priority(previous['clear_status'])
                    > self._clear_status_priority(clear_status)):
                best_clear_status = previous['clear_status']

            connection.execute(
                '''
                INSERT INTO music_scores (
                    user_id, music_id, music_difficulty, solo_high_score,
                    max_combo, solo_score_rank, clear_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, music_id, music_difficulty) DO UPDATE SET
                    solo_high_score = excluded.solo_high_score,
                    max_combo = excluded.max_combo,
                    solo_score_rank = excluded.solo_score_rank,
                    clear_status = excluded.clear_status,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (
                    user_id,
                    music_id,
                    music_difficulty,
                    solo_high_score,
                    max_combo,
                    solo_score_rank,
                    best_clear_status,
                ),
            )

            achievements = set()
            if self._clear_status_priority(clear_status) >= 1:
                achievements.add(f'combo_{music_difficulty}')
            if clear_status in {'full_combo', 'all_perfect'}:
                achievements.add(f'full_combo_{music_difficulty}')
            if total_notes_count and combo >= total_notes_count:
                achievements.add(f'full_combo_{music_difficulty}')
            if clear_rank in rank_order:
                rank_index = rank_order.index(clear_rank)
                achievements.update(
                    f'score_rank_{rank}'
                    for rank in rank_order[1:rank_index + 1]
                )
            existing_achievements = {
                row['achievement_type']
                for row in connection.execute(
                    '''
                    SELECT achievement_type FROM music_achievements
                    WHERE user_id = ? AND music_id = ?
                    ''',
                    (user_id, music_id),
                ).fetchall()
            }
            new_achievement_types = tuple(sorted(
                achievements - existing_achievements
            ))
            connection.executemany(
                '''
                INSERT OR IGNORE INTO music_achievements (
                    user_id, music_id, achievement_type
                ) VALUES (?, ?, ?)
                ''',
                [(user_id, music_id, value) for value in achievements],
            )

            reward_multiplier = live_boost_bonus(live_boost_use_count)
            live_point = (
                max(score // 10_000, 1) * reward_multiplier
                if event_id else 0
            )
            if event_id:
                previous_event = connection.execute(
                    '''
                    SELECT solo_high_score, max_combo, solo_score_rank,
                           clear_status
                    FROM event_music_scores
                    WHERE user_id = ? AND event_id = ? AND music_id = ?
                      AND music_difficulty = ?
                    ''',
                    (user_id, event_id, music_id, music_difficulty),
                ).fetchone()
                event_solo_high_score = (
                    score
                    if previous_event is None
                    else max(score, previous_event['solo_high_score'])
                )
                event_max_combo = (
                    combo
                    if previous_event is None
                    else max(combo, previous_event['max_combo'])
                )
                previous_event_rank = (
                    previous_event['solo_score_rank']
                    if previous_event is not None else 'd'
                )
                event_solo_score_rank = max(
                    (previous_event_rank, clear_rank),
                    key=lambda rank: (
                        rank_order.index(rank) if rank in rank_order else 0
                    ),
                )
                event_best_clear_status = clear_status
                if (previous_event is not None
                        and self._clear_status_priority(
                            previous_event['clear_status']
                        ) > self._clear_status_priority(clear_status)):
                    event_best_clear_status = previous_event['clear_status']

                connection.execute(
                    '''
                    INSERT INTO event_music_scores (
                        user_id, event_id, music_id, music_difficulty,
                        solo_high_score, max_combo, solo_score_rank,
                        clear_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(
                        user_id, event_id, music_id, music_difficulty
                    ) DO UPDATE SET
                        solo_high_score = excluded.solo_high_score,
                        max_combo = excluded.max_combo,
                        solo_score_rank = excluded.solo_score_rank,
                        clear_status = excluded.clear_status,
                        updated_at = CURRENT_TIMESTAMP
                    ''',
                    (
                        user_id,
                        event_id,
                        music_id,
                        music_difficulty,
                        event_solo_high_score,
                        event_max_combo,
                        event_solo_score_rank,
                        event_best_clear_status,
                    ),
                )
                connection.executemany(
                    '''
                    INSERT OR IGNORE INTO event_music_achievements (
                        user_id, event_id, music_id, achievement_type,
                        live_type
                    ) VALUES (?, ?, ?, ?, ?)
                    ''',
                    [
                        (user_id, event_id, music_id, value, live_type)
                        for value in achievements
                    ],
                )
                self._grant_resources(
                    connection,
                    user_id,
                    [ResourceState('event_item', event_id, live_point)],
                )
            drops = (
                ResourceState('coin', 0, 300 * reward_multiplier),
                *(
                    ResourceState('item', item_id, reward_multiplier)
                    for item_id in range(1, 5)
                ),
            )
            self._grant_resources(connection, user_id, drops)
            self._grant_rank_exp(
                connection,
                user_id,
                DEFAULT_LIVE_RANK_EXP * reward_multiplier,
            )

            connection.execute(
                '''
                UPDATE user_missions
                SET progress = progress + 1,
                    mission_progress_type = CASE
                        WHEN progress + 1 >= 1 THEN 'complete'
                        ELSE 'in_progress'
                    END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND mission_id = 5
                  AND mission_progress_type = 'in_progress'
                ''',
                (user_id,),
            )
            connection.execute(
                'DELETE FROM active_lives WHERE user_id = ?',
                (user_id,),
            )
            user_state = self._get_user_state(connection, user_id)
            music_score = next(
                item
                for item in user_state.music_scores
                if (item.music_id == music_id
                    and item.music_difficulty == music_difficulty)
            )
            return LiveClearState(
                user=user_state,
                score=music_score,
                event_id=event_id,
                live_type=live_type,
                live_point=live_point,
                live_boost_use_count=live_boost_use_count,
                live_boost_bonus=reward_multiplier,
                drops=drops,
                new_achievement_types=new_achievement_types,
            )
