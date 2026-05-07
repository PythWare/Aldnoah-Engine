"""General purpose utility tools for Aldnoah Engine"""

from __future__ import annotations

from dataclasses import dataclass
import os, shutil, tempfile, time, uuid
from typing import List, Optional, Tuple


TAILDATA_SIZE = 6
DIAGNOSTIC_PROBE_BYTES = b"Aldnoah Engine diagnostics probe\n"
RECOMMENDED_UNPACK_FREE_SPACE_BYTES = 70 * 1000 * 1000 * 1000
DEFAULT_FREE_SPACE_WARNING_BYTES = RECOMMENDED_UNPACK_FREE_SPACE_BYTES
CRITICAL_FREE_SPACE_BYTES = 512 * 1000 * 1000
WINDOWS_LONG_PATH_WARNING_LENGTH = 120


@dataclass(frozen=True)
class DirectoryDiagnosticIssue:
    severity: str
    code: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.severity == "error"

    @property
    def is_warning(self) -> bool:
        return self.severity == "warning"


@dataclass(frozen=True)
class DirectoryDiagnostics:
    path: str
    nearest_existing_path: str
    drive: str
    exists: bool
    is_directory: bool
    disk_total_bytes: Optional[int]
    disk_used_bytes: Optional[int]
    disk_free_bytes: Optional[int]
    can_read: bool
    can_write_file: bool
    can_create_directory: bool
    can_delete_probe: bool
    protected_location: bool
    protected_location_name: str
    issues: Tuple[DirectoryDiagnosticIssue, ...]

    @property
    def has_errors(self) -> bool:
        return any(issue.is_error for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.is_warning for issue in self.issues)

    @property
    def should_warn_user(self) -> bool:
        return self.has_errors or self.has_warnings

    @property
    def can_use_directory(self) -> bool:
        return not self.has_errors

    @property
    def is_recommended_directory(self) -> bool:
        return not self.has_errors and not self.has_warnings

    @property
    def status_label(self) -> str:
        if self.has_errors:
            return "Blocked"
        if self.has_warnings:
            return "Warning"
        return "Good"

    def report_lines(self) -> Tuple[str, ...]:
        lines = [
            f"Status: {self.status_label}",
            f"Path: {self.path}",
            f"Drive: {self.drive or 'Unknown'}",
            f"Free Space: {format_byte_size(self.disk_free_bytes)} available / {format_byte_size(self.disk_total_bytes)} total",
            f"Read Permission: {'OK' if self.can_read else 'Blocked'}",
            f"File Write Permission: {'OK' if self.can_write_file else 'Blocked'}",
            f"Folder Create Permission: {'OK' if self.can_create_directory else 'Blocked'}",
            f"Delete Probe: {'OK' if self.can_delete_probe else 'Blocked'}",
        ]
        if self.protected_location:
            lines.append(f"Protected Location: {self.protected_location_name}")
        if self.issues:
            lines.append("")
            lines.append("Findings:")
            for issue in self.issues:
                lines.append(f"- {issue.severity.upper()}: {issue.message}")
        else:
            lines.append("")
            lines.append("No directory warnings found.")
        return tuple(lines)

    def report_text(self) -> str:
        return "\n".join(self.report_lines())


@dataclass(frozen=True)
class TaildataTransferResult:
    source_path: str
    destination_path: str
    taildata: bytes
    destination_size: int

    @property
    def taildata_hex(self) -> str:
        return self.taildata.hex(" ")


def aldnoah_root() -> str:
    """Return the directory that contains the Aldnoah Engine install"""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def format_byte_size(size: Optional[int]) -> str:
    if size is None:
        return "Unknown"
    size = int(size)
    sign = "-" if size < 0 else ""
    value = float(abs(size))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000.0 or unit == "TB":
            if unit == "B":
                return f"{sign}{int(value)} {unit}"
            formatted = f"{value:.2f}".rstrip("0").rstrip(".")
            return f"{sign}{formatted} {unit}"
        value /= 1000.0
    return f"{sign}{value:.2f} TB"


def diagnose_aldnoah_directory(
    path: Optional[str] = None,
    *,
    required_free_bytes: int = 0,
    warning_free_bytes: int = DEFAULT_FREE_SPACE_WARNING_BYTES,
) -> DirectoryDiagnostics:
    """
    Check whether the Aldnoah Engine directory is a good place to run from

    required_free_bytes is useful when a caller has a known unpack/repack size,
    warning_free_bytes gives AE a general unpacking space warning even when no
    exact job size is known
    """
    target_path = os.path.abspath(path or aldnoah_root())
    exists = os.path.exists(target_path)
    is_directory = os.path.isdir(target_path)
    nearest_existing = nearest_existing_path(target_path)
    drive = os.path.splitdrive(nearest_existing or target_path)[0] or os.path.abspath(os.sep)
    issues: List[DirectoryDiagnosticIssue] = []

    disk_total = None
    disk_used = None
    disk_free = None
    try:
        usage = shutil.disk_usage(nearest_existing or target_path)
        disk_total = usage.total
        disk_used = usage.used
        disk_free = usage.free
    except OSError as exc:
        issues.append(diagnostic_issue("error", "disk_usage_failed", f"Could not read drive storage: {exc}"))

    protected_name = protected_location_name(target_path)
    protected_location = bool(protected_name)

    can_read = False
    can_write_file = False
    can_create_directory = False
    can_delete_probe = False

    if not exists:
        issues.append(diagnostic_issue("error", "missing_directory", "The Aldnoah Engine directory does not exist."))
    elif not is_directory:
        issues.append(diagnostic_issue("error", "not_directory", "The Aldnoah Engine path is not a folder."))
    else:
        can_read, read_error = probe_directory_read(target_path)
        can_write_file, file_delete_ok, file_error = probe_file_write(target_path)
        can_create_directory, dir_delete_ok, dir_error = probe_directory_create(target_path)
        can_delete_probe = file_delete_ok and dir_delete_ok

        if not can_read:
            issues.append(diagnostic_issue("error", "read_denied", f"Could not read the directory: {read_error}"))
        if not can_write_file:
            issues.append(diagnostic_issue("error", "write_denied", f"Could not create/write a test file: {file_error}"))
        elif not file_delete_ok:
            issues.append(diagnostic_issue("error", "delete_file_denied", f"Could not delete a test file: {file_error}"))
        if not can_create_directory:
            issues.append(diagnostic_issue("error", "mkdir_denied", f"Could not create a test folder: {dir_error}"))
        elif not dir_delete_ok:
            issues.append(diagnostic_issue("error", "delete_dir_denied", f"Could not delete a test folder: {dir_error}"))

    if protected_location:
        issues.append(
            diagnostic_issue(
                "warning",
                "protected_location",
                f"AE is inside {protected_name}. Windows may block writes there unless it is run as administrator.",
            )
        )

    if disk_free is not None:
        if required_free_bytes > 0 and disk_free < required_free_bytes:
            issues.append(
                diagnostic_issue(
                    "error",
                    "required_space_low",
                    f"Only {format_byte_size(disk_free)} is available, below the required {format_byte_size(required_free_bytes)}.",
                )
            )
        elif disk_free < CRITICAL_FREE_SPACE_BYTES:
            issues.append(
                diagnostic_issue(
                    "error",
                    "critical_space_low",
                    f"Only {format_byte_size(disk_free)} is available on this drive.",
                )
            )
        elif warning_free_bytes > 0 and disk_free < warning_free_bytes:
            issues.append(
                diagnostic_issue(
                    "warning",
                    "space_low",
                    "Only "
                    f"{format_byte_size(disk_free)} is available on this drive. More than "
                    f"{format_byte_size(warning_free_bytes)} is recommended for modders who unpack games. "
                    "This warning is not usually relevant if you only install finished mods.",
                )
            )

    if os.name == "nt" and len(target_path) >= WINDOWS_LONG_PATH_WARNING_LENGTH:
        issues.append(
            diagnostic_issue(
                "warning",
                "long_path",
                "The AE folder path is long. Deep unpacked folders may hit Windows path-length limits.",
            )
        )

    return DirectoryDiagnostics(
        path=target_path,
        nearest_existing_path=nearest_existing,
        drive=drive,
        exists=exists,
        is_directory=is_directory,
        disk_total_bytes=disk_total,
        disk_used_bytes=disk_used,
        disk_free_bytes=disk_free,
        can_read=can_read,
        can_write_file=can_write_file,
        can_create_directory=can_create_directory,
        can_delete_probe=can_delete_probe,
        protected_location=protected_location,
        protected_location_name=protected_name,
        issues=tuple(issues),
    )


def diagnostic_issue(severity: str, code: str, message: str) -> DirectoryDiagnosticIssue:
    return DirectoryDiagnosticIssue(severity=severity, code=code, message=message)


def nearest_existing_path(path: str) -> str:
    candidate = os.path.abspath(path)
    while candidate and not os.path.exists(candidate):
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent
    return candidate if candidate and os.path.exists(candidate) else os.path.abspath(os.sep)


def probe_directory_read(path: str) -> Tuple[bool, str]:
    try:
        with os.scandir(path) as entries:
            next(entries, None)
        return True, ""
    except OSError as exc:
        return False, str(exc)


def probe_file_write(path: str) -> Tuple[bool, bool, str]:
    temp_path = ""
    write_ok = False
    error = ""
    try:
        handle_fd, temp_path = tempfile.mkstemp(prefix="aldnoah_diag_", suffix=".tmp", dir=path)
        with os.fdopen(handle_fd, "wb") as handle:
            handle.write(DIAGNOSTIC_PROBE_BYTES)
        with open(temp_path, "rb") as handle:
            if handle.read() != DIAGNOSTIC_PROBE_BYTES:
                error = "The test file contents did not round-trip correctly."
            else:
                write_ok = True
    except OSError as exc:
        error = str(exc)

    delete_ok = True
    if temp_path:
        delete_ok, delete_error = remove_file_with_retries(temp_path)
        if delete_error and not error:
            error = delete_error
    return write_ok, delete_ok, error


def probe_directory_create(path: str) -> Tuple[bool, bool, str]:
    temp_path = ""
    directory_created = False
    error = ""
    try:
        temp_path = make_probe_directory(path)
        directory_created = True
    except OSError as exc:
        error = str(exc)

    delete_ok = True
    if temp_path:
        delete_ok, delete_error = remove_directory_with_retries(temp_path)
        if delete_error and not error:
            error = delete_error
    return directory_created, delete_ok, error


def make_probe_directory(path: str) -> str:
    for _attempt in range(32):
        temp_path = os.path.join(path, f"aldnoah_diag_dir_{uuid.uuid4().hex}")
        try:
            os.mkdir(temp_path)
            return temp_path
        except FileExistsError:
            continue
    raise FileExistsError("Could not reserve a unique diagnostic test folder name.")


def remove_file_with_retries(path: str) -> Tuple[bool, str]:
    last_error = ""
    for attempt in range(4):
        try:
            if not os.path.exists(path):
                return True, ""
            os.remove(path)
            return True, ""
        except OSError as exc:
            last_error = str(exc)
            if attempt < 3:
                time.sleep(0.05)
    return False, last_error


def remove_directory_with_retries(path: str) -> Tuple[bool, str]:
    last_error = ""
    for attempt in range(4):
        try:
            if not os.path.isdir(path):
                return True, ""
            os.rmdir(path)
            return True, ""
        except OSError as exc:
            last_error = str(exc)
            if attempt < 3:
                time.sleep(0.05)
    return False, last_error


def protected_location_name(path: str) -> str:
    normalized_path = normalize_for_compare(path)
    for label, root in protected_roots():
        if path_is_within(normalized_path, normalize_for_compare(root)):
            return label

    _drive, tail = os.path.splitdrive(os.path.abspath(path))
    parts = [part for part in tail.replace("/", os.sep).split(os.sep) if part]
    if parts:
        first = parts[0].lower()
        if first in {"program files", "program files (x86)"}:
            return parts[0]
        if first == "windows":
            return parts[0]
    return ""


def protected_roots() -> Tuple[Tuple[str, str], ...]:
    roots: List[Tuple[str, str]] = []
    for label, env_name in (
        ("Program Files", "ProgramFiles"),
        ("Program Files (x86)", "ProgramFiles(x86)"),
        ("Program Files", "ProgramW6432"),
        ("Windows", "SystemRoot"),
        ("Windows", "windir"),
    ):
        value = os.environ.get(env_name)
        if value:
            roots.append((label, value))
    return tuple(roots)


def normalize_for_compare(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def path_is_within(path: str, root: str) -> bool:
    try:
        return os.path.commonpath((path, root)) == root
    except ValueError:
        return False


def read_taildata(path: str) -> bytes:
    """Read the final 6 byte Aldnoah taildata block from a file"""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")

    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        if size < TAILDATA_SIZE:
            raise ValueError(f"File is too small to contain {TAILDATA_SIZE} byte taildata: {path}")
        handle.seek(size - TAILDATA_SIZE)
        taildata = handle.read(TAILDATA_SIZE)

    if len(taildata) != TAILDATA_SIZE:
        raise OSError(f"Could not read {TAILDATA_SIZE} byte taildata from: {path}")
    return taildata


def transfer_taildata(source_path: str, destination_path: str) -> TaildataTransferResult:
    """
    Copy the final 6 byte Aldnoah taildata block from source_path into
    the final 6 bytes of destination_path
    """
    source_path = os.path.abspath(source_path)
    destination_path = os.path.abspath(destination_path)

    if source_path == destination_path:
        raise ValueError("Source and destination must be different files.")
    if not os.path.isfile(destination_path):
        raise FileNotFoundError(f"Destination file not found: {destination_path}")

    taildata = read_taildata(source_path)

    with open(destination_path, "r+b") as handle:
        handle.seek(0, os.SEEK_END)
        destination_size = handle.tell()
        if destination_size < TAILDATA_SIZE:
            raise ValueError(
                f"Destination file is too small to contain {TAILDATA_SIZE} byte taildata: {destination_path}"
            )
        handle.seek(destination_size - TAILDATA_SIZE)
        handle.write(taildata)

    return TaildataTransferResult(
        source_path=source_path,
        destination_path=destination_path,
        taildata=taildata,
        destination_size=destination_size,
    )
