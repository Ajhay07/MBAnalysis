"""DWG -> DXF access via ODA File Converter (free, closed-source; chosen over LibreDWG to
avoid pulling GPL-3.0 code into this proprietary codebase), wrapped through ezdxf's own
`ezdxf.addons.odafc` subprocess integration rather than reimplementing DWG parsing.

Requires ODA File Converter to be installed on the machine running extraction, and
`configure_oda_converter()` to be called once with its executable path before any .dwg
load - there is no bundled/auto-discovered default, since the install location varies
per machine and per ODA version.
"""
from __future__ import annotations

import os

import ezdxf
from ezdxf.addons import odafc


def configure_oda_converter(exe_path: str) -> None:
    """Point ezdxf's odafc addon at a real ODA File Converter executable. Must be called
    before load_drawing() is used on a .dwg file."""
    ezdxf.options.set("odafc-addon", "win_exec_path", exe_path)


def load_drawing(cad_path: str):
    """Returns an ezdxf Drawing for a .dxf file directly, or for a .dwg file by shelling
    out to ODA File Converter. Raises RuntimeError (not a silent fallback) if a .dwg is
    given but the converter isn't configured/installed - callers must know extraction
    didn't happen, not get an empty result that looks like 'nothing found'."""
    ext = os.path.splitext(cad_path)[1].lower()
    if ext == ".dxf":
        return ezdxf.readfile(cad_path)
    if ext == ".dwg":
        if not odafc.is_installed():
            raise RuntimeError(
                "DWG input requires ODA File Converter, which is not configured on this "
                "machine. Call dwg_converter.configure_oda_converter(path_to_exe) first, "
                "or convert the file to .dxf externally and pass that path instead."
            )
        return odafc.readfile(cad_path)
    raise ValueError(f"Unsupported CAD file extension: {ext!r} (expected .dxf or .dwg)")
