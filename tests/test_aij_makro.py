"""oeffnen.ijm must point at the table where it lies now, not where it was created (other computer, drive or NAS)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from transit.aij import write_macro            # noqa: E402


def test_makro_zeigt_auf_aktuellen_ort(tmp_path):
    alt = tmp_path / "rechnerA" / "aij"
    neu = tmp_path / "rechnerB" / "aij"
    for d in (alt, neu):
        d.mkdir(parents=True)
        (d / "X_Measurements.xls").write_text("Label\n")
    write_macro(str(alt / "X_Measurements.xls"))
    # measurement copied to another computer: the old macro still names rechnerA
    (neu / "oeffnen.ijm").write_text((alt / "oeffnen.ijm").read_text())
    ijm = write_macro(str(neu / "X_Measurements.xls"))
    text = open(ijm, encoding="utf-8").read()
    assert ijm == os.path.join(str(neu), "oeffnen.ijm")
    assert str(neu / "X_Measurements.xls").replace("\\", "/") in text
    assert "rechnerA" not in text
