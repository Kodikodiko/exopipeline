"""transit gui - the new page (served at /).  The classic page (gui.PAGE) stays available at /klassisch
and with `transit gui --klassisch`; both use the same HTTP interface in gui.py.

Layout: header with areas (Planen, Auswerten, Logbuch, Hilfe) and an activity chip; in "Auswerten" a list of
measurements on the left and a step bar Daten -> Lauf -> Vergleichen -> Hochladen; a run view with all pipeline steps
and the live console; a comparison/upload view; the advanced settings as a side drawer.
"""

PAGE_NEU = r"""<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>transit</title>
<style>
:root{--bg:#f6f7f9;--fg:#1d232b;--fg2:#3d4651;--mut:#5d6773;--card:#fff;--line:#d8dde3;--line2:#eceef1;--soft:#f4f6f8;
 --acc:#1f5fbf;--acc2:#1a4fa0;--accbg:#e3ecf9;--accsoft:#f4f7fc;--accline:#c3cfe0;--ok:#2e7d4f;
 --pg-b:#e2f1e7;--pg-f:#1d6a3f;--py-b:#fbefd2;--py-f:#6f4b00;--pr-b:#f8e1de;--pr-f:#9e2a1e;--pn-b:#eceef1;--pn-f:#4a535e;
 --warnbg:#fff7e3;--warnline:#ecd28f;--warnfg:#5c3e00;--badbg:#fdeeec;--badline:#eab4ad;--logbg:#1d232b;--logfg:#dfe5ec}
@media (prefers-color-scheme:dark){:root{--bg:#14181d;--fg:#e6e9ed;--fg2:#c9d0d8;--mut:#9aa4af;--card:#1c2228;--line:#2f3841;--line2:#262d34;--soft:#20272e;
 --acc:#4d8ae6;--acc2:#8fb6f5;--accbg:#1f2f47;--accsoft:#1a2533;--accline:#35507a;--ok:#3f9e66;
 --pg-b:#1d3a28;--pg-f:#9fd9b4;--py-b:#3d3115;--py-f:#f0cf85;--pr-b:#43221e;--pr-f:#f2aaa0;--pn-b:#2a3138;--pn-f:#c2cad3;
 --warnbg:#2f2814;--warnline:#5e4d1f;--warnfg:#f0d79a;--badbg:#36201d;--badline:#6b322a;--logbg:#0d1013;--logfg:#d6dde5}}
*{box-sizing:border-box}
body{margin:0;font:14px/1.45 "Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--fg)}
a{color:var(--acc2)}
h1,h2,h3{margin:0}
[hidden]{display:none!important}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:20px}
.btn{font:inherit;font-size:14px;font-weight:600;min-height:40px;padding:0 16px;border-radius:8px;border:1px solid var(--acc);background:var(--acc);color:#fff;display:inline-flex;align-items:center;justify-content:center;gap:8px;cursor:pointer;text-decoration:none;white-space:nowrap}
.btn.sec{background:var(--card);color:var(--acc2);border-color:var(--accline)}
.btn.dng{background:var(--card);color:var(--pr-f);border-color:var(--badline)}
.btn.ok{background:var(--ok);border-color:var(--ok)}
.btn.big{min-height:48px;padding:0 24px;font-size:15px}
.btn.sm{min-height:32px;padding:0 10px;font-size:13px}
.btn:disabled{opacity:.5;cursor:default}
.lnk{font:inherit;font-size:13px;background:none;border:none;color:var(--acc2);cursor:pointer;padding:6px 4px;min-height:32px;text-decoration:underline}
.pill{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
.pg{background:var(--pg-b);color:var(--pg-f)}.py{background:var(--py-b);color:var(--py-f)}.pr{background:var(--pr-b);color:var(--pr-f)}.pb{background:var(--accbg);color:var(--acc2)}.pn{background:var(--pn-b);color:var(--pn-f)}
.lbl{display:flex;flex-direction:column;gap:6px;font-size:13px;font-weight:600;color:var(--fg2);min-width:0}
.inp{font:inherit;font-size:14px;font-weight:400;min-height:40px;padding:0 12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);width:100%}
.inp.chg{border:2px solid var(--acc);background:var(--accsoft)}
.hint{font-size:12px;font-weight:400;color:var(--mut)}
.mono{font-family:Consolas,ui-monospace,monospace;font-size:12px}
.row{display:flex;flex-wrap:wrap;gap:12px;align-items:center}
.between{display:flex;flex-wrap:wrap;gap:12px;align-items:baseline;justify-content:space-between}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px 20px}
table{border-collapse:collapse;width:100%}
th{font-size:12px;color:var(--mut);font-weight:600;text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
td{font-size:13px;padding:10px;border-bottom:1px solid var(--line2);vertical-align:middle}
.scroll{overflow-x:auto}
.seg{display:flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.seg button{font:inherit;flex:1;min-height:40px;border:none;border-left:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer;padding:0 8px}
.seg button:first-child{border-left:none}
.seg button.on{background:var(--acc);color:#fff;font-weight:600}
/* header */
header{background:var(--card);border-bottom:1px solid var(--line);padding:0 24px;display:flex;flex-wrap:wrap;align-items:center;gap:8px 24px;min-height:60px;position:sticky;top:0;z-index:5}
.brand b{font-size:20px;letter-spacing:-.01em}
nav.areas{display:flex;gap:4px;flex-wrap:wrap}
nav.areas a{text-decoration:none;padding:8px 14px;border-radius:8px;color:var(--fg2);font-weight:600}
nav.areas a.on{background:var(--accbg);color:var(--acc2);font-weight:700}
#aktiv{margin-left:auto;text-decoration:none;display:inline-flex;align-items:center;gap:10px;padding:6px 12px;border:1px solid var(--accline);border-radius:999px;background:var(--accsoft);color:var(--fg);font-size:13px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--acc);flex:none}
@keyframes pulse{50%{opacity:.35}}
.dot.puls{animation:pulse 1.4s ease-in-out infinite}
/* layout */
.shell{display:flex;flex-wrap:wrap;align-items:stretch;min-height:calc(100vh - 61px)}
aside#side{flex:1 1 280px;max-width:340px;background:var(--card);border-right:1px solid var(--line);padding:20px 16px;display:flex;flex-direction:column;gap:14px}
main{flex:999 1 560px;min-width:0;padding:24px;display:flex;flex-direction:column;gap:20px}
.view{display:flex;flex-direction:column;gap:20px;max-width:1240px;width:100%;margin:0 auto}
.mitem{font:inherit;text-align:left;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:8px;padding:10px 12px;cursor:pointer;display:flex;flex-direction:column;gap:4px;width:100%}
.mitem.on{border:2px solid var(--acc);background:var(--accsoft);padding:9px 11px}
.mhead{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;color:var(--mut);margin-top:4px}
.chip{font:inherit;border:1px solid var(--line);cursor:pointer;padding:6px 10px}
.chip.on{border-color:var(--accline)}
/* stepper */
ol.steps{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px}
ol.steps li a{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;background:var(--card);border:1px solid var(--line);color:var(--fg2);font-weight:600;text-decoration:none;min-height:44px}
ol.steps li.done a{background:var(--pg-b);color:var(--pg-f);border-color:transparent}
ol.steps li.cur a{background:var(--acc);color:#fff;border-color:var(--acc);font-weight:700}
.num{width:24px;height:24px;border-radius:50%;background:var(--pn-b);color:var(--pn-f);display:inline-flex;align-items:center;justify-content:center;font-size:12px;flex:none}
li.done .num{background:var(--ok);color:#fff} li.cur .num{background:#fff;color:var(--acc)}
.note{display:flex;gap:12px;align-items:flex-start;padding:14px 16px;border-radius:10px;background:var(--warnbg);border:1px solid var(--warnline);color:var(--warnfg)}
.note.info{background:var(--accsoft);border-color:var(--accline);color:var(--fg)}
.note.bad{background:var(--badbg);border-color:var(--badline);color:var(--fg)}
.bar{height:8px;border-radius:4px;background:var(--line);overflow:hidden}
.bar>i{display:block;height:100%;background:var(--acc);border-radius:4px}
@keyframes slide{0%{margin-left:-35%}100%{margin-left:100%}}
.bar>i.indet{width:35%;animation:slide 1.6s linear infinite}
.pstep{display:flex;flex-direction:column;gap:6px;padding:12px;overflow-wrap:anywhere;border-radius:8px;border:1px solid var(--line);background:var(--card);min-width:0}
.pstep.cur{border:2px solid var(--acc);background:var(--accsoft);padding:11px}
.pstep.err{border:2px solid var(--pr-f);padding:11px}
.sdot{width:22px;height:22px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;flex:none;font-size:11px;font-weight:700;background:var(--pn-b);color:var(--pn-f)}
pre.log{margin:0;padding:12px;border-radius:8px;background:var(--logbg);color:var(--logfg);white-space:pre-wrap;line-height:1.6;overflow-x:auto;font-family:Consolas,ui-monospace,monospace;font-size:12px;height:340px;min-height:120px;overflow-y:auto;resize:vertical}
.kv{display:grid;grid-template-columns:150px minmax(0,1fr) auto;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid var(--line2)}
.kv>span:first-child{font-size:13px;color:var(--mut)}
tr.sel td{background:var(--accsoft)} tr.best td{background:var(--pg-b)}
tr.click{cursor:pointer}
img.blatt{max-width:100%;border:1px solid var(--line);border-radius:8px;background:#fff}
.bbox{position:relative;display:inline-block;max-width:100%;line-height:0}
.bbox>a{display:block}
.hz{position:absolute;pointer-events:none;border-radius:3px}
.hz.on{background:rgba(37,99,235,.07);outline:1px solid rgba(37,99,235,.35)}
.hz>button{position:absolute;top:2px;right:2px;width:15px;height:15px;padding:0;border:0;border-radius:50%;cursor:pointer;pointer-events:auto;
  font:600 10px/15px system-ui,sans-serif;text-align:center;color:#fff;background:rgba(37,99,235,.75);opacity:0;transition:opacity .15s}
.hz.c>button{width:12px;height:12px;font-size:8.5px;line-height:12px;top:1px;right:1px}
.bbox:hover .hz>button,.hz>button:focus-visible,.hz.on>button{opacity:.85}
.hpop{position:absolute;z-index:30;max-width:340px;padding:10px 12px;border-radius:8px;background:var(--card,#fff);color:var(--fg,#111);
  border:1px solid var(--line);box-shadow:0 6px 24px rgba(0,0,0,.18);font-size:13px;line-height:1.45;text-align:left;pointer-events:none}
.hpop b{display:block;margin-bottom:3px}
.thi{display:inline-block;margin-left:4px;width:14px;height:14px;border-radius:50%;border:0;padding:0;vertical-align:1px;cursor:help;
  font:600 9.5px/14px system-ui,sans-serif;text-align:center;color:var(--acc2,#2563eb);background:var(--accsoft,#e8efff);opacity:.55}
.thi:hover,.thi:focus-visible,.thi.on{opacity:1}
.hpop.fix{position:fixed;z-index:1000}
/* drawer */
#scrim{position:fixed;inset:0;background:rgba(10,14,20,.35);z-index:20}
#drawer{position:fixed;top:0;right:0;bottom:0;width:min(720px,100%);background:var(--card);border-left:1px solid var(--line);z-index:21;display:flex;flex-direction:column;box-shadow:-8px 0 24px rgba(0,0,0,.12)}
#drawer .dbody{flex:1;overflow-y:auto;padding:0 24px}
#drawer section{display:flex;flex-direction:column;gap:12px;padding:18px 0;border-top:1px solid var(--line2)}
#drawer section:first-child{border-top:none}
.sec-h{display:flex;justify-content:space-between;align-items:center;gap:8px}
.sec-h h3{font-size:15px}
.g3{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
#toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);background:var(--fg);color:var(--bg);padding:10px 16px;border-radius:8px;z-index:30;display:flex;gap:12px;align-items:center;max-width:min(680px,92vw);box-shadow:0 4px 16px rgba(0,0,0,.2)}
#toast button{font:inherit;background:none;border:none;color:inherit;text-decoration:underline;cursor:pointer;font-weight:600}
@media (max-width:700px){header{padding:8px 16px}main{padding:16px}aside#side{max-width:none;border-right:none;border-bottom:1px solid var(--line)}.kv{grid-template-columns:110px minmax(0,1fr) auto}}
</style></head><body>
<header>
 <div class="brand row" style="gap:10px;align-items:baseline"><b>transit</b><span class="hint">Transit-Auswertung bis zur ExoClock-Datei</span></div>
 <nav class="areas" aria-label="Bereiche">
  <a href="#/planen" data-area="planen">Planen</a><a href="#/auswerten" data-area="auswerten">Auswerten</a>
  <a href="#/logbuch" data-area="logbuch">Logbuch</a><a href="#/hilfe" data-area="hilfe">Hilfe</a>
 </nav>
 <a id="aktiv" href="#" hidden><span class="dot puls"></span><span id="aktivtxt"></span></a>
</header>
<div class="shell">
 <aside id="side" aria-label="Messungen">
  <div class="between" style="align-items:center"><h2 style="font-size:15px">Messungen</h2>
   <div class="row" style="gap:6px"><button class="btn sec" style="padding:0 10px" aria-label="Liste neu einlesen" title="Liste neu einlesen (lokal und NAS)" onclick="ladeListe(1)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/></svg></button>
   <button class="btn sec" style="padding:0 12px" onclick="ordnerWaehlen()" title="Messordner mit dem Windows-Dialog wählen">Ordner…</button></div></div>
  <label style="position:relative;display:block"><span hidden>Suchen</span>
   <input id="such" class="inp" placeholder="Planet oder Ordner, z. B. KELT-7b" style="padding-left:36px" oninput="S.such=this.value;zeigeListe()" onkeydown="if(event.key==='Enter')nasSuche()">
   <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true" style="position:absolute;left:12px;top:12px;color:var(--mut)"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg></label>
  <div id="filter" role="group" aria-label="Filter" class="row" style="gap:6px"></div>
  <div id="liste" style="display:flex;flex-direction:column;gap:4px"><span class="hint">lade Messungen …</span></div>
 </aside>
 <main>
  <!-- AUSWERTEN -->
  <div class="view" id="v-auswerten" hidden>
   <div id="a-leer" class="card" hidden><h2 style="font-size:18px;margin-bottom:6px">Messung wählen</h2>
    <p class="hint" style="font-size:14px;margin:0">Links eine Messung anklicken, suchen oder mit „Ordner…“ einen Messordner wählen. Ordner mit LIGHT / LIGHTS / _work / _orig; die Originale werden nur gelesen.</p></div>
   <div id="a-inhalt" hidden style="display:flex;flex-direction:column;gap:20px">
    <div class="between" style="align-items:flex-end">
     <div style="display:flex;flex-direction:column;gap:4px;min-width:0"><h1 style="font-size:26px;letter-spacing:-.01em"><span id="a-planet"></span> <span id="a-nacht" style="font-weight:400;color:var(--mut)"></span></h1>
      <span id="a-pfad" class="mono" style="color:var(--mut);overflow-wrap:anywhere"></span></div>
     <button class="btn sec" onclick="oeffneOrdner()"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h6l2 2h10v11H3z"/></svg>RESULT öffnen</button>
    </div>
    <ol class="steps" id="stepper" aria-label="Arbeitsschritte"></ol>
    <div id="hinweise" style="display:flex;flex-direction:column;gap:10px"></div>
    <section class="card" aria-labelledby="h-neu" style="display:flex;flex-direction:column;gap:18px">
     <div class="between"><h2 id="h-neu" style="font-size:18px">Neuer Lauf</h2><span class="hint">Werte aus dem FITS-Header vorgeschlagen</span></div>
     <div class="grid2">
      <label class="lbl">Planet (ExoClock-Schreibweise)<input id="f_planet" class="inp" placeholder="z. B. HAT-P-42b"><span id="f_planet_h" class="hint"></span></label>
      <label class="lbl">Filter (ExoClock-Menü)<select id="f_filter" class="inp"></select><span id="f_filter_h" class="hint"></span></label>
      <div class="lbl" role="group" aria-label="Kalibrierung">Kalibrierung
       <div class="seg" id="f_mode"></div>
       <label style="display:flex;gap:8px;align-items:center;font-weight:400;font-size:13px;color:var(--fg2)"><input id="f_extra" type="checkbox" checked style="width:18px;height:18px;margin:0" onchange="zeigeFuss()"> <span id="f_extra_t"></span></label>
      </div>
      <label class="lbl">Photometrie übernehmen von<select id="f_basis" class="inp" onchange="basisGeaendert()"></select><span class="hint">Cube und Kandidaten eines Laufs mit gleicher Kalibrierung</span></label>
     </div>
     <div class="row" style="justify-content:space-between;padding:12px 14px;border-radius:8px;background:var(--soft);border:1px solid var(--line2)">
      <div class="row" style="gap:8px"><b style="font-size:13px">Erweitert:</b><span id="erw-chips" class="row" style="gap:8px"></span></div>
      <button class="btn sec" onclick="drawerAuf()">Erweitert bearbeiten…</button>
     </div>
     <div class="row" style="justify-content:space-between;border-top:1px solid var(--line2);padding-top:16px">
      <label class="hint row" style="font-size:13px;gap:6px">Name <input id="f_lauf" class="inp mono" style="width:220px;min-height:34px" oninput="zeigeFuss()"> <span id="f_fuss"></span></label>
      <button id="startbtn" class="btn big" onclick="start()"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4v16l13-8z"/></svg><span id="starttxt">Lauf starten</span></button>
     </div>
    </section>
    <section class="card" aria-labelledby="h-laeufe" style="display:flex;flex-direction:column;gap:12px;padding-bottom:8px">
     <div class="between"><h2 id="h-laeufe" style="font-size:18px">Läufe dieser Nacht</h2><a href="#/vergleich">Vergleichen und hochladen</a></div>
     <div class="scroll"><table style="min-width:640px"><thead><tr><th>Lauf</th><th>Zustand</th><th>O-C</th><th title="Rauschen außerhalb des Transits">OOT-RMS</th><th title="rotes Rauschen, 1 = weiß">β</th><th title="ExoClock-Kriterium: grün unter 2, gelb 2–3, rot ab 3">Drift</th><th></th></tr></thead><tbody id="laeufe"></tbody></table></div>
    </section>
   </div>
  </div>

  <!-- LAUF -->
  <div class="view" id="v-lauf" hidden style="max-width:1180px">
   <a href="#/auswerten" id="l-zurueck" style="font-size:13px"></a>
   <div class="between" style="align-items:flex-end">
    <div style="display:flex;flex-direction:column;gap:4px"><h1 style="font-size:26px">Lauf <span id="l-name"></span> <span id="l-pill"></span></h1><span id="l-sub" class="hint" style="font-size:13px"></span></div>
    <div class="row" style="gap:8px"><button class="btn sec" onclick="oeffneOrdner(S.lauf)">Lauf-Ordner öffnen</button>
     <a class="btn" id="l-ergebnis" href="#/vergleich" hidden>Ergebnis ansehen</a>
     <button class="btn dng" id="l-stop" onclick="abbrechen()" hidden>Abbrechen</button></div>
   </div>
   <div id="l-fehler"></div>
   <section class="card" aria-labelledby="h-ablauf" style="display:flex;flex-direction:column;gap:16px">
    <div class="between"><h2 id="h-ablauf" style="font-size:18px">Ablauf</h2><span id="l-eta" class="hint" style="font-size:13px"></span></div>
    <ol id="l-steps" style="list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px"></ol>
    <div id="l-akt"></div>
   </section>
   <div class="row" style="align-items:stretch;gap:20px">
    <section class="card" aria-labelledby="h-log" style="flex:999 1 520px;min-width:0;display:flex;flex-direction:column;gap:10px">
     <div class="between"><h2 id="h-log" style="font-size:16px">Protokoll (live)</h2><span id="l-hb" class="hint row" style="gap:6px"></span></div>
     <pre class="log" id="l-log"></pre>
     <a id="l-runlog" href="#" target="_blank" style="font-size:13px">Ganzes Protokoll anzeigen (run.log)</a>
    </section>
    <section class="card" aria-labelledby="h-warten" style="flex:1 1 280px;display:flex;flex-direction:column;gap:12px">
     <h2 id="h-warten" style="font-size:16px">Während du wartest</h2>
     <label style="display:flex;gap:10px;align-items:center;font-size:14px"><input id="notify" type="checkbox" style="width:18px;height:18px;margin:0" onchange="notifyUmschalten(this)"> Benachrichtigen, wenn fertig</label>
     <span class="hint" style="font-size:13px">Die Seite kann geschlossen werden, der Lauf läuft weiter. Beim nächsten Öffnen steht er unter „Läufe“.</span>
     <div id="l-folge"></div>
    </section>
   </div>
  </div>

  <!-- VERGLEICH -->
  <div class="view" id="v-vergleich" hidden>
   <a href="#/auswerten" id="v-zurueck" style="font-size:13px"></a>
   <h1 style="font-size:26px">Läufe vergleichen</h1>
   <div id="v-leer" class="card" hidden><p style="margin:0">Noch kein fertiger Lauf. <a href="#/auswerten">Lauf starten</a></p></div>
   <div id="v-inhalt" style="display:flex;flex-direction:column;gap:20px">
    <section class="card" aria-labelledby="h-kz" style="display:flex;flex-direction:column;gap:12px">
     <div class="between"><h2 id="h-kz" style="font-size:18px">Kennzahlen</h2><span class="hint" style="font-size:13px">Auswahl nur nach Datenqualität, nie nach der Literatur-Tiefe</span></div>
     <div class="scroll"><table style="min-width:860px"><thead><tr><th>Lauf</th><th>Kalibr.</th><th>O-C</th><th title="Rauschen außerhalb des Transits">OOT-RMS</th><th title="rotes Rauschen, 1 = weiß">β</th><th title="ExoClock-Kriterium">Drift</th><th>Rp/Rs</th><th>Ausreißer</th><th>Prüfungen</th><th></th></tr></thead><tbody id="kz"></tbody></table></div>
    </section>
    <div class="row" style="align-items:flex-start;gap:20px">
     <section class="card" aria-labelledby="h-blatt" style="flex:999 1 560px;min-width:0;display:flex;flex-direction:column;gap:12px">
      <div class="between" style="align-items:center"><h2 id="h-blatt" style="font-size:18px"></h2>
       <div role="tablist" aria-label="Ansicht" class="row" style="gap:4px" id="tabs"></div></div>
      <div id="blatt"></div>
     </section>
     <section class="card" aria-labelledby="h-pruef" style="flex:1 1 320px;display:flex;flex-direction:column;gap:12px">
      <h2 id="h-pruef" style="font-size:18px">Prüfungen</h2>
      <ul id="pruef" style="list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px;font-size:13px"></ul>
      <div id="gueltigbox" style="border-top:1px solid var(--line2);padding-top:14px;display:flex;flex-direction:column;gap:10px"></div>
     </section>
    </div>
    <section class="card" id="upcard" aria-labelledby="h-up" style="display:flex;flex-direction:column;gap:16px;border:2px solid var(--ok)" hidden>
     <div class="between" style="align-items:center">
      <div style="display:flex;flex-direction:column;gap:2px"><h2 id="h-up" style="font-size:18px">ExoClock-Upload <span id="up-lauf" class="pill pg" style="vertical-align:middle"></span></h2>
       <span class="hint" style="font-size:13px">Werte genau so ins Formular übernehmen. Jede Zeile hat einen Kopierknopf.</span></div>
      <div class="row" style="gap:8px"><button class="btn sec" onclick="oeffneOrdner()">Upload-Ordner öffnen</button>
       <a class="btn" href="https://www.exoclock.space/" target="_blank" rel="noopener">ExoClock öffnen <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M18 14v6H4V6h6"/></svg></a></div>
     </div>
     <div class="row" style="align-items:flex-start;gap:24px">
      <div id="up-felder" style="flex:1 1 460px;min-width:0"></div>
      <div style="flex:1 1 420px;min-width:0;display:flex;flex-direction:column;gap:8px">
       <label for="up-kom" style="font-size:13px;font-weight:600;color:var(--fg2)">Kommentar für ExoClock (Englisch, editierbar)</label>
       <textarea id="up-kom" rows="7" style="font:13px/1.5 Consolas,ui-monospace,monospace;padding:10px 12px;border:1px solid var(--line);border-radius:8px;resize:vertical;color:var(--fg);background:var(--card)"></textarea>
       <div class="row" style="gap:8px"><button class="btn" onclick="kopiere(document.getElementById('up-kom').value,'Kommentar kopiert')">Kommentar kopieren</button><button class="btn sec" onclick="ladeUpload(true)">Neu erzeugen</button></div>
      </div>
     </div>
     <div class="row" style="padding:12px 14px;border-radius:8px;background:var(--soft)">
      <label style="display:flex;gap:10px;align-items:center;font-size:14px;font-weight:600"><input id="up-done" type="checkbox" style="width:18px;height:18px;margin:0" onchange="hochgeladen(this.checked)"> Bei ExoClock hochgeladen</label>
      <span id="up-done-h" class="hint" style="font-size:13px"></span>
     </div>
    </section>
   </div>
  </div>

  <!-- PLANEN -->
  <div class="view" id="v-planen" hidden>
   <h1 style="font-size:26px">Beobachtungsvorschlag</h1>
   <section class="card" style="display:flex;flex-direction:column;gap:12px">
    <div class="row" style="align-items:flex-end">
     <label class="lbl">Nächte<input id="pl_n" class="inp" type="number" value="3" min="1" max="7" style="width:90px"></label>
     <label class="lbl">pro Nacht<input id="pl_top" class="inp" type="number" value="10" min="1" max="50" style="width:90px"></label>
     <label style="display:flex;gap:8px;align-items:center;min-height:40px"><input id="pl_wx" type="checkbox" checked style="width:18px;height:18px;margin:0"> Wetter (Open-Meteo)</label>
     <label style="display:flex;gap:8px;align-items:center;min-height:40px"><input id="pl_gaia" type="checkbox" style="width:18px;height:18px;margin:0"> Vergleichssterne zählen (Gaia, langsamer)</label>
     <button id="pl_btn" class="btn" onclick="planRechnen()">Berechnen</button><span id="pl_msg" class="hint"></span>
    </div>
    <div class="hint">Transits aus der ExoClock-Datenbank, vollständig in der Dunkelheit über der Mindesthöhe ([planning] in der Konfiguration), tief genug für das Teleskop. Score = Priorität × erwartete Genauigkeit × Wetter × Abzüge für Hinweise. Zeiten lokal.</div>
    <div id="plan"></div>
   </section>
  </div>

  <!-- LOGBUCH -->
  <div class="view" id="v-logbuch" hidden>
   <div class="between" style="align-items:flex-end"><h1 style="font-size:26px">Logbuch</h1>
    <label class="lbl" style="width:260px"><span hidden>Filtern</span><input id="lb_such" class="inp" placeholder="Planet filtern" oninput="zeigeLogbuch()"></label></div>
   <section class="card"><div class="scroll"><table style="min-width:820px"><thead><tr><th>Planet</th><th>Nacht</th><th>Lauf</th><th>Status</th><th>O-C</th><th>Tiefe</th><th>Drift</th><th>Upload-Datei</th></tr></thead><tbody id="lb"></tbody></table></div></section>
  </div>

  <!-- HILFE -->
  <div class="view" id="v-hilfe" hidden style="max-width:900px">
   <h1 style="font-size:26px">Hilfe</h1>
   <section class="card" style="display:flex;flex-direction:column;gap:12px">
    <h2 style="font-size:18px">Ablauf in vier Schritten</h2>
    <ol style="margin:0;padding-left:20px;display:flex;flex-direction:column;gap:8px">
     <li><b>Daten:</b> Messung links wählen. Hinweise aus dem FITS-Header (Farbkamera, Filter) stehen über dem Formular.</li>
     <li><b>Lauf starten:</b> Planet, Filter und Kalibrierung prüfen, Start. Mit dem Haken wird eine zweite Kalibrierung gleich danach gerechnet. Der Fortschritt jedes Schritts ist unter „Details“ zu sehen.</li>
     <li><b>Vergleichen:</b> Läufe nach Datenqualität vergleichen (OOT-RMS, β, Prüfungen) und den besten als gültig setzen.</li>
     <li><b>Hochladen:</b> Felder einzeln kopieren, Kommentar übernehmen, bei ExoClock hochladen und abhaken.</li>
    </ol>
   </section>
   <section class="card" style="display:flex;flex-direction:column;gap:10px">
    <h2 style="font-size:18px">Mehr</h2>
    <a href="/handbuch" target="_blank">Handbuch (HANDBUCH.md)</a>
    <a href="/klassisch">Klassische Oberfläche öffnen</a>
    <span class="hint" style="font-size:13px">Die klassische Oberfläche bleibt immer erreichbar: unter /klassisch oder mit <span class="mono">transit gui --klassisch</span>.</span>
   </section>
  </div>
 </main>
</div>

<div id="scrim" hidden onclick="drawerZu()"></div>
<div id="drawer" hidden role="dialog" aria-modal="true" aria-labelledby="h-erw">
 <div style="padding:20px 24px 14px;display:flex;flex-direction:column;gap:12px;border-bottom:1px solid var(--line)">
  <div class="between" style="align-items:center"><h2 id="h-erw" style="font-size:20px">Erweitert</h2>
   <button class="btn sec" style="padding:0 10px" aria-label="Schließen" onclick="drawerZu()"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button></div>
  <nav aria-label="Gruppen" id="erw-nav" class="row" style="gap:6px"></nav>
 </div>
 <div class="dbody" id="erw-body">
  <section id="g-kal" data-g="kal"><div class="sec-h"><h3>Kalibrierung <span class="gz"></span></h3><button class="lnk" onclick="gruppeReset('kal')">Zurücksetzen</button></div>
   <label class="lbl">Flat (Pfad)<input class="inp" data-k="flat" placeholder="automatisch: passender Master aus der Bibliothek"></label>
   <div class="g3"><label class="lbl">Bias<input class="inp" data-k="bias" placeholder="automatisch"></label><label class="lbl">Dark<input class="inp" data-k="dark" placeholder="automatisch"></label>
    <label class="lbl">Prozesse<input class="inp" data-k="workers" type="number" min="1" max="64" placeholder="auto"></label></div>
   <span class="hint">Leer: passende Master aus der Kalibrierbibliothek (Kamera, Größe, Filter; gebinnte Lights werden unterstützt).</span></section>
  <section id="g-kam" data-g="kam"><div class="sec-h"><h3>Kamera &amp; Gaia <span class="gz"></span></h3><button class="lnk" onclick="gruppeReset('kam')">Zurücksetzen</button></div>
   <div class="g3"><label class="lbl">Farbkamera<select class="inp" data-k="farbkamera"><option value="">automatisch (BAYERPAT)</option><option value="ja">ja: 2×2-Superpixel</option><option value="nein">nein: wie Mono</option></select><span class="hint">Bayer-Bilder → 2×2-Superpixel</span></label>
    <label class="lbl">Gaia-Quelle<select class="inp" data-k="gaia_quelle"><option value="">Standard</option><option value="vizier">VizieR (CDS)</option><option value="esa">ESA-Gaia-Archiv</option></select><span class="hint" id="h-gaia"></span></label></div></section>
  <section id="g-ver" data-g="ver"><div class="sec-h"><h3>Vergleichssterne <span class="gz"></span></h3><button class="lnk" onclick="gruppeReset('ver')">Zurücksetzen</button></div>
   <div class="g3"><label class="lbl">hell ΔG<input class="inp" data-k="dmag_bright" type="number" step="0.1"></label><label class="lbl">schwach ΔG<input class="inp" data-k="dmag_faint" type="number" step="0.1"></label>
    <label class="lbl">Nachbar px<input class="inp" data-k="neighbour_px" type="number"></label><label class="lbl">Rand px<input class="inp" data-k="edge_px" type="number"></label></div>
   <span class="hint">Fenster für Gaia-Vergleichssterne relativ zum Ziel. Ampel: RUWE über 1,4 (Doppelstern?), Gaia VARIABLE, Transitfenster-Test über 3 σ.</span>
   <div id="kand"></div></section>
  <section id="g-ape" data-g="ape"><div class="sec-h"><h3>Apertur <span class="gz"></span></h3><button class="lnk" onclick="gruppeReset('ape')">Zurücksetzen</button></div>
   <div class="g3"><label class="lbl">Modus<select class="inp" data-k="aperture_mode"><option value="">Standard</option><option value="beides">beides</option><option value="fest">fest</option><option value="variabel">mitwachsend</option></select></label>
    <label class="lbl">von × FWHM<input class="inp" data-k="ap_min" type="number" step="0.5"></label><label class="lbl">bis × FWHM<input class="inp" data-k="ap_max" type="number" step="0.5"></label>
    <label class="lbl">Ring innen,außen px<input class="inp" data-k="annulus"></label></div>
   <span class="hint" id="ap-vorschau">Fest: ein Radius für die ganze Nacht. Mitwachsend: Radius = k × FWHM in jedem Bild. Bei „beides“ treten beide gegeneinander an; gewählt wird nach dem Rauschen außerhalb des Transits.</span></section>
  <section id="g-fit" data-g="fit"><div class="sec-h"><h3>Fit &amp; Ausreißer <span class="gz"></span></h3><button class="lnk" onclick="gruppeReset('fit')">Zurücksetzen</button></div>
   <div class="lbl" role="group" aria-label="Ausreißer entfernen">Ausreißer entfernen<div class="seg" id="seg-aus"></div>
    <span class="hint">Wolken, Flugzeug, Wind: betroffene Bilder werden entfernt und der Fit wiederholt (Liste in summary.md und ausreisser.json).</span></div>
   <div class="g3"><label class="lbl">Detrending<select class="inp" data-k="airmass_order"><option value="">Standard</option><option value="1">linear</option><option value="2">quadratisch</option></select></label>
    <label class="lbl">Meridian-Flip<select class="inp" data-k="flip"><option value="">Standard</option><option value="prior">Prior aus Vergleichssternen</option><option value="free">frei</option><option value="none">ignorieren</option></select></label>
    <label class="lbl">Geometrie<select class="inp" data-k="fix_geometry"><option value="">Standard</option><option value="true">fest (ExoClock)</option><option value="false">frei</option></select></label>
    <label class="lbl">Airmass-Grenze<input class="inp" data-k="airmass_max" type="number" step="0.1"></label>
    <label class="lbl">MCMC-Schritte<input class="inp" data-k="mcmc_steps" type="number" step="1000"></label>
    <label class="lbl">Symmetrie-Gewicht<input class="inp" data-k="symmetry_weight" type="number" step="0.5"></label></div>
   <span class="hint">Quadratisch nur, wenn der BIC besser wird. Die Airmass-Grenze schneidet Randpunkte ab (Baseline vor Ingress mindestens 30 min lassen).</span></section>
 </div>
 <div style="padding:16px 24px;border-top:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:12px;background:var(--soft);flex-wrap:wrap">
  <button class="lnk" onclick="allesReset()">Alles auf Standard</button>
  <div class="row" style="gap:12px"><label style="display:flex;gap:8px;align-items:center;font-size:13px"><input id="merken" type="checkbox" style="width:18px;height:18px;margin:0"> als meine Vorgabe merken</label>
   <button class="btn" onclick="drawerZu(true)">Übernehmen</button></div>
 </div>
</div>
<div id="toast" hidden></div>

<script>
const H={'Content-Type':'application/json','X-Transit':'1'};
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const komma=(v,d)=>v==null||v===''||isNaN(+v)?'':(+v).toFixed(d).replace('.',',');
const MODI=[['f','Flat'],['bf','Bias + Flat'],['bfd','+ Dark'],['raw','keine']];
const MODNAME={f:'Flat',bf:'Bias + Flat',bfd:'Bias + Flat + Dark',raw:'ohne Kalibrierung'};
const SCHRITT={inventory:'Inventur',solve:'Plate-Solve',calibrate:'Kalibrieren',cube:'Photometrie',compsearch:'Vergleichssterne',fit:'Fit (MCMC)',export:'Export',report:'Ergebnisblatt'};
const STEPS=['inventory','calibrate','cube','compsearch','fit','export','report'];
const GRUPPEN={kal:['flat','bias','dark','workers'],kam:['farbkamera','gaia_quelle'],ver:['dmag_bright','dmag_faint','neighbour_px','edge_px','exclude'],ape:['aperture_mode','ap_min','ap_max','annulus'],
  fit:['ausreisser_sigma','airmass_order','flip','fix_geometry','airmass_max','mcmc_steps','symmetry_weight']};
const GNAME={kal:'Kalibrierung',kam:'Kamera & Gaia',ver:'Vergleichssterne',ape:'Apertur',fit:'Fit & Ausreißer'};
const ELBL={flat:'Flat',bias:'Bias',dark:'Dark',workers:'Prozesse',farbkamera:'Farbkamera',gaia_quelle:'Gaia-Quelle',dmag_bright:'hell ΔG',dmag_faint:'schwach ΔG',neighbour_px:'Nachbar',edge_px:'Rand',
  aperture_mode:'Apertur',ap_min:'Apertur von',ap_max:'Apertur bis',annulus:'Ring',ausreisser_sigma:'Ausreißer',airmass_order:'Detrending',flip:'Flip',fix_geometry:'Geometrie',airmass_max:'Airmass-Grenze',mcmc_steps:'MCMC',symmetry_weight:'Symmetrie',exclude:'ohne Sterne'};
const AUS=[['','aus'],['4','wenige > 4 σ'],['3','normal > 3 σ'],['2.5','viele > 2,5 σ']];
const ICHK='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg>';
const ICOPY='<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/></svg>';
const IWARN='<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" style="flex:none;margin-top:1px"><path d="M12 3 2 20h20z"/><path d="M12 10v4"/><path d="M12 17h.01"/></svg>';
const IINFO='<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true" style="flex:none;margin-top:1px"><circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><path d="M12 7h.01"/></svg>';

let S={liste:[],filter:'alle',such:'',pfad:null,M:null,lauf:null,L:null,erw:{},mode:null,sel:null,tab:'kurve',K:null,laufend:new Set(),lb:[],undo:null};
function lsGet(k,d){try{const v=localStorage.getItem(k);return v==null?d:JSON.parse(v);}catch(e){return d;}}
function lsSet(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}}
async function api(url,body){
  let r; try{ r=await fetch(url,body===undefined?{}:{method:'POST',headers:H,body:JSON.stringify(body)}); }
  catch(e){ return {fehler:'Keine Antwort von der Oberfläche (Fenster „Transit GUI“ noch offen?)'}; }
  let j={}; try{j=await r.json();}catch(e){j={fehler:'Antwort nicht lesbar ('+r.status+')'};}
  return j;
}
let toastT=null;
function toast(msg,aktion,fn){ const t=$('toast'); t.innerHTML=`<span>${esc(msg)}</span>`+(aktion?`<button id="toastbtn">${esc(aktion)}</button>`:''); t.hidden=false;
  if(aktion) $('toastbtn').onclick=()=>{t.hidden=true;fn();};
  clearTimeout(toastT); toastT=setTimeout(()=>t.hidden=true,aktion?10000:5000); }
const sep=p=>String(p||'').includes('\\')?'\\':'/';
const datei=(pfad,lauf,f)=>'/datei?pfad='+encodeURIComponent(pfad+sep(pfad)+'RESULT'+sep(pfad)+lauf+sep(pfad)+f);
const mmss=s=>{ if(s==null||isNaN(s))return ''; s=Math.max(0,Math.round(s)); return s>=3600?`${Math.floor(s/3600)}:${String(Math.floor(s%3600/60)).padStart(2,'0')} h`:`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`; };
const minuten=s=>s<90?'< 1 min':'~'+Math.round(s/60)+' min';
const uhr=t=>new Date(t*1000).toLocaleTimeString('de-AT',{hour:'2-digit',minute:'2-digit'});

// ------------------------------------------------------------------ routing
function route(){
  const h=location.hash.replace(/^#\/?/,'').split('/');
  let v=h[0]||'auswerten';
  if(!['auswerten','lauf','vergleich','planen','logbuch','hilfe'].includes(v)) v='auswerten';
  if(v==='lauf'){ S.lauf=decodeURIComponent(h.slice(1).join('/')||''); if(!S.lauf) v='auswerten'; }
  document.querySelectorAll('.view').forEach(e=>e.hidden=e.id!=='v-'+v);
  const area=['lauf','vergleich'].includes(v)?'auswerten':v;
  document.querySelectorAll('nav.areas a').forEach(a=>{a.classList.toggle('on',a.dataset.area===area); if(a.dataset.area===area)a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current');});
  $('side').hidden=v!=='auswerten';
  S.view=v;
  if(v==='lauf') ladeLauf();
  if(v==='vergleich') zeigeVergleich();
  if(v==='planen' && !window.PLAN) planLaden();
  if(v==='logbuch') ladeLogbuch();
  window.scrollTo(0,0);
}
window.addEventListener('hashchange',route);

// ------------------------------------------------------------------ list of measurements
async function ladeListe(neu){
  if(neu) $('liste').innerHTML='<span class="hint">lese Liste neu (lokal und NAS) …</span>';
  const r=await api('/api/messungen2'+(neu?'?neu=1':''));
  S.liste=Array.isArray(r)?r:[]; zeigeListe();
}
const norm=s=>String(s||'').toLowerCase().replace(/[^a-z0-9]/g,'');
function mstatus(m){
  if(m.zustand==='laeuft') return '<span class="pill pb">läuft</span>';
  if(m.zustand==='wartet') return '<span class="pill pb">wartet</span>';
  if(m.zustand==='fehler') return '<span class="pill pr">Fehler</span>';
  if(m.gueltig) return m.hochgeladen?'<span class="pill pg">hochgeladen</span>':'<span class="pill pg">gültig</span>';
  if(m.ausgewertet) return `<span class="pill pn">${m.ausgewertet} ${m.ausgewertet===1?'Lauf':'Läufe'}</span>`;
  return '<span class="pill py">neu</span>';
}
function zeigeListe(){
  const F={alle:['Alle',()=>true],neu:['Neu',m=>!m.ausgewertet],offen:['Ohne gültig',m=>m.ausgewertet&&!m.gueltig],gueltig:['Gültig',m=>!!m.gueltig]};
  $('filter').innerHTML=Object.entries(F).map(([k,[t,f]])=>`<button class="pill chip ${S.filter===k?'pb on':'pn'}" aria-pressed="${S.filter===k}" onclick="S.filter='${k}';zeigeListe()">${t} ${S.liste.filter(f).length}</button>`).join('');
  const q=norm(S.such);
  const ms=S.liste.filter(F[S.filter][1]).filter(m=>!q||norm(m.planet).includes(q)||norm(m.name).includes(q));
  if(!ms.length){ $('liste').innerHTML=`<span class="hint">${S.liste.length?'Nichts gefunden.':'Keine Messungen im Arbeitsordner.'}</span>`+(q?' <button class="btn sec sm" onclick="nasSuche()">Lokal und am NAS suchen</button>':''); return; }
  let h='',akt='';
  for(const m of ms){
    const mon=m.nacht?new Date(m.nacht+'T12:00').toLocaleDateString('de-AT',{month:'long',year:'numeric'}):'ohne Datum';
    if(mon!==akt){ h+=`<div class="mhead">${esc(mon)}</div>`; akt=mon; }
    const sub=[m.nacht,m.n_lights?m.n_lights+' Lights':'Lights '+(m.lights_ort||'fehlen'),m.ort].filter(Boolean).join(' · ');
    h+=`<button class="mitem ${S.pfad===m.pfad?'on':''}" ${S.pfad===m.pfad?'aria-current="true"':''} data-p="${esc(m.pfad)}" onclick="waehle(this.dataset.p)" title="${esc(m.pfad)}">
      <span class="between" style="gap:8px;align-items:center"><b>${esc(m.planet)}</b>${mstatus(m)}</span><span class="hint">${esc(sub)}</span></button>`;
  }
  $('liste').innerHTML=h;
}
async function nasSuche(){
  const n=$('such').value.trim(); if(!n)return;
  $('liste').innerHTML='<span class="hint">suche lokal und am NAS …</span>';
  const r=await api('/api/suche?name='+encodeURIComponent(n));
  if(r.fehler){ toast(r.fehler); zeigeListe(); return; }
  for(const t of r.treffer||[]) if(!S.liste.some(m=>m.pfad===t.pfad)) S.liste.push(Object.assign({planet:t.name,nacht:''},t));
  zeigeListe(); if((r.treffer||[]).length===1) waehle(r.treffer[0].pfad);
  else if(!(r.treffer||[]).length) toast('Nichts gefunden (lokal und NAS)'+(r.hinweis?': '+r.hinweis:''));
}
async function ordnerWaehlen(){
  toast('Ordnerdialog offen (eventuell hinter dem Browser) …');
  const r=await api('/api/ordner',{});
  if(r.fehler){ toast(r.fehler); return; }
  if(!r.pfad) return;
  if(!S.liste.some(m=>m.pfad===r.pfad)) S.liste.unshift(Object.assign({planet:r.name,nacht:''},r));
  waehle(r.pfad);
}

// ------------------------------------------------------------------ one measurement
async function waehle(p){
  S.pfad=p; lsSet('transit.pfad',p); S.sel=null; S.K=null; S.erw.exclude=undefined;
  if(S.view!=='auswerten') location.hash='#/auswerten';
  zeigeListe();
  $('a-leer').hidden=true; $('a-inhalt').hidden=false; $('a-planet').textContent='…';
  const M=await api('/api/messung2?pfad='+encodeURIComponent(p));
  if(M.fehler){ toast(M.fehler); $('a-inhalt').hidden=true; $('a-leer').hidden=false; return; }
  if(S.pfad!==p) return;
  S.M=M; S.mode=M.vorgaben.mode||'bf';
  zeigeKopf(); zeigeFormular(); zeigeLaeufe(); zeigeStepper();
  if(S.view==='vergleich') zeigeVergleich();
}
function zeigeKopf(){
  const M=S.M; $('a-planet').textContent=M.planet; $('a-nacht').textContent=M.nacht?'· Nacht '+M.nacht:''; $('a-pfad').textContent=M.pfad;
  const zur='← '+M.planet+(M.nacht?' · Nacht '+M.nacht:''); $('l-zurueck').textContent=zur; $('v-zurueck').textContent=zur;
  $('hinweise').innerHTML=(M.hinweise||[]).map(n=>`<div role="note" class="note ${n.level==='info'?'info':''}">${n.level==='info'?IINFO:IWARN}<div style="display:flex;flex-direction:column;gap:2px"><b>${esc(n.titel)}</b><span style="font-size:13px">${esc(n.text)}</span></div></div>`).join('');
}
function zeigeStepper(){
  const L=S.M?S.M.laeufe:[]; const fertig=L.some(l=>l.oc!==undefined), g=L.find(l=>l.status==='gueltig'&&l.oc!==undefined);
  const done=[!!S.M, fertig, !!g, !!(g&&g.hochgeladen)];
  const cur=done.indexOf(false);
  const T=[['Daten geprüft','#/auswerten'],['Lauf starten','#/auswerten'],['Vergleichen','#/vergleich'],['Hochladen','#/vergleich']];
  $('stepper').innerHTML=T.map(([t,h],i)=>`<li class="${done[i]?'done':i===cur?'cur':''}"><a href="${h}" ${i===cur?'aria-current="step"':''}><span class="num">${done[i]?ICHK:i+1}</span>${t}</a></li>`).join('');
}
function zeigeFormular(){
  const M=S.M, k=M.kopf||{};
  $('f_planet').value=k.planet||M.planet||'';
  const ex=M.exoclock||{};
  $('f_planet_h').innerHTML=ex.gefunden===true?`<span style="color:var(--pg-f)">In ExoClock gefunden${ex.prio?' · Priorität '+esc(ex.prio):''}</span>`:ex.gefunden===false?'<span style="color:var(--py-f)">Nicht in der ExoClock-Liste: Schreibweise prüfen (z. B. TOI-628b)</span>':'Vorschlag aus dem FITS-Header (OBJECT)';
  $('f_filter').innerHTML=M.filter_menu.map(f=>`<option ${f===k.filter_exoclock?'selected':''}>${esc(f)}</option>`).join('');
  $('f_filter_h').textContent=k.filter_header?`Header FILTER = ${k.filter_header}`+(k.filter_exoclock?'':', bitte prüfen'):'Header ohne FILTER, bitte prüfen';
  zeigeModus(); fuelleBasis(); $('f_lauf').value=''; zeigeErwChips(); zeigeFuss();
}
function zeigeModus(){
  $('f_mode').innerHTML=MODI.map(([k,t])=>`<button class="${S.mode===k?'on':''}" aria-pressed="${S.mode===k}" onclick="S.mode='${k}';zeigeModus();fuelleBasis();zeigeFuss()">${t}</button>`).join('');
  const x=S.mode==='f'?'bf':'f'; $('f_extra_t').textContent=`zusätzlich „${MODNAME[x]}“ starten (zum Vergleichen)`; $('f_extra').dataset.mode=x;
}
function sparSek(l){ let s=0; for(const st of l.schritte||[]) if(['calibrate','cube'].includes(st.name)&&st.state==='fertig') s+=st.duration_s||0; return s; }
function fuelleBasis(){
  const alt=$('f_basis').value, L=(S.M.laeufe||[]).filter(l=>l.zustand!=='wartet');
  $('f_basis').innerHTML='<option value="">neu messen</option>'+L.map(l=>{ const same=!l.modus||l.modus===S.mode, sp=sparSek(l);
    return `<option value="${esc(l.lauf)}">${esc(l.lauf)}${l.modus?' ('+esc(MODNAME[l.modus]||l.modus)+')':''}${same&&sp>60?', spart ca. '+Math.round(sp/60)+' min':same?'':', nur Gaia/Inventur'}</option>`;}).join('');
  if([...$('f_basis').options].some(o=>o.value===alt)) $('f_basis').value=alt;
}
function basisGeaendert(){ S.K=null; S.erw.exclude=undefined; zeigeFuss(); if(!$('drawer').hidden) ladeKand(); }
function laufBasis(){ const d=new Date(),z=n=>String(n).padStart(2,'0'); return `gui_${d.getFullYear()}${z(d.getMonth()+1)}${z(d.getDate())}_${z(d.getHours())}${z(d.getMinutes())}`; }
function schaetzung(){ // seconds for one run, from the finished runs of this measurement
  const med={}; for(const l of S.M.laeufe||[]) for(const st of l.schritte||[]) if(st.state==='fertig'&&st.duration_s) (med[st.name]=med[st.name]||[]).push(st.duration_s);
  let s=0,n=0; for(const k of STEPS){ const v=(med[k]||[]).sort((a,b)=>a-b); if(v.length){ s+=v[Math.floor(v.length/2)]; n++; } }
  return n>=4?s:null; }
function zeigeFuss(){
  const extra=$('f_extra').checked, n=extra?2:1;
  $('f_lauf').placeholder=laufBasis()+'_'+S.mode;
  const w=S.erw.workers||S.M.vorgaben.workers; let sch=schaetzung();
  if(sch&&$('f_basis').value){ const b=S.M.laeufe.find(l=>l.lauf===$('f_basis').value); if(b&&b.modus===S.mode) sch=Math.max(60,sch-sparSek(b)); }
  $('f_fuss').textContent=(extra?`und …_${$('f_extra').dataset.mode} danach`:'')+` · ${w} Prozesse`+(sch?` · Dauer ca. ${Math.round(sch*n/60)} min`:'');
  $('starttxt').textContent=n===2?'2 Läufe starten':'Lauf starten';
}
function zeigeLaeufe(){
  const L=[...(S.M.laeufe||[])].sort((a,b)=>String(b.lauf).localeCompare(String(a.lauf)));
  if(!L.length){ $('laeufe').innerHTML='<tr><td colspan="7" class="hint">Noch keine Läufe.</td></tr>'; return; }
  $('laeufe').innerHTML=L.map(l=>{
    const fertig=l.oc!==undefined;
    return `<tr><td><b>${esc(l.lauf)}</b> <span class="hint">${esc(MODNAME[l.modus]||l.modus||'')}</span> ${l.status==='gueltig'?'<span class="pill pg">gültig</span>':''}</td>
      <td>${zustandPill(l)}</td><td>${fertig?ocTxt(l):''}</td><td>${fertig?komma(l.oot_rms,2)+' ppt':''}</td><td>${fertig?komma(l.beta,2):''}</td><td>${fertig?ampel(l.drift):''}</td>
      <td style="text-align:right">${fertig?`<a href="#/vergleich" onclick="S.sel='${esc(l.lauf)}'">Ergebnis</a>`:`<a href="#/lauf/${encodeURIComponent(l.lauf)}">Details</a>`}</td></tr>`; }).join('');
}
function zustandPill(l){
  if(l.zustand==='laeuft'){ const st=SCHRITT[l.schritt]||l.schritt||''; return `<span class="pill pb">${esc(st)}${l.task?' · '+esc(l.task):''}${l.prozent!=null&&l.task?' '+Math.round(l.prozent)+' %':''}</span>`+(l.heartbeat_alter>120?' <span class="pill pr">hängt?</span>':''); }
  if(l.zustand==='wartet') return '<span class="pill pb">wartet</span>';
  if(l.zustand==='fehler') return `<span class="pill pr" title="${esc(l.fehler||'')}">Fehler</span>`;
  if(l.oc!==undefined) return '<span class="pill pn">fertig</span>'+(l.hochgeladen?' <span class="pill pg">hochgeladen</span>':'');
  return `<span class="pill pn">${esc(l.zustand||'?')}</span>`;
}
const ocTxt=l=>`${l.oc>=0?'+':'−'}${komma(Math.abs(l.oc),1)} ± ${komma(l.oc_err,1)} min`;
function ampel(v){ if(v==null||v==='')return ''; const a=Math.abs(+v); return `<span class="pill ${a<2?'pg':a<3?'py':'pr'}">${komma(a,1)}</span>`; }
async function oeffneOrdner(lauf){ const r=await api('/api/ordner_oeffnen',{messordner:S.pfad,lauf:lauf||null}); if(r.fehler) toast(r.fehler); }
async function aktualisiere(){
  if(!S.pfad||!S.M) return;
  const r=await api('/api/messung2?leicht=1&pfad='+encodeURIComponent(S.pfad));
  if(r.fehler||r.pfad!==S.M.pfad) return;
  S.M.laeufe=r.laeufe; S.M.upload=r.upload; zeigeLaeufe(); zeigeStepper();
  if(S.view==='vergleich'&&!document.activeElement.closest('#upcard')) zeigeVergleich(true);
}

// ------------------------------------------------------------------ start
function erweitertBody(){
  const e=S.erw, num=k=>e[k]===undefined||e[k]===''?null:+e[k];
  const er={flat:e.flat||null,bias:e.bias||null,dark:e.dark||null,dmag_bright:num('dmag_bright'),dmag_faint:num('dmag_faint'),neighbour_px:num('neighbour_px'),edge_px:num('edge_px'),
    airmass_order:num('airmass_order'),airmass_max:num('airmass_max'),flip:e.flip||null,fix_geometry:e.fix_geometry==='false'?false:e.fix_geometry==='true'?true:null,
    mcmc_steps:num('mcmc_steps'),symmetry_weight:num('symmetry_weight'),gaia_quelle:e.gaia_quelle||null,farbkamera:e.farbkamera||null,ausreisser_sigma:num('ausreisser_sigma')};
  if(e.annulus) er.annulus=String(e.annulus).split(',').map(Number);
  if(e.exclude!==undefined) er.exclude_stars=e.exclude;
  const amin=num('ap_min'),amax=num('ap_max');
  if(amin&&amax){ const K=S.K||{},fw=K.fwhm||5,rr=(K.radii&&K.radii.length)?K.radii:[8,10,12,14,16,18,20,22,24];
    er.radii=rr.filter(r=>r>=amin*fw&&r<=amax*fw); if(!er.radii.length) er.radii=null;
    er.k_fwhm=[]; for(let k=amin;k<=amax+1e-9;k+=0.5) er.k_fwhm.push(+k.toFixed(2)); }
  if(e.aperture_mode) er.aperture_mode=e.aperture_mode;
  return er;
}
async function start(){
  const lauf=($('f_lauf').value.trim()||$('f_lauf').placeholder);
  const body={messordner:S.pfad,planet:$('f_planet').value.trim(),filter:$('f_filter').value,mode:S.mode,lauf,basis:$('f_basis').value||null,
    workers:S.erw.workers?+S.erw.workers:null,erweitert:erweitertBody(),danach:$('f_extra').checked?[$('f_extra').dataset.mode]:[]};
  $('startbtn').disabled=true;
  try{ const r=await api('/api/start2',body);
    if(!r.ok){ toast('Nicht gestartet: '+(r.fehler||'unbekannter Fehler')); return; }
    await aktualisiere(); ladeAktiv(); location.hash='#/lauf/'+encodeURIComponent(r.lauf);
  } finally { $('startbtn').disabled=false; }
}

// ------------------------------------------------------------------ run view
async function ladeLauf(){
  if(!S.pfad||!S.lauf) return;
  const L=await api(`/api/lauf?pfad=${encodeURIComponent(S.pfad)}&lauf=${encodeURIComponent(S.lauf)}&voll=1`);
  if(L.fehler){ toast(L.fehler); return; }
  if(L.lauf!==S.lauf) return;
  S.L=L; zeigeLauf();
}
function zeigeLauf(){
  const L=S.L, st=L.status||{}, now=L.jetzt, e=L.einstellungen||{}, mt=L.meta||{};
  const state=L.wartet?'wartet':st.state||'?', laeuft=state==='laeuft';
  const hb=st.heartbeat_unix?now-st.heartbeat_unix:null, haengt=laeuft&&hb>120;
  $('l-name').textContent=L.lauf;
  $('l-pill').innerHTML={laeuft:'<span class="pill pb" style="font-size:13px;vertical-align:middle">läuft</span>',wartet:'<span class="pill pb" style="font-size:13px;vertical-align:middle">wartet</span>',
    fehler:'<span class="pill pr" style="font-size:13px;vertical-align:middle">Fehler</span>'}[state]||`<span class="pill pg" style="font-size:13px;vertical-align:middle">${esc(state==='fertig'?'fertig':state)}</span>`;
  const mode=mt.mode||(S.M&&(S.M.laeufe.find(l=>l.lauf===L.lauf)||{}).modus);
  const aus=(e.fit||{}).ausreisser_sigma;
  const sub=[MODNAME[mode]||mode,'Gaia: '+(L.gaia.quelle==='esa'?'ESA-Archiv':'VizieR'),aus?`Ausreißer > ${komma(aus,1).replace(',0','')} σ`:'',
    mt.basis?'Photometrie aus '+mt.basis:'',st.started?'gestartet '+String(st.started).slice(11,16):'',st.elapsed_s!=null?(laeuft?'läuft seit ':'Dauer ')+mmss(laeuft?now-st.heartbeat_unix+st.elapsed_s:st.elapsed_s)+' min':''].filter(Boolean);
  $('l-sub').textContent=sub.join(' · ');
  $('l-stop').hidden=!(laeuft&&L.laeuft_aus_gui)&&!L.wartet;
  const lr=S.M&&S.M.laeufe.find(l=>l.lauf===L.lauf); $('l-ergebnis').hidden=!(lr&&lr.oc!==undefined);
  $('l-ergebnis').onclick=()=>{S.sel=L.lauf;};
  $('l-fehler').innerHTML=state==='fehler'?`<div class="note bad" role="alert">${IWARN}<div style="display:flex;flex-direction:column;gap:2px"><b>Lauf mit Fehler beendet</b><span style="font-size:13px" class="mono">${esc(st.error||'siehe Protokoll')}</span></div></div>`:
    haengt?`<div class="note" role="alert">${IWARN}<div><b>Kein Lebenszeichen seit ${mmss(hb)} min</b><br><span style="font-size:13px">Der Prozess antwortet nicht. Läuft der PC noch? Sonst abbrechen und neu starten (fertige Schritte werden übersprungen).</span></div></div>`:'';
  // steps
  const steps=(st.steps&&st.steps.length?st.steps:STEPS.map(n=>({name:n,state:'offen'})));
  const est=L.schaetzung||{};
  const cur=steps.find(s=>s.state==='laeuft');
  const curEl=cur?(now-(st.last_progress_unix||now)):0;
  $('l-steps').innerHTML=steps.map((s,i)=>{
    let cls='pstep',dot=`<span class="sdot">${i+1}</span>`,sub='';
    if(s.state==='fertig'){ dot=`<span class="sdot" style="background:var(--ok);color:#fff">${ICHK}</span>`; sub=mmss(s.duration_s)+' min'; }
    else if(s.state==='uebersprungen'){ dot=`<span class="sdot" style="background:var(--pg-b);color:var(--pg-f)">${ICHK}</span>`; sub='übernommen'; }
    else if(s.state==='laeuft'){ cls+=' cur'; dot=`<span class="sdot" style="background:var(--acc);color:#fff">${i+1}</span>`; sub=`<span style="color:var(--acc2);font-weight:600">${st.task?esc(st.task)+' '+Math.round(st.percent||0)+' %':'läuft …'}</span>`; }
    else if(s.state==='fehler'){ cls+=' err'; dot='<span class="sdot" style="background:var(--pr-f);color:#fff">!</span>'; sub='<span style="color:var(--pr-f);font-weight:600">Fehler</span>'; }
    else sub=est[s.name]?minuten(est[s.name]):'';
    return `<li class="${cls}" title="${esc(s.note||'')}"><span class="row" style="gap:8px;flex-wrap:nowrap">${dot}<b>${esc(SCHRITT[s.name]||s.name)}</b></span><span class="hint">${sub}</span></li>`; }).join('');
  // ETA
  let eta='';
  if(laeuft){ let rest=0,ok=true;
    if(st.task&&st.eta_s!=null) rest+=st.eta_s; else if(cur&&est[cur.name]) rest+=Math.max(0,est[cur.name]-curEl); else ok=false;
    let after=false; for(const s of steps){ if(s===cur){after=true;continue;} if(after&&s.state==='offen'){ if(est[s.name]) rest+=est[s.name]; } }
    eta=(st.task&&st.eta_local&&!after)?'':''; if(rest>0) eta=`voraussichtlich fertig gegen <b style="color:var(--fg)">${uhr(now+rest)}</b>`+(ok?'':' (ohne den laufenden Schritt)');
  }
  $('l-eta').innerHTML=eta;
  // current activity
  let akt='';
  if(laeuft&&cur){
    const lines=L.log||[], gl=[...lines].reverse().find(x=>/Gaia/.test(x))||'';
    const gaiaWartet=cur.name==='cube'&&!st.task&&/frage .* an|nicht erreichbar/.test(gl);
    if(st.task){
      akt=`<div class="between"><b>${esc(st.task)}</b><span class="mono" style="font-size:13px">${st.done??''} / ${st.total??''} ${esc(st.unit||'')} · ${Math.round(st.percent||0)} %${st.eta_local?' · fertig ~'+esc(String(st.eta_local).replace(/:\d\d (\w+)$/,' $1')):''}</span></div>
        <div class="bar" role="progressbar" aria-label="${esc(st.task)}" aria-valuenow="${Math.round(st.percent||0)}" aria-valuemin="0" aria-valuemax="100"><i style="width:${st.percent||0}%"></i></div>`+(st.eta_includes?`<span class="hint">Restzeit enthält: ${esc(st.eta_includes)}</span>`:'');
    } else if(gaiaWartet){
      const q=(gl.match(/frage (.*) an/)||[])[1]||(L.gaia.quelle==='esa'?'ESA-Gaia-Archiv':'VizieR');
      const andere=L.gaia.quelle==='esa'?'vizier':'esa';
      akt=`<div class="between"><b>Gaia DR3 abfragen (${esc(q)})</b><span class="mono" style="font-size:13px">wartet seit ${mmss(curEl)} · Zeitlimit ${L.gaia.timeout} s je Dienst</span></div>
        <div class="bar" role="progressbar" aria-label="Gaia-Abfrage, Dauer unbekannt"><i class="indet"></i></div>
        <span class="hint" style="font-size:13px">Der Server meldet keinen Fortschritt. Nach dem Zeitlimit wird automatisch der nächste Dienst versucht (VizieR CDS, VizieR Harvard, ESA-Archiv).</span>
        <div class="row" style="gap:8px"><button class="btn sec" ${L.laeuft_aus_gui?'':'disabled title="Lauf wurde nicht aus dieser Oberfläche gestartet"'} onclick="gaiaWechsel('${andere}')">Jetzt auf ${andere==='esa'?'ESA-Archiv':'VizieR'} wechseln</button></div>`;
    } else {
      akt=`<div class="between"><b>${esc(SCHRITT[cur.name]||cur.name)}</b><span class="mono" style="font-size:13px">seit ${mmss(curEl)} ohne Prozentangabe</span></div><div class="bar" role="progressbar" aria-label="${esc(SCHRITT[cur.name]||cur.name)}"><i class="indet"></i></div>`;
    }
    akt=`<div style="display:flex;flex-direction:column;gap:10px;padding:16px;border-radius:8px;background:var(--accsoft);border:1px solid var(--accline)">${akt}</div>`;
    const nx=steps[steps.indexOf(cur)+1]; if(nx&&nx.state==='offen') akt+=`<span class="hint" style="font-size:13px">danach: ${esc(SCHRITT[nx.name]||nx.name)}</span>`;
  } else if(L.wartet){ akt='<div class="note info">'+IINFO+`<div>Dieser Lauf startet automatisch, wenn der vorherige fertig ist (${esc((S.M&&L.lauf)||'')}).</div></div>`; }
  $('l-akt').innerHTML=akt;
  // heartbeat + log
  $('l-hb').innerHTML=laeuft&&hb!=null?`<span class="dot" style="background:${hb>120?'var(--pr-f)':'var(--ok)'}"></span>Lebenszeichen vor ${hb<90?Math.round(hb)+' s':mmss(hb)+' min'}`:'';
  const pre=$('l-log'), unten=pre.scrollTop+pre.clientHeight>=pre.scrollHeight-8;
  const txt=(L.log||[]).join('\n')||'(noch keine Ausgabe)';
  if(pre.textContent!==txt){ const y=pre.scrollTop; pre.textContent=txt; pre.scrollTop=unten?pre.scrollHeight:y; }
  $('l-runlog').href=datei(L.pfad,L.lauf,'run.log');
  $('l-folge').innerHTML=(L.folgelauf||[]).map(f=>`<div style="border-top:1px solid var(--line2);padding-top:12px;display:flex;flex-direction:column;gap:6px"><b style="font-size:13px">Zweiter Lauf <a href="#/lauf/${encodeURIComponent(f)}">${esc(f)}</a></b><span class="hint" style="font-size:13px">wartet, startet danach und übernimmt die Gaia-Daten</span></div>`).join('');
  $('notify').checked=lsGet('transit.notify',false)&&('Notification' in window)&&Notification.permission==='granted';
}
async function abbrechen(){
  const r=await api('/api/abbrechen',{messordner:S.pfad,lauf:S.lauf}); toast(r.ok?'Lauf wird abgebrochen':r.fehler||'Fehler'); setTimeout(()=>{ladeLauf();aktualisiere();ladeAktiv();},1500);
}
async function gaiaWechsel(q){
  toast('Stoppe die Abfrage und setze mit '+(q==='esa'?'dem ESA-Archiv':'VizieR')+' fort …');
  const r=await api('/api/gaia_wechsel',{messordner:S.pfad,lauf:S.lauf,quelle:q}); if(!r.ok) toast(r.fehler||'Fehler'); setTimeout(ladeLauf,1500);
}
async function notifyUmschalten(cb){
  if(cb.checked&&'Notification' in window&&Notification.permission!=='granted'){ const p=await Notification.requestPermission(); if(p!=='granted'){ cb.checked=false; toast('Benachrichtigungen sind im Browser gesperrt'); } }
  lsSet('transit.notify',cb.checked);
}

// ------------------------------------------------------------------ activity chip + notifications
async function ladeAktiv(){
  const A=await api('/api/aktiv'); if(!Array.isArray(A)) return;
  const lauf=A.filter(a=>!a.wartet), c=$('aktiv');
  if(!A.length){ c.hidden=true; }
  else { const a=lauf[0]||A[0]; c.hidden=false;
    const was=a.wartet?'wartet':(SCHRITT[a.schritt]||a.schritt||'startet')+(a.task?' · '+a.task+(a.prozent!=null?' '+Math.round(a.prozent)+' %':''):a.seit?' · '+mmss(a.jetzt-a.seit):'');
    $('aktivtxt').innerHTML=`<b>${lauf.length||0} ${lauf.length===1?'Lauf':'Läufe'} aktiv</b> · ${esc(a.planet)} · ${esc(was)}`+(A.length>lauf.length?` · ${A.length-lauf.length} wartet`:'');
    c.onclick=ev=>{ ev.preventDefault(); if(S.pfad!==a.pfad){ waehle(a.pfad).then(()=>location.hash='#/lauf/'+encodeURIComponent(a.lauf)); } else location.hash='#/lauf/'+encodeURIComponent(a.lauf); };
  }
  const jetzt=new Set(lauf.map(a=>a.pfad+'|'+a.lauf));
  for(const k of S.laufend) if(!jetzt.has(k)) fertigGemeldet(k);
  S.laufend=jetzt;
}
async function fertigGemeldet(k){
  const [p,l]=k.split('|'); const r=await api(`/api/lauf?pfad=${encodeURIComponent(p)}&lauf=${encodeURIComponent(l)}`);
  const ok=(r.status||{}).state!=='fehler', t=`transit: ${l} ${ok?'fertig':'mit Fehler beendet'}`;
  toast(t); document.title=(ok?'✓ ':'! ')+'transit';
  if(lsGet('transit.notify',false)&&'Notification' in window&&Notification.permission==='granted'){ try{ new Notification(t,{body:r.pfad||''}); }catch(e){} }
  if(p===S.pfad) aktualisiere();
}
document.addEventListener('visibilitychange',()=>{ if(!document.hidden) document.title='transit'; });

// ------------------------------------------------------------------ comparison + upload
function zeigeVergleich(poll){
  if(!S.M){ $('v-leer').hidden=false; $('v-inhalt').hidden=true; return; }
  const L=S.M.laeufe.filter(l=>l.oc!==undefined).sort((a,b)=>String(b.lauf).localeCompare(String(a.lauf)));
  $('v-leer').hidden=!!L.length; $('v-inhalt').hidden=!L.length; if(!L.length) return;
  const best=L.reduce((a,b)=>(+b.oot_rms<+a.oot_rms?b:a));
  const g=L.find(l=>l.status==='gueltig');
  if(!S.sel||!L.some(l=>l.lauf===S.sel)) S.sel=(g||best).lauf;
  $('kz').innerHTML=L.map(l=>{ const P=l.pruefungen||[], nok=P.filter(p=>p.level==='ok').length, bad=P.some(p=>p.level==='bad'), warn=P.filter(p=>p.level!=='ok');
    return `<tr class="click ${l.lauf===S.sel?'sel':''}" onclick="waehleLauf('${esc(l.lauf)}')"><td><b>${esc(l.lauf)}</b><br>${l===best?'<span class="pill pg" style="margin-top:4px">beste Datenqualität</span> ':''}${l.status==='gueltig'?'<span class="pill pg" style="margin-top:4px">gültig</span>':''}</td>
      <td>${esc(MODNAME[l.modus]||l.modus||'')}</td><td style="white-space:nowrap">${ocTxt(l)}</td><td style="white-space:nowrap">${l===best?'<b>':''}${komma(l.oot_rms,2)} ppt${l===best?'</b>':''}</td><td>${komma(l.beta,2)}</td><td>${ampel(l.drift)}</td>
      <td style="white-space:nowrap">${l.rp?komma(l.rp,3)+' ± '+komma(l.rp_err,3):''}</td><td>${l.ausreisser==null?'aus':l.ausreisser+' entfernt'}</td>
      <td><span class="pill ${bad?'pr':warn.length?'py':'pg'}" title="${esc(warn.map(p=>p.text).join('; '))}">${nok}/${P.length}${warn.length?' · '+esc(warn[0].text.slice(0,24))+'…':' ok'}</span></td>
      <td style="white-space:nowrap"><button class="btn sec sm" onclick="event.stopPropagation();aij('${esc(l.lauf)}')">In AIJ öffnen</button></td></tr>`; }).join('');
  const s=L.find(l=>l.lauf===S.sel);
  $('h-blatt').textContent='Ergebnisblatt '+s.lauf;
  $('tabs').innerHTML=[['kurve','Lichtkurve'],['feld','Feld'],['sterne','Vergleichssterne']].map(([k,t])=>`<button role="tab" aria-selected="${S.tab===k}" class="btn sm ${S.tab===k?'':'sec'}" onclick="S.tab='${k}';zeigeBlatt()">${t}</button>`).join('');
  if(!poll) zeigeBlatt();
  $('pruef').innerHTML=(s.pruefungen||[]).map(p=>`<li style="display:flex;gap:10px;align-items:flex-start"><span class="pill ${p.level==='ok'?'pg':p.level==='bad'?'pr':'py'}">${p.level==='ok'?'ok':p.level==='bad'?'rot':'prüfen'}</span><span>${esc(p.text)}</span></li>`).join('')||'<li class="hint">keine Angaben</li>';
  $('gueltigbox').innerHTML=s.status==='gueltig'?`<div class="row" style="gap:8px"><span class="pill pg" style="font-size:13px;padding:6px 10px">${ICHK} gültige Messung dieser Nacht</span></div><span class="hint" style="font-size:13px">Ein anderer Lauf kann jederzeit stattdessen gültig gesetzt werden.</span>`:
    `<button class="btn ok big" onclick="gueltig('${esc(s.lauf)}')">${ICHK} Als gültige Messung dieser Nacht setzen</button><span class="hint" style="font-size:13px">Ersetzt die Upload-Datei unter RESULT\\. Rückgängig über die Meldung danach oder „gültig“ beim anderen Lauf.</span>`;
  $('upcard').hidden=!g;
  if(g&&(!poll||$('up-lauf').dataset.l!==g.lauf)) ladeUpload();
  if(g){ $('up-done').checked=!!g.hochgeladen; $('up-done-h').textContent=g.hochgeladen?'am '+g.hochgeladen+' abgehakt':'Haken setzen, sobald die Datei bei ExoClock hochgeladen ist'; }
}
function waehleLauf(l){ S.sel=l; zeigeVergleich(); }
// The three views of a run are built once per run and only shown/hidden when switching tabs; the comparison-star table
// is fetched in the background as soon as the run is selected and kept for the session (S.kc).
function zeigeBlatt(){
  const s=S.sel, p=S.M.pfad, lr=(S.M.laeufe||[]).find(l=>l.lauf===s)||{}, key=[p,s,lr.oc,lr.oot_rms,lr.beta].join('|');
  document.querySelectorAll('#tabs button').forEach(b=>{ const on=b.textContent===({kurve:'Lichtkurve',feld:'Feld',sterne:'Vergleichssterne'})[S.tab];
    b.setAttribute('aria-selected',on); b.classList.toggle('sec',!on); });
  const B=$('blatt');
  if(B.dataset.key!==key){
    B.dataset.key=key; const v=Date.now();
    const img=(f,alt,h)=>`<div class="bbox" data-hilfe="${h}"><a href="${datei(p,s,f)}&v=${v}" target="_blank"><img class="blatt" alt="${alt} ${esc(s)}" src="${datei(p,s,f)}&v=${v}" onerror="this.closest('.bbox').outerHTML='<span class=hint>Kein Bild vorhanden.</span>'"></a></div>`;
    B.innerHTML=`<div data-tab="kurve">${img('ergebnisblatt.png','Ergebnisblatt mit Lichtkurve','blatt')}</div><div data-tab="feld">${img('ergebnisblatt_feld.png','Feldbild','feld')}</div><div data-tab="sterne"></div>`;
    ladeSterne(p,s,key); ladeHilfe(p,s,key,v);
  }
  B.querySelectorAll('[data-tab]').forEach(d=>d.hidden=d.dataset.tab!==S.tab);
}
// Help on table column heads: every <th> whose text is in SPALTE gets a small (i); only a click on it shows the text.
// A MutationObserver also covers tables built later (run comparison, comparison stars, plan).
const SPALTE={
  'Lauf':'Name des Laufs (Ordner unter RESULT). gui_<Datum>_<Zeit>_<Kalibrierung>.',
  'Zustand':'Fertig, läuft, wartet oder mit Fehler beendet.',
  'Kalibr.':'Kalibrierung der Lights: raw (keine), f (nur Flat), bf (Bias + Flat), bfd (Bias + Flat + Dark).',
  'O-C':'Gemessene minus vorhergesagte Transitmitte in Minuten, mit Fehler. Nahe 0 innerhalb des Fehlers: Ephemeride bestätigt.',
  'OOT-RMS':'Streuung der Lichtkurve außerhalb des Transits (Promille). Je kleiner, desto ruhiger die Messung; der kleinste Wert ist markiert.',
  'β':'Faktor für rotes (zeitlich korreliertes) Rauschen. 1 = nur weißes Rauschen; größere Werte vergrößern die Fehler entsprechend.',
  'Drift':'ExoClock-Kriterium: Abweichung von Rp/R* vom Literaturwert in Einheiten des Fehlers. Grün unter 2, gelb 2–3, rot ab 3.',
  'Rp/Rs':'Gemessener Planetenradius relativ zum Sternradius (aus der Transittiefe).',
  'Ausreißer':'Wie viele Messpunkte das Sigma-Clipping gegen den Transit-Fit entfernt hat (Schwelle in ausreisser.json).',
  'Prüfungen':'Ergebnis der automatischen Prüfungen: Planung (Baseline, Airmass, Flip), Drift und Konvergenz (R-hat).',
  'Planet':'Planet in ExoClock-Schreibweise.',
  'Nacht':'Beobachtungsnacht (Datum des Abends).',
  'Status':'gültig = der Lauf, der für diese Nacht zählt (Upload, O-C-Diagramm); variante = weitere Auswertung derselben Nacht.',
  'Tiefe':'Transittiefe in Promille (Modell mit Randverdunkelung).',
  'Upload-Datei':'Datei für den ExoClock-Upload dieses Laufs.',
  'an':'Haken = Stern darf ins Ensemble der Vergleichssterne. Abgewählte Sterne schließt der nächste Lauf aus.',
  'Stern':'Kandidat für die Vergleichssterne (interne Nummer). * = im Ensemble dieses Laufs.',
  'G':'Gaia-G-Helligkeit in mag. Ideal: ähnlich hell wie der Zielstern.',
  'BP-RP':'Gaia-Farbe (blau minus rot). Größer = röter. Ähnliche Farbe wie das Ziel verringert Airmass-Effekte.',
  'RUWE':'Gaia-Astrometriegüte. Über 1,4 (gelb): möglicherweise Doppelstern.',
  'Gaia':'Variabilitätskennung aus Gaia/VSX. VARIABLE = bekannter Veränderlicher, ungeeignet.',
  'Ruhe':'Streuung des Sterns gegen die übrigen Kandidaten (10-min-Mittel), geteilt durch den Median aller. 1 = typisch, über 2 auffällig.',
  'Transitfenster':'Scheinbarer „Transit“ dieses Sterns im Zeitfenster des Planeten (ppt ± Fehler). Sollte null sein; über 3 σ rot.',
  'Score':'Gesamtwertung des Vorschlags aus ExoClock-Priorität, Signal-Rausch-Verhältnis, Abdeckung und Wetter.',
  'Prio':'ExoClock-Priorität: alert, high, medium, low.',
  'mag':'Helligkeit des Sterns (V, mag).',
  'Tiefe ppt':'Erwartete Transittiefe in Promille.',
  'SNR':'Erwartetes Signal-Rausch-Verhältnis des Transits mit deinem Teleskop (Rauschmodell: Photonen, Himmel, Szintillation).',
  'Beobachten':'Empfohlenes Beobachtungsfenster inklusive Baseline vor und nach dem Transit (Ortszeit).',
  'Ingress / Tc / Egress':'Vorhergesagter Beginn, Mitte (mit Unsicherheit) und Ende des Transits.',
  'X max':'Größte Airmass im Beobachtungsfenster. Unter 2 ist gut.',
  'Wolken':'Vorhergesagte mittlere Bewölkung im Fenster.',
  'RA / Dec':'Himmelskoordinaten des Sterns (J2000).',
  'Hinweise':'Warnungen zur Planung, z. B. kurze Baseline, Meridian-Flip, wenige Vergleichssterne.'
};
let thPop=null, thFest=null;
function thZeige(b){
  if(!thPop){ thPop=document.createElement('div'); thPop.className='hpop fix'; thPop.setAttribute('role','tooltip'); document.body.appendChild(thPop); }
  thPop.innerHTML=`<b>${esc(b.dataset.titel)}</b>${esc(SPALTE[b.dataset.titel])}`; thPop.hidden=false;
  const r=b.getBoundingClientRect(), w=Math.min(340,innerWidth-16);
  thPop.style.left=Math.max(8,Math.min(r.left,innerWidth-w-8))+'px';
  thPop.style.top=(r.bottom+6+thPop.offsetHeight>innerHeight?r.top-thPop.offsetHeight-6:r.bottom+6)+'px';
}
function thWeg(){ if(thPop&&!thFest) thPop.hidden=true; }
function spaltenHilfe(root){
  (root.querySelectorAll?root:document).querySelectorAll('th:not([data-hilfe])').forEach(th=>{
    const t=th.textContent.trim(); th.dataset.hilfe='1'; if(!SPALTE[t]) return;
    th.removeAttribute('title');
    th.insertAdjacentHTML('beforeend',`<button type="button" class="thi" data-titel="${esc(t)}" aria-label="Erklärung: ${esc(t)}">i</button>`);
    const b=th.lastElementChild;
    b.addEventListener('click',ev=>{ ev.stopPropagation(); if(thFest) thFest.classList.remove('on');
      if(thFest===b){ thFest=null; thWeg(); return; } thFest=b; b.classList.add('on'); thZeige(b); });
  });
}
document.addEventListener('click',()=>{ if(thFest){ thFest.classList.remove('on'); thFest=null; thWeg(); } });
addEventListener('scroll',()=>{ if(thPop&&!thPop.hidden){ if(thFest){ thFest.classList.remove('on'); thFest=null; } thPop.hidden=true; } },true);
new MutationObserver(ms=>{ for(const m of ms) for(const n of m.addedNodes) if(n.nodeType===1) spaltenHilfe(n); })
  .observe(document.documentElement,{childList:true,subtree:true});
addEventListener('DOMContentLoaded',()=>spaltenHilfe(document));

// Help on the result sheet: ergebnisblatt_hilfe.json holds rectangles (fractions of the PNG) with title and text; each
// gets a small (i) in its corner, visible while the mouse is over the sheet.  Only a click on the (i) shows the text.
async function ladeHilfe(p,s,key,v){
  let H; try{ const r=await fetch(datei(p,s,'ergebnisblatt_hilfe.json')+'&v='+v); if(!r.ok) return; H=await r.json(); }catch(e){ return; }
  const B=$('blatt'); if(B.dataset.key!==key) return;
  B.querySelectorAll('.bbox[data-hilfe]').forEach(bx=>{
    const L=H[bx.dataset.hilfe]||[]; if(!L.length) return;
    const pct=x=>(100*x).toFixed(2)+'%';
    bx.insertAdjacentHTML('beforeend',L.map((h,i)=>{ const [x0,y0,x1,y1]=h.r;
      return `<div class="hz${h.art==='block'?'':' c'}" style="left:${pct(x0)};top:${pct(y0)};width:${pct(x1-x0)};height:${pct(y1-y0)}"><button type="button" data-i="${i}" aria-label="Erklärung: ${esc(h.titel)}" aria-expanded="false">i</button></div>`; }).join(''));
    let pop=null, offen=null;
    const zu=()=>{ if(offen){ offen.parentNode.classList.remove('on'); offen.setAttribute('aria-expanded','false'); offen=null; } if(pop) pop.hidden=true; };
    const auf=b=>{ const h=L[+b.dataset.i], z=b.parentNode;
      if(!pop){ pop=document.createElement('div'); pop.className='hpop'; pop.setAttribute('role','tooltip'); bx.appendChild(pop); }
      pop.innerHTML=`<b>${esc(h.titel)}</b>${esc(h.text)}`; pop.hidden=false;
      const W=bx.clientWidth, x=z.offsetLeft, y=z.offsetTop+z.offsetHeight+6, w=Math.min(340,W-8);
      pop.style.left=Math.max(4,Math.min(x,W-w-4))+'px';
      pop.style.top=(y+pop.offsetHeight>bx.clientHeight&&z.offsetTop>pop.offsetHeight+6?z.offsetTop-pop.offsetHeight-6:y)+'px';
      offen=b; z.classList.add('on'); b.setAttribute('aria-expanded','true'); };
    bx.querySelectorAll('.hz>button').forEach(b=>b.addEventListener('click',ev=>{ ev.preventDefault(); ev.stopPropagation();
      const war=offen===b; zu(); if(!war) auf(b); }));
    document.addEventListener('click',function weg(ev){ if(!bx.isConnected) return document.removeEventListener('click',weg);
      if(offen&&!(pop&&pop.contains(ev.target))) zu(); });
  });
}
async function ladeSterne(p,s,key){
  S.kc=S.kc||{};
  const box=()=>{ const B=$('blatt'); return B.dataset.key===key?B.querySelector('[data-tab="sterne"]'):null; };
  const zeig=K=>{ const b=box(); if(b) b.innerHTML=K.fehler?esc(K.fehler):kandTabelle(K,false)+lcBild(K,p,s,true); };
  if(S.kc[key]){ zeig(S.kc[key]); return; }
  const t0=Date.now();
  const tick=()=>{ const b=box(); if(!b||S.kc[key]) return clearInterval(iv);
    const sek=Math.round((Date.now()-t0)/1000);
    b.innerHTML=`<span class="hint">lade Vergleichssterne … ${sek} s</span>`; };
  const iv=setInterval(tick,1000); tick();
  const K=await api(`/api/kandidaten?pfad=${encodeURIComponent(p)}&lauf=${encodeURIComponent(s)}`);
  clearInterval(iv);
  if(!K.fehler) S.kc[key]=K;
  zeig(K);
}
async function aij(l){ toast('Öffne AstroImageJ …'); const r=await api('/api/aij',{messordner:S.pfad,lauf:l}); toast(r.ok?'AIJ-Dateien erzeugt und geöffnet':(r.ausgabe||r.fehler||'Fehler').slice(-200)); }
async function gueltig(l){
  const alt=(S.M.laeufe.find(x=>x.status==='gueltig')||{}).lauf;
  const r=await api('/api/gueltig',{messordner:S.pfad,lauf:l});
  if(!r.ok){ toast((r.ausgabe||r.fehler||'Fehler').slice(-240)); return; }
  await aktualisiere(); S.sel=l; zeigeVergleich(); ladeListe();
  if(alt&&alt!==l) toast(`${l} ist jetzt gültig.`,'Rückgängig',()=>gueltig(alt)); else toast(`${l} ist jetzt gültig.`);
}
async function ladeUpload(neu){
  const g=S.M.laeufe.find(l=>l.status==='gueltig'); if(!g) return;
  const r=await api(`/api/upload?pfad=${encodeURIComponent(S.M.pfad)}&lauf=${encodeURIComponent(g.lauf)}`);
  if(r.fehler){ $('upcard').hidden=true; return; }
  $('up-lauf').textContent='gültig: '+r.lauf; $('up-lauf').dataset.l=r.lauf;
  const felder=[];
  for(const z of String(r.formular||'').split('\n')){ const m=z.match(/^(\S.*?) \.{2,} (.*)$/); if(!m) continue;
    let v=m[2], h=''; const i=v.indexOf('  ('); if(i>0){ h=v.slice(i+2); v=v.slice(0,i); }
    felder.push([m[1],v,h]); }
  window.FELDER=felder;
  $('up-felder').innerHTML=felder.map(([k,v,h],i)=>`<div class="kv"><span>${esc(k)}</span><span><span class="mono" style="font-size:13px;overflow-wrap:anywhere">${esc(v)}</span>${h?`<br><span class="hint">${esc(h)}</span>`:''}</span><button class="btn sec sm" aria-label="${esc(k)} kopieren" title="kopieren" onclick="kopiere(FELDER[${i}][1],'${esc(k)} kopiert')">${ICOPY}</button></div>`).join('')||'<span class="hint">exoclock_formular.txt fehlt</span>';
  $('up-kom').value=r.kommentar||''; if(neu) toast('Kommentar neu erzeugt');
}
async function kopiere(t,msg){ try{ await navigator.clipboard.writeText(t); }catch(e){ const a=document.createElement('textarea'); a.value=t; document.body.appendChild(a); a.select(); document.execCommand('copy'); a.remove(); } toast(msg||'kopiert'); }
async function hochgeladen(v){
  const g=S.M.laeufe.find(l=>l.status==='gueltig'); if(!g) return;
  await api('/api/hochgeladen',{messordner:S.M.pfad,lauf:g.lauf,wert:v}); await aktualisiere(); ladeListe(); toast(v?'Als hochgeladen vermerkt':'Vermerk entfernt');
}

// ------------------------------------------------------------------ advanced settings (drawer)
function drawerAuf(){
  const V=S.M?S.M.vorgaben:{};
  const ph={dmag_bright:V.dmag_bright,dmag_faint:V.dmag_faint,neighbour_px:V.neighbour_px,edge_px:V.edge_px,airmass_max:V.airmass_max||'keine',mcmc_steps:V.mcmc_steps,symmetry_weight:V.symmetry_weight,
    annulus:(V.annulus||[]).join(','),ap_min:(V.k_fwhm||[])[0],ap_max:(V.k_fwhm||[]).slice(-1)[0],workers:'auto ('+V.workers+')'};
  document.querySelectorAll('#drawer [data-k]').forEach(el=>{ const k=el.dataset.k; if(ph[k]!=null&&el.tagName==='INPUT') el.placeholder=String(ph[k]).replace('.',',');
    el.value=S.erw[k]??''; el.oninput=el.onchange=()=>{ S.erw[k]=el.value; erwMarkieren(); }; });
  const std={gaia_quelle:V.gaia_quelle==='esa'?'ESA-Archiv':'VizieR',aperture_mode:V.aperture_mode,airmass_order:V.airmass_order==2?'quadratisch':'linear',flip:V.flip,fix_geometry:V.fix_geometry?'fest':'frei'};
  for(const [k,t] of Object.entries(std)){ const o=document.querySelector(`#drawer [data-k="${k}"] option[value=""]`); if(o) o.textContent='Standard ('+t+')'; }
  $('h-gaia').textContent='Standard '+(V.gaia_quelle==='esa'?'ESA-Archiv':'VizieR')+'; der andere Dienst, wenn einer nicht antwortet';
  zeigeAus(); erwMarkieren(); ladeKand();
  $('scrim').hidden=false; $('drawer').hidden=false; $('drawer').querySelector('button').focus();
}
function zeigeAus(){ const v=String(S.erw.ausreisser_sigma||''); $('seg-aus').innerHTML=AUS.map(([k,t])=>`<button class="${v===k?'on':''}" aria-pressed="${v===k}" onclick="S.erw.ausreisser_sigma='${k}';zeigeAus();erwMarkieren()">${t}</button>`).join(''); }
function geaendert(k){ const v=S.erw[k]; return k==='exclude'?Array.isArray(v)&&S.K&&!gleich(v,vorschlagAus(S.K)):v!==undefined&&v!==''&&v!==null; }
function gleich(a,b){ return JSON.stringify([...a].sort())===JSON.stringify([...b].sort()); }
function erwMarkieren(){
  document.querySelectorAll('#drawer [data-k]').forEach(el=>el.classList.toggle('chg',geaendert(el.dataset.k)));
  let nav='';
  for(const [g,ks] of Object.entries(GRUPPEN)){ const n=ks.filter(geaendert).length; document.querySelector(`#g-${g} .gz`).innerHTML=n?`<span class="pill pb">${n} geändert</span>`:'';
    nav+=`<a href="#" onclick="event.preventDefault();document.getElementById('g-${g}').scrollIntoView({behavior:'smooth'})" class="pill ${n?'pb':'pn'}" style="text-decoration:none;padding:6px 10px">${GNAME[g]}${n?' · '+n:''}</a>`; }
  $('erw-nav').innerHTML=nav;
  const fw=S.K&&S.K.fwhm, a=+S.erw.ap_min, b=+S.erw.ap_max;
  if(a&&b&&fw){ const rr=(S.K.radii||[]).filter(r=>r>=a*fw&&r<=b*fw); const ks=[]; for(let k=a;k<=b+1e-9;k+=0.5) ks.push(komma(k,1)); $('ap-vorschau').textContent=`Vorschau: feste Radien ${rr.join(', ')||'keine'} px bei FWHM ${komma(fw,1)} px · k = ${ks.join(', ')}`; }
  zeigeErwChips(); zeigeFuss();
}
function chipWert(k){ const v=S.erw[k]; if(k==='exclude') return v.join(', ')||'keiner'; if(k==='ausreisser_sigma') return '> '+String(v).replace('.',',')+' σ'; if(k==='gaia_quelle') return v==='esa'?'ESA-Archiv':'VizieR';
  if(k==='airmass_order') return v==2?'quadratisch':'linear'; if(k==='fix_geometry') return v==='false'?'frei':'fest'; return String(v); }
function zeigeErwChips(){
  const ks=Object.values(GRUPPEN).flat().filter(geaendert);
  $('erw-chips').innerHTML=ks.length?ks.map(k=>`<span class="pill pb">${esc(ELBL[k])}: ${esc(chipWert(k))}</span>`).join('')+'<span class="hint">sonst Standard</span>':'<span class="hint">alles Standard</span>';
}
function gruppeReset(g){ for(const k of GRUPPEN[g]) delete S.erw[k]; if(g==='ver'&&S.K) S.erw.exclude=undefined; drawerAuf(); }
function allesReset(){ S.erw={}; drawerAuf(); }
function drawerZu(ok){ if(ok&&$('merken').checked){ const e=Object.assign({},S.erw); delete e.exclude; lsSet('transit.erw',e); toast('Als Vorgabe gemerkt'); }
  $('scrim').hidden=true; $('drawer').hidden=true; zeigeErwChips(); zeigeFuss(); }
document.addEventListener('keydown',e=>{ if(e.key==='Escape'&&!$('drawer').hidden) drawerZu(); });
const istVar=k=>k.var&&String(k.var).toUpperCase().startsWith('VARIABLE');
function vorschlagAus(K){ return K.kandidaten.filter(k=>!k.ziel&&(k.ausgeschlossen||istVar(k)||k.tw_flag||k.variabel)).map(k=>k.name); }
async function ladeKand(){
  const b=$('f_basis').value;
  if(!b){ $('kand').innerHTML='<span class="hint">Für die Liste der Vergleichssterne unter „Photometrie übernehmen von“ einen Lauf wählen.</span>'; return; }
  if(!S.K){ $('kand').innerHTML='<span class="hint">lade Kandidaten (Gaia-Abfrage beim ersten Mal) …</span>';
    const K=await api(`/api/kandidaten?pfad=${encodeURIComponent(S.pfad)}&lauf=${encodeURIComponent(b)}`);
    if(K.fehler){ $('kand').innerHTML=`<span class="hint">${esc(K.fehler)}</span>`; return; } S.K=K; }
  if(S.erw.exclude===undefined) S.erw.exclude=vorschlagAus(S.K);
  $('kand').innerHTML=kandTabelle(S.K,true)+lcBild(S.K,S.pfad,b)+(S.K.feldbild?`<details><summary style="cursor:pointer;font-size:13px">Feldbild zeigen</summary><img class="blatt" style="margin-top:8px" alt="Feldbild mit Vergleichssternen" src="${datei(S.pfad,b,'ergebnisblatt_feld.png')}"></details>`:'');
  erwMarkieren();
}
function kandTabelle(K,edit){
  const ex=new Set(edit?S.erw.exclude||[]:K.kandidaten.filter(k=>k.ausgeschlossen).map(k=>k.name));
  return `<div class="scroll"><table><thead><tr>${edit?'<th>an</th>':''}<th>Stern</th><th>G</th><th>BP-RP</th><th>RUWE</th><th>Gaia</th><th>Ruhe</th><th>Transitfenster</th></tr></thead><tbody>`+
    K.kandidaten.filter(k=>!k.ziel).map(k=>{
      const ru=k.ruwe==null?'<span class="pill pn">–</span>':`<span class="pill ${k.ruwe>1.4?'py':'pg'}">${komma(k.ruwe,2)}</span>`;
      const va=istVar(k)?'<span class="pill pr">VARIABLE</span>':'<span class="pill pg">ok</span>';
      const rh=k.ruhe==null?'<span class="pill pn">–</span>':`<span class="pill ${k.variabel||k.verworfen?'pr':k.ruhe>2?'py':'pg'}" title="${esc(k.verworfen||('Streuung der 10-min-Mittel '+komma(k.bin_ppt,2)+' ppt, β '+komma(k.beta,1)))}">${komma(k.ruhe,1)}${k.variabel?' · variabel':k.verworfen?' · verworfen':''}</span>`;
      const tw=k.tw==null?'<span class="hint">nur Ensemble</span>':`<span class="pill ${k.tw_flag?'pr':'pg'}">${komma(k.tw,1)} ± ${komma(k.tw_e,1)}</span>`;
      return `<tr>${edit?`<td><input type="checkbox" aria-label="${esc(k.name)} verwenden" style="width:18px;height:18px" ${ex.has(k.name)?'':'checked'} onchange="sternUmschalten('${esc(k.name)}',this.checked)"></td>`:''}<td>${esc(k.name)}${k.im_ensemble?' *':''}</td><td>${komma(k.G,1)}</td><td>${komma(k.bp_rp,2)}</td><td>${ru}</td><td>${va}</td><td>${rh}</td><td>${tw}</td></tr>`; }).join('')+
    '</tbody></table></div><span class="hint">* im Ensemble des Laufs. Ruhe = Streuung des Sterns gegen die übrigen Kandidaten (10-min-Mittel) geteilt durch den Median aller, 1 = typisch. Bekannte Veränderliche (Gaia, VSX) sind schon bei der Auswahl verworfen. Vorschlag: eigene Lichtkurve variabel und Transitfenster über 3 σ sind abgewählt.</span>';
}
function lcBild(K,p,l,offen){ if(!K.lcbild) return K.kandidaten.some(k=>k.ruhe!=null)?'':'<p class="hint">Ruhe-Werte und das Bild mit der Lichtkurve jedes Vergleichssterns gibt es erst für Läufe ab dem 1. November 2026. Dieser Lauf ist älter. Starte ihn neu, um sie zu sehen.</p>'; const u=datei(p,l,'vergleichssterne_lc.png');
  return `<details ${offen?'open':''}><summary style="cursor:pointer;font-size:13px">Lichtkurve jedes Vergleichssterns (gegen die übrigen)</summary><a href="${u}" target="_blank"><img class="blatt" style="margin-top:8px" alt="Lichtkurven der einzelnen Vergleichssterne" src="${u}&t=${Date.now()}"></a></details>`; }
function sternUmschalten(n,an){ const s=new Set(S.erw.exclude||[]); if(an) s.delete(n); else s.add(n); S.erw.exclude=[...s]; erwMarkieren(); }

// ------------------------------------------------------------------ logbook
async function ladeLogbuch(){ const r=await api('/api/logbuch'); S.lb=Array.isArray(r)?r:[]; zeigeLogbuch(); }
function zeigeLogbuch(){
  const q=norm($('lb_such').value);
  const R=S.lb.filter(r=>!q||norm(r.planet).includes(q)).sort((a,b)=>String(b.nacht).localeCompare(String(a.nacht)));
  $('lb').innerHTML=R.map((r,i)=>`<tr class="click" onclick="ausLogbuch(${S.lb.indexOf(r)})"><td><b>${esc(r.planet)}</b></td><td>${esc(r.nacht)}</td><td class="mono">${esc(r.lauf)}</td>
    <td>${r.status==='gueltig'?'<span class="pill pg">gültig</span>':'<span class="pill pn">Variante</span>'}</td><td style="white-space:nowrap">${r.oc_min!==''&&r.oc_min!=null?`${+r.oc_min>=0?'+':'−'}${komma(Math.abs(r.oc_min),1)} ± ${komma(r.oc_err_min,1)} min`:''}</td>
    <td>${r.tiefe_ppt?komma(r.tiefe_ppt,2)+' ppt':''}</td><td>${ampel(r.drift)}</td><td class="mono" style="font-size:11px">${esc(r.upload_datei||'')}</td></tr>`).join('')||'<tr><td colspan="8" class="hint">Logbuch leer.</td></tr>';
}
function ausLogbuch(i){ const r=S.lb[i]; if(!r) return; waehle(r.archiv&&!S.liste.some(m=>m.pfad===r.messordner)?r.archiv:r.messordner); }

// ------------------------------------------------------------------ planning (same logic as the classic page)
const PLC=['#1f5fbf','#c0392b','#2e8b57','#c98a00','#7d3cb5','#138d90','#8a5a2b','#d6338a'];
const hhmm=s=>s?new Date(s).toLocaleTimeString('de-AT',{hour:'2-digit',minute:'2-digit'}):'';
const AMP={gruen:'pg',gelb:'py',rot:'pr'}; const r0=v=>v==null?'?':Math.round(v);
async function planLaden(){ const r=await api('/api/plan'); if(r.naechte){window.PLAN=r; planZeigen(r);} else $('plan').innerHTML='<p class="hint">Noch kein Vorschlag berechnet.</p>'; }
async function planRechnen(){ $('pl_btn').disabled=true; $('pl_msg').textContent='rechne … (ExoClock, Sichtbarkeit'+($('pl_wx').checked?', Wetter':'')+($('pl_gaia').checked?', Gaia':'')+')';
  try{ const r=await api('/api/plan',{naechte:+$('pl_n').value,top:+$('pl_top').value,wetter:$('pl_wx').checked,vergleich:$('pl_gaia').checked});
    if(r.plan){window.PLAN=r.plan; planZeigen(r.plan); $('pl_msg').textContent='';} else $('pl_msg').textContent='Fehler: '+(r.ausgabe||r.fehler||'');
  } finally { $('pl_btn').disabled=false; } }
function planKurve(n){
  const S_=n.sonne, t0=new Date(S_.t0).getTime(), dt=S_.schritt_min*60000, N=S_.hoehe.length, W=640, Hh=170, L=30, B=20;
  const x=t=>L+(t-t0)/(dt*(N-1))*(W-L-6), y=a=>6+(90-Math.max(0,Math.min(90,a)))/90*(Hh-B-6);
  let g=`<svg viewBox="0 0 ${W} ${Hh}" style="width:100%;max-width:${W}px;font-size:10px" role="img" aria-label="Höhenkurven der Vorschläge">`;
  const d0=new Date(n.dunkel[0]).getTime(), d1=new Date(n.dunkel[1]).getTime();
  g+=`<rect x="${x(d0)}" y="6" width="${x(d1)-x(d0)}" height="${Hh-B-6}" fill="var(--line)" opacity=".45"/>`;
  for(const a of [0,30,60,90]) g+=`<line x1="${L}" x2="${W-6}" y1="${y(a)}" y2="${y(a)}" stroke="var(--line)"/><text x="2" y="${y(a)+3}" fill="var(--mut)">${a}&deg;</text>`;
  const am=window.PLAN.parameter.alt_min; g+=`<line x1="${L}" x2="${W-6}" y1="${y(am)}" y2="${y(am)}" stroke="var(--pr-f)" stroke-dasharray="4 3"/>`;
  for(let i=0;i<N;i+=6){ const t=t0+i*dt; g+=`<text x="${x(t)-12}" y="${Hh-5}" fill="var(--mut)">${hhmm(new Date(t).toISOString())}</text>`; }
  if(n.mond){ g+=`<polyline fill="none" stroke="var(--mut)" stroke-dasharray="2 3" points="${n.mond.map((a,i)=>x(t0+i*dt)+','+y(a)).join(' ')}"/>`; }
  n.vorschlaege.slice(0,8).forEach((s,j)=>{ const K=s.kurve, k0=new Date(K.t0).getTime(), kd=K.schritt_min*60000, c=PLC[j%PLC.length];
    const pts=K.hoehe.map((a,i)=>[k0+i*kd,a]); const s0=new Date(s.start).getTime(), s1=new Date(s.ende).getTime();
    g+=`<polyline fill="none" stroke="${c}" stroke-width="1" opacity=".5" points="${pts.map(p=>x(p[0])+','+y(p[1])).join(' ')}"/>`;
    g+=`<polyline fill="none" stroke="${c}" stroke-width="3" points="${pts.filter(p=>p[0]>=s0&&p[0]<=s1).map(p=>x(p[0])+','+y(p[1])).join(' ')}"><title>${esc(s.planet)}</title></polyline>`; });
  return g+'</svg>'; }
function planZeigen(P){
  const fmt=d=>new Date(d+'T12:00').toLocaleDateString('de-AT',{weekday:'short',day:'2-digit',month:'2-digit'});
  let h=`<p class="hint">Erstellt ${new Date(P.erstellt).toLocaleString('de-AT')} · ${P.instrument.oeffnung_cm} cm, Feld ${P.instrument.feld_arcmin[0]}'×${P.instrument.feld_arcmin[1]}' · Mindesthöhe ${P.parameter.alt_min}°`+(P.parameter.wetter?'':' · <b>ohne Wetter</b>')+'</p>';
  for(const n of P.naechte){
    if(!n.dunkel){ h+=`<h3 style="margin-top:12px">${fmt(n.datum)}</h3><p class="hint">${esc(n.hinweis||'keine Transits')}</p>`; continue; }
    const w=n.wetter; h+=`<h3 style="margin:14px 0 2px">${fmt(n.datum)} → dunkel ${hhmm(n.dunkel[0])}–${hhmm(n.dunkel[1])}</h3>
      <div class="hint">Mond ${n.mond_beleuchtung} % · `+(w?`Bewölkung im Mittel <span class="pill ${AMP[n.ampel]||'pn'}">${Math.round(w.wolken)} %</span> (max. tief ${r0(w.tief)} / mittel ${r0(w.mittel)} / hoch ${r0(w.hoch)} %)`:'Wetter: keine Vorhersage')+` · ${n.anzahl} beobachtbare Transits</div>`;
    if(!n.vorschlaege.length){ h+='<p class="hint">Kein passender Transit.</p>'; continue; }
    h+=planKurve(n);
    h+=`<div class="scroll"><table style="min-width:980px"><thead><tr><th></th><th>Score</th><th>Planet</th><th>Prio</th><th>mag</th><th>Tiefe ppt</th><th>SNR</th><th>Beobachten</th><th>Ingress / Tc / Egress</th><th>X max</th><th>Wolken</th><th>RA / Dec</th><th>Hinweise</th></tr></thead><tbody>`+
      n.vorschlaege.map((s,j)=>`<tr><td><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${j<8?PLC[j%PLC.length]:'transparent'}"></span></td>
        <td>${Math.round(s.score)}</td><td style="white-space:nowrap"><b>${esc(s.planet)}</b></td><td>${esc(s.prio)}</td><td>${s.mag!=null?komma(s.mag,1):''}</td><td>${komma(s.tiefe_ppt,1)}</td><td>${s.snr??''}</td>
        <td style="white-space:nowrap">${hhmm(s.start)}–${hhmm(s.ende)}</td><td>${hhmm(s.ingress)} / ${hhmm(s.tc)} ±${s.tc_err_min} min / ${hhmm(s.egress)}</td><td>${s.airmass_max}</td>
        <td>${s.wetter?`<span class="pill ${AMP[s.ampel]||'pn'}">${Math.round(s.wetter.wolken)} %</span>`:'?'}</td><td class="mono">${esc(s.ra)}<br>${esc(s.dec)}</td>
        <td>${esc(s.warnungen.concat(s.vergleichssterne!=null?[s.vergleichssterne+' Vergleichssterne']:[]).join('; '))}</td></tr>`).join('')+'</tbody></table></div>';
  }
  $('plan').innerHTML=h; }

// ------------------------------------------------------------------ start
async function init(){
  S.erw=lsGet('transit.erw',{})||{};
  if(!location.hash) history.replaceState(null,'','#/auswerten');
  route();
  await ladeListe();
  const p=lsGet('transit.pfad',null);
  if(p&&S.liste.some(m=>m.pfad===p)) await waehle(p); else { $('a-leer').hidden=false; }
  if(S.view==='lauf'||S.view==='vergleich') route();
  ladeAktiv();
  setInterval(()=>{ ladeAktiv(); if(document.hidden) return; if(S.view==='lauf') ladeLauf(); aktualisiere(); }, 4000);
  setInterval(()=>{ if(!document.hidden&&S.view==='auswerten') ladeListe(); }, 30000);
}
init();
</script></body></html>"""
