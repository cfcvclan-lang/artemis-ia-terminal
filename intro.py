# -*- coding: utf-8 -*-
"""Page d'introduction du terminal, sans connexion : presentation, sessions des marches, entree."""

INTRO = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Artemis IA Terminal</title>
<meta name="theme-color" content="#000000">
<link rel="icon" type="image/svg+xml" href="/icon.svg">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Barlow+Condensed:wght@500;600;700&display=swap">
<style>
:root{
  --bg:#000; --panel:#0a0c0d; --panel2:#0f1214; --grid:#1c2124; --grid2:#262c30;
  --amber:#ffa028; --amber-dim:#8a5a14; --amber-soft:#ffd9a0;
  --up:#00d46a; --down:#ff3b30; --fg:#e6e0d4; --fg-dim:#8d867a; --fg-mute:#5c5850;
  --f-mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
  --f-cond:"Barlow Condensed","Arial Narrow",system-ui,sans-serif;
  color-scheme:dark;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--f-mono);font-size:13px;line-height:1.55;
  min-height:100vh;min-height:100dvh;display:flex;flex-direction:column;-webkit-font-smoothing:antialiased}
.tnum{font-variant-numeric:tabular-nums}

/* ---------- bandeau ---------- */
.bandeau{display:flex;align-items:center;gap:18px;flex-wrap:wrap;
  padding:14px max(28px,env(safe-area-inset-left,0px)) 14px max(28px,env(safe-area-inset-right,0px));
  padding-top:max(14px,env(safe-area-inset-top,0px));border-bottom:1px solid var(--grid)}
.marque{font-family:var(--f-cond);font-size:21px;font-weight:700;letter-spacing:.15em;color:var(--amber);margin:0;white-space:nowrap}
.marque span{color:var(--fg-dim);font-weight:500}
.bandeau .vide{flex:1 1 auto}
.signature{font-family:var(--f-cond);font-size:13px;font-weight:500;letter-spacing:.18em;text-transform:uppercase;
  color:var(--amber-dim);padding-left:16px;border-left:1px solid var(--grid2);white-space:nowrap}
.horloge{display:flex;align-items:baseline;gap:12px;color:var(--fg-dim);font-size:12px;white-space:nowrap}
.horloge b{color:var(--amber-soft);font-weight:500;font-size:14px}
.etatmarche{display:inline-flex;align-items:center;gap:7px;font-size:11.5px;color:var(--fg-dim);white-space:nowrap}
.etatmarche i{width:7px;height:7px;border-radius:50%;background:var(--fg-mute)}
.etatmarche.on i{background:var(--up);box-shadow:0 0 6px var(--up)}
.etatmarche.on{color:var(--fg)}

/* ---------- grille principale ---------- */
.page{flex:1 1 auto;display:grid;grid-template-columns:minmax(340px,5fr) minmax(0,7fr);
  max-width:1440px;width:100%;margin:0 auto}
.gauche{padding:56px 48px 48px max(28px,env(safe-area-inset-left,0px));border-right:1px solid var(--grid);
  display:flex;flex-direction:column}
.droite{padding:56px max(28px,env(safe-area-inset-right,0px)) 48px 44px;min-width:0}

h1{font-family:var(--f-cond);font-weight:700;font-size:clamp(38px,4.1vw,66px);line-height:.95;
  letter-spacing:.015em;margin:0 0 24px;color:var(--fg);text-transform:uppercase}
h1 em{font-style:normal;color:var(--amber)}
@media (max-width:1100px){ h1{font-size:clamp(38px,8vw,72px)} }
@media (max-width:480px){ h1{font-size:clamp(30px,10vw,44px)} .signature{border-left:0;padding-left:0} }
.chapo{color:#bdb6aa;max-width:46ch;margin:0 0 36px;font-size:13.5px}

.aide{font-size:11.5px;color:var(--fg-dim);margin:14px 0 0;line-height:1.6}
.gauche .bas{margin-top:auto;padding-top:40px;color:var(--fg-mute);font-size:11px;max-width:44ch}

.entree{display:flex;align-items:center;gap:18px;flex-wrap:wrap}
.cta{display:inline-flex;align-items:center;gap:14px;font-family:var(--f-cond);font-size:20px;font-weight:600;
  letter-spacing:.08em;background:var(--amber);color:#000;text-decoration:none;padding:15px 30px;border-radius:2px;
  min-height:54px;border:1px solid var(--amber);transition:background .14s}
.cta span{font-size:13px;transition:transform .14s}
.cta:hover{background:var(--amber-soft);border-color:var(--amber-soft)}
.cta:hover span{transform:translateX(3px)}
.cta:focus-visible{outline:2px solid #4fc3f7;outline-offset:3px}
.raccourci{color:var(--fg-dim);font-size:12px}
.raccourci kbd{font-family:var(--f-mono);font-size:11px;color:var(--amber);border:1px solid var(--amber-dim);border-radius:2px;padding:1px 6px}
.gauche .aide{max-width:44ch;margin-top:22px}
@media (pointer:coarse){ .raccourci{display:none} }

/* ---------- sessions mondiales ---------- */
.titre{display:flex;align-items:baseline;gap:14px;margin:0 0 16px;flex-wrap:wrap}
.titre h2{font-family:var(--f-cond);font-size:22px;font-weight:600;letter-spacing:.04em;margin:0;color:var(--fg)}
.titre span{color:var(--fg-dim);font-size:11.5px}
.sessions{position:relative;border-top:1px solid var(--grid);margin-top:30px}
.ligne{display:grid;grid-template-columns:112px minmax(0,1fr) 96px;align-items:center;height:30px;
  border-bottom:1px solid #111517}
.ligne .nom{font-size:12px;color:var(--fg-dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ligne.on .nom{color:var(--fg)}
.ligne .etat{text-align:right;font-size:11px;color:var(--fg-mute);white-space:nowrap}
.ligne.on .etat{color:var(--up)}
.ligne.bientot .etat{color:var(--amber)}
.piste{position:relative;height:100%}
.bande{position:absolute;top:9px;height:12px;background:#1f2427;border-radius:1px}
.ligne.on .bande.cur{background:var(--amber);box-shadow:0 0 10px rgba(255,160,40,.35)}
.ligne.bientot .bande{background:#3a2a10}
.axe{display:grid;grid-template-columns:112px minmax(0,1fr) 96px;height:26px;align-items:end}
.graduations{position:relative;height:100%}
.graduations span{position:absolute;bottom:4px;transform:translateX(-50%);font-size:10.5px;color:var(--fg-mute)}
.graduations span:first-child{transform:none}
.maintenant{position:absolute;top:0;bottom:0;width:0;border-left:1px solid var(--amber);pointer-events:none;z-index:2}
.maintenant b{position:absolute;top:-22px;left:0;transform:translateX(-50%);background:var(--amber);color:#000;
  font-size:10.5px;font-weight:600;padding:1px 6px;border-radius:1px;white-space:nowrap;font-family:var(--f-mono)}
.calque{position:absolute;top:0;bottom:0;left:112px;right:96px;pointer-events:none}
.legende{display:flex;gap:18px;flex-wrap:wrap;margin-top:12px;font-size:11px;color:var(--fg-dim)}
.legende i{display:inline-block;width:14px;height:8px;margin-right:6px;vertical-align:0;border-radius:1px}

/* ---------- index des fonctions ---------- */
.fonctions{margin-top:44px}
.fonctions ol{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));
  border-top:1px solid var(--grid);border-left:1px solid var(--grid)}
.fonctions li{border-right:1px solid var(--grid);border-bottom:1px solid var(--grid);padding:14px 16px 16px;min-width:0}
.fonctions kbd{font-family:var(--f-mono);font-size:11px;color:var(--amber);border:1px solid var(--amber-dim);
  border-radius:2px;padding:0 5px;margin-right:8px}
.fonctions b{font-family:var(--f-cond);font-size:16px;font-weight:600;letter-spacing:.04em;color:var(--fg)}
.fonctions p{margin:7px 0 0;font-size:11.5px;color:var(--fg-dim);line-height:1.55}

footer{border-top:1px solid var(--grid);color:var(--fg-mute);font-size:10.5px;letter-spacing:.03em;
  display:flex;gap:18px;flex-wrap:wrap;justify-content:space-between;
  padding:14px max(28px,env(safe-area-inset-right,0px)) max(14px,env(safe-area-inset-bottom,0px)) max(28px,env(safe-area-inset-left,0px))}

/* ---------- tablette et mobile ---------- */
@media (max-width:1100px){
  .page{grid-template-columns:1fr}
  .gauche{border-right:0;border-bottom:1px solid var(--grid);padding:44px 28px 40px}
  .gauche .bas{display:none}
  .droite{padding:40px 28px 44px}
}
@media (max-width:760px){
  .fonctions ol{grid-template-columns:1fr 1fr}
  .ligne,.axe{grid-template-columns:84px minmax(0,1fr) 78px}
  .calque{left:84px;right:78px}
  .horloge .date{display:none}
}
.etat .court{display:none}
@media (max-width:480px){
  .fonctions ol{grid-template-columns:1fr}
  .etat .long{display:none} .etat .court{display:inline}
  .ligne,.axe{grid-template-columns:74px minmax(0,1fr) 76px}
  .calque{left:74px;right:76px}
  .ligne .etat{font-size:10.5px}
  .graduations span.mineure{display:none}
}
@media (prefers-reduced-motion:reduce){ *{transition:none!important} }
</style>
</head>
<body>
<header class="bandeau">
  <p class="marque">ARTEMIS <span>IA TERMINAL</span></p>
  <span class="signature">Designed by OB</span>
  <span class="vide"></span>
  <span class="etatmarche" id="em"><i></i><span id="em-txt">Euronext Paris</span></span>
  <span class="horloge"><span class="date" id="h-date"></span><b class="tnum" id="h-heure">--:--:--</b><span>Paris</span></span>
</header>

<main class="page">
  <section class="gauche">
    <h1>Beyond data.<br>Into <em>intelligence.</em></h1>
    <p class="chapo">Le terminal interne d'Artemis Investment Advisors. Cotations en continu, performances
      de la séance à trois ans, taux, crédit, calendrier et actualité sur l'ensemble des sous-jacents suivis par le desk.</p>

    <div class="entree">
      <a class="cta" href="/terminal" id="go">Entrer dans le terminal<span aria-hidden="true">&#9654;</span></a>
      <span class="raccourci">ou appuyez sur <kbd>Entrée</kbd></span>
    </div>

    <p class="bas">Données de marché fournies à titre d'information, avec un différé possible selon les sources.
      Elles ne constituent ni un conseil ni une recommandation d'investissement.</p>
  </section>

  <section class="droite" aria-label="Sessions des marchés">
    <div class="titre"><h2>Sessions des marchés</h2><span id="s-sous">Horaires de séance au comptant, heure de Paris</span></div>
    <div class="sessions" id="sessions"></div>
    <div class="axe"><span></span><div class="graduations" id="grad"></div><span></span></div>
    <div class="legende">
      <span><i style="background:var(--amber)"></i>Séance en cours</span>
      <span><i style="background:#3a2a10"></i>Ouverture dans moins d'une heure</span>
      <span><i style="background:#1f2427"></i>Séance fermée</span>
    </div>

    <div class="fonctions">
      <div class="titre"><h2>Dans le terminal</h2><span>Une touche par fonction, au clavier comme au doigt</span></div>
      <ol>
        <li><kbd>F1</kbd><b>Moniteur</b><p>Cotations, variations sur six fenêtres, tendances et volatilité, liste par liste.</p></li>
        <li><kbd>F2</kbd><b>Heatmap</b><p>La séance d'un coup d'œil, triée de la plus forte hausse à la plus forte baisse.</p></li>
        <li><kbd>F3</kbd><b>Performance</b><p>Matrice de la séance à trois ans pour comparer toute une liste.</p></li>
        <li><kbd>F4</kbd><b>Graphiques</b><p>Historique jusqu'à cinq ans, moyennes mobiles, RSI, Bollinger et comparaison.</p></li>
        <li><kbd>F5</kbd><b>Taux</b><p>Courbes souveraines, Euribor et taux directeurs, avec leur fréquence de publication.</p></li>
        <li><kbd>F6</kbd><b>Actualité</b><p>Le fil de marché filtré par liste ou par valeur.</p></li>
        <li><kbd>F7</kbd><b>Scanner</b><p>Volumes inhabituels, écarts aux moyennes et plus hauts, sur tout l'univers.</p></li>
        <li><kbd>F8</kbd><b>Calendrier</b><p>Banques centrales, publications de résultats et échéances personnelles.</p></li>
        <li><kbd>F9</kbd><b>Crédit</b><p>Spreads CDS 5 ans des émetteurs suivis, issus d'ICE Clear Credit.</p></li>
      </ol>
    </div>
  </section>
</main>

<footer>
  <span>ARTEMIS INVESTMENT ADVISORS, 89 boulevard Malesherbes, 75008 Paris</span>
  <span>ORIAS n° 24006144, CIF régulé ACPR / AMF. Outil interne.</span>
</footer>

<script>
(function(){
  "use strict";
  var $=function(i){return document.getElementById(i);};

  /* ---------- entree au clavier ---------- */
  document.addEventListener("keydown",function(e){
    if(e.key==="Enter"&&!e.metaKey&&!e.ctrlKey&&!e.altKey){ e.preventDefault(); location.href="/terminal"; }
  });

  /* ---------- sessions des marchés, heure de Paris ---------- */
  var PLACES=[
    {v:"Sydney",    z:"Australia/Sydney", o:600, c:960},
    {v:"Tokyo",     z:"Asia/Tokyo",       o:540, c:930},
    {v:"Hong Kong", z:"Asia/Hong_Kong",   o:570, c:960},
    {v:"Shanghai",  z:"Asia/Shanghai",    o:570, c:900},
    {v:"Mumbai",    z:"Asia/Kolkata",     o:555, c:930},
    {v:"Dubai",     z:"Asia/Dubai",       o:600, c:840},
    {v:"Francfort", z:"Europe/Berlin",    o:540, c:1050},
    {v:"Paris",     z:"Europe/Paris",     o:540, c:1050},
    {v:"Londres",   z:"Europe/London",    o:480, c:990},
    {v:"New York",  z:"America/New_York", o:570, c:960},
    {v:"Sao Paulo", z:"America/Sao_Paulo",o:600, c:1075}
  ];
  function decalage(z){
    try{
      var p=new Intl.DateTimeFormat("en-US",{timeZone:z,timeZoneName:"longOffset"})
        .formatToParts(new Date()).filter(function(x){return x.type==="timeZoneName";})[0];
      var m=/GMT([+-])(\d{1,2}):?(\d{2})?/.exec(p?p.value:"");
      if(!m) return 0;
      return (m[1]==="-"?-1:1)*(parseInt(m[2],10)*60+parseInt(m[3]||"0",10));
    }catch(e){ return 0; }
  }
  function local(z){
    var f=new Intl.DateTimeFormat("en-GB",{timeZone:z,hour12:false,weekday:"short",hour:"2-digit",minute:"2-digit",second:"2-digit"})
      .formatToParts(new Date());
    var g={}; f.forEach(function(x){ g[x.type]=x.value; });
    return {min:(parseInt(g.hour,10)%24)*60+parseInt(g.minute,10), hms:(g.hour%24<10?"0"+(g.hour%24):g.hour)+":"+g.minute+":"+g.second,
            ouvrable:["Sat","Sun"].indexOf(g.weekday)<0};
  }
  function duree(m){ var h=Math.floor(m/60), mi=m%60; return (h?h+" h ":"")+(mi<10&&h?"0":"")+mi+(h?"":" min"); }
  function pc(m){ return (m/1440*100).toFixed(3)+"%"; }
  function bandes(deb,fin){
    /* une seance peut traverser minuit a l'heure de Paris */
    deb=((deb%1440)+1440)%1440; fin=((fin%1440)+1440)%1440;
    if(fin>deb) return [[deb,fin]];
    return [[deb,1440],[0,fin]];
  }
  function construire(){
    var g=$("grad"), h="";
    for(var k=0;k<=24;k+=3){ if(k<24) h+='<span'+(k%6?' class="mineure"':'')+' style="left:'+pc(k*60)+'">'+(k<10?"0":"")+k+"h</span>"; }
    g.innerHTML=h;
  }
  function rendre(){
    var paris=local("Europe/Paris"), offP=decalage("Europe/Paris");
    $("h-heure").textContent=paris.hms;
    try{ $("h-date").textContent=new Date().toLocaleDateString("fr-FR",{timeZone:"Europe/Paris",weekday:"long",day:"numeric",month:"long"}); }catch(e){}
    var html="", nbOn=0;
    PLACES.forEach(function(p){
      var t=local(p.z), off=decalage(p.z);
      var on=t.ouvrable&&t.min>=p.o&&t.min<p.c;
      var avant=p.o-t.min, bientot=t.ouvrable&&!on&&avant>0&&avant<=60;
      if(on) nbOn++;
      var etat = on ? '<span class="long">ferme dans </span>'+duree(p.c-t.min)
               : (t.ouvrable&&avant>0 ? '<span class="long">ouvre </span>dans '+duree(avant) : "fermée");
      var deb=p.o-off+offP, fin=p.c-off+offP;
      var bs=bandes(deb,fin).map(function(b){
        return '<span class="bande'+(on?" cur":"")+'" style="left:'+pc(b[0])+";width:"+pc(b[1]-b[0])+'"></span>'; }).join("");
      html+='<div class="ligne'+(on?" on":"")+(bientot?" bientot":"")+'"><span class="nom">'+p.v+
        '</span><div class="piste">'+bs+'</div><span class="etat">'+etat+"</span></div>";
    });
    html+='<div class="calque"><div class="maintenant" style="left:'+pc(paris.min)+'"><b>'+paris.hms.slice(0,5)+"</b></div></div>";
    $("sessions").innerHTML=html;
    var pa=local("Europe/Paris"), ouvert=pa.ouvrable&&pa.min>=540&&pa.min<1050;
    $("em").className="etatmarche"+(ouvert?" on":"");
    $("em-txt").textContent="Euronext Paris "+(ouvert?"ouverte":"fermée");
    $("s-sous").textContent=nbOn+" place"+(nbOn>1?"s":"")+" en séance sur "+PLACES.length+", horaires au comptant, heure de Paris";
  }
  construire(); rendre();
  setInterval(function(){ $("h-heure").textContent=local("Europe/Paris").hms; },1000);
  setInterval(rendre,30000);
})();
</script>
</body>
</html>
"""
