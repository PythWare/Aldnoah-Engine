# Aldnoah_Logic/aldnoah_energy.py
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Dict, Tuple

LILAC = "#C8A2C8"


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


EXT4 = {
    b"GT1G": ".g1t",
    b"_M1G": ".g1m",
    b"_S2G": ".g1s",
    b"ME1G": ".g1em",
    b"_A1G": ".g1a",
    b"_A2G": ".g1a",
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
