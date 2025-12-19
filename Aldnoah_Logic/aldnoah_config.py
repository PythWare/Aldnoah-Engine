# Aldnoah_Logic/aldnoah_config.py
import os

# Folder where this file lives (Aldnoah_Logic)
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
# Configs folder inside Aldnoah_Logic
CONFIG_DIR = os.path.join(THIS_DIR, "Configs")

def _maybe_int(s: str):
    """Convert purely decimal strings to int, leave others as is"""
    s = s.strip()
    return int(s) if s.isdigit() else s

def load_ref_config(game_id: str) -> dict:
    """
    Load Configs/<game_id>.ref into a dict

    Supports:
      Key: value
      Key: v1, v2, v3
      continuation lines for the last key:
            Containers: A, B, C,
                        D, E, F
      multiple lines with the same key:
            Containers: A, B
            Containers: C, D

    Comma separated values become lists
    Pure digit values (e.g. 32) become ints
    """
    path = os.path.join(CONFIG_DIR, f"{game_id}.ref")
    cfg = {}

    if not os.path.isfile(path):
        raise FileNotFoundError(f"Config not found: {path}")

    last_key = None

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n")
            stripped = line.strip()

            # Skip blank lines or comments
            if not stripped or stripped.startswith("#"):
                continue

            if ":" in stripped:
                # New key:value line
                key, value = stripped.split(":", 1)
                key = key.strip()
                value = value.strip()

                # Comma-separated => list
                if "," in value:
                    parts = [v.strip() for v in value.split(",") if v.strip()]
                    parts = [_maybe_int(p) for p in parts]

                    if key in cfg:
                        # If already list, extend. if scalar, convert to list
                        existing = cfg[key]
                        if isinstance(existing, list):
                            existing.extend(parts)
                        else:
                            cfg[key] = [existing] + parts
                    else:
                        cfg[key] = parts
                else:
                    # Single value
                    cfg[key] = _maybe_int(value)

                last_key = key
            else:
                # Continuation line: no ":", so append to the last key if it exists
                if last_key is None:
                    continue  # nothing to attach to

                value = stripped
                if not value:
                    continue

                # Treat continuation as comma separated chunk as well
                if "," in value:
                    parts = [v.strip() for v in value.split(",") if v.strip()]
                else:
                    parts = [value]

                parts = [_maybe_int(p) for p in parts]

                existing = cfg.get(last_key)
                if isinstance(existing, list):
                    existing.extend(parts)
                elif existing is None:
                    cfg[last_key] = parts
                else:
                    cfg[last_key] = [existing] + parts

    return cfg
