"""Help texts for the browser GUI and the command line, from one source.

transit/hilfe/*.md     one topic per file (workflows, error patterns, terms).  First line is a comment with the meta data:
                       <!-- gruppe: workflow; reihenfolge: 3; seiten: auswerten, lauf; kurz: one line for the list -->
                       then "# Title" and the text.  "## Hintergrund" starts the deeper level (physics, maths, code);
                       the GUI shows it folded, the command line only with --tief.
transit/hilfe/felder.toml   the explanation of every field ([feld.<key>]) and table column ([spalte."<head>"]).

Only a small Markdown subset is understood: headings, paragraphs, lists (also nested), **bold**, `code`, links, pipe
tables, "> " tip boxes, ``` blocks (```formel = a formula) and ---.  Link targets: #hilfe:<id> opens another topic,
#zeige:<element id> scrolls to and highlights a field of the page, #/<view> switches the page, handbuch#<anchor> opens
the manual, http(s) opens a new tab.
"""
import html
import os
import re
import tomllib

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hilfe")
GRUPPEN = [("workflow", "Der Weg einer Nacht"), ("fehler", "Was tun, wenn …"), ("begriffe", "Begriffe")]
TIEF = "Hintergrund"          # heading of the deeper level


# ------------------------------------------------------------------ reading
def _meta(line):
    m = re.match(r"\s*<!--(.*)-->\s*$", line)
    out = {}
    if m:
        for part in m.group(1).split(";"):
            if ":" in part:
                k, v = part.split(":", 1)
                out[k.strip()] = v.strip()
    return out


def themen():
    """All topics, sorted by group and order: list of dicts id, titel, gruppe, reihenfolge, seiten, kurz, md."""
    out = []
    if not os.path.isdir(DIR):
        return out
    for fn in os.listdir(DIR):
        if not fn.endswith(".md"):
            continue
        txt = open(os.path.join(DIR, fn), encoding="utf-8").read().replace("\r\n", "\n")
        lines = txt.split("\n")
        meta = _meta(lines[0]) if lines else {}
        if meta:
            lines = lines[1:]
        while lines and not lines[0].strip():
            lines.pop(0)
        titel = fn[:-3]
        if lines and lines[0].startswith("# "):
            titel = lines.pop(0)[2:].strip()
        out.append(dict(id=fn[:-3], titel=titel, gruppe=meta.get("gruppe", "begriffe"),
                        reihenfolge=float(meta.get("reihenfolge", 99)),
                        seiten=[s.strip() for s in meta.get("seiten", "").split(",") if s.strip()],
                        kurz=meta.get("kurz", ""), md="\n".join(lines).strip()))
    rang = {g: i for i, (g, _) in enumerate(GRUPPEN)}
    out.sort(key=lambda t: (rang.get(t["gruppe"], 9), t["reihenfolge"], t["titel"]))
    return out


def felder():
    """Field and column help: {"feld": {key: {titel, was, wirkung, wann, thema?}}, "spalte": {head: {text, thema?}}}."""
    p = os.path.join(DIR, "felder.toml")
    if not os.path.exists(p):
        return {"feld": {}, "spalte": {}}
    d = tomllib.load(open(p, "rb"))
    return {"feld": d.get("feld", {}), "spalte": d.get("spalte", {})}


# ------------------------------------------------------------------ Markdown -> HTML
def slug(t):
    t = t.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def _link(text, url):
    if url.startswith("#hilfe:"):
        return f'<a href="#" data-thema="{html.escape(url[7:])}">{text}</a>'
    if url.startswith("#zeige:"):
        return f'<a href="#" data-zeige="{html.escape(url[7:])}">{text}</a>'
    if url.startswith("handbuch"):
        return f'<a href="/{html.escape(url)}" target="_blank">{text}</a>'
    if url.startswith("http"):
        return f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{text}</a>'
    return f'<a href="{html.escape(url)}">{text}</a>'


def inline(s):
    """Escape and render **bold**, `code` and [links](url)."""
    codes = []

    def keep(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"
    s = re.sub(r"`([^`]+)`", keep, s)
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", lambda m: _link(m.group(1), html.unescape(m.group(2))), s)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{html.escape(codes[int(m.group(1))], quote=False)}</code>", s)


def _cells(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", line)]


def _list(lines, i, ind):
    """Render a (nested) list starting at lines[i] with indentation ind; returns (html, next index)."""
    m = re.match(r"(\s*)(\d+\.|[-*])\s", lines[i])
    tag = "ol" if m.group(2)[0].isdigit() else "ul"
    out = [f"<{tag}>"]
    while i < len(lines):
        m = re.match(r"(\s*)(\d+\.|[-*])\s+(.*)", lines[i])
        if not m or len(m.group(1)) < ind:
            break
        if len(m.group(1)) > ind:                       # deeper: nested list inside the last item
            sub, i = _list(lines, i, len(m.group(1)))
            out[-1] = out[-1][:-5] + sub + "</li>"
            continue
        item = [m.group(3)]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"\s*(\d+\.|[-*])\s", lines[i]) \
                and len(lines[i]) - len(lines[i].lstrip()) > ind:
            item.append(lines[i].strip())             # continuation line
            i += 1
        out.append(f"<li>{inline(' '.join(item))}</li>")
    out.append(f"</{tag}>")
    return "".join(out), i


def html_von(md, anker=False, tief_offen=False):
    """Markdown subset -> HTML.  anker=True gives headings an id (manual).  In topics "## Hintergrund" opens a folded
    <details> that runs to the end of the text."""
    lines = md.replace("\r\n", "\n").split("\n")
    out, i, tief = [], 0, False
    para = []

    def flush():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if not s:
            flush(); i += 1; continue
        if s.startswith("```"):
            flush()
            art = s[3:].strip()
            j = i + 1
            body = []
            while j < len(lines) and not lines[j].strip().startswith("```"):
                body.append(lines[j]); j += 1
            txt = html.escape("\n".join(body), quote=False)
            out.append(f'<div class="formel">{txt}</div>' if art == "formel" else f"<pre>{txt}</pre>")
            i = j + 1; continue
        m = re.match(r"(#{1,4})\s+(.*)", s)
        if m:
            flush()
            n, t = len(m.group(1)), m.group(2).strip()
            if not anker and n == 2 and t.lower().startswith(TIEF.lower()):
                if tief:
                    out.append("</div></details>")
                if t.lower() == TIEF.lower():
                    t = TIEF + ": Physik, Formeln, Code"
                out.append(f'<details class="tief"{" open" if tief_offen else ""}><summary>{inline(t)}</summary><div>')
                tief = True
            else:
                lvl = n if anker else min(6, n + 1)
                ida = f' id="{slug(t)}"' if anker else ""
                out.append(f"<h{lvl}{ida}>{inline(t)}</h{lvl}>")
            i += 1; continue
        if s == "---":
            flush(); out.append("<hr>"); i += 1; continue
        if s.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i]); i += 1
            head = _cells(rows[0])
            body = rows[2:] if len(rows) > 1 and re.match(r"^\|?[\s:|-]+\|?$", rows[1].strip()) else rows[1:]
            t = ['<div class="tab"><table><thead><tr>' + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"]
            for r in body:
                t.append("<tr>" + "".join(f"<td>{inline(c.replace(chr(92) + '|', '|'))}</td>" for c in _cells(r)) + "</tr>")
            out.append("".join(t) + "</tbody></table></div>")
            continue
        if re.match(r"\s*(\d+\.|[-*])\s", ln):
            flush()
            h, i = _list(lines, i, len(ln) - len(ln.lstrip()))
            out.append(h); continue
        if s.startswith(">"):
            flush()
            q = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q.append(lines[i].strip()[1:].strip()); i += 1
            out.append(f'<div class="tipp">{inline(" ".join(q))}</div>')
            continue
        para.append(s)
        i += 1
    flush()
    if tief:
        out.append("</div></details>")
    return "\n".join(out)


def text_von(md, tief=False):
    """Markdown subset -> plain text for the console.  Without tief the part from "## Hintergrund" on is left out."""
    out = []
    for ln in md.replace("\r\n", "\n").split("\n"):
        s = ln.rstrip()
        m = re.match(r"(#{1,4})\s+(.*)", s.strip())
        if m and m.group(2).lower().startswith(TIEF.lower()) and not tief:
            out.append("\n(Hintergrund mit Physik und Formeln: transit hilfe <thema> --tief)")
            break
        if m:
            out += ["", m.group(2).upper()]
            continue
        if s.strip().startswith("```"):
            continue
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = re.sub(r"`([^`]+)`", r"\1", s)
        s = re.sub(r"\[([^\]]+)\]\(#hilfe:([^)]+)\)", r"\1 (transit hilfe \2)", s)
        s = re.sub(r"\[([^\]]+)\]\((https?:[^)]+)\)", r"\1 (\2)", s)
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        if s.strip().startswith(">"):
            s = "  Tipp: " + s.strip()[1:].strip()
        out.append("  " + s if s else "")
    return "\n".join(out).strip("\n")


# ------------------------------------------------------------------ for the GUI
def handbuch_kapitel(pfad):
    """Chapters of HANDBUCH.md as (anchor, title) for the help panel."""
    if not os.path.exists(pfad):
        return []
    out = []
    for ln in open(pfad, encoding="utf-8"):
        if ln.startswith("## "):
            t = ln[3:].strip()
            out.append((slug(t), t))
    return out


def fuer_gui(handbuch=None):
    """Everything the help panel needs, as one JSON-able dict."""
    T = themen()
    f = felder()
    return {"gruppen": GRUPPEN,
            "themen": [dict(id=t["id"], titel=t["titel"], gruppe=t["gruppe"], seiten=t["seiten"], kurz=t["kurz"],
                            html=html_von(t["md"]), such=(t["titel"] + " " + t["kurz"] + " " + text_von(t["md"], True)).lower())
                       for t in T],
            "feld": f["feld"], "spalte": f["spalte"],
            "handbuch": handbuch_kapitel(handbuch) if handbuch else []}


HANDBUCH_CSS = """body{margin:0;font:15px/1.6 "Segoe UI",system-ui,sans-serif;background:#f6f7f9;color:#1d232b}
main{max-width:920px;margin:0 auto;padding:24px 20px 80px;background:#fff;border-left:1px solid #d8dde3;border-right:1px solid #d8dde3}
h1{font-size:28px}h2{font-size:22px;margin-top:40px;border-top:1px solid #eceef1;padding-top:20px}h3{font-size:17px;margin-top:24px}
code{font:13px Consolas,ui-monospace,monospace;background:#f1f3f5;padding:1px 4px;border-radius:4px}
pre,.formel{font:13px/1.5 Consolas,ui-monospace,monospace;background:#f4f6f8;padding:10px 12px;border-radius:6px;overflow-x:auto}
.tab{overflow-x:auto}table{border-collapse:collapse;font-size:14px;margin:8px 0}th,td{border:1px solid #d8dde3;padding:6px 8px;text-align:left;vertical-align:top}
th{background:#f4f6f8}.tipp{background:#f4f7fc;border-left:3px solid #1f5fbf;padding:8px 12px}a{color:#1a4fa0}
nav{font-size:14px;columns:2 260px;margin:12px 0 24px}nav a{display:block}
@media (prefers-color-scheme:dark){body{background:#14181d;color:#e6e9ed}main{background:#1c2228;border-color:#2f3841}
code,pre,.formel,th{background:#20272e}th,td{border-color:#2f3841}h2{border-color:#262d34}.tipp{background:#1a2533}a{color:#8fb6f5}}"""


def handbuch_html(pfad):
    """HANDBUCH.md as a readable HTML page with a table of contents and anchors (served at /handbuch)."""
    md = open(pfad, encoding="utf-8").read()
    kap = handbuch_kapitel(pfad)
    nav = "<nav>" + "".join(f'<a href="#{a}">{html.escape(t)}</a>' for a, t in kap) + "</nav>"
    body = html_von(md, anker=True)
    body = body.replace("</h1>", "</h1>" + nav, 1)
    return ("<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
            "content=\"width=device-width,initial-scale=1\"><title>Handbuch transit</title><style>" + HANDBUCH_CSS +
            "</style></head><body><main>" + body + "</main></body></html>")
