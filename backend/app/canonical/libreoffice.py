"""LibreOffice headless discovery and conversion helpers."""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from backend.app.canonical.errors import CanonicalisationError
from backend.app.contracts.errors import ErrorCode
from backend.app.settings.config import Settings

logger = logging.getLogger("veridemand.canonical.libreoffice")

_EXECUTABLE_NAMES = ("soffice.com", "soffice.exe", "soffice", "libreoffice")
_VERSION_RE = re.compile(r"LibreOffice\s+([0-9][^\s]*)", re.IGNORECASE)


@dataclass(frozen=True)
class LibreOfficeRuntime:
    """Resolved LibreOffice executable and version string."""

    executable: Path
    version: str


class LibreOfficeService:
    """Resolve, cache, and invoke LibreOffice for headless PDF conversion."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._runtime: LibreOfficeRuntime | None = None

    def resolve(self) -> LibreOfficeRuntime:
        """Return a cached LibreOffice runtime or discover one."""

        if self._runtime is not None:
            return self._runtime
        executable = self._discover_executable()
        version = self._read_version(executable)
        self._runtime = LibreOfficeRuntime(executable=executable, version=version)
        return self._runtime

    def convert_to_pdf(
        self,
        source: Path,
        *,
        output_dir: Path,
        profile_dir: Path,
    ) -> Path:
        """Convert ``source`` to PDF inside ``output_dir`` and return the output path.

        On Windows, LibreOffice silently fails when the UserInstallation / outdir
        path is very long. When ``profile_dir`` exceeds a safe length, conversion
        runs in a short workspace under ``<TEMP_ROOT>/lo/<hash>/`` and the PDF is
        copied back into ``output_dir`` (still session-owned staging).
        """

        runtime = self.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        profile_dir.mkdir(parents=True, exist_ok=True)

        work_root = profile_dir
        if sys.platform == "win32" and len(str(profile_dir.resolve())) > 90:
            digest = hashlib.sha256(str(profile_dir.resolve()).encode("utf-8")).hexdigest()[:12]
            work_root = self._settings.temp_root / "lo" / digest
            if work_root.exists():
                shutil.rmtree(work_root, ignore_errors=True)
            work_root.mkdir(parents=True, exist_ok=True)

        input_dir = work_root / "input"
        temp_dir = work_root / "temp"
        user_profile = work_root / "profile"
        work_output = work_root / "output" if work_root != profile_dir else output_dir
        input_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        user_profile.mkdir(parents=True, exist_ok=True)
        work_output.mkdir(parents=True, exist_ok=True)

        # Opaque internal filename — never pass the client display name to LO.
        opaque = input_dir / f"document{source.suffix.lower()}"
        if opaque.resolve() != source.resolve():
            shutil.copy2(source, opaque)

        profile_uri = _profile_uri(user_profile)
        convert_exe = self._convert_executable(runtime.executable)
        command = [
            str(convert_exe),
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--norestore",
            f"-env:UserInstallation={profile_uri}",
            "--convert-to",
            "pdf:writer_pdf_Export",
            "--outdir",
            str(work_output),
            str(opaque),
        ]
        # Inherit the process environment. Overriding HOME/USERPROFILE/TMP on
        # Windows causes LibreOffice to exit successfully without writing a PDF.
        env = os.environ.copy()
        stdout_path = temp_dir / "soffice.stdout"
        stderr_path = temp_dir / "soffice.stderr"
        try:
            with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
                completed = subprocess.run(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    timeout=self._settings.libreoffice_timeout_seconds,
                    env=env,
                    shell=False,
                    check=False,
                    startupinfo=_windows_startupinfo(),
                )
        except subprocess.TimeoutExpired as exc:
            self._terminate_process(exc)
            _kill_orphan_libreoffice_processes()
            raise CanonicalisationError(
                ErrorCode.LIBREOFFICE_TIMEOUT,
                "LibreOffice conversion timed out.",
            ) from exc
        except OSError as exc:
            raise CanonicalisationError(
                ErrorCode.LIBREOFFICE_NOT_FOUND,
                "LibreOffice could not be started.",
            ) from exc

        if completed.returncode != 0:
            logger.warning(
                "LibreOffice conversion failed with exit code %s",
                completed.returncode,
            )
            raise CanonicalisationError(
                ErrorCode.LIBREOFFICE_PROCESS_FAILED,
                "LibreOffice conversion failed.",
            )

        expected = work_output / f"{opaque.stem}.pdf"
        produced: Path | None = None
        if expected.exists() and expected.stat().st_size > 0:
            produced = expected
        else:
            candidates = sorted(
                (path for path in work_output.glob("*.pdf") if path.stat().st_size > 0),
                key=lambda path: path.stat().st_mtime,
            )
            if candidates:
                produced = candidates[-1]
        if produced is None:
            raise CanonicalisationError(
                ErrorCode.CANONICALISATION_OUTPUT_MISSING,
                "LibreOffice did not produce a PDF.",
            )

        if produced.parent.resolve() != output_dir.resolve():
            output_dir.mkdir(parents=True, exist_ok=True)
            destination = output_dir / produced.name
            shutil.copy2(produced, destination)
            if work_root != profile_dir:
                shutil.rmtree(work_root, ignore_errors=True)
            return destination
        return produced

    def _discover_executable(self) -> Path:
        configured = self._settings.libreoffice_executable.strip()
        if configured:
            path = Path(configured)
            if path.is_file():
                return path.resolve()
            raise CanonicalisationError(
                ErrorCode.LIBREOFFICE_NOT_FOUND,
                "Configured LibreOffice executable was not found.",
            )

        for name in _EXECUTABLE_NAMES:
            found = shutil.which(name)
            if found:
                return Path(found).resolve()

        for candidate in _windows_standard_paths():
            if candidate.is_file():
                return candidate.resolve()

        raise CanonicalisationError(
            ErrorCode.LIBREOFFICE_NOT_FOUND,
            "LibreOffice is not available.",
        )

    @staticmethod
    def _convert_executable(discovered: Path) -> Path:
        """On Windows prefer soffice.exe for conversion when available."""

        if sys.platform == "win32" and discovered.name.lower() == "soffice.com":
            exe = discovered.with_name("soffice.exe")
            if exe.is_file():
                return exe.resolve()
        return discovered

    def _read_version(self, executable: Path) -> str:
        # On Windows, soffice.exe --version often hangs when stdout is a pipe;
        # prefer soffice.com for version probes and redirect to files.
        version_exe = executable
        if sys.platform == "win32" and executable.name.lower() == "soffice.exe":
            com = executable.with_name("soffice.com")
            if com.is_file():
                version_exe = com

        stdout_path = Path(os.environ.get("TEMP", ".")) / "veridemand-lo-version.out"
        stderr_path = Path(os.environ.get("TEMP", ".")) / "veridemand-lo-version.err"
        try:
            with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
                completed = subprocess.run(
                    [str(version_exe), "--version"],
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    timeout=30.0,
                    shell=False,
                    check=False,
                    startupinfo=_windows_startupinfo(),
                )
            output = stdout_path.read_text(encoding="utf-8", errors="replace")
            output += stderr_path.read_text(encoding="utf-8", errors="replace")
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise CanonicalisationError(
                ErrorCode.LIBREOFFICE_UNAVAILABLE,
                "LibreOffice version could not be determined.",
            ) from exc
        finally:
            stdout_path.unlink(missing_ok=True)
            stderr_path.unlink(missing_ok=True)

        if completed.returncode not in (0, None):
            # Some builds still print version to stdout with a non-zero code.
            pass
        match = _VERSION_RE.search(output)
        if match:
            return match.group(0).strip()
        if output.strip():
            return output.strip().splitlines()[0]
        raise CanonicalisationError(
            ErrorCode.LIBREOFFICE_UNAVAILABLE,
            "LibreOffice version could not be determined.",
        )

    def _terminate_process(self, exc: subprocess.TimeoutExpired) -> None:
        process = getattr(exc, "process", None)
        if process is None:
            return
        with contextlib.suppress(OSError):
            process.terminate()
        grace = self._settings.libreoffice_termination_grace_seconds
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return
            time.sleep(0.05)
        with contextlib.suppress(OSError):
            process.kill()


def _kill_orphan_libreoffice_processes() -> None:
    """Best-effort cleanup of leftover soffice.bin processes on Windows."""

    if sys.platform != "win32":
        return
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        subprocess.run(
            ["taskkill", "/F", "/IM", "soffice.bin", "/T"],
            capture_output=True,
            check=False,
            timeout=10,
        )


def _windows_standard_paths() -> tuple[Path, ...]:
    roots = (
        Path(r"D:\programming\tools\libreoffice\program"),
        Path(r"C:\Program Files\LibreOffice\program"),
        Path(r"C:\Program Files (x86)\LibreOffice\program"),
    )
    names = ("soffice.com", "soffice.exe")
    return tuple(root / name for root in roots for name in names)


def _profile_uri(profile_dir: Path) -> str:
    """Build a file URI LibreOffice accepts on Windows and POSIX.

    Do not percent-encode the drive-letter colon (``C:``); LibreOffice rejects
    ``file:///C%3A/...`` and will hang or fail the conversion.
    """

    resolved = profile_dir.resolve()
    as_posix = resolved.as_posix()
    if len(as_posix) >= 2 and as_posix[1] == ":":
        drive = as_posix[:2]
        rest = as_posix[2:]
        return f"file:///{drive}{quote(rest, safe='/')}"
    return f"file://{quote(as_posix, safe='/')}"


def _controlled_env(temp_dir: Path, profile_dir: Path) -> dict[str, str]:
    """Reserved helper; LibreOffice on Windows must inherit the process env."""

    return os.environ.copy()


def _windows_startupinfo() -> object | None:
    if sys.platform != "win32":
        return None
    startupinfo_cls = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_cls is None:
        return None
    info = startupinfo_cls()
    flags = getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
    info.dwFlags |= flags
    return info
