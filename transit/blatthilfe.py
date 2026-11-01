"""Explanations for the elements of the Ergebnisblatt (page 1 and the field page), shown in the GUI as tooltips.

ergebnisblatt.py writes RESULT\\<lauf>\\ergebnisblatt_hilfe.json: for every element its rectangle as fractions of the
PNG (x0, y0 from the top left, x1, y1) plus title and text.  The PNG/PDF themselves are not changed.  Texts live here
in one place (German; a later English version translates this module).
"""
import json

# ---------------------------------------------------------------- page 1: blocks
BLOCK = {
    "kopf": ("Kernergebnis",
             "Tc: gemessene Transitmitte in BJD_TDB, mit Fehler nach oben/unten (MCMC, 16./84. Perzentil). "
             "O-C: gemessen minus vorhergesagt in Minuten (positiv = Transit kam später). "
             "STD: Streuung der Residuen in Promille, wie ExoClock „Residuals STD“. "
             "SNR: Transittiefe geteilt durch ihren Fehler, wie ExoClock „Transit SNR“ (gut: deutlich über 10). "
             "Darüber: Nacht, Lauf, Kalibrierung und das Ensemble der Vergleichssterne mit Apertur. „(von Hand gewählt)“ = "
             "die Sterne wurden in der Oberfläche festgelegt (Ergebnis → Vergleichssterne → Haken, [search] ensemble), "
             "ohne automatische Suche; das steht auch im ExoClock-Kommentar."),
    "lc": ("Lichtkurve",
           "Helligkeit des Zielsterns relativ zum Ensemble der Vergleichssterne, von Airmass (und ggf. Meridian-Flip) "
           "bereinigt. Grau: Einzelpunkte, blau: Mittelwerte, rot: Transitmodell aus dem MCMC-Fit. "
           "Grau gestrichelt: vorhergesagter Beginn/Ende, rot gestrichelt: gemessener 1./4. Kontakt, rot gepunktet: 2./3. Kontakt."),
    "res": ("Residuen",
            "Messpunkte minus Modell in Promille (ppt). Sollten ohne Muster um null streuen. "
            "Wellen oder Stufen deuten auf Wolken, Flip, schlechte Vergleichssterne oder rotes Rauschen hin."),
    "skizze": ("Maßstäbliche Skizze",
               "Stern und Planet im richtigen Größenverhältnis. Sternfarbe aus der Temperatur (Teff), Randverdunkelung "
               "mit den Koeffizienten des Fits. Schwarze Scheibe: dein gemessenes Rp/R*; gestrichelter Umriss: "
               "Literaturwert. Blaue Linie mit Band: Bahn mit dem gemessenen Stoßparameter b ± 1 σ aus dem freien "
               "Geometrie-Fit; weiß gestrichelt: b aus der Literatur. Ist b aus der Nacht nicht bestimmbar, sitzt der "
               "Planet auf der Bahn der Fit-Geometrie. Jupiter und Erde im selben Maßstab (R* aus der Literatur)."),
    "tabelle": ("Dein Wert vs. Literatur",
                "Jede Zeile vergleicht eine Größe aus deiner Messung mit dem Literaturwert. Die Ampel in „Abw. sigma“ "
                "zeigt, wie gut beide zusammenpassen. Die grauen Zeilen unten beschreiben die Güte der Messung."),
    "plausi": ("Plausibilität der Tiefe",
               "Automatische Prüfungen, warum die Transittiefe von der Literatur abweichen könnte (z. B. Filter, "
               "Nachbarsterne in der Apertur, Drift). [!] markiert auffällige Punkte."),
    "oc": ("O-C-Diagramm",
           "Alle deine Messungen dieses Planeten aus dem Logbuch: Abweichung der Transitmitte von der Vorhersage über "
           "der Epoche. Grauer Streifen: Unsicherheit der Vorhersage. Stern: dieser Lauf. Ein Trend über viele "
           "Epochen hieße, dass die Ephemeride nachgeführt werden muss."),
    "profil": ("Planetenprofil (Literatur)",
               "Steckbrief aus ExoClock und dem NASA Exoplanet Archive. Reine Literaturwerte, nicht aus deiner Messung."),
    "fuss": ("Aufnahme und Herkunft",
             "Beobachter, Teleskop, Kamera, Filter, Belichtung und Standort aus Konfiguration und FITS-Header, dazu "
             "Lauf, Ordner und Programmversion."),
}

# ---------------------------------------------------------------- page 1: table column heads
SPALTE = {
    "Groesse": "Was verglichen wird. „frei“ heißt: aus einem Fit mit freier Geometrie (a/R*, i), nur zur Info.",
    "Dein Wert": "Ergebnis dieser Nacht mit 1-σ-Fehler (MCMC bzw. freier Fit). „unbestimmt“: Fehler so groß, dass der Wert nichts aussagt.",
    "Literatur": "Vergleichswert aus ExoClock bzw. NASA Exoplanet Archive (Quelle siehe Spalte „Quelle“), mit Fehler, sofern bekannt.",
    "Abw. sigma": "(Dein Wert − Literatur) / kombinierter Fehler. Ampel: grün unter 2 σ, gelb 2–3 σ, rot über 3 σ, grau = schwach bestimmt oder ohne Fehler.",
    "Quelle": "Woher der Literaturwert stammt.",
    "Hinweis": "Wie der eigene Wert entstanden ist bzw. was dabei zu beachten ist.",
}

# ---------------------------------------------------------------- page 1: table rows (first column, by prefix)
ZEILE = {
    "Tc (BJD_TDB)": "Gemessene Transitmitte (Baryzentrische Julianische Zeit, TDB). Literatur: Vorhersage aus der Ephemeride.",
    "O-C (min)": "Gemessen minus vorhergesagt. Innerhalb des Fehlers um 0: Ephemeride bestätigt. Der Wert, den ExoClock sammelt.",
    "Tiefe (ppt)": "Größter Helligkeitseinbruch des Modells in Promille (mit Randverdunkelung). Hängt vom Filter ab.",
    "Tiefe (mmag)": "Dieselbe Tiefe in Millimagnituden, wie ExoClock sie angibt.",
    "Rp/R*-Drift": "ExoClock-Kriterium: Abweichung des Radienverhältnisses von der Literatur in Einheiten des Fehlers. |Drift| < 2 gut, < 3 ok.",
    "Rp/R*": "Radius des Planeten relativ zum Stern, aus der Tiefe. Die zentrale „Größe“ des Transits.",
    "Rp (R_Jup)": "Planetenradius in Jupiterradien: Rp/R* mal Sternradius aus der Literatur.",
    "Rp (R_Erde)": "Planetenradius in Erdradien.",
    "t14 (h)": "Gesamtdauer vom 1. bis 4. Kontakt (Planet berührt den Sternrand erstmals bis zuletzt).",
    "t12 = t34": "Dauer von Ein- bzw. Austritt (1.–2. bzw. 3.–4. Kontakt). Lang bei streifenden Transits (großes b).",
    "a/R* (frei)": "Bahnradius in Sternradien aus dem freien Fit. Aus einer Amateurnacht meist nur grob bestimmbar.",
    "i (Grad, frei)": "Bahnneigung aus dem freien Fit (90° = genau mittig von vorne).",
    "b (frei)": "Stoßparameter: kleinster Abstand der Planetenbahn von der Sternmitte in Sternradien (0 = mittig, ~1 = streifend). b = a/R* · cos i.",
    "rho*": "Mittlere Sterndichte aus a/R* und Periode (Keplers 3. Gesetz). Nur sinnvoll, wenn a/R* gut bestimmt ist.",
    "Spektraltyp": "Aus der Sterndichte geschätzter Spektraltyp (Hauptreihenstern angenommen).",
    "Streuung sigma": "Standardabweichung aller Residuen in Promille. Direkt vergleichbar mit ExoClock „Residuals STD“.",
    "Transit-SNR": "Tiefe geteilt durch ihren Fehler. Unter etwa 10 ist der Transit nur schwach nachgewiesen.",
    "OOT-RMS": "Streuung außerhalb des Transits (out of transit). Danach werden Apertur und Ensemble blind gewählt.",
    "chi2/dof": "Güte des Fits relativ zu den erwarteten Fehlern. Deutlich über 1: mehr Rauschen als Photonen- und Ausleserauschen erklären.",
    "BIC": "Bayessches Informationskriterium des Fits. Nur zum Vergleich von Varianten derselben Nacht.",
    "beta": "Faktor für rotes (zeitlich korreliertes) Rauschen. 1 = weißes Rauschen; größer: Fehler werden entsprechend vergrößert.",
    "Tc-Streuung Top-50": "Wie stark Tc zwischen den 50 besten Kombinationen aus Apertur und Ensemble schwankt, verglichen mit dem MCMC-Fehler.",
    "MCMC": "Anzahl der Markov-Ketten und Konvergenz (R-hat unter 1,05 = konvergiert).",
    "Detrending": "Welche Trends aus der Lichtkurve entfernt wurden (Airmass linear/quadratisch, Sprung beim Meridian-Flip).",
    "Apertur": "Gewählter Blendenradius der Photometrie (fest in Pixeln oder mitwachsend mit dem Seeing).",
    "Ensemble-Asymmetrie": "Wie einseitig die Vergleichssterne um das Ziel verteilt sind (0 = rundum, 1 = alle auf einer Seite).",
    "Ausgeschlossene Sterne": "Von Hand aus dem Ensemble genommene Vergleichssterne.",
}

# ---------------------------------------------------------------- page 2: field page
FELD_BLOCK = {
    "feldbild": ("Feldbild",
                 "Ein Frame der Nacht (bestes Seeing nahe Transitmitte), asinh-gestretcht, Norden oben, Osten links. "
                 "Rot: Zielstern, blau: verwendete Vergleichssterne C1…, grau gestrichelt: geeignete, aber nicht "
                 "genutzte Kandidaten, x: verworfene Sterne."),
    "feldtabelle": ("Vergleichssterne",
                    "Eigenschaften und Begründung jedes Vergleichssterns. Gelb hinterlegt: auffällig (RUWE, Nachbar, "
                    "Variabilität). Sterne von Hand ins Ensemble nehmen oder herausnehmen: Oberfläche → Ergebnis → "
                    "Vergleichssterne → Spalte „wählen“ → Vorschau → Als neuen Lauf rechnen."),
}
FELD_SPALTE = {
    "Kennung": "Name im Ergebnisblatt (Ziel, C1, C2 …) und interne Sternnummer.",
    "Gaia DR3": "Kennung im Gaia-Katalog DR3.",
    "RA / Dec (J2000)": "Himmelskoordinaten.",
    "Abst. '": "Abstand zum Zielstern in Bogenminuten.",
    "G": "Gaia-G-Helligkeit (mag).",
    "dG": "Helligkeitsunterschied zum Ziel (mag). Ideal: ähnlich hell.",
    "BP-RP": "Gaia-Farbe (blau minus rot). Größer = röter.",
    "dFarbe": "Farbunterschied zum Ziel. Ähnliche Farbe verringert Airmass-Effekte.",
    "Peak max": "Höchster Pixelwert des Sterns in der Nacht (ADU). Nahe der Sättigung ist der Stern unbrauchbar.",
    "RUWE": "Gaia-Astrometriegüte. Über 1,4: möglicherweise Doppelstern.",
    "Var.": "Variabilitätskennung aus Gaia/VSX (z. B. VARIABLE). Variable Sterne verfälschen die Lichtkurve.",
    "Nb.<10\"": "Anzahl Nachbarsterne innerhalb von 10 Bogensekunden (können in die Apertur fallen).",
    "Streu.": "Streuung der Lichtkurve dieses Sterns relativ zu den anderen (ppt).",
    "Anteil%": "Anteil am Gesamtfluss des Ensembles.",
    "JK dO-C": "Jackknife: Änderung von O-C in Minuten, wenn dieser Stern weggelassen wird. Groß = Ergebnis hängt an ihm.",
    "Transitf. ppt": "Scheinbarer „Transit“ im Zeitfenster des Planeten bei diesem Stern. Sollte null sein.",
}


def _lookup(table, name):
    name = str(name).strip()
    if name in table:
        return table[name]
    for k in sorted(table, key=len, reverse=True):         # longest prefix first: "Rp/R*-Drift" before "Rp/R*"
        if name.startswith(k):
            return table[k]
    return None


def _rect(bb, fig):
    """Display-space bbox -> fractions of the saved PNG (top-left origin), rounded."""
    W, H = fig.bbox.width, fig.bbox.height
    return [round(float(v), 4) for v in (bb.x0 / W, 1 - bb.y1 / H, bb.x1 / W, 1 - bb.y0 / H)]


def regions(fig, blocks, table=None, columns=SPALTE, rows=ZEILE, block_texts=BLOCK):
    """blocks: {key: artist (Axes or Text)}; table: matplotlib Table with a header row.  Returns a list of
    {art, titel, text, r=[x0, y0, x1, y1]}."""
    fig.canvas.draw()
    rd = fig.canvas.get_renderer()
    out = []
    for key, art in blocks.items():
        if art is None or key not in block_texts:
            continue
        t, txt = block_texts[key]
        bb = art.get_window_extent(rd) if hasattr(art, "get_text") else art.get_position().transformed(fig.transFigure)   # Text / Axes
        out.append(dict(art="block", titel=t, text=txt, r=_rect(bb, fig)))
    if table is not None:
        for (i, j), cl in table.get_celld().items():
            name = cl.get_text().get_text()
            if i == 0:
                txt = columns.get(name)
                kind = "spalte"
            elif j == 0:
                txt = _lookup(rows, name)
                kind = "zeile"
            else:
                continue
            if txt:
                out.append(dict(art=kind, titel=name.split(" (")[0] if kind == "zeile" else name, text=txt,
                                r=_rect(cl.get_window_extent(rd), fig)))
    return out


def write(path, blatt, feld):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(dict(blatt=blatt, feld=feld), fh, ensure_ascii=False, indent=0)
