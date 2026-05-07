from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Set, Tuple


ORRERY_BG = "#0A0710"
ORRERY_BG_2 = "#120B1D"
REACTOR_CORE = "#F2D789"
NEBULA_DIM = "#211831"
CONSTELLATION_LINE = "#5E4A82"
ENABLED_CHAIN = "#D8B75E"
CONFLICT_TETHER = "#D95364"
DEPENDENCY_LINE = "#4BA3FF"
PATCH_LINE = "#9462D8"
SIGNAL_RING = "#6FCBFF"
LENS_BG = "#150F22"
LENS_PANEL = "#231735"
LENS_EDGE = "#C7A7F2"
LENS_GOLD = "#F0D37A"
TEXT = "#F7F1FF"
TEXT_MUTED = "#BAABD0"
TEXT_DARK = "#1D1429"

STAR_DISABLED_FILL = "#625B7A"
STAR_DISABLED_OUTLINE = "#8EA0B8"
STAR_ENABLED_FILL = "#FFF4CB"
STAR_ENABLED_OUTLINE = "#FFE38D"
STAR_ERROR_FILL = "#812A38"
STAR_ERROR_OUTLINE = "#FF6D7A"
STAR_SELECTED_FILL = "#FFFFFF"
STAR_SELECTED_OUTLINE = "#FFFFFF"
STAR_CONFLICT_OUTLINE = "#FF5367"
STAR_PACKAGE_FILL = "#D9C6FF"
STAR_INSTALLER_FILL = "#11101A"
COMET_TRAIL = "#7BD3FF"


SKY_MODE_META = {
    "overview": {
        "label": "Overview",
        "status": "All skies visible. The reactor holds every orbit in view.",
        "dim_others": False,
        "field": "#1A1128",
        "accent": "#A889F0",
        "zoom": 0.22,
    },
    "all": {
        "label": "Universal Sky",
        "status": "Universal sky expanded. Other sectors collapse into dim nebulae.",
        "dim_others": True,
        "field": "#17263B",
        "accent": "#6FCBFF",
        "zoom": 0.42,
    },
    "texture": {
        "label": "Texture Sky",
        "status": "Texture signal resolved. Visual payloads glow at the outer veil.",
        "dim_others": True,
        "field": "#132E38",
        "accent": "#5FD3C1",
        "zoom": 0.42,
    },
    "model": {
        "label": "Model Sky",
        "status": "Model orbit dive engaged. Dense bodies pull toward the center.",
        "dim_others": True,
        "field": "#221D32",
        "accent": "#D6D0E8",
        "zoom": 0.46,
    },
    "text": {
        "label": "Text Sky",
        "status": "Text sky resolved. Script fragments drift like thin constellations.",
        "dim_others": True,
        "field": "#18273A",
        "accent": "#8FB8FF",
        "zoom": 0.42,
    },
    "overhaul": {
        "label": "Overhaul Sky",
        "status": "Overhaul field unstable. Large packages burn red and gold.",
        "dim_others": True,
        "field": "#3A151B",
        "accent": "#F0B85E",
        "zoom": 0.44,
    },
    "misc": {
        "label": "Misc Sky",
        "status": "Misc debris belt folded open. Loose tools and odd payloads surface.",
        "dim_others": True,
        "field": "#241B2F",
        "accent": "#B8A1D9",
        "zoom": 0.42,
    },
}


@dataclass(frozen=True)
class OrreryLink:
    left: str
    right: str
    kind: str
    color: str
    width: int = 2


def signal_text_for_mod(mod) -> str:
    return " ".join(
        [
            getattr(mod, "filename", ""),
            getattr(mod, "display_name", ""),
            getattr(mod, "author", ""),
            getattr(mod, "version", ""),
            getattr(mod, "genre", ""),
            getattr(mod, "subgroup", ""),
            getattr(mod, "build_mode", ""),
        ]
    ).lower()


def signal_matches(mod, signal: str) -> bool:
    needle = (signal or "").strip().lower()
    if not needle:
        return True
    return needle in signal_text_for_mod(mod)


def mod_visual_state(mod, *, selected_filename: str = "", conflict_names: Set[str] | None = None, signal: str = "") -> dict:
    conflict_names = conflict_names or set()
    filename = getattr(mod, "filename", "")
    selected = bool(selected_filename and filename == selected_filename)
    parse_error = bool(getattr(mod, "parse_error", ""))
    enabled = bool(getattr(mod, "enabled", False))
    installer = filename.lower().endswith(".aldnoah")
    package = bool(getattr(mod, "file_count", 0) > 1) and not installer
    conflict = filename in conflict_names
    matched = signal_matches(mod, signal)

    if parse_error:
        fill = STAR_ERROR_FILL
        outline = STAR_ERROR_OUTLINE
    elif enabled:
        fill = STAR_ENABLED_FILL
        outline = STAR_ENABLED_OUTLINE
    elif package:
        fill = STAR_PACKAGE_FILL
        outline = "#B49BF0"
    else:
        fill = STAR_DISABLED_FILL
        outline = STAR_DISABLED_OUTLINE

    if installer:
        fill = STAR_INSTALLER_FILL
        outline = "#E8D7FF"
    if conflict:
        outline = STAR_CONFLICT_OUTLINE
    if selected:
        fill = STAR_SELECTED_FILL
        outline = STAR_SELECTED_OUTLINE

    return {
        "selected": selected,
        "parse_error": parse_error,
        "enabled": enabled,
        "package": package,
        "installer": installer,
        "conflict": conflict,
        "matched": matched,
        "fill": fill,
        "outline": outline,
        "alpha_dim": bool(signal and not matched),
    }


def build_conflict_links(mod_targets: Dict[str, Set[Tuple[int, int]]]) -> Tuple[List[OrreryLink], Set[str]]:
    by_target: Dict[Tuple[int, int], List[str]] = {}
    for filename, targets in mod_targets.items():
        for target in targets:
            by_target.setdefault(target, []).append(filename)

    pair_counts: Dict[Tuple[str, str], int] = {}
    conflict_names: Set[str] = set()
    for names in by_target.values():
        unique = sorted(set(names))
        if len(unique) < 2:
            continue
        conflict_names.update(unique)
        for left_idx in range(len(unique)):
            for right_idx in range(left_idx + 1, len(unique)):
                pair = (unique[left_idx], unique[right_idx])
                pair_counts[pair] = pair_counts.get(pair, 0) + 1

    links = [
        OrreryLink(left, right, "conflict", CONFLICT_TETHER, width=2 + min(4, count // 2))
        for (left, right), count in sorted(pair_counts.items())
    ]
    return links, conflict_names


def find_target_collisions(
    filename: str,
    targets: Set[Tuple[int, int]],
    mod_targets: Dict[str, Set[Tuple[int, int]]],
    candidate_names: Iterable[str],
) -> Dict[str, Set[Tuple[int, int]]]:
    own_targets = set(targets or set())
    if not own_targets:
        return {}

    collisions: Dict[str, Set[Tuple[int, int]]] = {}
    for other in candidate_names:
        if not other or other == filename:
            continue
        shared = own_targets & set(mod_targets.get(other, set()))
        if shared:
            collisions[other] = shared
    return collisions


def build_contextual_conflict_links(
    mod_targets: Dict[str, Set[Tuple[int, int]]],
    enabled_names: Set[str],
    selected_filename: str = "",
) -> Tuple[List[OrreryLink], Set[str]]:
    enabled_names = set(enabled_names or set())
    selected_filename = selected_filename or ""
    pair_counts: Dict[Tuple[str, str], int] = {}
    conflict_names: Set[str] = set()

    def add_pair(left: str, right: str, count: int = 1):
        if not left or not right or left == right or count <= 0:
            return
        pair = tuple(sorted((left, right)))
        pair_counts[pair] = pair_counts.get(pair, 0) + count
        conflict_names.update(pair)

    by_target: Dict[Tuple[int, int], List[str]] = {}
    for filename in enabled_names:
        for target in mod_targets.get(filename, set()):
            by_target.setdefault(target, []).append(filename)

    for names in by_target.values():
        unique = sorted(set(names))
        if len(unique) < 2:
            continue
        for left_idx in range(len(unique)):
            for right_idx in range(left_idx + 1, len(unique)):
                add_pair(unique[left_idx], unique[right_idx])

    if selected_filename:
        selected_targets = set(mod_targets.get(selected_filename, set()))
        collisions = find_target_collisions(selected_filename, selected_targets, mod_targets, enabled_names)
        for other, shared in collisions.items():
            add_pair(selected_filename, other, len(shared))

    links = [
        OrreryLink(left, right, "conflict", CONFLICT_TETHER, width=2 + min(4, count // 2))
        for (left, right), count in sorted(pair_counts.items())
    ]
    return links, conflict_names


def enabled_chain_links(mods: Iterable) -> List[OrreryLink]:
    enabled = sorted(
        [getattr(mod, "filename", "") for mod in mods if getattr(mod, "enabled", False)],
        key=str.lower,
    )
    return [
        OrreryLink(enabled[idx], enabled[idx + 1], "enabled", ENABLED_CHAIN, width=2)
        for idx in range(len(enabled) - 1)
    ]
