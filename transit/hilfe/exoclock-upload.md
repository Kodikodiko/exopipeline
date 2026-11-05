<!-- gruppe: workflow; reihenfolge: 7; seiten: vergleich; kurz: Datei und Formularwerte zu ExoClock bringen -->
# Auf ExoClock hochladen

Die Pipeline lädt nichts selbst hoch. Sie bereitet die Datei und alle Formularwerte vor, du überträgst sie.

1. Einen Lauf **gültig** setzen (siehe [Den besten Lauf wählen](#hilfe:bester-lauf)). Darunter erscheint der grüne Kasten **ExoClock-Upload**. [Zeig mir den Kasten](#zeige:upcard)
2. **ExoClock öffnen** und anmelden, dort das Upload-Formular öffnen.
3. Jede Zeile links einzeln mit dem Kopierknopf übernehmen. Wichtig: **Time format** JD_UTC, **Time stamp** Exposure start, **Flux format** Flux, **Filter** wie angegeben.
4. **Upload-Ordner öffnen** und die genannte Datei hochladen.
5. Den **Kommentar** kopieren und einfügen. Du kannst ihn vorher ergänzen, z. B. um Wolken.
6. Nach dem Absenden **Bei ExoClock hochgeladen** anhaken. Das steht dann im Logbuch.

> Die Upload-Datei ist absichtlich nicht von der Airmass bereinigt: ExoClock fittet das selbst. Nur ein Meridian-Flip-Sprung ist schon korrigiert.

Wenn ExoClock die Beobachtung ablehnt: [ExoClock lehnt ab](#hilfe:abgelehnt).
