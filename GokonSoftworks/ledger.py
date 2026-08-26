from __future__ import annotations
import json
from pathlib import Path
from .wetworks import GokonSoftworksError, log, taildata_dir

LEDGER_SUFFIX = ".tab.json"
LEDGER_VERSION = 2

class LedgerError(GokonSoftworksError):
    pass

def slot_key(idx_marker, entry_off) -> str:
    return f"{int(idx_marker)}:{int(entry_off)}"


def ledger_path(game_dir, game_id: str) -> Path:
    return taildata_dir() / f"{game_id}{LEDGER_SUFFIX}"


class Tab:

    def __init__(self, game_dir, game_id: str):
        self.game_dir = Path(game_dir)
        self.game_id = game_id
        self.path = ledger_path(game_dir, game_id)
        self.container_sizes: dict[str, int] = {}
        self.vanilla_slots: dict[str, str] = {}
        self.mods: dict[str, list] = {}

    def load(self) -> "Tab":
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self
        if data.get("version") != LEDGER_VERSION or data.get("game") != self.game_id:
            return self

        recorded = data.get("game_dir")
        if recorded and Path(recorded) != self.game_dir:
            log.warning(
                "Ignoring the %s tab: it was taken against %s, not %s",
                self.game_id, recorded, self.game_dir,
            )
            return self

        sizes = data.get("container_sizes")
        if isinstance(sizes, dict):
            self.container_sizes = {str(k): int(v) for k, v in sizes.items()}
        vanilla = data.get("vanilla_slots")
        if isinstance(vanilla, dict):
            self.vanilla_slots = dict(vanilla)
        mods = data.get("mods")
        if isinstance(mods, dict):
            self.mods = mods
        return self

    def save(self):
        payload = {
            "version": LEDGER_VERSION,
            "game": self.game_id,
            "game_dir": str(self.game_dir),
            "container_sizes": self.container_sizes,
            "vanilla_slots": self.vanilla_slots,
            "mods": self.mods,
        }
        try:
            temp = self.path.with_suffix(self.path.suffix + ".tmp")
            temp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
            temp.replace(self.path)
        except OSError as exc:
            raise LedgerError(f"Couldnt update the tab: {exc}") from None

    def measured(self) -> bool:
        return bool(self.container_sizes)

    def remember_size(self, idx_marker: int, size: int):
        key = str(idx_marker)
        if key not in self.container_sizes:
            self.container_sizes[key] = int(size)

    def original_size(self, idx_marker: int):
        return self.container_sizes.get(str(idx_marker))

    def remember_slot(self, idx_marker: int, entry_off: int, original: str):
        key = slot_key(idx_marker, entry_off)
        if key not in self.vanilla_slots:
            self.vanilla_slots[key] = original

    def vanilla_for(self, idx_marker: int, entry_off: int):
        return self.vanilla_slots.get(slot_key(idx_marker, entry_off))

    def all_vanilla_slots(self) -> list[dict]:
        out = []
        for key, original in self.vanilla_slots.items():
            marker, _sep, offset = key.partition(":")
            out.append({
                "idx_marker": int(marker),
                "entry_off": int(offset),
                "original": original,
            })
        return out

    def is_enabled(self, mod_id: str) -> bool:
        return mod_id in self.mods

    def enabled_ids(self) -> list[str]:
        return sorted(self.mods)

    def record(self, mod_id: str, slots: list[dict]):
        self.mods[mod_id] = slots

    def forget(self, mod_id: str) -> list[dict]:
        return self.mods.pop(mod_id, [])

    def clear(self):
        self.mods = {}


def load_tab(game_dir, game_id: str) -> Tab:
    return Tab(game_dir, game_id).load()
