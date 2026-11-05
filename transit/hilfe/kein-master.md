<!-- gruppe: fehler; reihenfolge: 8; seiten: auswerten; kurz: Kalibrieren findet kein Flat, Bias oder Dark -->
# Kein passender Kalibrier-Master

Ein **Master** ist ein aus vielen Einzelbildern gemitteltes Korrekturbild. Die Pipeline nimmt nur Master, die zu den Lights passen:

| Master | muss passen in |
| --- | --- |
| Bias | Kamera, Gain, Offset, Bildgröße |
| Flat | zusätzlich derselbe Filter |
| Dark | zusätzlich dieselbe Belichtungszeit und Temperatur |

Bei mehreren passenden nimmt sie den mit dem nächsten Datum.

Was tun:

1. Liegt der Master in der **Kalibrierbibliothek** (`[calib] library`) oder im LIGHT-Ordner der Messung?
2. Stimmt der **Filter** im Header des Flats mit dem der Lights überein?
3. Unter **Erweitert**, Kalibrierung, den Pfad zum Master direkt eintragen (Datei oder Ordner).
4. Hat die Kamera die Temperatur nicht gehalten, passt kein Dark: Kalibrierung „Bias + Flat“ wählen.

Siehe auch [Handbuch, Kapitel 18](handbuch#18-kalibrier-master-quellen-und-formate).
