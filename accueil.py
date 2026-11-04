# -*- coding: utf-8 -*-
"""Page d'accueil publique du terminal : presentation, demande d'acces, connexion."""

ACCUEIL = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Artemis IA Terminal</title>
<meta name="theme-color" content="#ffa028">
<link rel="icon" type="image/svg+xml" href="/icon.svg">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Barlow+Condensed:wght@500;600;700&display=swap">
<style>
:root{
  --bg:#000; --panel:#0a0c0d; --panel2:#0f1214; --grid:#1c2124; --grid2:#262c30;
  --amber:#ffa028; --amber-dim:#8a5a14; --amber-soft:#ffd9a0;
  --up:#00d46a; --down:#ff3b30; --fg:#e6e0d4; --fg-dim:#8d867a;
  --f-mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
  --f-cond:"Barlow Condensed","Arial Narrow",system-ui,sans-serif;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--f-mono);font-size:13px;line-height:1.5;
  min-height:100vh;display:flex;flex-direction:column}
body::after{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(900px 500px at 50% -10%,rgba(255,160,40,.10),transparent 70%)}
.wrap{position:relative;z-index:1;flex:1 1 auto;width:100%;max-width:1060px;margin:0 auto;
  padding:34px max(18px,env(safe-area-inset-left,0px)) 60px}
header{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;
  border-bottom:1px solid var(--amber-dim);padding-bottom:14px;margin-bottom:30px}
.brand{font-family:var(--f-cond);font-size:30px;font-weight:700;letter-spacing:.15em;color:var(--amber);margin:0}
.brand span{color:var(--fg-dim);font-weight:500}
.sous{color:var(--fg-dim);font-size:11.5px;letter-spacing:.06em;text-transform:uppercase}
h2{font-family:var(--f-cond);font-size:19px;letter-spacing:.11em;color:var(--amber);margin:0 0 14px;
  text-transform:uppercase;font-weight:600}
.intro{max-width:70ch;color:#cdc6ba;margin:0 0 26px}
.intro b{color:var(--amber-soft);font-weight:600}
.cartes{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px;margin:0 0 34px}
.carte{background:var(--panel);border:1px solid var(--grid);border-radius:3px;padding:14px 15px}
.carte h3{font-family:var(--f-cond);font-size:14px;letter-spacing:.1em;color:var(--amber-soft);
  margin:0 0 7px;text-transform:uppercase;font-weight:600}
.carte p{margin:0;color:var(--fg-dim);font-size:12px}
.choix{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:30px}
.gros{font-family:var(--f-cond);font-size:16px;letter-spacing:.11em;text-transform:uppercase;font-weight:600;
  background:transparent;border:1px solid var(--amber-dim);color:var(--amber);padding:13px 26px;border-radius:3px;
  cursor:pointer;transition:background .14s,border-color .14s}
.gros:hover{background:#1a1206;border-color:var(--amber)}
.gros[aria-pressed="true"]{background:var(--amber);border-color:var(--amber);color:#000}
.boite{background:var(--panel);border:1px solid var(--grid2);border-radius:3px;padding:22px;max-width:560px}
.boite[hidden]{display:none}
.champs{display:grid;grid-template-columns:1fr 1fr;gap:12px 14px}
.champ{display:flex;flex-direction:column;gap:5px}
.champ.large{grid-column:1 / -1}
label{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--fg-dim)}
input{background:#05070a;border:1px solid var(--grid2);color:var(--fg);padding:9px 10px;border-radius:2px;
  font-family:var(--f-mono);font-size:13px;width:100%}
input:focus{outline:none;border-color:var(--amber);box-shadow:0 0 0 1px var(--amber-dim)}
.aide{font-size:11px;color:var(--fg-dim);margin:4px 0 0}
.envoi{margin-top:18px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.envoi button{font-family:var(--f-cond);font-size:14px;letter-spacing:.11em;text-transform:uppercase;font-weight:600;
  background:var(--amber);border:1px solid var(--amber);color:#000;padding:11px 24px;border-radius:3px;cursor:pointer}
.envoi button:disabled{opacity:.5;cursor:default}
.msg{font-size:12px;min-height:18px}
.msg.ko{color:#ffb4ae}
.msg.ok{color:#7ee2a8}
.lien{background:none;border:none;color:var(--amber);text-decoration:underline;cursor:pointer;
  font-family:var(--f-mono);font-size:12px;padding:0}
footer{position:relative;z-index:1;border-top:1px solid var(--grid);padding:16px;text-align:center;
  color:var(--fg-dim);font-size:10.5px;letter-spacing:.05em}
@media(max-width:560px){.champs{grid-template-columns:1fr}.brand{font-size:24px}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1 class="brand">ARTEMIS <span>IA TERMINAL</span></h1>
    <div class="sous">Acces reserve aux collaborateurs</div>
  </header>

  <p class="intro">Terminal de marche interne d'<b>Artemis Investment Advisors</b>. Cotations, performances
    sur six fenetres, volatilites, taux souverains et monetaires, actualite de marche et scanner quotidien
    sur l'ensemble des sous-jacents suivis par le desk. L'acces est nominatif et valide un par un par
    l'administrateur.</p>

  <div class="cartes">
    <div class="carte"><h3>Suivi de marche</h3>
      <p>Seize portefeuilles thematiques, cotations rafraichies en continu, mini graphiques, carte de chaleur
        et matrice de performance intraday a trois ans.</p></div>
    <div class="carte"><h3>Taux et macro</h3>
      <p>Courbes souveraines France, Allemagne et Etats-Unis, Euribor, taux directeurs BCE, avec la frequence
        de publication indiquee serie par serie.</p></div>
    <div class="carte"><h3>Listes personnelles</h3>
      <p>Chaque collaborateur dispose de ses propres watchlists et ajoute les titres qu'il veut suivre,
        sans toucher a la configuration des autres.</p></div>
  </div>

  <h2>Acceder au terminal</h2>
  <div class="choix">
    <button class="gros" type="button" id="b-co" aria-pressed="true">Se connecter</button>
    <button class="gros" type="button" id="b-de" aria-pressed="false" hidden>Demander un acces</button>
  </div>

  <form class="boite" id="f-co" autocomplete="on">
    <div class="champs">
      <div class="champ large"><label for="co-mail">Adresse email</label>
        <input id="co-mail" name="username" type="email" autocomplete="username" required></div>
      <div class="champ large"><label for="co-mdp">Mot de passe</label>
        <input id="co-mdp" name="password" type="password" autocomplete="current-password" required></div>
    </div>
    <div class="envoi">
      <button type="submit" id="co-go">Entrer</button>
      <span class="msg" id="co-msg"></span>
    </div>
    <p class="aide">Mot de passe oublie, ou pas encore d'acces : contactez l'administrateur,
      les acces de ce terminal sont crees a la main.</p>
  </form>

  <form class="boite" id="f-de" hidden autocomplete="on">
    <div class="champs">
      <div class="champ"><label for="de-prenom">Prenom</label>
        <input id="de-prenom" type="text" autocomplete="given-name" required></div>
      <div class="champ"><label for="de-nom">Nom</label>
        <input id="de-nom" type="text" autocomplete="family-name" required></div>
      <div class="champ large"><label for="de-mail">Adresse email, qui servira d'identifiant</label>
        <input id="de-mail" type="email" autocomplete="email" required></div>
      <div class="champ"><label for="de-prof">Profession</label>
        <input id="de-prof" type="text" autocomplete="organization-title" required></div>
      <div class="champ"><label for="de-tel">Telephone</label>
        <input id="de-tel" type="tel" autocomplete="tel" required></div>
      <div class="champ large"><label for="de-mdp">Mot de passe souhaite</label>
        <input id="de-mdp" type="password" autocomplete="new-password" required>
        <p class="aide">Dix caracteres minimum, melangeant au moins trois types parmi minuscules,
          majuscules, chiffres et signes. Vous le choisissez maintenant, il ne sera actif qu'apres validation.</p></div>
    </div>
    <div class="envoi">
      <button type="submit" id="de-go">Envoyer la demande</button>
      <span class="msg" id="de-msg"></span>
    </div>
  </form>
</div>
<footer>ARTEMIS INVESTMENT ADVISORS &middot; ORIAS n&deg; 24006144 &middot; CIF regule ACPR / AMF<br>
Outil interne reserve aux collaborateurs</footer>

<script>
(function(){
  "use strict";
  var $=function(i){return document.getElementById(i);};
  function onglet(co){
    $("b-co").setAttribute("aria-pressed",co?"true":"false");
    $("b-de").setAttribute("aria-pressed",co?"false":"true");
    $("f-co").hidden=!co; $("f-de").hidden=co;
  }
  $("b-co").onclick=function(){onglet(true);};
  $("b-de").onclick=function(){onglet(false);};
  /* le bouton de demande n'apparait que si le serveur accepte les demandes */
  fetch("/auth/demande",{method:"POST",credentials:"same-origin",
    headers:{"Content-Type":"application/json"},body:"{}"})
    .then(function(r){
      if(r.status!==403){
        $("b-de").hidden=false;
        if(location.hash==="#demande") onglet(false);
      }
    }).catch(function(){});

  function dire(el,txt,ok){ el.textContent=txt; el.className="msg "+(ok?"ok":"ko"); }

  function poste(url,corps){
    return fetch(url,{method:"POST",credentials:"same-origin",
      headers:{"Content-Type":"application/json"},body:JSON.stringify(corps)})
      .then(function(r){ return r.json().then(function(j){ j._code=r.status; return j; }); });
  }

  $("f-co").addEventListener("submit",function(e){
    e.preventDefault();
    var b=$("co-go"), m=$("co-msg");
    b.disabled=true; dire(m,"Verification en cours…",true);
    poste("/auth/connexion",{email:$("co-mail").value,mdp:$("co-mdp").value})
      .then(function(j){
        if(j.ok){ dire(m,"Acces accorde, ouverture du terminal…",true); location.href="/terminal"; }
        else { dire(m,j.erreur||"Connexion impossible."); b.disabled=false; }
      })
      .catch(function(){ dire(m,"Serveur injoignable, reessayez dans un instant."); b.disabled=false; });
  });

  $("f-de").addEventListener("submit",function(e){
    e.preventDefault();
    var b=$("de-go"), m=$("de-msg");
    b.disabled=true; dire(m,"Envoi en cours…",true);
    poste("/auth/demande",{
      email:$("de-mail").value, nom:$("de-nom").value, prenom:$("de-prenom").value,
      profession:$("de-prof").value, telephone:$("de-tel").value, mdp:$("de-mdp").value})
      .then(function(j){
        if(j.ok){
          $("f-de").reset();
          dire(m,"Demande transmise. Vous recevrez l'acces des que l'administrateur l'aura validee.",true);
        } else { dire(m,j.erreur||"Demande refusee."); }
        b.disabled=false;
      })
      .catch(function(){ dire(m,"Serveur injoignable, reessayez dans un instant."); b.disabled=false; });
  });
})();
</script>
</body>
</html>
"""
