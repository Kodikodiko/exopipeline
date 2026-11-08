<!-- gruppe: workflow; reihenfolge: 3; seiten: auswerten; kurz: Messordner finden und öffnen -->
# Daten laden

Eine **Messung** ist ein Ordner mit den Bildern (Lights) einer Nacht. Die Pipeline liest die Lights nur, sie verändert sie nie.

1. Seite **Auswerten** öffnen. Links steht die Liste aller Messungen, lokal und am NAS.
2. Die Messung anklicken. Nicht dabei? Oben den Planeten eintippen. [Zeig mir die Suche](#zeige:such)
3. Immer noch nicht dabei? **Enter** sucht auch am NAS, oder **Ordner…** öffnet den Windows-Dialog.
4. Rechts erscheinen Planet und Nacht, darunter Hinweise aus dem FITS-Header (z. B. Farbkamera, Filter). Bekannte Hinweise lassen sich mit **×** rechts ausblenden. Das gilt nur für diese Messung, und die Meldung kommt wieder, sobald sich ihr Inhalt ändert. „ausgeblendete Meldungen wieder anzeigen“ holt sie zurück.

## So muss der Ordner aussehen

| Ordner | Inhalt |
| --- | --- |
| `<Messung>\LIGHT` (oder `LIGHTS`, `_work`, `_orig`) | die Original-Lights, werden nur gelesen |
| `<Messung>\RESULT\<lauf>` | alle Ergebnisse eines Laufs |
| `<Messung>\SOLVED` | Kopien mit Plate-Solve, falls die Lights keine Himmelskoordinaten (WCS) hatten |

Kalibrier-Master (Bias, Flat, Dark) sucht die Pipeline in der Kalibrierbibliothek oder direkt im LIGHT-Ordner. Siehe [Kein passender Kalibrier-Master](#hilfe:kein-master).

> Liegen die Lights nur noch am NAS, schreibt die Pipeline die Ergebnisse trotzdem lokal. Die Lights werden vom NAS gelesen.

Danach: [Einen Lauf starten und verfolgen](#hilfe:auswerten).
