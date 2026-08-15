# Aldnoah_Logic/aldnoah_merge.py
"""
Mod merging engine
"""
from __future__ import annotations

import os, shutil, tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .aldnoah_mod_manager import (
    ModFileEntry,
    ModParser,
    installer_payloads_to_entries,
    is_installer_filename,
)
from .aldnoah_installer import AldnoahInstallerReader
from .aldnoah_taildata import load_manifest
from .aldnoah_unpack import (
    looks_like_classic_split_zlib,
    looks_like_kshl_blob,
    looks_like_mdlk_blob,
    looks_like_split_zlib_pairtable_wrapper,
    read_rebuild_chunk,
    read_universal_subcontainer_layout,
    unpack_nested_resource,
)

# (idx_marker, entry_off)
Target = Tuple[int, int]

KIND_UNIQUE = "unique"
KIND_IDENTICAL = "identical"
KIND_SUBCONTAINER = "subcontainer"
KIND_LOOSE = "loose"
KIND_CONFLICT = "conflict"


def target_of(entry: ModFileEntry) -> Target:
    return (int(entry.tail.idx_marker), int(entry.tail.entry_off))


def describe_target(target: Target) -> str:
    marker, off = target
    return f"container {marker}, slot {off // 32}"


def looks_like_subcontainer(blob: bytes) -> bool:
    """Whether a payload has members that can be merged individually"""
    if not blob or len(blob) < 8:
        return False
    if blob[:4] == b"KOVS":
        return True
    return bool(
        looks_like_mdlk_blob(blob)
        or looks_like_kshl_blob(blob)
        or looks_like_split_zlib_pairtable_wrapper(blob)
        or looks_like_classic_split_zlib(blob)
        or read_universal_subcontainer_layout(blob) is not None
    )

@dataclass
class MergeSource:
    """One mod package taking part in the merge"""
    name: str
    path: str
    entries: List[ModFileEntry] = field(default_factory=list)

    @property
    def targets(self) -> set:
        return {target_of(e) for e in self.entries}

    def entry_for(self, target: Target) -> Optional[ModFileEntry]:
        for entry in self.entries:
            if target_of(entry) == target:
                return entry
        return None


def load_source(path: str) -> MergeSource:
    """
    Read a mod package into entries, reusing the readers the manager already uses

    Handles both the plain mod packages and the wizard installer format
    """
    name = os.path.basename(path)
    if is_installer_filename(name):
        package = AldnoahInstallerReader(path).read()
        payloads = list(getattr(package, "payloads", []) or [])
        _valid, entries, invalid = installer_payloads_to_entries(payloads)
        if invalid and not entries:
            raise ValueError(f"{name}: no usable payloads ({invalid[0]})")
        return MergeSource(name=name, path=path, entries=entries)

    parsed = ModParser(path).read(include_media=False)
    return MergeSource(name=name, path=path, entries=list(parsed.entries))

class BaseLibrary:
    """
    Original payloads, looked up by container slot

    Backed by the unpack folder and its taildata manifest, so the bytes here are
    in exactly the same form as the payloads inside a mod package
    """

    def __init__(self, game_id: str, root: str = "."):
        self.game_id = game_id
        self.root = root
        self.manifest = load_manifest(game_id, root)
        self.by_target: Dict[Target, str] = {}
        for key, record in self.manifest.files.items():
            try:
                target = (int(record["idx_marker"]), int(record["entry_off"]))
            except (KeyError, TypeError, ValueError):
                continue
            self.by_target[target] = key

    @property
    def available(self) -> bool:
        return bool(self.by_target)

    def payload_for(self, target: Target) -> Optional[bytes]:
        key = self.by_target.get(target)
        if not key:
            return None
        path = os.path.join(self.root, key.replace("/", os.sep))
        try:
            with open(path, "rb") as handle:
                return handle.read()
        except OSError:
            return None

@dataclass
class MemberMerge:
    merged: Optional[bytes]
    taken: Dict[str, List[str]] = field(default_factory=dict)
    conflicts: List[str] = field(default_factory=list)
    error: str = ""

SEQUENCE_DIFF_LIMIT = 4 * 1024 * 1024


def diff_regions(base: bytes, variant: bytes) -> Optional[List[Tuple[int, int, bytes]]]:
    """
    Where a variant departs from the original, as (start, end, replacement)
    """
    if base == variant:
        return []

    if len(base) == len(variant):
        regions: List[Tuple[int, int, bytes]] = []
        start = None
        for i, (a, b) in enumerate(zip(base, variant)):
            if a != b:
                if start is None:
                    start = i
            elif start is not None:
                regions.append((start, i, variant[start:i]))
                start = None
        if start is not None:
            regions.append((start, len(base), variant[start:]))
        return regions

    if max(len(base), len(variant)) > SEQUENCE_DIFF_LIMIT:
        return None

    from difflib import SequenceMatcher
    matcher = SequenceMatcher(None, base, variant, autojunk=False)
    regions = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            regions.append((i1, i2, variant[j1:j2]))
    return regions


def merge_bytes(base: bytes, variants: Sequence[Tuple[str, bytes]]) -> MemberMerge:
    """
    Three way merge of a loose file

    Each variant is diffed against the original, so AE knows which stretches it
    actually rewrote

    Stretches touched by one mod are applied, stretches two
    mods rewrote differently are a conflict because there is no finer structure
    left to separate them
    """
    changes: List[Tuple[int, int, bytes, str]] = []
    for name, blob in variants:
        regions = diff_regions(base, blob)
        if regions is None:
            return MemberMerge(None, error=f"{name} is too large to diff")
        for start, end, replacement in regions:
            changes.append((start, end, replacement, name))

    if not changes:
        return MemberMerge(base)

    changes.sort(key=lambda c: (c[0], c[1]))

    merged = bytearray()
    cursor = 0
    taken: Dict[str, List[str]] = {}
    conflicts: List[str] = []
    index = 0
    while index < len(changes):
        start, end, replacement, name = changes[index]

        group = [changes[index]]
        reach = end
        probe = index + 1
        while probe < len(changes) and changes[probe][0] < reach:
            group.append(changes[probe])
            reach = max(reach, changes[probe][1])
            probe += 1
        index = probe

        owners = {c[3] for c in group}
        distinct = {(c[0], c[1], c[2]) for c in group}
        if len(owners) > 1 and len(distinct) > 1:
            conflicts.append(f"bytes {start}..{reach}")
            continue

        if start < cursor:
            conflicts.append(f"bytes {start}..{reach}")
            continue

        merged += base[cursor:start]
        merged += replacement
        cursor = reach
        taken.setdefault(name, []).append(f"bytes {start}..{reach}")

    if conflicts:
        return MemberMerge(None, taken=taken, conflicts=conflicts)

    merged += base[cursor:]
    return MemberMerge(bytes(merged), taken=taken)


def read_members(work_dir: str, blob: bytes) -> Optional[Dict[str, bytes]]:
    """
    Explode a subcontainer into its members using the engine's own unpacker

    Returns member path (relative to the nested folder) -> bytes or None when
    the blob has no nested structure
    """
    holder = os.path.join(work_dir, "chunk.bin")
    with open(holder, "wb") as handle:
        handle.write(blob)
    try:
        if not unpack_nested_resource(holder, blob=blob):
            return None
    except Exception:
        return None

    nested = os.path.join(work_dir, "chunk")
    if not os.path.isdir(nested):
        return None

    members: Dict[str, bytes] = {}
    for dirpath, _dirs, files in os.walk(nested):
        for name in files:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, nested).replace("\\", "/")
            try:
                with open(full, "rb") as handle:
                    members[rel] = handle.read()
            except OSError:
                continue
    return members or None


def merge_subcontainer(base: bytes, variants: Sequence[Tuple[str, bytes]]) -> MemberMerge:
    """
    Combine several edits of one subcontainer, member by member

    Each variant is compared against the original so AE knows which members that
    mod actually touched, members touched by exactly one mod are taken from it
    
    members touched by more than one with differing content are conflicts
    """
    work = tempfile.mkdtemp(prefix="aldnoah_merge_")
    try:
        base_dir = os.path.join(work, "base")
        os.makedirs(base_dir)
        base_members = read_members(base_dir, base)
        if not base_members:
            return MemberMerge(None, error="original has no readable members")

        changed_by: Dict[str, List[Tuple[str, bytes]]] = {}
        for index, (name, blob) in enumerate(variants):
            var_dir = os.path.join(work, f"var{index}")
            os.makedirs(var_dir)
            members = read_members(var_dir, blob)
            if members is None:
                return MemberMerge(None, error=f"{name} has no readable members")
            for rel, data in members.items():
                if base_members.get(rel) != data:
                    changed_by.setdefault(rel, []).append((name, data))

        merged_members = dict(base_members)
        taken: Dict[str, List[str]] = {}
        conflicts: List[str] = []
        for rel, edits in changed_by.items():
            distinct = {data for _n, data in edits}
            if len(distinct) > 1:
                inner = merge_bytes(base_members[rel], edits)
                if inner.merged is None:
                    conflicts.append(rel)
                    continue
                merged_members[rel] = inner.merged
                for name in inner.taken:
                    taken.setdefault(name, []).append(rel)
                continue
            name, data = edits[0]
            merged_members[rel] = data
            taken.setdefault(name, []).append(rel)

        if conflicts:
            return MemberMerge(None, taken=taken, conflicts=conflicts)
        out_dir = os.path.join(work, "out")
        os.makedirs(out_dir)
        holder = os.path.join(out_dir, "chunk.bin")
        with open(holder, "wb") as handle:
            handle.write(base)
        nested = os.path.join(out_dir, "chunk")
        for rel, data in merged_members.items():
            dest = os.path.join(nested, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as handle:
                handle.write(data)

        try:
            rebuilt = read_rebuild_chunk(holder)
        except Exception as exc:
            return MemberMerge(None, taken=taken, error=f"rebuild failed: {exc}")

        if not rebuilt or rebuilt == base:
            return MemberMerge(None, taken=taken,
                               error="rebuild produced no change")
        return MemberMerge(rebuilt, taken=taken)
    finally:
        shutil.rmtree(work, ignore_errors=True)

@dataclass
class Resolution:
    target: Target
    kind: str
    sources: List[str]
    detail: str = ""
    entry: Optional[ModFileEntry] = None
    members_taken: Dict[str, List[str]] = field(default_factory=dict)
    members_conflicted: List[str] = field(default_factory=list)

    @property
    def is_conflict(self) -> bool:
        return self.kind == KIND_CONFLICT

@dataclass
class MergePlan:
    resolutions: List[Resolution] = field(default_factory=list)
    order: List[str] = field(default_factory=list)

    @property
    def merged_entries(self) -> List[ModFileEntry]:
        return [r.entry for r in self.resolutions if r.entry is not None]

    @property
    def conflicts(self) -> List[Resolution]:
        return [r for r in self.resolutions if r.is_conflict]

    @property
    def stats(self) -> Dict[str, int]:
        counts = {KIND_UNIQUE: 0, KIND_IDENTICAL: 0, KIND_SUBCONTAINER: 0,
                  KIND_LOOSE: 0, KIND_CONFLICT: 0}
        for r in self.resolutions:
            counts[r.kind] = counts.get(r.kind, 0) + 1
        return counts

    @property
    def ok(self) -> bool:
        return not self.conflicts


def plan_merge(sources: Sequence[MergeSource],
               base: Optional[BaseLibrary] = None,
               winner_by_target: Optional[Dict[Target, str]] = None) -> MergePlan:
    """
    Work out a single entry per target across every mod

    Priority order is the order sources are given: later ones win when a
    conflict is resolved by preference rather than by structure
    """
    winner_by_target = winner_by_target or {}
    order = [s.name for s in sources]

    touched: Dict[Target, List[MergeSource]] = {}
    for source in sources:
        for entry in source.entries:
            touched.setdefault(target_of(entry), []).append(source)

    plan = MergePlan(order=order)
    for target in sorted(touched):
        owners = touched[target]
        names = [o.name for o in owners]
        entries = [o.entry_for(target) for o in owners]

        if len(owners) == 1:
            plan.resolutions.append(Resolution(
                target, KIND_UNIQUE, names, "only one mod touches this",
                entry=entries[0]))
            continue

        payloads = {e.payload for e in entries if e is not None}
        if len(payloads) == 1:
            plan.resolutions.append(Resolution(
                target, KIND_IDENTICAL, names,
                "every mod ships identical bytes", entry=entries[0]))
            continue

        # an explicit user choice short circuits the structural work
        chosen = winner_by_target.get(target)
        if chosen:
            picked = next((e for o, e in zip(owners, entries) if o.name == chosen), None)
            if picked is not None:
                plan.resolutions.append(Resolution(
                    target, KIND_UNIQUE, names,
                    f"resolved by choosing {chosen}", entry=picked))
                continue

        original = base.payload_for(target) if base is not None else None
        if original is not None and looks_like_subcontainer(original):
            result = merge_subcontainer(
                original, [(o.name, e.payload) for o, e in zip(owners, entries) if e])
            if result.merged is not None:
                template = entries[0]
                merged_entry = ModFileEntry(
                    stored_name=template.stored_name,
                    payload=result.merged,
                    tail=template.tail,
                )
                detail = ", ".join(
                    f"{n}: {len(v)} member(s)" for n, v in result.taken.items()
                ) or "members combined"
                plan.resolutions.append(Resolution(
                    target, KIND_SUBCONTAINER, names, detail,
                    entry=merged_entry, members_taken=result.taken))
                continue
            if result.conflicts:
                plan.resolutions.append(Resolution(
                    target, KIND_CONFLICT, names,
                    f"same member(s) edited by more than one mod: "
                    f"{', '.join(result.conflicts[:4])}",
                    members_conflicted=result.conflicts))
                continue
            reason = result.error or "members could not be combined"
            plan.resolutions.append(Resolution(target, KIND_CONFLICT, names, reason))
            continue

        if original is None:
            plan.resolutions.append(Resolution(
                target, KIND_CONFLICT, names,
                "no unpacked original available to compare against"))
            continue

        loose = merge_bytes(original, [(o.name, e.payload)
                                       for o, e in zip(owners, entries) if e])
        if loose.merged is not None:
            template = entries[0]
            merged_entry = ModFileEntry(
                stored_name=template.stored_name,
                payload=loose.merged,
                tail=template.tail,
            )
            detail = ", ".join(
                f"{n}: {len(v)} region(s)" for n, v in loose.taken.items()
            ) or "regions combined"
            plan.resolutions.append(Resolution(
                target, KIND_LOOSE, names, detail,
                entry=merged_entry, members_taken=loose.taken))
            continue

        reason = loose.error or (
            f"same bytes rewritten by more than one mod: "
            f"{', '.join(loose.conflicts[:3])}" if loose.conflicts
            else "changes could not be combined")
        plan.resolutions.append(Resolution(
            target, KIND_CONFLICT, names, reason,
            members_conflicted=loose.conflicts))

    return plan


def resolve_conflicts_by_priority(plan: MergePlan, sources: Sequence[MergeSource]) -> MergePlan:
    """Fall back to last-one-wins for whatever structure could not separate"""
    by_name = {s.name: s for s in sources}
    for res in plan.resolutions:
        if not res.is_conflict:
            continue
        winner = res.sources[-1]
        source = by_name.get(winner)
        entry = source.entry_for(res.target) if source else None
        if entry is not None:
            res.kind = KIND_UNIQUE
            res.entry = entry
            res.detail = f"{res.detail}; taking {winner} by priority"
    return plan

def write_merged_package(plan: MergePlan, out_path: str, *, game_id: str,
                         display_name: str, author: str, version_text: str,
                         description: str, genre_name: str = "Overhaul") -> str:
    """
    Emit the merged result as a normal mod package
    """
    from .aldnoah_mod_creator import AldnoahPackageWriter, PayloadEntry

    entries = plan.merged_entries
    if not entries:
        raise ValueError("nothing to write: the merge produced no entries")

    staging = tempfile.mkdtemp(prefix="aldnoah_merged_")
    try:
        payload_entries = []
        used = set()
        for index, entry in enumerate(entries):
            stem = os.path.basename(entry.stored_name or f"entry_{index:05d}.bin")
            if stem in used:
                root, ext = os.path.splitext(stem)
                stem = f"{root}_{index}{ext}"
            used.add(stem)
            staged = os.path.join(staging, stem)
            with open(staged, "wb") as handle:
                handle.write(entry.payload)
            payload_entries.append(PayloadEntry(
                source_path=staged, stored_name=stem,
                size=os.path.getsize(staged),
                record={
                    "idx_marker": entry.tail.idx_marker,
                    "entry_off": entry.tail.entry_off,
                    "comp_marker": entry.tail.comp_marker,
                }))

        writer = AldnoahPackageWriter(game_id=game_id)
        writer.write_package(
            out_path,
            display_name=display_name,
            author=author,
            version_text=version_text,
            description=description,
            build_release=True,
            genre_name=genre_name,
            preview_paths=[],
            audio_path=None,
            payload_entries=payload_entries,
        )
        return out_path
    finally:
        shutil.rmtree(staging, ignore_errors=True)
