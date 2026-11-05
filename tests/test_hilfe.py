"""Help texts: every field and column of the new GUI has an explanation, links between topics work, Markdown renders.

Run: python -m pytest tests  (or python tests/test_hilfe.py)
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from transit import hilfetexte as H            # noqa: E402
from transit.gui_neu import PAGE_NEU            # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# column heads without an explanation on purpose (empty or self-explanatory)
SPALTEN_OHNE = {""}


def test_jedes_feld_erklaert():
    F = H.felder()["feld"]
    keys = set(re.findall(r'data-(?:k|h|hilfe-feld)="([^"$]+)"', PAGE_NEU))
    keys |= {"g-" + g for g in re.findall(r'data-g="([a-z]+)"', PAGE_NEU)}
    fehlt = sorted(k for k in keys if k not in F)
    assert not fehlt, f"Felder ohne Hilfetext in transit/hilfe/felder.toml: {fehlt}"


def test_jede_spalte_erklaert():
    S = H.felder()["spalte"]
    heads = {re.sub(r"<[^>]+>", "", h).strip() for h in re.findall(r"<th[^>]*>(.*?)</th>", PAGE_NEU)}
    heads = {h for h in heads if "${" not in h}
    fehlt = sorted(h for h in heads if h not in S and h not in SPALTEN_OHNE)
    assert not fehlt, f"Spalten ohne Hilfetext: {fehlt}"


def test_links_gueltig():
    T = H.themen()
    ids = {t["id"] for t in T}
    anker = {a for a, _ in H.handbuch_kapitel(os.path.join(ROOT, "HANDBUCH.md"))}
    F = H.felder()
    for t in T:
        for z in re.findall(r"\(#hilfe:([^)]+)\)", t["md"]):
            assert z in ids, f"{t['id']}: Thema {z} gibt es nicht"
        for z in re.findall(r"\(handbuch#([^)]+)\)", t["md"]):
            assert z in anker, f"{t['id']}: Handbuch-Kapitel {z} gibt es nicht"
        for z in re.findall(r"\(#zeige:([^)]+)\)", t["md"]):
            assert f'id="{z}"' in PAGE_NEU, f"{t['id']}: Element {z} gibt es nicht"
    for art in ("feld", "spalte"):
        for k, v in F[art].items():
            assert not v.get("thema") or v["thema"] in ids, f"{art} {k}: Thema {v['thema']} gibt es nicht"
    gruppen = {g for g, _ in H.GRUPPEN}
    assert all(t["gruppe"] in gruppen for t in T)


def test_markdown():
    h = H.html_von("Text **fett** und `code` [x](#hilfe:planen)\n\n1. eins\n    - unter\n2. zwei\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\n"
                   "> Tipp\n\n## Hintergrund\n\n```formel\na < b\n```")
    assert "<b>fett</b>" in h and "<code>code</code>" in h and 'data-thema="planen"' in h
    assert "<ol><li>eins<ul><li>unter</li></ul></li><li>zwei</li></ol>" in h
    assert "<td>1</td>" in h and 'class="tipp"' in h and "<details" in h and "a &lt; b" in h
    assert "Hintergrund" not in H.text_von("a\n\n## Hintergrund\n\nb").split("\n")[0]
    assert "b" not in H.text_von("a\n\n## Hintergrund\n\nb").split("(Hintergrund")[0]


def test_handbuch_seite():
    h = H.handbuch_html(os.path.join(ROOT, "HANDBUCH.md"))
    assert h.startswith("<!doctype html>") and "<nav>" in h and "<table>" in h


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
