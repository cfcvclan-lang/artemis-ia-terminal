# -*- coding: utf-8 -*-
"""
Comptes, sessions et configurations du terminal Artemis IA.

Tout est stocke dans un fichier SQLite pose sur le disque persistant Render.
Aucune dependance supplementaire, uniquement la bibliotheque standard.

Variables d'environnement lues au demarrage :
  ARTX_DATA         repertoire du disque persistant (defaut /var/data)
  ADMIN_EMAIL       adresse du compte administrateur
  ADMIN_PASSWORD    mot de passe de ce compte, defini par Othman sur Render
  ADMIN_NOM         facultatif, defaut "Administrateur"
  ADMIN_PRENOM      facultatif
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))

ITERATIONS = 200_000
DUREE_SESSION = 30 * 24 * 3600          # trente jours
DUREE_NETTOYAGE = 6 * 3600
COOKIE = "artx_s"

STATUTS = ("attente", "actif", "refuse", "suspendu")

_verrou = threading.Lock()
_cx: Optional[sqlite3.Connection] = None
_dernier_nettoyage = 0.0

# garde fou anti force brute, en memoire, suffisant a cette echelle
_tentatives: Dict[str, List[float]] = {}


# =====================================================================
#  Mode sans base : les acces vivent dans une variable d'environnement
# =====================================================================
#  Sur le plan gratuit de Render, le disque s'efface a chaque
#  redeploiement et le service s'endort au bout de quinze minutes. Une
#  base de comptes n'y survit pas. Les variables d'environnement, si.
#  Tant que les acces sont crees a la main, elles suffisent.
#
#  ARTX_USERS, une ligne par personne :
#      email | sel$empreinte | Nom Prenom | admin
#  Le dernier champ est facultatif, il vaut membre par defaut.
#  Le mot de passe n'apparait jamais, seulement son empreinte PBKDF2.

import base64
import hashlib as _hl

JOURNAL = []
JOURNAL_MAX = 500
_verrou_journal = threading.Lock()


def mode_env() -> bool:
    return bool((os.environ.get("ARTX_USERS") or "").strip())


def _lignes_env():
    brut = os.environ.get("ARTX_USERS") or ""
    brut = brut.replace("\\n", "\n")
    for ligne in brut.replace(";", "\n").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        yield ligne


def comptes_env() -> Dict[str, Dict[str, Any]]:
    """Table des acces declares dans l'environnement, email en minuscules."""
    out: Dict[str, Dict[str, Any]] = {}
    admin_env = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    for ligne in _lignes_env():
        parts = [x.strip() for x in ligne.split("|")]
        if len(parts) < 2:
            continue
        email = parts[0].lower()
        if not email_valide(email):
            continue
        sel, _, emp = parts[1].partition("$")
        if not sel or not emp:
            continue
        nom = parts[2] if len(parts) > 2 else ""
        role = (parts[3].lower() if len(parts) > 3 else "")
        if role not in ("admin", "membre"):
            role = "admin" if email == admin_env else "membre"
        morceaux = nom.split()
        out[email] = {
            "email": email, "sel": sel, "empreinte": emp,
            "prenom": morceaux[0] if morceaux else "",
            "nom": " ".join(morceaux[1:]) if len(morceaux) > 1 else "",
            "profession": "", "telephone": "",
            "role": role, "statut": "actif", "cree": 0, "decide": 0,
        }
    return out


# ------------------------------------------------- sessions signees
#  Pas de table de sessions : le cookie porte lui-meme l'identite et sa
#  date d'expiration, scellees par un HMAC. Le service peut redemarrer
#  autant de fois qu'il veut, personne n'est deconnecte.

def _secret() -> bytes:
    s = os.environ.get("ARTX_SECRET")
    if s:
        return s.encode("utf-8")
    # a defaut, une cle stable derivee des acces declares
    base = (os.environ.get("ARTX_USERS") or "") + (os.environ.get("ADMIN_PASSWORD") or "")
    return _hl.sha256(("artx|" + base).encode("utf-8")).digest()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _deb64(t: str) -> bytes:
    t = t + "=" * (-len(t) % 4)
    return base64.urlsafe_b64decode(t.encode("ascii"))


def jeton_signe(email: str) -> str:
    corps = email + "|" + str(int(time.time()) + DUREE_SESSION)
    sceau = hmac.new(_secret(), corps.encode("utf-8"), _hl.sha256).digest()[:18]
    return _b64(corps.encode("utf-8")) + "." + _b64(sceau)


def email_du_jeton(jeton: Optional[str]) -> Optional[str]:
    if not jeton or "." not in jeton:
        return None
    try:
        a, b = jeton.rsplit(".", 1)
        corps = _deb64(a).decode("utf-8")
        attendu = hmac.new(_secret(), corps.encode("utf-8"), _hl.sha256).digest()[:18]
        if not hmac.compare_digest(_deb64(b), attendu):
            return None
        email, _, fin = corps.rpartition("|")
        if int(fin) < int(time.time()):
            return None
        return email
    except Exception:
        return None


def utilisateur_env(jeton: Optional[str]) -> Optional[Dict[str, Any]]:
    email = email_du_jeton(jeton)
    if not email:
        return None
    return comptes_env().get(email)


def connecter_env(email: str, mdp: str) -> Dict[str, Any]:
    email = (email or "").strip().lower()
    u = comptes_env().get(email)
    if not u or not verifier(mdp or "", u["sel"], u["empreinte"]):
        return {"ok": False, "erreur": "Adresse ou mot de passe incorrect."}
    return {"ok": True, "jeton": jeton_signe(email), "moi": public_env(u)}


def public_env(u: Dict[str, Any]) -> Dict[str, Any]:
    return {k: u.get(k) for k in
            ("email", "nom", "prenom", "profession", "telephone", "role", "statut", "cree", "decide")}


# ------------------------------------------------------------- journal
#  Tampon circulaire en memoire, plus une ligne imprimee que Render
#  conserve sept jours dans son flux de logs.

def noter(evenement: str, email: str = "", detail: str = "", ip: str = "") -> None:
    ligne = {"t": int(time.time() * 1000), "ev": evenement,
             "email": email or "", "detail": (detail or "")[:160], "ip": ip or ""}
    with _verrou_journal:
        JOURNAL.append(ligne)
        if len(JOURNAL) > JOURNAL_MAX:
            del JOURNAL[:len(JOURNAL) - JOURNAL_MAX]
    try:
        print("ARTX %-12s %-32s %-16s %s" % (evenement, email or "-", ip or "-", detail or ""),
              flush=True)
    except Exception:
        pass


def journal(n: int = 200) -> List[Dict[str, Any]]:
    with _verrou_journal:
        return list(JOURNAL[-max(1, min(n, JOURNAL_MAX)):])[::-1]


def etat_env() -> Dict[str, Any]:
    t = comptes_env()
    return {"mode": "variable d'environnement", "comptes": len(t),
            "admins": sum(1 for v in t.values() if v["role"] == "admin"),
            "secret_dedie": bool(os.environ.get("ARTX_SECRET")),
            "journal": len(JOURNAL)}


# ---------------------------------------------------------------- stockage

def repertoire() -> str:
    """Repertoire de donnees reellement utilisable."""
    voulu = os.environ.get("ARTX_DATA", "/var/data")
    for essai in (voulu, os.path.join(HERE, "donnees"), "/tmp/artx"):
        try:
            os.makedirs(essai, exist_ok=True)
            sonde = os.path.join(essai, ".ecriture")
            with open(sonde, "w") as fh:
                fh.write("ok")
            os.remove(sonde)
            return essai
        except Exception:
            continue
    return HERE


CHEMIN_BASE = os.path.join(repertoire(), "artemis.db")


def cx() -> sqlite3.Connection:
    global _cx
    if _cx is None:
        _cx = sqlite3.connect(CHEMIN_BASE, check_same_thread=False)
        _cx.row_factory = sqlite3.Row
        _cx.execute("PRAGMA journal_mode=WAL")
        _cx.execute("PRAGMA synchronous=NORMAL")
    return _cx


SCHEMA = """
CREATE TABLE IF NOT EXISTS utilisateurs (
  email       TEXT PRIMARY KEY,
  nom         TEXT NOT NULL DEFAULT '',
  prenom      TEXT NOT NULL DEFAULT '',
  profession  TEXT NOT NULL DEFAULT '',
  telephone   TEXT NOT NULL DEFAULT '',
  empreinte   TEXT NOT NULL DEFAULT '',
  sel         TEXT NOT NULL DEFAULT '',
  role        TEXT NOT NULL DEFAULT 'membre',
  statut      TEXT NOT NULL DEFAULT 'attente',
  motif       TEXT NOT NULL DEFAULT '',
  cree        INTEGER NOT NULL DEFAULT 0,
  decide      INTEGER NOT NULL DEFAULT 0,
  vu          INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
  jeton   TEXT PRIMARY KEY,
  email   TEXT NOT NULL,
  cree    INTEGER NOT NULL,
  expire  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_email ON sessions(email);
CREATE TABLE IF NOT EXISTS configs (
  email  TEXT PRIMARY KEY,
  json   TEXT NOT NULL,
  maj    INTEGER NOT NULL
);
"""


def init() -> None:
    if mode_env():
        noter("demarrage", "", "acces lus dans ARTX_USERS, aucune base")
        return
    with _verrou:
        c = cx()
        c.executescript(SCHEMA)
        c.commit()
    bootstrap_admin()


def bootstrap_admin() -> Optional[str]:
    """Cree ou remet a jour le compte administrateur depuis les variables Render."""
    email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    mdp = os.environ.get("ADMIN_PASSWORD") or ""
    if not email or not mdp:
        return None
    sel, emp = hacher(mdp)
    maintenant = int(time.time())
    with _verrou:
        c = cx()
        ligne = c.execute("SELECT email FROM utilisateurs WHERE email=?", (email,)).fetchone()
        if ligne:
            c.execute(
                "UPDATE utilisateurs SET empreinte=?, sel=?, role='admin', statut='actif' WHERE email=?",
                (emp, sel, email),
            )
        else:
            c.execute(
                "INSERT INTO utilisateurs (email,nom,prenom,profession,telephone,empreinte,sel,"
                "role,statut,cree,decide,vu) VALUES (?,?,?,?,?,?,?,'admin','actif',?,?,1)",
                (
                    email,
                    os.environ.get("ADMIN_NOM", "Administrateur"),
                    os.environ.get("ADMIN_PRENOM", ""),
                    "Administrateur",
                    "",
                    emp,
                    sel,
                    maintenant,
                    maintenant,
                ),
            )
        c.commit()
    return email


# ------------------------------------------------------------ mots de passe

def hacher(mdp: str, sel: Optional[str] = None):
    sel = sel or secrets.token_hex(16)
    emp = hashlib.pbkdf2_hmac("sha256", mdp.encode("utf-8"), sel.encode("ascii"), ITERATIONS)
    return sel, emp.hex()


def verifier(mdp: str, sel: str, empreinte: str) -> bool:
    if not sel or not empreinte:
        return False
    _, calcul = hacher(mdp, sel)
    return hmac.compare_digest(calcul, empreinte)


RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def email_valide(v: str) -> bool:
    return bool(RE_EMAIL.match((v or "").strip()))


def souci_mdp(mdp: str) -> Optional[str]:
    if len(mdp or "") < 10:
        return "Le mot de passe doit comporter au moins dix caracteres."
    classes = sum(
        [
            any(c.islower() for c in mdp),
            any(c.isupper() for c in mdp),
            any(c.isdigit() for c in mdp),
            any(not c.isalnum() for c in mdp),
        ]
    )
    if classes < 3:
        return ("Le mot de passe doit melanger au moins trois types de caracteres "
                "parmi minuscules, majuscules, chiffres et signes.")
    return None


# --------------------------------------------------------------- cadencement

def trop_de_tentatives(cle: str, maxi: int = 8, fenetre: float = 600.0) -> bool:
    t = time.time()
    liste = [x for x in _tentatives.get(cle, []) if t - x < fenetre]
    _tentatives[cle] = liste
    return len(liste) >= maxi


def noter_tentative(cle: str) -> None:
    _tentatives.setdefault(cle, []).append(time.time())


# ------------------------------------------------------------------ sessions

def _empreinte_jeton(jeton: str) -> str:
    return hashlib.sha256(jeton.encode("ascii")).hexdigest()


def nettoyer() -> None:
    global _dernier_nettoyage
    if time.time() - _dernier_nettoyage < DUREE_NETTOYAGE:
        return
    _dernier_nettoyage = time.time()
    with _verrou:
        c = cx()
        c.execute("DELETE FROM sessions WHERE expire < ?", (int(time.time()),))
        c.commit()


def ouvrir_session(email: str) -> str:
    jeton = secrets.token_urlsafe(32)
    maintenant = int(time.time())
    with _verrou:
        c = cx()
        c.execute(
            "INSERT INTO sessions (jeton,email,cree,expire) VALUES (?,?,?,?)",
            (_empreinte_jeton(jeton), email, maintenant, maintenant + DUREE_SESSION),
        )
        c.commit()
    nettoyer()
    return jeton


def fermer_session(jeton: str) -> None:
    if not jeton:
        return
    with _verrou:
        c = cx()
        c.execute("DELETE FROM sessions WHERE jeton=?", (_empreinte_jeton(jeton),))
        c.commit()


def fermer_toutes(email: str) -> None:
    with _verrou:
        c = cx()
        c.execute("DELETE FROM sessions WHERE email=?", (email,))
        c.commit()


def utilisateur_du_jeton(jeton: Optional[str]) -> Optional[sqlite3.Row]:
    if not jeton:
        return None
    with _verrou:
        c = cx()
        s = c.execute(
            "SELECT email,expire FROM sessions WHERE jeton=?", (_empreinte_jeton(jeton),)
        ).fetchone()
        if not s or s["expire"] < int(time.time()):
            return None
        u = c.execute("SELECT * FROM utilisateurs WHERE email=?", (s["email"],)).fetchone()
    if not u or u["statut"] != "actif":
        return None
    return u


# -------------------------------------------------------------- utilisateurs

def public(u: sqlite3.Row) -> Dict[str, Any]:
    return {
        "email": u["email"],
        "nom": u["nom"],
        "prenom": u["prenom"],
        "profession": u["profession"],
        "telephone": u["telephone"],
        "role": u["role"],
        "statut": u["statut"],
        "cree": u["cree"],
        "decide": u["decide"],
    }


def creer_demande(d: Dict[str, str]) -> Dict[str, Any]:
    email = (d.get("email") or "").strip().lower()
    if not email_valide(email):
        return {"ok": False, "erreur": "Adresse email invalide."}
    souci = souci_mdp(d.get("mdp") or "")
    if souci:
        return {"ok": False, "erreur": souci}
    for champ, libelle in (
        ("nom", "le nom"),
        ("prenom", "le prenom"),
        ("profession", "la profession"),
        ("telephone", "le numero de telephone"),
    ):
        if not (d.get(champ) or "").strip():
            return {"ok": False, "erreur": "Merci de renseigner " + libelle + "."}

    sel, emp = hacher(d["mdp"])
    maintenant = int(time.time())
    with _verrou:
        c = cx()
        ex = c.execute("SELECT statut FROM utilisateurs WHERE email=?", (email,)).fetchone()
        if ex and ex["statut"] == "actif":
            return {"ok": False, "erreur": "Un acces existe deja pour cette adresse. Utilisez la connexion."}
        if ex and ex["statut"] == "attente":
            return {"ok": False, "erreur": "Une demande est deja en attente pour cette adresse."}
        champs = (
            d["nom"].strip()[:80],
            d["prenom"].strip()[:80],
            d["profession"].strip()[:120],
            d["telephone"].strip()[:40],
            emp,
            sel,
            maintenant,
        )
        if ex:
            c.execute(
                "UPDATE utilisateurs SET nom=?,prenom=?,profession=?,telephone=?,empreinte=?,sel=?,"
                "cree=?,statut='attente',motif='',decide=0,vu=0 WHERE email=?",
                champs + (email,),
            )
        else:
            c.execute(
                "INSERT INTO utilisateurs (email,nom,prenom,profession,telephone,empreinte,sel,cree,"
                "role,statut,motif,decide,vu) VALUES (?,?,?,?,?,?,?,?,'membre','attente','',0,0)",
                (email,) + champs,
            )
        c.commit()
    return {"ok": True}


def connecter(email: str, mdp: str) -> Dict[str, Any]:
    email = (email or "").strip().lower()
    with _verrou:
        c = cx()
        u = c.execute("SELECT * FROM utilisateurs WHERE email=?", (email,)).fetchone()
    if not u or not verifier(mdp or "", u["sel"], u["empreinte"]):
        return {"ok": False, "erreur": "Adresse ou mot de passe incorrect."}
    if u["statut"] == "attente":
        return {"ok": False, "erreur": "Votre demande est en cours d'examen par l'administrateur."}
    if u["statut"] == "refuse":
        return {"ok": False, "erreur": "Cette demande d'acces n'a pas ete retenue."}
    if u["statut"] == "suspendu":
        return {"ok": False, "erreur": "Cet acces est suspendu. Contactez l'administrateur."}
    return {"ok": True, "jeton": ouvrir_session(email), "moi": public(u)}


def changer_mdp(email: str, ancien: str, nouveau: str) -> Dict[str, Any]:
    souci = souci_mdp(nouveau or "")
    if souci:
        return {"ok": False, "erreur": souci}
    with _verrou:
        c = cx()
        u = c.execute("SELECT * FROM utilisateurs WHERE email=?", (email,)).fetchone()
    if not u or not verifier(ancien or "", u["sel"], u["empreinte"]):
        return {"ok": False, "erreur": "Ancien mot de passe incorrect."}
    sel, emp = hacher(nouveau)
    with _verrou:
        c = cx()
        c.execute("UPDATE utilisateurs SET empreinte=?, sel=? WHERE email=?", (emp, sel, email))
        c.commit()
    return {"ok": True}


def liste(statut: Optional[str] = None) -> List[Dict[str, Any]]:
    with _verrou:
        c = cx()
        if statut:
            r = c.execute(
                "SELECT * FROM utilisateurs WHERE statut=? ORDER BY cree DESC", (statut,)
            ).fetchall()
        else:
            r = c.execute(
                "SELECT * FROM utilisateurs ORDER BY "
                "CASE statut WHEN 'attente' THEN 0 WHEN 'actif' THEN 1 ELSE 2 END, cree DESC"
            ).fetchall()
    return [public(x) for x in r]


def en_attente() -> int:
    with _verrou:
        c = cx()
        n = c.execute("SELECT COUNT(*) n FROM utilisateurs WHERE statut='attente'").fetchone()
    return int(n["n"])


def decider(email: str, action: str, source_config: Optional[str] = None) -> Dict[str, Any]:
    email = (email or "").strip().lower()
    maintenant = int(time.time())
    with _verrou:
        c = cx()
        u = c.execute("SELECT * FROM utilisateurs WHERE email=?", (email,)).fetchone()
        if not u:
            return {"ok": False, "erreur": "Compte introuvable."}
        if u["role"] == "admin" and action in ("refuser", "suspendre", "supprimer"):
            return {"ok": False, "erreur": "Le compte administrateur ne peut pas etre modifie ici."}

        if action == "valider":
            c.execute(
                "UPDATE utilisateurs SET statut='actif', decide=?, vu=1 WHERE email=?",
                (maintenant, email),
            )
        elif action == "refuser":
            c.execute(
                "UPDATE utilisateurs SET statut='refuse', decide=?, vu=1 WHERE email=?",
                (maintenant, email),
            )
            c.execute("DELETE FROM sessions WHERE email=?", (email,))
        elif action == "suspendre":
            c.execute("UPDATE utilisateurs SET statut='suspendu', decide=? WHERE email=?",
                      (maintenant, email))
            c.execute("DELETE FROM sessions WHERE email=?", (email,))
        elif action == "reactiver":
            c.execute("UPDATE utilisateurs SET statut='actif', decide=? WHERE email=?",
                      (maintenant, email))
        elif action == "supprimer":
            c.execute("DELETE FROM utilisateurs WHERE email=?", (email,))
            c.execute("DELETE FROM sessions WHERE email=?", (email,))
            c.execute("DELETE FROM configs WHERE email=?", (email,))
        else:
            return {"ok": False, "erreur": "Action inconnue."}
        c.commit()

    # a la validation, le nouveau venu recoit une copie des listes de l'administrateur
    if action == "valider" and source_config:
        with _verrou:
            c = cx()
            deja = c.execute("SELECT email FROM configs WHERE email=?", (email,)).fetchone()
            src = c.execute("SELECT json FROM configs WHERE email=?", (source_config,)).fetchone()
            if src and not deja:
                c.execute(
                    "INSERT INTO configs (email,json,maj) VALUES (?,?,?)",
                    (email, _config_transmissible(src["json"]), maintenant),
                )
                c.commit()
    return {"ok": True}


# le nouveau venu herite des listes, pas de l'etat d'ecran ni du panneau d'administration
VOLATILES = ("view", "base", "src", "zoom", "q", "strike", "mm")


def _config_transmissible(brut: str) -> str:
    try:
        d = json.loads(brut)
    except Exception:
        return brut
    if not isinstance(d, dict):
        return brut
    for k in VOLATILES:
        d.pop(k, None)
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------- configs

LIMITE_CONFIG = 400_000


def lire_config(email: str) -> Optional[dict]:
    with _verrou:
        c = cx()
        r = c.execute("SELECT json FROM configs WHERE email=?", (email,)).fetchone()
    if not r:
        return None
    try:
        return json.loads(r["json"])
    except Exception:
        return None


def ecrire_config(email: str, donnees: Any) -> Dict[str, Any]:
    try:
        brut = json.dumps(donnees, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return {"ok": False, "erreur": "Configuration illisible."}
    if len(brut) > LIMITE_CONFIG:
        return {"ok": False, "erreur": "Configuration trop volumineuse."}
    with _verrou:
        c = cx()
        c.execute(
            "INSERT INTO configs (email,json,maj) VALUES (?,?,?) "
            "ON CONFLICT(email) DO UPDATE SET json=excluded.json, maj=excluded.maj",
            (email, brut, int(time.time())),
        )
        c.commit()
    return {"ok": True}


def etat() -> Dict[str, Any]:
    with _verrou:
        c = cx()
        n = c.execute("SELECT COUNT(*) n FROM utilisateurs").fetchone()["n"]
        a = c.execute("SELECT COUNT(*) n FROM utilisateurs WHERE statut='actif'").fetchone()["n"]
    return {
        "base": CHEMIN_BASE,
        "persistant": CHEMIN_BASE.startswith(os.environ.get("ARTX_DATA", "/var/data")),
        "comptes": n,
        "actifs": a,
        "attente": en_attente(),
        "admin_configure": bool(os.environ.get("ADMIN_EMAIL") and os.environ.get("ADMIN_PASSWORD")),
    }
