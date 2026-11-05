<!-- gruppe: workflow; reihenfolge: 2; seiten: planen; kurz: Kurz: was die Aufnahme für eine gute Auswertung braucht -->
# Aufnahme: worauf achten

Diese Hilfe geht davon aus, dass deine Aufnahmen in Ordnung sind. Die wichtigsten Punkte in Kürze:

- **Früh genug anfangen und lange genug aufnehmen:** mindestens eine Stunde vor dem Ingress bis eine Stunde nach dem Egress.
- **Nicht sättigen:** Der hellste Pixel des Zielsterns sollte deutlich unter dem Sättigungswert bleiben (ATR2600M: unter etwa 45 000 ADU). Lieber kürzer belichten oder leicht defokussieren.
- **Stern an derselben Stelle halten:** gute Nachführung; wenn möglich Guiding.
- **FITS-Header:** NINA schreibt Ziel (OBJECT, OBJCTRA, OBJCTDEC), Standort (SITELAT, SITELONG), Zeit (DATE-OBS) und Filter. Die Pipeline braucht diese Angaben.
- **Flats** mit demselben Filter, Fokus und derselben Kameradrehung.
- **Meridian-Flip** möglichst vor die Baseline legen, nicht in den Transit.

Mehr dazu im [Handbuch, Kapitel AstroImageJ](handbuch#6-astroimagej-richtige-header-einstellungen) und unter [Kalibrier-Master](#hilfe:kein-master).
