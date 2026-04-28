# Aldnoah_Logic/aldnoah_energy.py
from __future__ import annotations

import os
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Dict, Optional, Tuple

from .aldnoah_infos import DW8XL_WEAPON_NAMES, section_1_names

LILAC = "#C8A2C8"
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


@dataclass(frozen=True)
class GameSchema:
    game_id: str
    display_name: str
    containers: Tuple[str, ...]
    idx_files: Tuple[str, ...]
    unpack_folder: str
    endian: str = "little"
    compression: str = "ZLIB"
    idx_chunk_read: int = 32
    raw_variables: Tuple[str, ...] = ("Offset", "Original_Size", "Compressed_Size", "Compression_Marker")
    field_size: int = 8
    start_from_offset: int = 0
    shift_bits: int = 0
    vars_to_shift: Tuple[str, ...] = ()


@dataclass(frozen=True)
class BinaryRecordSectionSchema:
    file_label: str
    file_path: str
    export_dir: str
    file_name: str
    offset: int
    record_size: int
    fields: Tuple[Tuple[str, int], ...]
    section_title: str
    section_subtitle: str
    columns: int = 2
    toggle_names: Tuple[str, ...] = ()
    toggle_title: str = ""
    toggle_subtitle: str = ""
    toggle_columns: int = 4
    hex_field_prefixes: Tuple[str, ...] = ("Unknown",)

    @property
    def export_path(self) -> str:
        return os.path.join(self.export_dir, self.file_name)

    @property
    def mapped_bytes(self) -> int:
        return sum(byte_width for _label, byte_width in self.fields) + len(self.toggle_names)


@dataclass(frozen=True)
class OfficerEditorSchema:
    game_id: str
    display_name: str
    officer_count: int
    primary_section: BinaryRecordSectionSchema
    secondary_section: Optional[BinaryRecordSectionSchema] = None
    officer_names: Tuple[str, ...] = ()
    name_list_path: str = ""
    placeholder_prefix: str = "Officer"
    hero_star_seed: int = 887
    hero_star_count: int = 46
    constellation_star_seed: int = 941
    constellation_star_count: int = 82
    constellation_arms: int = 10


@dataclass(frozen=True)
class NpcEditorSchema:
    game_id: str
    display_name: str
    npc_count: int
    section: BinaryRecordSectionSchema
    placeholder_prefix: str = "Unit"
    name_field: str = "Name"
    name_list_path: str = ""
    voice_map_path: str = ""
    model_map_path: str = ""
    moveset_map_path: str = ""
    hero_star_seed: int = 905
    hero_star_count: int = 48
    constellation_star_seed: int = 953
    constellation_star_count: int = 90
    constellation_arms: int = 18


@dataclass(frozen=True)
class WeaponEditorSchema:
    game_id: str
    display_name: str
    weapon_count: int
    section: BinaryRecordSectionSchema
    weapon_names: Tuple[str, ...] = ()
    placeholder_prefix: str = "Weapon Slot"
    hero_star_seed: int = 921
    hero_star_count: int = 50
    constellation_star_seed: int = 983
    constellation_star_count: int = 96
    constellation_arms: int = 25


GAME_SCHEMAS: Dict[str, GameSchema] = {
    "DW7XL": GameSchema(
        game_id="DW7XL",
        display_name="Dynasty Warriors 7 XL",
        containers=("LINKDATA_CMN.BIN", "LINKDATA_ENG.BIN", "LINKDATA_JPN.BIN", "LINKDATA_TCH.BIN"),
        idx_files=("LINKDATA_CMN.IDX", "LINKDATA_ENG.IDX", "LINKDATA_JPN.IDX", "LINKDATA_TCH.IDX"),
        unpack_folder="DW7XL_Unpacked",
    ),
    "DW8XL": GameSchema(
        game_id="DW8XL",
        display_name="Dynasty Warriors 8 XL",
        containers=("LINKDATA0.BIN", "LINKDATA1.BIN", "LINKDATA2.BIN", "LINKDATA3.BIN"),
        idx_files=("LINKDATA.IDX",),
        unpack_folder="DW8XL_Unpacked",
        field_size=4,
        raw_variables=(
            "Offset",
            "Unused_00",
            "Original_Size",
            "Unused_01",
            "Compressed_Size",
            "Unused_02",
            "Compression_Marker",
            "Unused_03",
        ),
    ),
    "DW8E": GameSchema(
        game_id="DW8E",
        display_name="Dynasty Warriors 8 Empires",
        containers=("LINKDATA0.BIN",),
        idx_files=("LINKDATA.IDX",),
        unpack_folder="DW8E_Unpacked",
    ),
    "WO3": GameSchema(
        game_id="WO3",
        display_name="Warriors Orochi 3",
        containers=("LINKFILE_000.BIN", "LINKFILE_001.BIN", "LINKFILE_002.BIN", "LINKFILE_003.BIN", "LINKFILE_CHS.BIN", "LINKFILE_CHT.BIN", "LINKFILE_ENG.BIN", "LINKFILE_JPN.BIN"),
        idx_files=("LINKIDX_000.BIN", "LINKIDX_001.BIN", "LINKIDX_002.BIN", "LINKIDX_003.BIN", "LINKIDX_CHS.BIN", "LINKIDX_CHT.BIN", "LINKIDX_ENG.BIN", "LINKIDX_JPN.BIN"),
        unpack_folder="WO3_Unpacked",
    ),
    "TK": GameSchema(
        game_id="TK",
        display_name="Toukiden Kiwami",
        containers=("LINKDATA0.BIN", "LINKDATA1.BIN", "LINKDATA2.BIN", "LINKDATA3.BIN"),
        idx_files=("LINKDATA0.IDX", "LINKDATA1.IDX", "LINKDATA2.IDX", "LINKDATA3.IDX"),
        unpack_folder="TK_Unpacked",
    ),
    "BN": GameSchema(
        game_id="BN",
        display_name="Bladestorm Nightmare",
        containers=("LINKDATA0.BIN", "LINKDATA1.BIN", "LINKDATA2.BIN"),
        idx_files=("LINKDATA0.IDX", "LINKDATA1.IDX", "LINKDATA2.IDX"),
        unpack_folder="BN_Unpacked",
    ),
    "WAS": GameSchema(
        game_id="WAS",
        display_name="Warriors All Stars",
        containers=("LINKDATA.BIN",),
        idx_files=("LINKDATA.IDX",),
        unpack_folder="WAS_Unpacked",
    ),
}


DW8XL_PLAYABLE_PRIMARY_FIELDS: Tuple[Tuple[str, int], ...] = (
    ("Gender", 2),
    ("Attack", 2),
    ("Max Attack", 2),
    ("Defense", 2),
    ("Max Defense", 2),
    ("HP", 2),
    ("Max HP", 2),
    ("Unknown 1", 2),
    ("Unknown 2", 2),
    ("Unknown 3", 2),
    ("Faction", 2),
    ("Unknown 4", 2),
    ("Unknown 5", 1),
    ("Unknown 6", 1),
    ("Dash", 1),
    ("Dive", 1),
    ("Shadow Sprint", 1),
    ("Whirlwind", 1),
    ("Unknown 7", 1),
) + tuple((f"Unknown {index}", 2) for index in range(8, 26))

DW8E_PLAYABLE_PRIMARY_FIELDS: Tuple[Tuple[str, int], ...] = (
    ("Gender", 2),
    ("Attack", 2),
    ("Max Attack", 2),
    ("Defense", 2),
    ("Max Defense", 2),
    ("HP", 2),
    ("Max HP", 2),
    ("Unknown 1", 2),
    ("Unknown 2", 2),
    ("Unknown 3", 2),
    ("Faction", 2),
    ("Unknown 4", 2),
    ("Unknown 5", 1),
    ("Unknown 6", 1),
    ("Dash", 1),
    ("Dive", 1),
    ("Shadow Sprint", 1),
    ("Whirlwind", 1),
    ("Unknown 7", 1),
) + tuple((f"Unknown {index}", 2) for index in range(8, 26))

DW8E_PLAYABLE_SECONDARY_FIELDS: Tuple[Tuple[str, int], ...] = tuple((f"Outfit Flag {index:03d}", 1) for index in range(1, 66))

DW8XL_PLAYABLE_OUTFIT_FIELDS: Tuple[Tuple[str, int], ...] = (("Outfit Category", 1),) + tuple((f"Outfit {index:02d}", 1) for index in range(1, 49))

WO3_PLAYABLE_PRIMARY_FIELDS: Tuple[Tuple[str, int], ...] = (
    ("Name", 2),
    ("Gender", 2),
    ("Unknown ID 1", 2),
    ("Unknown ID 2", 2),
    ("Param 1", 2),
    ("Life", 2),
    ("Param 2", 2),
    ("Musou", 2),
    ("Param 3", 2),
    ("Attack", 2),
    ("Param 4", 2),
    ("Defense", 2),
    ("Speed 1?", 2),
    ("Speed 2?", 2),
    ("Jump Height", 2),
    ("Faction", 2),
    ("Param 7", 2),
    ("Param 8", 2),
    ("Unknown 1", 2),
    ("Unknown 2", 2),
) + tuple((f"Param {index}", 2) for index in range(9, 34)) + (
    ("Attack Category", 2),
    ("Team Ability 1", 2),
    ("Team Ability 2", 2),
) + tuple((f"Param {index}", 2) for index in range(34, 66))

DW7XL_PLAYABLE_PRIMARY_FIELDS: Tuple[Tuple[str, int], ...] = (
    ("Name ID", 2),
    ("Gender", 2),
    ("Unknown ID 1", 2),
    ("Unknown ID 2", 2),
    ("Max HP", 2),
    ("HP", 2),
    ("Max Musou?", 2),
    ("Musou?", 2),
    ("Max Attack", 2),
    ("Attack", 2),
    ("Max Defense", 2),
    ("Defense", 2),
    ("Power", 2),
    ("Speed", 2),
) + tuple((f"Unknown {index}", 2) for index in range(1, 46)) + (
    ("Unknown 46", 1),
    ("Unknown 47", 1),
) + tuple((f"Unknown {index}", 2) for index in range(48, 52)) + tuple((f"Unknown {index}", 1) for index in range(52, 72))

DW7XL_NPC_FIELDS: Tuple[Tuple[str, int], ...] = (
    ("Name ID", 2),
    ("Unknown 1", 2),
    ("Voice ID", 2),
    ("Model ID", 2),
    ("Unknown 2", 1),
    ("Unknown 3", 1),
    ("Unknown 4", 1),
    ("Unknown 5", 1),
    ("Unknown 6", 1),
    ("Unknown 7", 1),
    ("Weapon", 2),
    ("Unknown 8", 2),
) + tuple((f"Param {index}", 2) for index in range(1, 14)) + (
    ("Unknown 9", 1),
    ("Unknown 10", 1),
    ("Unknown 11", 1),
    ("Unknown 12", 1),
    ("Unknown 13", 1),
    ("Unknown 14", 1),
)

DW8XL_NPC_FIELDS: Tuple[Tuple[str, int], ...] = (
    ("Name ID", 2),
    ("Unknown", 2),
    ("Voice ID", 2),
    ("Model ID", 2),
    ("Unknown 1", 1),
    ("Unknown 2", 1),
    ("Unknown 3", 1),
    ("Unknown 4", 1),
    ("Unknown 5", 1),
    ("Unknown 6", 1),
    ("Unknown 7", 2),
    ("Unknown 8", 2),
    ("Weapon", 2),
    ("Unknown 9", 2),
    ("Unknown 10", 2),
    ("Unknown 11", 2),
    ("Unknown 12", 2),
    ("Jump Height", 2),
    ("Speed", 2),
    ("Unknown 13", 2),
    ("Unknown 14", 2),
    ("Unknown 15", 1),
    ("Unknown 16", 1),
    ("Set Animal", 1),
    ("Unknown 17", 1),
    ("Faction", 1),
    ("Unknown 18", 1),
    ("Unknown 19", 2),
    ("Unknown 20", 1),
    ("Unknown 21", 2),
)

DW8E_NPC_FIELDS: Tuple[Tuple[str, int], ...] = (
    ("Name ID", 2),
    ("Unknown 1", 2),
    ("Voice ID", 2),
    ("Model ID", 2),
    ("Unknown 2", 1),
    ("Unknown 3", 1),
    ("Unknown 4", 1),
    ("Unknown 5", 1),
    ("Unknown 6", 1),
    ("Unknown 7", 1),
    ("Unknown 8", 2),
    ("Unknown 9", 2),
) + tuple((f"Param {index}", 2) for index in range(1, 17)) + (
    ("Unknown 10", 2),
) + tuple((f"Param {index}", 1) for index in range(17, 25)) + (
    ("AI Level?", 2),
) + (
    ("Param 25", 1),
    ("Param 26", 1),
    ("Param 27", 2),
) + tuple((f"Param {index}", 1) for index in range(28, 54))

WO3_NPC_FIELDS: Tuple[Tuple[str, int], ...] = (
    ("Name", 2),
    ("Unknown 1", 1),
    ("Unknown 2", 1),
    ("Voice ID", 2),
    ("Model ID", 2),
    ("Moveset", 2),
    ("Unknown 6", 1),
    ("Unknown 7", 1),
    ("Unknown 8", 1),
    ("Unknown 9", 1),
    ("Life", 2),
    ("Unknown 10", 1),
    ("Unknown 11", 1),
    ("Unknown 12", 1),
    ("Unknown 13", 1),
    ("Unknown 14", 1),
    ("Unknown 15", 1),
    ("Param 1", 2),
    ("Param 2", 2),
    ("Jump", 2),
    ("Speed", 2),
    ("Unknown 16", 1),
    ("Unknown 17", 1),
    ("AI Level", 2),
    ("AI Related ?", 1),
    ("AI Type", 1),
    ("Unknown 18", 1),
    ("Weapon ID", 2),
    ("Unknown 19", 1),
)

DW8XL_WEAPON_FIELDS: Tuple[Tuple[str, int], ...] = (
    ("Unknown 1", 2),
    ("Level", 1),
    ("Unknown 2", 1),
    ("Attack", 1),
    ("Unknown 3", 1),
    ("Cost", 4),
    ("Unknown 4", 2),
    ("Unknown 5", 2),
    ("Element 1", 1),
    ("Element 1 Level", 1),
    ("Element 2", 1),
    ("Element 2 Level", 1),
    ("Element 3", 1),
    ("Element 3 Level", 1),
    ("Element 4", 1),
    ("Element 4 Level", 1),
    ("Element 5", 1),
    ("Element 5 Level", 1),
    ("Element 6", 1),
    ("Element 6 Level", 1),
    ("Unknown 6", 1),
    ("Unknown 7", 1),
    ("Unknown 8", 1),
    ("Unknown 9", 1),
    ("Unknown 10", 1),
    ("Unknown 11", 1),
    ("Unknown 12", 2),
    ("Unknown 13", 1),
)

WO3_WEAPON_FIELDS: Tuple[Tuple[str, int], ...] = (
    ("Unknown 1", 1),
    ("Unknown 2", 1),
    ("Unknown 3", 1),
    ("Star Rank", 1),
    ("Attack", 2),
    ("Cost", 2),
    ("Unknown 4", 1),
    ("Unknown 5", 1),
    ("Weapon Image", 2),
    ("Unknown 6", 1),
    ("Unknown 7", 1),
    ("Unknown 8", 1),
    ("Unknown 9", 1),
    ("Unknown 10", 1),
    ("Unknown 11", 1),
)

DW7XL_PLAYABLES = OfficerEditorSchema(
    game_id="DW7XL",
    display_name="Dynasty Warriors 7 XL",
    officer_count=92,
    officer_names=(),
    name_list_path=os.path.join(PROJECT_ROOT, "Aldnoah_Logic", "dw7xl_doc", "dw7xl_names.txt"),
    primary_section=BinaryRecordSectionSchema(
        file_label="001.xl",
        file_path=os.path.join(PROJECT_ROOT, "DW7XL_Unpacked", "Pack_01", "entry_00000", "001.xl"),
        export_dir=os.path.join(PROJECT_ROOT, "DW7XL_Officer_Edits", "Pack_01", "entry_00000"),
        file_name="001.xl",
        offset=0x64,
        record_size=148,
        fields=DW7XL_PLAYABLE_PRIMARY_FIELDS,
        section_title="001.xl Core Data",
        section_subtitle="Mapped playable officer fields from the DW7XL officer blocks.",
        columns=2,
        hex_field_prefixes=("Unknown",),
    ),
    hero_star_seed=881,
    hero_star_count=44,
    constellation_star_seed=937,
    constellation_star_count=80,
    constellation_arms=10,
)

DW8XL_PLAYABLES = OfficerEditorSchema(
    game_id="DW8XL",
    display_name="Dynasty Warriors 8 XL",
    officer_count=100,
    officer_names=tuple(section_1_names[:100]),
    primary_section=BinaryRecordSectionSchema(
        file_label="001.xl",
        file_path=os.path.join(PROJECT_ROOT, "DW8XL_Unpacked", "Pack_00", "entry_00000", "001.xl"),
        export_dir=os.path.join(PROJECT_ROOT, "DW8XL_Officer_Edits", "Pack_00", "entry_00000"),
        file_name="001.xl",
        offset=0x9C,
        record_size=167,
        fields=DW8XL_PLAYABLE_PRIMARY_FIELDS,
        section_title="001.xl Core Data",
        section_subtitle="Mapped playable-officer fields from the main officer block.",
        toggle_names=tuple(f"Flag {index:03d}" for index in range(1, 101)),
        toggle_title="001.xl Flags 1-100",
        toggle_subtitle="Untoggled writes 00 and toggled writes 01.",
        toggle_columns=5,
    ),
    secondary_section=BinaryRecordSectionSchema(
        file_label="002.xl",
        file_path=os.path.join(PROJECT_ROOT, "DW8XL_Unpacked", "Pack_00", "entry_00000", "002.xl"),
        export_dir=os.path.join(PROJECT_ROOT, "DW8XL_Officer_Edits", "Pack_00", "entry_00000"),
        file_name="002.xl",
        offset=0x44,
        record_size=49,
        fields=DW8XL_PLAYABLE_OUTFIT_FIELDS,
        section_title="002.xl Outfit Data",
        section_subtitle="Outfit Category plus all 48 outfit bytes.",
        columns=4,
        hex_field_prefixes=(),
    ),
    hero_star_seed=887,
    hero_star_count=46,
    constellation_star_seed=941,
    constellation_star_count=82,
    constellation_arms=10,
)

DW8E_PLAYABLES = OfficerEditorSchema(
    game_id="DW8E",
    display_name="Dynasty Warriors 8 Empires",
    officer_count=100,
    officer_names=(),
    name_list_path=os.path.join(PROJECT_ROOT, "Aldnoah_Logic", "dw8e_doc", "dw8e_unit_names.txt"),
    primary_section=BinaryRecordSectionSchema(
        file_label="001.xl",
        file_path=os.path.join(PROJECT_ROOT, "DW8E_Unpacked", "Pack_00", "entry_00000", "001.xl"),
        export_dir=os.path.join(PROJECT_ROOT, "DW8E_Officer_Edits", "Pack_00", "entry_00000"),
        file_name="001.xl",
        offset=0x9C,
        record_size=167,
        fields=DW8E_PLAYABLE_PRIMARY_FIELDS,
        section_title="001.xl Core Data",
        section_subtitle="Mapped playable-officer fields from the DW8E main officer block.",
        toggle_names=tuple(f"Flag {index:03d}" for index in range(1, 101)),
        toggle_title="001.xl Flags 1-100",
        toggle_subtitle="Untoggled writes 00 and toggled writes 01.",
        toggle_columns=5,
        hex_field_prefixes=("Unknown",),
    ),
    secondary_section=BinaryRecordSectionSchema(
        file_label="002.xl",
        file_path=os.path.join(PROJECT_ROOT, "DW8E_Unpacked", "Pack_00", "entry_00000", "002.xl"),
        export_dir=os.path.join(PROJECT_ROOT, "DW8E_Officer_Edits", "Pack_00", "entry_00000"),
        file_name="002.xl",
        offset=0x54,
        record_size=65,
        fields=DW8E_PLAYABLE_SECONDARY_FIELDS,
        section_title="002.xl Outfit Flags",
        section_subtitle="All 65 outfit-flag bytes from the DW8E secondary officer block.",
        columns=5,
        hex_field_prefixes=("Outfit Flag",),
    ),
    hero_star_seed=889,
    hero_star_count=46,
    constellation_star_seed=943,
    constellation_star_count=84,
    constellation_arms=10,
)

WO3_PLAYABLES = OfficerEditorSchema(
    game_id="WO3",
    display_name="Warriors Orochi 3",
    officer_count=150,
    officer_names=(),
    name_list_path=os.path.join(PROJECT_ROOT, "Aldnoah_Logic", "wo3_doc", "wo3_names.txt"),
    primary_section=BinaryRecordSectionSchema(
        file_label="002.XL",
        file_path=os.path.join(PROJECT_ROOT, "WO3_Unpacked", "Pack_00", "entry_00032", "002.XL"),
        export_dir=os.path.join(PROJECT_ROOT, "WO3_Officer_Edits", "Pack_00", "entry_00032"),
        file_name="002.XL",
        offset=0x60,
        record_size=160,
        fields=WO3_PLAYABLE_PRIMARY_FIELDS,
        section_title="002.XL Core Data",
        section_subtitle="Mapped playable officer fields from the WO3 officer blocks.",
        columns=2,
        hex_field_prefixes=("Unknown", "Param"),
    ),
    hero_star_seed=893,
    hero_star_count=46,
    constellation_star_seed=947,
    constellation_star_count=86,
    constellation_arms=12,
)

DW7XL_NPC = NpcEditorSchema(
    game_id="DW7XL",
    display_name="Dynasty Warriors 7 XL",
    npc_count=1098,
    section=BinaryRecordSectionSchema(
        file_label="000.xl",
        file_path=os.path.join(PROJECT_ROOT, "DW7XL_Unpacked", "Pack_01", "entry_00000", "000.xl"),
        export_dir=os.path.join(PROJECT_ROOT, "DW7XL_Unit_Edits", "Pack_01", "entry_00000"),
        file_name="000.xl",
        offset=0x2F,
        record_size=50,
        fields=DW7XL_NPC_FIELDS,
        section_title="000.xl Core Data",
        section_subtitle="Mapped DW7XL fields from the unit blocks.",
        columns=2,
        hex_field_prefixes=("Unknown", "Param"),
    ),
    placeholder_prefix="Unit",
    name_field="Name ID",
    name_list_path=os.path.join(PROJECT_ROOT, "Aldnoah_Logic", "dw7xl_doc", "dw7xl_names.txt"),
    hero_star_seed=901,
    hero_star_count=46,
    constellation_star_seed=949,
    constellation_star_count=90,
    constellation_arms=18,
)

DW8XL_NPC = NpcEditorSchema(
    game_id="DW8XL",
    display_name="Dynasty Warriors 8 XL",
    npc_count=1160,
    section=BinaryRecordSectionSchema(
        file_label="000.xl",
        file_path=os.path.join(PROJECT_ROOT, "DW8XL_Unpacked", "Pack_00", "entry_00000", "000.xl"),
        export_dir=os.path.join(PROJECT_ROOT, "DW8XL_Unit_Edits", "Pack_00", "entry_00000"),
        file_name="000.xl",
        offset=0x50,
        record_size=79,
        fields=DW8XL_NPC_FIELDS,
        section_title="000.xl Core Data",
        section_subtitle="Mapped DW8XL fields from the unit blocks.",
        columns=2,
        toggle_names=tuple(f"Flag {index:02d}" for index in range(1, 33)),
        toggle_title="000.xl Flags 1-32",
        toggle_subtitle="Untoggled writes 00 and toggled writes 01.",
        toggle_columns=4,
        hex_field_prefixes=("Unknown",),
    ),
    placeholder_prefix="Unit",
    name_field="Name ID",
    hero_star_seed=905,
    hero_star_count=48,
    constellation_star_seed=953,
    constellation_star_count=90,
    constellation_arms=20,
)

DW8E_NPC = NpcEditorSchema(
    game_id="DW8E",
    display_name="Dynasty Warriors 8 Empires",
    npc_count=2360,
    section=BinaryRecordSectionSchema(
        file_label="000.xl",
        file_path=os.path.join(PROJECT_ROOT, "DW8E_Unpacked", "Pack_00", "entry_00000", "000.xl"),
        export_dir=os.path.join(PROJECT_ROOT, "DW8E_Unit_Edits", "Pack_00", "entry_00000"),
        file_name="000.xl",
        offset=0x58,
        record_size=92,
        fields=DW8E_NPC_FIELDS,
        section_title="000.xl Core Data",
        section_subtitle="Mapped DW8E fields from the shared unit block.",
        columns=2,
        hex_field_prefixes=("Unknown", "Param"),
    ),
    placeholder_prefix="Unit",
    name_field="Name ID",
    name_list_path=os.path.join(PROJECT_ROOT, "Aldnoah_Logic", "dw8e_doc", "dw8e_unit_names.txt"),
    hero_star_seed=907,
    hero_star_count=50,
    constellation_star_seed=955,
    constellation_star_count=92,
    constellation_arms=24,
)

WO3_NPC = NpcEditorSchema(
    game_id="WO3",
    display_name="Warriors Orochi 3",
    npc_count=2206,
    section=BinaryRecordSectionSchema(
        file_label="000.XL",
        file_path=os.path.join(PROJECT_ROOT, "WO3_Unpacked", "Pack_00", "entry_00032", "000.XL"),
        export_dir=os.path.join(PROJECT_ROOT, "WO3_Unit_Edits", "Pack_00", "entry_00032"),
        file_name="000.XL",
        offset=0x26,
        record_size=40,
        fields=WO3_NPC_FIELDS,
        section_title="000.XL Core Data",
        section_subtitle="Mapped WO3 unit / NPC fields from the shared unit block.",
        columns=2,
        hex_field_prefixes=("Unknown", "Param"),
    ),
    placeholder_prefix="Unit",
    name_field="Name",
    name_list_path=os.path.join(PROJECT_ROOT, "Aldnoah_Logic", "wo3_doc", "wo3_names.txt"),
    voice_map_path=os.path.join(PROJECT_ROOT, "Aldnoah_Logic", "wo3_doc", "WO3DE_Voices.txt"),
    model_map_path=os.path.join(PROJECT_ROOT, "Aldnoah_Logic", "wo3_doc", "WO3DE_Models.txt"),
    moveset_map_path=os.path.join(PROJECT_ROOT, "Aldnoah_Logic", "wo3_doc", "WO3DE_Moveset.txt"),
    hero_star_seed=909,
    hero_star_count=52,
    constellation_star_seed=957,
    constellation_star_count=94,
    constellation_arms=28,
)

DW8XL_WEAPONS = WeaponEditorSchema(
    game_id="DW8XL",
    display_name="Dynasty Warriors 8 XL",
    weapon_count=2000,
    section=BinaryRecordSectionSchema(
        file_label="004.xl",
        file_path=os.path.join(PROJECT_ROOT, "DW8XL_Unpacked", "Pack_00", "entry_00000", "004.xl"),
        export_dir=os.path.join(PROJECT_ROOT, "DW8XL_Weapon_Edits", "Pack_00", "entry_00000"),
        file_name="004.xl",
        offset=0x30,
        record_size=43,
        fields=DW8XL_WEAPON_FIELDS,
        section_title="004.xl Core Data",
        section_subtitle="Mapped weapon field data.",
        columns=2,
        toggle_names=tuple(f"Flag {index:02d}" for index in range(1, 9)),
        toggle_title="004.xl Flags 1-8",
        toggle_subtitle="Untoggled writes 00 and toggled writes 01.",
        toggle_columns=4,
        hex_field_prefixes=("Unknown",),
    ),
    weapon_names=tuple(DW8XL_WEAPON_NAMES.get(index, "") for index in range(2000)),
    hero_star_seed=921,
    hero_star_count=50,
    constellation_star_seed=983,
    constellation_star_count=96,
    constellation_arms=25,
)

WO3_WEAPONS = WeaponEditorSchema(
    game_id="WO3",
    display_name="Warriors Orochi 3",
    weapon_count=1400,
    section=BinaryRecordSectionSchema(
        file_label="003.xl",
        file_path=os.path.join(PROJECT_ROOT, "WO3_Unpacked", "Pack_00", "entry_00032", "003.xl"),
        export_dir=os.path.join(PROJECT_ROOT, "WO3_Weapon_Edits", "Pack_00", "entry_00032"),
        file_name="003.xl",
        offset=0x1A,
        record_size=18,
        fields=WO3_WEAPON_FIELDS,
        section_title="003.xl Core Data",
        section_subtitle="Mapped WO3 weapon field data.",
        columns=2,
        hex_field_prefixes=("Unknown",),
    ),
    weapon_names=(),
    hero_star_seed=925,
    hero_star_count=48,
    constellation_star_seed=989,
    constellation_star_count=94,
    constellation_arms=22,
)

OFFICER_EDITOR_SCHEMAS: Dict[str, OfficerEditorSchema] = {
    "DW7XL": DW7XL_PLAYABLES,
    "DW8XL": DW8XL_PLAYABLES,
    "DW8E": DW8E_PLAYABLES,
    "WO3": WO3_PLAYABLES,
}

NPC_EDITOR_SCHEMAS: Dict[str, NpcEditorSchema] = {
    "DW7XL": DW7XL_NPC,
    "DW8XL": DW8XL_NPC,
    "DW8E": DW8E_NPC,
    "WO3": WO3_NPC,
}

WEAPON_EDITOR_SCHEMAS: Dict[str, WeaponEditorSchema] = {
    "DW8XL": DW8XL_WEAPONS,
    "WO3": WO3_WEAPONS,
}


EXT4 = {
    b"GT1G": ".g1t",
    b"_M1G": ".g1m",
    b"_S1G": ".g1s",
    b"_S2G": ".g2s",
    b"ME1G": ".g1em",
    b"_E1G": ".g1e",
    b"_A1G": ".g1a",
    b"_A2G": ".g2a",
    b"XF1G": ".g1fx",
    b"OC1G": ".g1c",
    b"_L1G": ".g1l",
    b"_N1G": ".g1n",
    b"_H1G": ".g1h",
    b"SV1G": ".g1vs",
    b"LCSK": ".kscl",
    b"TLSK": ".kslt",
    b"KTSR": ".ktsl2stbin",
    b"KTSC": ".ktsl2asbin",
    b"KTSS": ".ktss",
    b"KOVS": ".kvs",
    b"_SPK": ".postfx",
    b"_OLS": ".sebin",
    b"OggS": ".ogg",
    b"RIFF": ".riff",
    b"1DHW": ".sed",
    b"_HBW": ".wbh",
    b"_DBW": ".wbd",
    b"KPMG": ".gmpk",
    b"KPML": ".lmpk",
    b"KPAG": ".gapk",
    b"KPEG": ".gepk",
    b"0KPB": ".bpk",
    b"KPTR": ".rtrpk",
    b"KLMD": ".mdlk",
    b"RLDM": ".mdlpack",
    b"TLDM": ".mdltexpack",
    b"GRAX": ".exarg",
    b"RFFE": ".effectpack",
    b"DAEH": ".exhead",
    b"RRRT": ".ktfkpack",
    b"RLOC": ".colpack",
    b"APDT": ".tdpack",
    b"_DRK": ".rdb",
    b"IDRK": ".rdb.bin",
    b"PDRK": ".fdata",
    b"_RNK": ".name",
    b"IRNK": ".name.bin",
    b"_DOK": ".kidsobjdb",
    b"IDOK": ".kidsobjdb.bin",
    b"RDOK": ".kidsobjdb.bin",
    b"MDLS": ".mdls",
    b"DXBC": ".dxbc",
    b"FP1G": ".fp1g",
    b"HWYX": ".hwyx",
    b"SCM_": ".scm",
    b"DLV0": ".dlv0",
    b"DLV4": ".dlv4",
    b"SV00": ".sv00",
    b"SV01": ".sv01",
    b"SV02": ".sv02",
    b"SV03": ".sv03",
    b"SV20": ".sv20",
    b"SV30": ".sv30",
    b"SV40": ".sv40",
    b"SV41": ".sv41",
    b"Act_": ".act",
    b"ET00": ".et00",
    b"ET01": ".et01",
    b"ET02": ".et02",
    b"ET03": ".et03",
    b"FT02": ".ft02",
    b"SARC": ".sarc",
    b"CRAE": ".elixir",
    b"SPKG": ".spkg",
    b"SCEN": ".scene",
    b"KPS3": ".shaderpack",
    b"QGWS": ".swg",
    b"EVIR": ".river",
    b"BGIR": ".rig",
    b"RTRE": ".ertr",
    b"DATD": ".datd",
    b"D0CL": ".lcd0",
    b"HDDB": ".hdb",
    b"RTXE": ".extra",
    b"LLOC": ".coll",
    b"ONUN": ".nuno",
    b"VNUN": ".nunv",
    b"SNUN": ".nuns",
    b"TFOS": ".soft",
    b"RIAH": ".hair",
    b"TNOC": ".cont",
    b"pkgi": ".pkginfo",
    b"DDS ": ".dds",
    b"char": ".chardata",
    b"clip": ".clip",
    b"body": ".bodybase",
    b"MSBP": ".material",
    b"tdpa": ".tdpack",
    b"HIUB": ".hiub",
    b"MDLK": ".MDLK",
    b"ipu2": ".ipu2",
    b"MESC": ".MESC",
    b"OFNI": ".INFO",
    b"_COK": ".KOC",
    b"SWGQ": ".SWGQ",
    b"DJBO": ".OBJD",
    b"WHD1": ".whd",
    b"DMIG": ".G1MD",
    b"LHSK": ".KSHL"
    
}

EXT3 = {
    b"XFT": ".xft",
    b"GT1": ".g1t",
}

EXT2 = {
    b"BM": ".bmp",
    b"XL": ".XL",
}


def get_game_schema(game_id: str) -> GameSchema:
    try:
        return GAME_SCHEMAS[game_id]
    except KeyError as exc:
        raise KeyError(f"Unknown Aldnoah game schema: {game_id}") from exc


def get_officer_editor_schema(game_id: str) -> OfficerEditorSchema:
    try:
        return OFFICER_EDITOR_SCHEMAS[game_id]
    except KeyError as exc:
        raise KeyError(f"Unknown officer editor schema for Aldnoah game: {game_id}") from exc


def get_npc_editor_schema(game_id: str) -> NpcEditorSchema:
    try:
        return NPC_EDITOR_SCHEMAS[game_id]
    except KeyError as exc:
        raise KeyError(f"Unknown NPC editor schema for Aldnoah game: {game_id}") from exc


def get_weapon_editor_schema(game_id: str) -> WeaponEditorSchema:
    try:
        return WEAPON_EDITOR_SCHEMAS[game_id]
    except KeyError as exc:
        raise KeyError(f"Unknown weapon editor schema for Aldnoah game: {game_id}") from exc


def schema_to_ref_dict(schema: GameSchema) -> dict:
    return {
        "Game": schema.display_name,
        "Containers": list(schema.containers),
        "IDX_Files": list(schema.idx_files),
        "Main_Unpack_Folder": schema.unpack_folder,
        "Endian": schema.endian,
        "Compression": schema.compression,
        "IDX_Chunk_Read": schema.idx_chunk_read,
        "Raw_Variables": list(schema.raw_variables),
        "Length_Per_Raw_Variables": schema.field_size,
        "Start_From_Offset": schema.start_from_offset,
        "Raw_Shift_Bits": schema.shift_bits,
        "Raw_Variables_To_Shift": list(schema.vars_to_shift),
    }


def setup_lilac_styles(root: tk.Misc) -> ttk.Style:
    """
    Create/refresh lilac ttk styles for the given Tk interpreter
    """
    style = ttk.Style(master=root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("Lilac.TFrame", background=LILAC)
    style.configure("Lilac.TLabel", background=LILAC, foreground="black", padding=0)
    style.map("Lilac.TLabel", background=[("active", LILAC)])
    return style


def apply_lilac_to_root(root: tk.Misc) -> None:
    """For plain tk widgets (tk.Frame/tk.Label/etc) that rely on root bg"""
    try:
        root.configure(bg=LILAC)
    except tk.TclError:
        pass


def lilac_label(*args, **kw) -> tk.Label:
    """
    Backward-compatible helper
    """
    if len(args) == 1:
        parent = args[0]
    elif len(args) >= 2:
        parent = args[1]
    else:
        raise TypeError("lilac_label requires at least (parent)")

    base = dict(bg=LILAC, bd=0, relief="flat", highlightthickness=0, takefocus=0)
    base.update(kw)
    return tk.Label(parent, **base)

stage_names_dict = {
    1: 'Escape from Luoyang',
    2: 'Battle of Hulao Gate',
    3: 'Battle of Yan Province',
    4: 'Battle of Xu Province',
    5: 'Imperial Escort',
    6: 'Battle of Wan Castle',
    7: 'Battle of Guandu',
    8: 'Battle of Mt. Bailang',
    9: 'Battle of Xinye',
    10: 'Battle of Chibi',
    11: 'Battle of Puyang',
    12: 'Battle of Xiapi',
    13: 'Battle of Tong Gate',
    14: 'Battle of Hefei',
    15: 'Battle of Mt. Dingjun',
    16: 'Battle of Fan Castle',
    17: 'Campaign for Jianye',
    18: 'Uprising at Xuchang',
    19: 'Pursuit at Nanjun',
    20: 'Battle of Baidi Castle',
    21: 'Battle of Xiangyang',
    22: 'Conquest of Wujun',
    23: 'The Little Conqueror in Peril',
    24: 'Battle of Nanjun',
    25: 'Battle of Jing Province',
    26: 'Battle of Liang Province',
    27: 'Defeat Gan Ji',
    28: 'Battle of Ruxukou',
    29: 'Battle of Yiling',
    30: 'Battle of Shiting',
    31: 'Battle of New Hefei Castle',
    32: 'Battle of Guangling',
    33: 'Pursuit at Shouchun',
    34: 'Defense of Jiangxia',
    35: 'Battle of Runan',
    36: 'Assault on Xuchang',
    37: 'Assault at Xinye',
    38: 'Yellow Turban Rebellion',
    39: 'Defense of Xu Province',
    40: 'Battle of Changban',
    41: 'Battle of Chengdu',
    42: 'Disturbance at Guandu',
    43: 'Battle of Tianshui',
    44: 'Battle of Jieting',
    45: 'Battle of the Wuzhang Plains',
    46: 'Battle of Chencang',
    47: 'Battle of Lukou',
    48: "Ambush at Chang'an",
    49: 'Invasion of Luoyang',
    50: 'Capture of Wei',
    51: 'Pacification of Nanzhong',
    52: 'Pursuit at the Wuzhang Plains',
    53: 'Battle of Mt. Xingshi',
    54: "Coup d'tat",
    55: 'East Gates Battle',
    56: 'Battle of Mt. Tielong',
    57: "Guanqiu Jian & Wen Qin's Rebellion",
    58: 'Battle of Xuchang',
    59: "Xiahou Ba's Journey",
    60: "Zhuge Dan's Rebellion",
    61: "Wei Emperor's Last Stand",
    62: 'Battle of Taoyang',
    63: 'Battle of Jiange',
    64: 'Capture of Chengdu',
    65: 'Battle of Jianye',
    66: 'Defend Chengdu',
    67: 'Final Conflict at Chibi',
    68: 'Defeat the Rebels',
    69: 'Yellow Turban Conflict',
    70: 'Eliminate Dong Zhuo',
    71: 'Chase at Hulao Gate',
    72: 'Xiapi Defensive Battle',
    73: 'Skirmish at Guandu',
    74: 'Nanzhong Rescue Mission',
    75: 'Phantoms of Xuchang',
    76: 'Rescue at Baidi Castle',
    77: 'TUTORIAL',
    78: "Battle of Yan Province - Xu Zhu's Forces",
    79: 'Battle of Mt. Bailang - Coalition Forces',
    80: "Battle of Puyang - Lu Bu's Forces",
    81: 'Battle of Tong Gate - Coalition Forces',
    82: 'Campaign for Jianye - Wu Forces',
    83: "Battle of Xiangyang - Liu Biao's Forces",
    84: "Conquest of Wujun - Liu Yao's Forces",
    85: "The Little Conqueror in Peril - Cao Cao's Forces",
    86: "Battle of Nanjun - Cao Cao's Forces",
    87: "Battle of Jing Province - Liu Bei's Forces",
    88: 'Battle of Liang Province - Rebel Forces',
    89: 'Battle of Ruxukou - Wei Forces',
    90: 'Battle of Shiting - Wei Forces',
    91: 'Battle of New Hefei Castle - Wei Forces',
    92: 'Battle of Guangling - Wei Forces',
    93: 'Defense of Jiangxia - Wei Forces',
    94: 'Battle of Runan - Wei Forces',
    95: 'Assault on Xuchang - Wei Forces',
    96: "Battle of Chengdu - Liu Zhang's Forces",
    97: 'Battle of Tianshui - Wei Forces',
    98: 'Battle of Jieting - Wei Forces',
    99: 'Battle of Chencang - Wei Forces',
    100: 'Battle of Lukou - Wu Forces',
    101: "Ambush at Chang'an - Wei Forces",
    102: 'Invasion of Luoyang - Wei Forces',
    103: 'Capture of Wei - Wei Forces',
    104: "Battle of Xiangping - Gongsun Yuan's Forces",
    105: 'East Gates Battle - Wu Forces',
    106: 'Battle of Mt. Tielong - Shu Forces',
    107: "Guanqiu Jian & Wen Qin's Rebellion - Rebel Forces",
    108: 'Battle of Xuchang - Rebel Forces',
    109: "Battle of New Hefei Castle - Zhuge Ke's Forces",
    110: "Zhuge Dan's Rebellion - Zhuge Dan's Forces",
    111: 'Battle of Taoyang - Shu Forces',
    112: 'Battle of Jiange - Shu Forces',
    113: 'Battle of Chengdu - Shu Forces',
    114: 'Capture of Chengdu - Shu Forces',
    115: 'Battle of Jianye - Wu Forces',
    116: 'Defend Chengdu - Shu Forces',
    117: 'Final Conflict at Chibi - Coalition Forces',
    118: "Defeat the Rebels - Zhong Hui's Forces",
    119: 'Luoyang - Great Battle',
    120: 'Luoyang - Unconventional Battle',
    121: 'Luoyang - Skirmish',
    122: 'Luoyang - Duel',
    123: 'Luoyang - Mock Battle',
    124: 'Guandu - Great Battle',
    125: 'Guandu - Unconventional Battle',
    126: 'Guandu - Skirmish',
    127: 'Guandu - Duel',
    128: 'Guandu - Mock Battle',
    129: 'Chibi - Great Battle',
    130: 'Chibi - Unconventional Battle',
    131: 'Chibi - Skirmish',
    132: 'Chibi - Duel',
    133: 'Chibi - Mock Battle',
    134: 'Xiapi - Great Battle',
    135: 'Xiapi - Unconventional Battle',
    136: 'Xiapi - Skirmish',
    137: 'Xiapi - Duel',
    138: 'Xiapi - Mock Battle',
    139: 'Tong Gate - Great Battle',
    140: 'Tong Gate - Unconventional Battle',
    141: 'Tong Gate - Skirmish',
    142: 'Tong Gate - Duel',
    143: 'Tong Gate - Mock Battle',
    144: 'Hefei - Great Battle',
    145: 'Hefei - Unconventional Battle',
    146: 'Hefei - Skirmish',
    147: 'Hefei - Duel',
    148: 'Hefei - Mock Battle',
    149: 'Fan Castle - Great Battle',
    150: 'Fan Castle - Unconventional Battle',
    151: 'Fan Castle - Skirmish',
    152: 'Fan Castle - Duel',
    153: 'Fan Castle - Mock Battle',
    154: 'Jianye - Great Battle',
    155: 'Jianye - Unconventional Battle',
    156: 'Jianye - Skirmish',
    157: 'Jianye - Duel',
    158: 'Jianye - Mock Battle',
    159: 'Xuchang - Great Battle',
    160: 'Xuchang - Unconventional Battle',
    161: 'Xuchang - Skirmish',
    162: 'Xuchang - Duel',
    163: 'Xuchang - Mock Battle',
    164: 'Baidi Castle - Great Battle',
    165: 'Baidi Castle - Unconventional Battle',
    166: 'Baidi Castle - Skirmish',
    167: 'Baidi Castle - Duel',
    168: 'Baidi Castle - Mock Battle',
    169: 'Xiangyang - Great Battle',
    170: 'Xiangyang - Unconventional Battle',
    171: 'Xiangyang - Skirmish',
    172: 'Xiangyang - Duel',
    173: 'Xiangyang - Mock Battle',
    174: 'Wujun - Great Battle',
    175: 'Wujun - Unconventional Battle',
    176: 'Wujun - Skirmish',
    177: 'Wujun - Duel',
    178: 'Wujun - Mock Battle',
    179: 'Yiling - Great Battle',
    180: 'Yiling - Unconventional Battle',
    181: 'Yiling - Skirmish',
    182: 'Yiling - Duel',
    183: 'Yiling - Mock Battle',
    184: 'Guangling - Great Battle',
    185: 'Guangling - Unconventional Battle',
    186: 'Guangling - Skirmish',
    187: 'Guangling - Duel',
    188: 'Guangling - Mock Battle',
    189: 'Jiangxia - Great Battle',
    190: 'Jiangxia - Unconventional Battle',
    191: 'Jiangxia - Skirmish',
    192: 'Jiangxia - Duel',
    193: 'Jiangxia - Mock Battle',
    194: 'Yellow Turban Rebellion - Great Battle',
    195: 'Yellow Turban Rebellion - Unconventional Battle',
    196: 'Yellow Turban Rebellion - Skirmish',
    197: 'Yellow Turban Rebellion - Duel',
    198: 'Yellow Turban Rebellion - Mock Battle',
    199: 'Changban - Great Battle',
    200: 'Changban - Unconventional Battle',
    201: 'Changban - Skirmish',
    202: 'Changban - Duel',
    203: 'Changban - Mock Battle',
    204: 'Tianshui - Great Battle',
    205: 'Tianshui - Unconventional Battle',
    206: 'Tianshui - Skirmish',
    207: 'Tianshui - Duel',
    208: 'Tianshui - Mock Battle',
    209: 'Wuzhang Plains - Great Battle',
    210: 'Wuzhang Plains - Unconventional Battle',
    211: 'Wuzhang Plains - Skirmish',
    212: 'Wuzhang Plains - Duel',
    213: 'Wuzhang Plains - Mock Battle',
    214: "Chang'an - Great Battle",
    215: "Chang'an - Unconventional Battle",
    216: "Chang'an - Skirmish",
    217: "Chang'an - Duel",
    218: "Chang'an - Mock Battle",
    219: "Ten Eunuchs' Rebellion",
    220: 'Getaway from Hulao Gate',
    221: "Uprising at Chang'an",
    222: 'Capture of Puyang',
    223: 'Battle of Dingtao',
    224: 'Battle of Changshan',
    225: 'Assault on Xiapi',
    226: 'Battle of Shouchun',
    227: 'Battle of Xiaopei',
    228: 'Showdown at Xiapi',
    229: 'Invasion of Xu Province',
    230: 'Assault on Wujun',
    231: 'Clash at Guandu',
    232: "Recapture of Chang'an",
    233: 'Final Conflict at Guandu',
    234: "Defense of Chang'an",
    235: 'Mt. Dingjun Rescue Mission',
    236: 'Defense of Fan Castle',
    237: 'Pacification of Jing Province',
    238: 'Defense of Xinye',
    239: 'Battle of Zitong',
    240: 'Find the Beauties',
    241: 'Assault on Shouchun',
    242: 'Invasion of Runan',
    243: 'Assault on Xu Province',
    244: 'Pursuit at Yiling',
    245: 'Defense of Jiangling',
    246: 'Assault on Xiangyang',
    247: 'Battle of Lujiang',
    248: 'Chief Commander Face-off',
    249: 'Defeat Lu Bu',
    250: 'Clash at Changban',
    251: 'Escape from Jiangdong',
    252: 'Defense of Mt. Dingjun',
    253: 'Revenge at Yiling',
    254: "Defense of Yong'an",
    255: 'Final Conflict at Wuzhang Plains',
    256: 'Find Red Hare',
    257: 'Riot at Luoyang',
    258: 'Defense of Shangyong',
    259: 'Defense of New Hefei Castle',
    260: 'Escape from Chengdu',
    261: 'Pacification of Bashu',
    262: 'Battle of Shangyong',
    263: "Zhuge Dan's Secret Plan",
    264: 'Seek the Secret Ingredients',
    265: 'Runan Rescue Mission',
    266: 'Final Conflict at Hulao Gate',
    267: 'Ultimate Warrior Competition',
    268: 'Melee at Chibi',
    269: 'Nobility Face-off',
    270: 'Protect the Animals',
    271: "Ten Eunuchs' Rebellion - Government Forces",
    272: "Uprising at Chang'an - Dong Zhuo's Forces",
    273: "Battle of Dingtao - Cao Cao's Forces",
    274: 'Battle of Changshan - Coaltion Forces',
    275: "Assault on Xiapi - Liu Bei's Forces",
    276: "Battle of Shouchun - Yuan Shu's Forces",
    277: "Battle of Xiaopei - Liu Bei's Forces",
    278: "Invasion of Xu Province - Cao Cao's Forces",
    279: "Assault on Wujun - Sun Ce's Forces",
    280: "Clash at Guandu - Yuan Shao's Forces",
    281: "Recapture of Chang'an - Coalition Forces",
    282: "Final Conflict at Guandu - Yuan Shao's Forces",
    283: "Defense of Chang'an - Coalition Forces",
    284: 'Defense of Fan Castle - Coalition Forces',
    285: 'Pacification of Jing Province - Shu Forces',
    286: 'Defense of Xinye - Shu Forces',
    287: 'Battle of Zitong - Shu Forces',
    288: "Assault on Shouchun - Cao Cao's Forces",
    289: "Invasion of Runan - Cao Cao's Forces",
    290: "Assault on Xu Province - Liu Bei's Forces",
    291: "Defense of Jiangling - Cao Cao's Forces",
    292: "Assault on Xiangyang - Cao Cao's Forces",
    293: "Defeat Lu Bu - Lu Bu's Forces",
    294: "Clash at Changban - Cao Cao's Forces",
    295: "Defense of Yong'an - Wu Forces",
    296: 'Final Conflict at Wuzhang Plains - Wei Forces',
    297: "Riot at Luoyang - Cao Shuang's Forces",
    298: 'Defense of Shangyong - Shu Forces',
    299: 'Defense of New Hefei Castle - Wu Forces',
    300: "Pacification of Bashu - Zhong Hui's Forces",
    301: 'Battle of Shangyong - Shu Forces',
    302: "Zhuge Dan's Secret Plan - Wu Forces",
    303: "Runan Rescue Mission - Cao Cao's Forces",
    304: "Final Conflict at Hulao Gate - Yuan Shao's Forces",
    305: "Melee at Chibi - Sun Ce's Forces",
    306: 'Rampage',
    307: 'Bridge Melee',
    308: 'Speed Run',
    309: 'Arena',
    310: 'Inferno',
    311: "Battle of Hulao Gate - Cao Cao's Forces",
    312: "Battle of Yan Province - Cao Cao's Forces",
    313: "Battle of Mt. Bailang - Cao Cao's Forces",
    314: "Battle of Xinye - Cao Cao's Forces",
    315: "Battle of Chibi - Cao Cao's Forces",
    316: "Battle of Puyang - Cao Cao's Forces",
    317: "Battle of Tong Gate - Cao Cao's Forces",
    318: 'Battle of Hefei - Wei Forces',
    319: 'Battle of Mt. Dingjun - Wei Forces',
    320: 'Battle of Fan Castle - Wei Forces',
    321: 'Campaign for Jianye - Wei Forces',
    322: "Battle of Xiangyang - Sun Jian's Forces",
    323: "Conquest of Wujun - Sun Ce's Forces",
    324: "The Little Conqueror in Peril - Sun Ce's Forces",
    325: "Battle of Chibi - Sun Quan's Forces",
    326: "Battle of Nanjun - Sun Quan's Forces",
    327: "Battle of Jing Province - Sun Quan's Forces",
    328: 'Battle of Hefei - Wu Forces',
    329: 'Battle of Liang Province - Coalition Forces',
    330: 'Battle of Ruxukou - Wu Forces',
    331: 'Battle of Fan Castle - Wu Forces',
    332: 'Battle of Yiling - Wu Forces',
    333: 'Battle of Shiting - Wu Forces',
    334: 'Battle of New Hefei Castle - Wu Forces',
    335: 'Battle of Guangling - Wu Forces',
    336: 'Defense of Jiangxia - Wu Forces',
    337: 'Battle of Runan - Wu Forces',
    338: 'Assault on Xuchang - Wu Forces',
    339: "Battle of Hulao Gate - Liu Bei's Forces",
    340: "Battle of Xinye - Liu Bei's Forces",
    341: "Battle of Chibi - Liu Bei's Forces",
    342: "Battle of Chengdu - Liu Bei's Forces",
    343: 'Battle of Mt. Dingjun - Shu Forces',
    344: 'Battle of Fan Castle - Shu Forces',
    345: 'Battle of Yiling - Shu Forces',
    346: 'Battle of Tianshui - Shu Forces',
    347: 'Battle of Jieting - Shu Forces',
    348: 'Battle of Chencang - Shu Forces',
    349: 'Battle of Lukou - Shu Forces',
    350: "Ambush at Chang'an - Shu Forces",
    351: 'Invasion of Luoyang - Shu Forces',
    352: 'Capture of Wei - Shu Forces',
    353: "Battle of Xiangyang - Sima Yi's Forces",
    354: "East Gates Battle - Sima Zhao's Forces",
    355: "Battle of Mt. Tielong - Sima Zhao's Forces",
    356: "Guanqiu Jian & Wen Qin's Rebellion - Wei Forces",
    357: "Battle of Xuchang - Sima Zhao's Forces",
    358: "Battle of New Hefei Castle - Sima Shi's Forces",
    359: "Battle of Taoyang - Sima Zhao's Forces",
    360: "Battle of Jiange - Deng Ai's Forces",
    361: "Battle of Chengdu - Sima Zhao's Forces",
    362: "Capture of Chengdu - Sima Shi's Forces",
    363: "Battle of Jianye - Sima Zhao's Forces",
    364: "Defend Chengdu - Sima Shi's Forces",
    365: "Final Conflict at Chibi - Sima Shi's Forces",
    366: "Defeat the Rebels - Sima Yi's Forces"
}
