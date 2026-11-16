# -*- coding: utf-8 -*-
"""Panneau d'administration : demandes en attente, liste des comptes avec
reinitialisation de mot de passe en un clic, et journal d'activite."""

ADMIN = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Artemis IA Terminal &middot; Administration</title>
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
  min-height:100vh}
.wrap{max-width:1040px;margin:0 auto;padding:28px max(18px,env(safe-area-inset-left,0px)) 60px}
header{display:flex;align-items:baseline;justify-content:space-between;gap:14px;flex-wrap:wrap;
  border-bottom:1px solid var(--amber-dim);padding-bottom:14px;margin-bottom:26px}
.brand{font-family:var(--f-cond);font-size:26px;font-weight:700;letter-spacing:.14em;color:var(--amber);margin:0}
.brand span{color:var(--fg-dim);font-weight:500}
.nav{display:flex;gap:16px;align-items:center;font-size:12px}
.nav a,.nav button{color:var(--fg-dim);text-decoration:none;background:none;border:none;cursor:pointer;
  font-family:var(--f-mono);font-size:12px;padding:0}
.nav a:hover,.nav button:hover{color:var(--amber)}
h2{font-family:var(--f-cond);font-size:17px;letter-spacing:.1em;color:var(--amber);margin:30px 0 12px;
  text-transform:uppercase;font-weight:600}
h2:first-of-type{margin-top:0}
.vide{color:var(--fg-dim);font-size:12px;padding:10px 0}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{text-align:left;color:var(--fg-dim);font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;
  font-weight:600;padding:7px 10px;border-bottom:1px solid var(--grid2)}
td{padding:9px 10px;border-bottom:1px solid var(--grid);vertical-align:middle}
tr.ligne:hover td{background:#0d1012}
.role-admin{color:var(--amber-soft)}
.statut{font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;padding:2px 7px;border-radius:2px;
  border:1px solid var(--grid2);display:inline-block}
.statut.actif{color:var(--up);border-color:#0a3a23}
.statut.attente{color:var(--amber);border-color:var(--amber-dim)}
.statut.refuse,.statut.suspendu{color:var(--down);border-color:#4a1612}
.act{display:flex;gap:8px;flex-wrap:wrap}
button.b{font-family:var(--f-mono);font-size:11.5px;background:transparent;border:1px solid var(--grid2);
  color:var(--fg);padding:5px 10px;border-radius:2px;cursor:pointer;white-space:nowrap}
button.b:hover{border-color:var(--amber);color:var(--amber)}
button.b.ok{border-color:#0a3a23;color:var(--up)}
button.b.ok:hover{background:#0a3a23}
button.b.ko{border-color:#4a1612;color:var(--down)}
button.b.ko:hover{background:#2a0e0c}
.journal{background:var(--panel);border:1px solid var(--grid2);border-radius:3px;padding:12px 14px;
  max-height:340px;overflow:auto;font-size:11.5px;color:var(--fg-dim)}
.journal div{padding:3px 0;border-bottom:1px solid var(--grid);white-space:pre-wrap}
.journal div:last-child{border-bottom:none}
.recharge{font-size:11px}
/* boite modale de reinitialisation */
.fond{position:fixed;inset:0;background:rgba(0,0,0,.72);display:none;align-items:center;justify-content:center;
  z-index:50;padding:18px}
.fond.ouvert{display:flex}
.boite{background:var(--panel2);border:1px solid var(--grid2);border-radius:4px;padding:22px;max-width:420px;
  width:100%}
.boite h3{font-family:var(--f-cond);font-size:16px;letter-spacing:.08em;color:var(--amber-soft);margin:0 0 4px;
  text-transform:uppercase}
.boite p.sous{color:var(--fg-dim);font-size:11.5px;margin:0 0 16px}
label{font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--fg-dim);display:block;
  margin-bottom:5px}
input{background:#05070a;border:1px solid var(--grid2);color:var(--fg);padding:9px 10px;border-radius:2px;
  font-family:var(--f-mono);font-size:13px;width:100%}
input:focus{outline:none;border-color:var(--amber);box-shadow:0 0 0 1px var(--amber-dim)}
.aide{font-size:11px;color:var(--fg-dim);margin:6px 0 0}
.envoi{margin-top:16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.envoi button{font-family:var(--f-cond);font-size:13px;letter-spacing:.1em;text-transform:uppercase;font-weight:600;
  background:var(--amber);border:1px solid var(--amber);color:#000;padding:10px 20px;border-radius:3px;cursor:pointer}
.envoi button.annule{background:transparent;color:var(--fg-dim);border-color:var(--grid2)}
.envoi button:disabled{opacity:.5;cursor:default}
.msg{font-size:12px;min-height:16px;width:100%}
.msg.ko{color:#ffb4ae}
.msg.ok{color:#7ee2a8}
.note{color:var(--fg-dim);font-size:11.5px;margin:0 0 14px}
@media(max-width:620px){
  table,thead,tbody,th,td,tr{display:block}
  thead{display:none}
  tr.ligne{border-bottom:1px solid var(--grid2);padding:10px 0;margin-bottom:6px}
  td{border-bottom:none;padding:3px 0}
  td[data-k]::before{content:attr(data-k);display:inline-block;min-width:92px;color:var(--fg-dim);
    font-size:10.5px;text-transform:uppercase;letter-spacing:.05em}
}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1 class="brand">ARTEMIS <span>IA TERMINAL</span> &middot; Administration</h1>
    <div class="nav"><a href="/terminal">&larr; Retour au terminal</a>
      <button type="button" id="deco">Deconnexion</button></div>
  </header>

  <div id="note-env" class="note" hidden>Les acces sont declares dans la variable <b>ARTX_USERS</b> sur Render :
    la liste ci-dessous est en lecture seule, les mots de passe et validations se gerent en modifiant
    cette variable (demandez-moi de le faire).</div>

  <h2 id="t-attente">Demandes en attente</h2>
  <div id="attente"><p class="vide">Chargement&hellip;</p></div>

  <h2>Comptes</h2>
  <p class="aide" style="margin:0 0 10px">Cliquez sur un membre pour lui attribuer un nouveau mot de passe.</p>
  <div id="comptes"><p class="vide">Chargement&hellip;</p></div>

  <h2>Journal <span class="recharge">(<button type="button" class="b" id="rafraichir" style="font-size:10.5px;padding:3px 8px">Rafraichir</button>)</span></h2>
  <div class="journal" id="journal"><div>Chargement&hellip;</div></div>
</div>

<div class="fond" id="fond-mdp">
  <form class="boite" id="f-mdp">
    <h3 id="mdp-qui">Nouveau mot de passe</h3>
    <p class="sous" id="mdp-email"></p>
    <label for="mdp-val">Mot de passe</label>
    <input id="mdp-val" type="text" autocomplete="off" required>
    <p class="aide">Visible en clair pour pouvoir le transmettre tel quel. Au moins dix caracteres,
      lettres et chiffres uniquement conseille (plus simple a retaper sur un clavier AZERTY).</p>
    <div class="envoi">
      <button type="submit" id="mdp-go">Enregistrer</button>
      <button type="button" class="annule" id="mdp-annule">Annuler</button>
      <span class="msg" id="mdp-msg"></span>
    </div>
  </form>
</div>

<script>
(function(){
  "use strict";
  var $=function(i){return document.getElementById(i);};
  var EMAIL_CIBLE=null;

  function poste(url,corps){
    return fetch(url,{method:"POST",credentials:"same-origin",
      headers:{"Content-Type":"application/json"},body:JSON.stringify(corps||{})})
      .then(function(r){ return r.json().then(function(j){ j._code=r.status; return j; }); });
  }

  function dire(el,txt,ok){ el.textContent=txt||""; el.className="msg "+(ok?"ok":"ko"); }

  function echap(s){
    return String(s==null?"":s).replace(/[&<>"]/g,function(c){
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];
    });
  }

  function date(s){
    if(!s) return "";
    try{ return new Date(s*1000).toLocaleDateString("fr-FR",{day:"2-digit",month:"2-digit",year:"numeric"}); }
    catch(e){ return ""; }
  }

  var ENV=false;

  function rendreAttente(liste){
    var zone=$("attente");
    var att=(liste||[]).filter(function(u){return u.statut==="attente";});
    $("t-attente").style.display = att.length ? "" : "none";
    if(!att.length){ zone.innerHTML=""; zone.style.display="none"; return; }
    zone.style.display="";
    var h='<table><thead><tr><th>Nom</th><th>Email</th><th>Profession</th><th>Telephone</th>'
      +'<th>Demande</th><th></th></tr></thead><tbody>';
    att.forEach(function(u){
      h+='<tr class="ligne"><td data-k="Nom">'+echap(u.prenom)+' '+echap(u.nom)+'</td>'
        +'<td data-k="Email">'+echap(u.email)+'</td>'
        +'<td data-k="Profession">'+echap(u.profession)+'</td>'
        +'<td data-k="Telephone">'+echap(u.telephone)+'</td>'
        +'<td data-k="Demande">'+date(u.cree)+'</td>'
        +'<td><div class="act">'
        +(ENV?'':'<button type="button" class="b ok" data-action="valider" data-email="'+echap(u.email)+'">Valider</button>'
                +'<button type="button" class="b ko" data-action="refuser" data-email="'+echap(u.email)+'">Refuser</button>')
        +'</div></td></tr>';
    });
    h+="</tbody></table>";
    zone.innerHTML=h;
  }

  function rendreComptes(liste){
    var zone=$("comptes");
    var h='<table><thead><tr><th>Nom</th><th>Email</th><th>Role</th><th>Statut</th><th>Depuis</th><th></th></tr></thead><tbody>';
    (liste||[]).filter(function(u){return u.statut!=="attente";}).forEach(function(u){
      var estAdmin=u.role==="admin";
      h+='<tr class="ligne"><td data-k="Nom">'+echap(u.prenom)+' '+echap(u.nom)+'</td>'
        +'<td data-k="Email">'+echap(u.email)+'</td>'
        +'<td data-k="Role" class="'+(estAdmin?"role-admin":"")+'">'+(estAdmin?"Administrateur":"Membre")+'</td>'
        +'<td data-k="Statut"><span class="statut '+echap(u.statut)+'">'+echap(u.statut)+'</span></td>'
        +'<td data-k="Depuis">'+date(u.decide||u.cree)+'</td>'
        +'<td><div class="act">';
      if(!ENV){
        h+='<button type="button" class="b" data-action="mdp" data-email="'+echap(u.email)+'" '
          +'data-nom="'+echap(u.prenom+" "+u.nom)+'">Mot de passe</button>';
        if(!estAdmin){
          if(u.statut==="actif"){
            h+='<button type="button" class="b" data-action="suspendre" data-email="'+echap(u.email)+'">Suspendre</button>';
          } else if(u.statut==="suspendu"){
            h+='<button type="button" class="b ok" data-action="reactiver" data-email="'+echap(u.email)+'">Reactiver</button>';
          }
          h+='<button type="button" class="b ko" data-action="supprimer" data-email="'+echap(u.email)+'">Supprimer</button>';
        }
      }
      h+='</div></td></tr>';
    });
    h+="</tbody></table>";
    zone.innerHTML=h;
  }

  function rendreJournal(lignes){
    var zone=$("journal");
    if(!lignes||!lignes.length){ zone.innerHTML="<div>Aucune activite enregistree.</div>"; return; }
    var h="";
    lignes.slice(0,120).forEach(function(l){
      var t="";
      try{ t=new Date(l.t||0).toLocaleString("fr-FR"); }catch(e){}
      h+="<div>"+echap(t)+" &middot; "+echap(l.ev||"")+(l.email?" &middot; "+echap(l.email):"")
        +(l.detail?" &middot; "+echap(l.detail):"")+"</div>";
    });
    zone.innerHTML=h;
  }

  function chargerComptes(){
    fetch("/admin/comptes",{credentials:"same-origin"}).then(function(r){return r.json();}).then(function(j){
      if(!j.ok) return;
      ENV=!!j.env;
      $("note-env").hidden=!ENV;
      rendreAttente(j.comptes);
      rendreComptes(j.comptes);
    }).catch(function(){});
  }

  function chargerJournal(){
    fetch("/admin/journal?n=200",{credentials:"same-origin"}).then(function(r){return r.json();})
      .then(function(j){ if(j.ok) rendreJournal(j.lignes); }).catch(function(){});
  }

  function ouvrirMdp(email,nom){
    EMAIL_CIBLE=email;
    $("mdp-qui").textContent="Nouveau mot de passe";
    $("mdp-email").textContent=(nom?nom+" — ":"")+email;
    $("mdp-val").value="";
    dire($("mdp-msg"),"",true);
    $("fond-mdp").classList.add("ouvert");
    setTimeout(function(){ $("mdp-val").focus(); },30);
  }
  function fermerMdp(){ $("fond-mdp").classList.remove("ouvert"); EMAIL_CIBLE=null; }

  $("fond-mdp").addEventListener("click",function(e){ if(e.target===this) fermerMdp(); });
  $("mdp-annule").addEventListener("click",fermerMdp);

  $("f-mdp").addEventListener("submit",function(e){
    e.preventDefault();
    if(!EMAIL_CIBLE) return;
    var b=$("mdp-go"), m=$("mdp-msg");
    b.disabled=true; dire(m,"Enregistrement en cours…",true);
    poste("/admin/reinitialiser",{email:EMAIL_CIBLE,nouveau:$("mdp-val").value})
      .then(function(j){
        if(j.ok){ dire(m,"Mot de passe mis a jour.",true); setTimeout(fermerMdp,900); }
        else { dire(m,j.erreur||"Echec de la mise a jour."); b.disabled=false; }
      })
      .catch(function(){ dire(m,"Serveur injoignable."); b.disabled=false; });
  });

  function decision(email,action,bouton){
    if(action==="supprimer" && !confirm("Supprimer definitivement ce compte ("+email+") ?")) return;
    if(bouton) bouton.disabled=true;
    poste("/admin/decision",{email:email,action:action}).then(function(j){
      if(j.ok){ chargerComptes(); } else { alert(j.erreur||"Action impossible."); if(bouton) bouton.disabled=false; }
    }).catch(function(){ alert("Serveur injoignable."); if(bouton) bouton.disabled=false; });
  }

  document.addEventListener("click",function(e){
    var b=e.target.closest("button[data-action]");
    if(!b) return;
    var action=b.getAttribute("data-action"), email=b.getAttribute("data-email");
    if(action==="mdp"){ ouvrirMdp(email,b.getAttribute("data-nom")); return; }
    decision(email,action,b);
  });

  $("rafraichir").addEventListener("click",chargerJournal);

  $("deco").addEventListener("click",function(){
    poste("/auth/deconnexion",{}).then(function(){ location.href="/"; }).catch(function(){ location.href="/"; });
  });

  chargerComptes();
  chargerJournal();
})();
</script>
</body>
</html>
"""
