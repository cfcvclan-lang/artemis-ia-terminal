"""
Taux souverains et CDS 5 ans repris de Boursorama, ABC Bourse en secours.
------------------------------------------------------------------------
Boursorama ne publie ni API ni flux : on lit les tableaux de ses pages
publiques, rendus cote serveur. Deux constats verifies sur le site :

  * les taux sont des clotures de la veille (le site les marque RATES J-1),
  * les CDS aussi (SPREAD CDS J-1, avec la date du dernier calcul).

Rien ici n'est donc du temps reel, et le terminal l'affiche tel quel.
Chaque appel est mis en cache pour ne solliciter le site que quelques fois
par heure : les pages pesent pres d'un megaoctet chacune.

Ce module ne depend que de requests et de la bibliotheque standard.
"""
from __future__ import annotations

import datetime as _dt
import re
import threading
import time
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

import requests

BRS = "https://www.boursorama.com"
ABC_TAUX = "https://www.abcbourse.com/marches/cotation_taux"

TAUX_TTL = 30 * 60.0        # clotures J-1 : inutile de relire plus souvent
CDS_TTL = 60 * 60.0
ECHEC_TTL = 5 * 60.0        # une source en panne n'est pas relancee a chaque requete

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
_S = requests.Session()
_S.headers.update({
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.6",
})

# pays pour lesquels Boursorama publie une courbe de benchmarks
PAYS_COURBE = ("DEU", "BEL", "ESP", "FRA", "GRC", "IRL", "ITA", "NLD", "PRT")

_cache: Dict[str, Tuple[float, Any]] = {}
_verrou = threading.Lock()
# dernier etat connu de chaque source, pour le diagnostic
ETAT: Dict[str, Dict[str, Any]] = {}

# Boursorama ne livre pas d'historique exploitable : chaque cloture lue est
# confiee a cette fonction, que le serveur branche sur son registre
# persistant. Les courbes se remplissent ainsi au fil des jours.
NOTER = None


def _releve(date: str, valeurs: Dict[str, float]):
    if NOTER is None or not date or not valeurs:
        return
    try:
        NOTER(date, valeurs)
    except Exception:
        pass


def _cget(cle: str, ttl: float):
    with _verrou:
        v = _cache.get(cle)
    if v and time.time() - v[0] < ttl:
        return v[1]
    return None


def _cput(cle: str, val):
    with _verrou:
        _cache[cle] = (time.time(), val)


def _noter(source: str, ok: bool, ms: int, n: int = 0, err: str = ""):
    ETAT[source] = {"ok": ok, "ms": ms, "n": n, "err": err[:160], "quand": int(time.time() * 1000)}


# ----------------------------------------------------------------- lecture HTML
class _Tableaux(HTMLParser):
    """Recupere chaque <table> : lignes, cellules (texte et premier lien)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: List[List[List[Tuple[str, str]]]] = []
        self._pile: List[List[List[Tuple[str, str]]]] = []
        self._ligne: Optional[List[Tuple[str, str]]] = None
        self._cell: Optional[List[str]] = None
        self._lien = ""

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._pile.append([])
        elif tag == "tr" and self._pile:
            self._ligne = []
        elif tag in ("td", "th") and self._ligne is not None:
            self._cell, self._lien = [], ""
        elif tag == "a" and self._cell is not None and not self._lien:
            self._lien = dict(attrs).get("href") or ""
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._ligne is not None:
            self._ligne.append((" ".join("".join(self._cell).split()), self._lien))
            self._cell = None
        elif tag == "tr" and self._ligne is not None:
            if self._ligne and self._pile:
                self._pile[-1].append(self._ligne)
            self._ligne = None
        elif tag == "table" and self._pile:
            self.tables.append(self._pile.pop())

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def tableaux(html_text: str):
    p = _Tableaux()
    try:
        p.feed(html_text)
        p.close()
    except Exception:
        pass
    return p.tables


_RE_NB = re.compile(r"[-+−]?\d[\d\s  ]*(?:[.,]\d+)?")


def nombre(txt: str) -> Optional[float]:
    """'3,11%' -> 3.11, '8 374,15' -> 8374.15, '+30,0 BP' -> 30.0, '12.10' -> 12.1"""
    if not txt:
        return None
    m = _RE_NB.search(txt.replace("−", "-"))
    if not m:
        return None
    s = re.sub(r"[\s  ]", "", m.group(0)).replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _get(url: str, params=None, timeout: float = 20.0) -> str:
    r = _S.get(url, params=params, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError("HTTP %d" % r.status_code)
    if len(r.text) < 2000:
        raise RuntimeError("page trop courte, probable blocage")
    return r.text


# ----------------------------------------------------------------- taux
_RE_BENCH = re.compile(r"^([A-Z]{3})\s+BENCHMARK\s+\+?(\d+)\s*A$", re.I)
_RE_TEC = re.compile(r"^[A-Z]{3}\s+(\d+)\s*A$", re.I)


def lire_souverains(html_text: str) -> Dict[str, Any]:
    """Courbe de benchmarks du pays, TEC (France), 10 ans de tous les pays."""
    bench: Dict[str, Dict[float, dict]] = {}
    tec: Dict[float, dict] = {}
    dix: Dict[str, dict] = {}
    for t in tableaux(html_text):
        if not t:
            continue
        tete = " ".join(c[0].lower() for c in t[0])
        for ligne in t[1:]:
            if len(ligne) < 2:
                continue
            nom, lien = ligne[0]
            v = nombre(ligne[1][0])
            var = nombre(ligne[2][0]) if len(ligne) > 2 else None
            if v is None:
                continue
            m = _RE_BENCH.match(nom)
            if m:
                pays, ans = m.group(1).upper(), float(m.group(2))
                bench.setdefault(pays, {})[ans] = {"v": v, "var": var, "nom": nom}
                continue
            if "2xTEC" in lien:
                m = _RE_TEC.match(nom)
                if m:
                    tec[float(m.group(1))] = {"v": v, "var": var, "nom": "TEC " + m.group(1)}
                continue
            if "10 ans" in tete and "spread" in tete:
                # la colonne 'spread' est en fait la variation du jour en points de base
                if v > 0:
                    dix[nom.upper()] = {"v": v, "var": var, "nom": nom}
    return {"bench": bench, "tec": tec, "dix": dix}


def souverains(pays: str = "FRA") -> Dict[str, Any]:
    pays = (pays or "FRA").upper()
    if pays not in PAYS_COURBE:
        pays = "FRA"
    cle = "brs:souv:" + pays
    hit = _cget(cle, TAUX_TTL)
    if hit is not None:
        return hit
    if _cget("x:" + cle, ECHEC_TTL):
        raise RuntimeError("Boursorama indisponible, nouvel essai dans quelques minutes")
    t0 = time.time()
    try:
        params = None if pays == "FRA" else {"area_filter[countries]": pays}
        d = lire_souverains(_get(BRS + "/bourse/taux/souverains/", params=params))
        n = sum(len(v) for v in d["bench"].values()) + len(d["tec"]) + len(d["dix"])
        if not n:
            raise RuntimeError("aucun taux lu, la mise en page a peut-etre change")
        d["asof"] = _veille_ouvree()
        d["lu"] = int(time.time() * 1000)
        _cput(cle, d)
        vals = {}
        for pp, courbe in d["bench"].items():
            for a, r in courbe.items():
                vals["%s:BM:%g" % (pp, a)] = r["v"]
        for a, r in d["tec"].items():
            vals["FRA:TEC:%g" % a] = r["v"]
        for nom, r in d["dix"].items():
            vals["10A:" + nom] = r["v"]
        _releve(d["asof"], vals)
        _noter("boursorama_taux", True, int((time.time() - t0) * 1000), n)
        return d
    except Exception as exc:
        _cput("x:" + cle, True)
        _noter("boursorama_taux", False, int((time.time() - t0) * 1000), 0, str(exc))
        raise


def _veille_ouvree(auj: Optional[_dt.date] = None) -> str:
    """Date de la derniere cloture : la veille ouvree."""
    d = (auj or _dt.date.today()) - _dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= _dt.timedelta(days=1)
    return d.isoformat()


# ----------------------------------------------------------------- ABC Bourse (secours)
_RE_ABC = re.compile(r"taux\s+(\d+)\s*(an|ans|mois)\s+(.+)$", re.I)
PAYS_ABC = {"allemagne": "DEU", "france": "FRA", "italie": "ITA", "espagne": "ESP",
            "usa": "USA", "canada": "CAN", "royaume-uni": "GBR", "japon": "JPN"}


def lire_abc(html_text: str) -> Dict[str, dict]:
    """{'FRA:10': {...}, 'DEU:2': {...}, 'TEC10': {...}, 'EURIBOR3M': {...}}"""
    out: Dict[str, dict] = {}
    for t in tableaux(html_text):
        for ligne in t:
            if len(ligne) < 2:
                continue
            nom = ligne[0][0]
            v = nombre(ligne[1][0])
            if v is None:
                continue
            m = _RE_ABC.search(nom)
            if m:
                n, unite, pays = int(m.group(1)), m.group(2).lower(), m.group(3).strip().lower()
                code = PAYS_ABC.get(pays)
                if not code:
                    continue
                ans = n / 12.0 if unite == "mois" else float(n)
                out["%s:%g" % (code, ans)] = {"v": v, "nom": nom}
            elif nom.upper().replace(" ", "") == "TEC10":
                out["TEC10"] = {"v": v, "nom": nom}
            elif nom.lower().startswith("euribor"):
                out["EURIBOR:" + nom.split(" ", 1)[-1].lower()] = {"v": v, "nom": nom}
    return out


def abc() -> Dict[str, dict]:
    hit = _cget("abc", TAUX_TTL)
    if hit is not None:
        return hit
    if _cget("x:abc", ECHEC_TTL):
        raise RuntimeError("ABC Bourse indisponible, nouvel essai dans quelques minutes")
    t0 = time.time()
    try:
        d = lire_abc(_get(ABC_TAUX))
        if not d:
            raise RuntimeError("aucun taux lu, la mise en page a peut-etre change")
        _cput("abc", d)
        _releve(_veille_ouvree(), {"ABC:" + k: v["v"] for k, v in d.items() if ":" in k})
        _noter("abcbourse_taux", True, int((time.time() - t0) * 1000), len(d))
        return d
    except Exception as exc:
        _cput("x:abc", True)
        _noter("abcbourse_taux", False, int((time.time() - t0) * 1000), 0, str(exc))
        raise


# ----------------------------------------------------------------- resolution d'un taux
def taux(code: str) -> Dict[str, Any]:
    """Resout un code de taux.

    PAYS:BM:ANS   benchmark Boursorama, par exemple DEU:BM:10
    FRA:TEC:ANS   TEC de la courbe francaise, par exemple FRA:TEC:2
    10A:PAYS      10 ans du tableau multi-pays, par exemple 10A:ITALIE
    ABC:PAYS:ANS  ABC Bourse, par exemple ABC:USA:2

    Renvoie {v, var (pb), date, src, fr} ou leve une erreur explicite.
    """
    p = [x.strip() for x in (code or "").upper().split(":")]
    if len(p) >= 3 and p[0] == "ABC":
        d = abc().get("%s:%g" % (p[1], float(p[2])))
        if not d:
            raise RuntimeError("ABC Bourse ne publie pas " + code)
        return {"v": d["v"], "var": None, "date": None, "src": "ABC Bourse", "fr": "J-1",
                "nom": d["nom"]}
    if len(p) == 2 and p[0] == "10A":
        # le tableau multi-pays omet le pays de la page : la France se lit
        # donc sur la page allemande
        for page_pays in (("DEU", "FRA") if p[1] == "FRANCE" else ("FRA", "DEU")):
            s = souverains(page_pays)
            rec = s["dix"].get(p[1]) or s["dix"].get(p[1].replace("-", " "))
            if rec:
                return _sortie(rec, s)
        raise RuntimeError("10 ans absent chez Boursorama pour " + p[1])
    if len(p) == 3 and p[1] == "TEC":
        s = souverains("FRA")
        rec = s["tec"].get(float(p[2]))
        if not rec:
            raise RuntimeError("TEC %s ans absent" % p[2])
        return _sortie(rec, s)
    if len(p) == 3 and p[1] == "BM":
        s = souverains(p[0])
        courbe = s["bench"].get(p[0]) or {}
        rec = courbe.get(float(p[2]))
        if not rec:
            raise RuntimeError("benchmark %s %s ans absent" % (p[0], p[2]))
        return _sortie(rec, s)
    raise RuntimeError("code de taux inconnu : " + code)


def _sortie(rec: dict, page: dict) -> Dict[str, Any]:
    return {"v": rec["v"], "var": rec.get("var"), "date": page.get("asof"),
            "src": "Boursorama", "fr": "J-1", "nom": rec.get("nom")}


# Lignes du terminal livrees sans cotation : ce qui les alimente desormais.
# Chaque ligne a sa source principale puis ses secours, dans l'ordre.
LIGNES_ND = {
    "ND:ALLEMAGNE_2A":  ["DEU:BM:2", "ABC:DEU:2"],
    "ND:ALLEMAGNE_10A": ["DEU:BM:10", "10A:ALLEMAGNE", "ABC:DEU:10"],
    "ND:FRANCE_1A":     ["FRA:TEC:1"],
    "ND:FRANCE_2A":     ["FRA:TEC:2", "ABC:FRA:2"],
    "ND:FRANCE_10A":    ["FRA:TEC:10", "10A:FRANCE", "ABC:FRA:10"],
    "ND:ETATS-UNIS_2A": ["ABC:USA:2"],
}


def cotation(sym: str) -> Optional[Dict[str, Any]]:
    """Cotation au format de /api/quotes pour une ligne N/D ou un code BRS:..."""
    if sym.upper().startswith("BRS:CDS:"):
        code = sym[8:]
        try:
            d = cds()
        except Exception:
            return None
        for r in d["souverains"] + d["entreprises"]:
            if (r.get("code") or "").upper() == code.upper():
                ts = int(time.mktime(_dt.date.fromisoformat(d["asof"]).timetuple()) * 1000) + 9 * 3600 * 1000
                return {"p": r["spread"], "pc": r.get("veille"), "t": ts, "cur": "pb",
                        "src": "Boursorama", "fr": "J-1", "code": "CDS:" + code,
                        "nom": "CDS " + r["nom"] + " 5 ans"}
        return None
    if sym in LIGNES_ND:
        codes = LIGNES_ND[sym]
    elif sym.upper().startswith("BRS:"):
        codes = [sym[4:]]
    else:
        return None
    for c in codes:
        try:
            r = taux(c)
        except Exception:
            continue
        v, var = r["v"], r.get("var")
        pc = round(v - var / 100.0, 4) if var is not None else None
        ts = None
        if not r.get("date"):
            r["date"] = _veille_ouvree()
        if r.get("date"):
            try:
                ts = int(time.mktime(_dt.date.fromisoformat(r["date"]).timetuple()) * 1000) + 17 * 3600 * 1000
            except Exception:
                ts = None
        return {"p": v, "pc": pc, "t": ts or int(time.time() * 1000), "cur": "%",
                "src": r["src"], "fr": r["fr"], "code": c}
    return None


# ----------------------------------------------------------------- CDS 5 ans
_RE_CDS = re.compile(r"^CDS-5A\s+(.+)$", re.I)
_RE_CODE_CDS = re.compile(r"/cours/cds/3x([^/]+)/")
_RE_CALCUL = re.compile(r"dernier\s+calcul\s*(?:<[^>]+>\s*)*(\d{2})/(\d{2})/(\d{4})", re.I)
_RE_CALCUL_TXT = re.compile(r"DERNIER\s+CALCUL[^0-9]{0,200}?(\d{2})/(\d{2})/(\d{4})", re.I | re.S)


_SIGLES = {"BNP", "UBS", "HSBC", "MPS", "SA", "VZ"}


def _joli(nom: str) -> str:
    """CDS-5A BNP PARIBAS -> BNP Paribas, NOUVELLE-ZELANDE -> Nouvelle-Zelande"""
    mots = []
    for m in nom.strip().split():
        if m.upper() in _SIGLES:
            mots.append(m.upper())
        elif m.upper() == "JPMORGAN":
            mots.append("JPMorgan")
        else:
            mots.append("-".join(x.capitalize() for x in m.split("-")))
    return " ".join(mots)


def lire_cds(html_text: str, nature: str) -> List[dict]:
    """Lit le tableau des CDS. Boursorama affiche les variations multipliees
    par cent (0,30 pb ecrit +30,0 BP) : l'echelle est retrouvee en comparant
    la variation du jour a l'ecart dernier - veille."""
    brut = []
    for t in tableaux(html_text):
        for ligne in t:
            if len(ligne) < 4:
                continue
            m = _RE_CDS.match(ligne[0][0])
            if not m:
                continue
            dern, var, veille = nombre(ligne[1][0]), nombre(ligne[2][0]), nombre(ligne[3][0])
            s1 = nombre(ligne[4][0]) if len(ligne) > 4 else None
            m1 = nombre(ligne[5][0]) if len(ligne) > 5 else None
            if dern is None:
                continue
            cm = _RE_CODE_CDS.search(ligne[0][1] or "")
            brut.append({"nom": _joli(m.group(1)), "code": cm.group(1) if cm else None,
                         "sym": ("BRS:CDS:" + cm.group(1)) if cm else None,
                         "spread": dern, "veille": veille, "_var": var, "_s1": s1, "_m1": m1,
                         "nature": nature})
    # echelle des variations
    votes = [0, 0]
    for r in brut:
        if r["veille"] is None or r["_var"] in (None, 0):
            continue
        ecart = r["spread"] - r["veille"]
        if abs(ecart) < 1e-9:
            continue
        votes[0 if abs(r["_var"] / ecart - 100) < 5 else 1] += 1
    k = 100.0 if votes[0] >= votes[1] and votes[0] > 0 else 1.0
    for r in brut:
        r["var"] = round(r["spread"] - r["veille"], 2) if r["veille"] is not None else (
            None if r["_var"] is None else round(r["_var"] / k, 2))
        r["var_1s"] = None if r["_s1"] is None else round(r["_s1"] / k, 2)
        r["var_1m"] = None if r["_m1"] is None else round(r["_m1"] / k, 2)
        for x in ("_var", "_s1", "_m1"):
            r.pop(x, None)
    return brut


def date_calcul(html_text: str) -> Optional[str]:
    # le libelle se trouve vers le dernier quart d'une page d'un megaoctet
    m = _RE_CALCUL.search(html_text)
    if not m:
        m = _RE_CALCUL_TXT.search(re.sub(r"<[^>]+>", " ", html_text))
    if not m:
        return None
    j, mo, a = m.groups()
    return "%s-%s-%s" % (a, mo, j)


def cds() -> Dict[str, Any]:
    hit = _cget("brs:cds", CDS_TTL)
    if hit is not None:
        return hit
    if _cget("x:brs:cds", ECHEC_TTL):
        raise RuntimeError("Boursorama indisponible, nouvel essai dans quelques minutes")
    t0 = time.time()
    f = "credit_default_swap_filter"
    try:
        souv = lire_cds(_get(BRS + "/bourse/taux/cds/",
                             params={f + "[types]": "sovereign", f + "[area]": "0"}), "souverain")
        entr = lire_cds(_get(BRS + "/bourse/taux/cds/",
                             params={f + "[types]": "company", f + "[sectors]": "0"}), "entreprise")
        if not souv and not entr:
            raise RuntimeError("aucun CDS lu, la mise en page a peut-etre change")
        asof = None
        try:
            asof = date_calcul(_get(BRS + "/cours/cds/3xFRTR/"))
        except Exception:
            pass
        d = {"source": "Boursorama", "fr": "J-1", "asof": asof or _veille_ouvree(),
             "asof_exact": bool(asof), "lu": int(time.time() * 1000),
             "souverains": sorted(souv, key=lambda r: r["spread"]),
             "entreprises": sorted(entr, key=lambda r: r["spread"])}
        _cput("brs:cds", d)
        _releve(d["asof"], {"CDS:" + r["code"]: r["spread"]
                            for r in souv + entr if r.get("code")})
        _noter("boursorama_cds", True, int((time.time() - t0) * 1000), len(souv) + len(entr))
        return d
    except Exception as exc:
        _cput("x:brs:cds", True)
        _noter("boursorama_cds", False, int((time.time() - t0) * 1000), 0, str(exc))
        raise


# ----------------------------------------------------------------- diagnostic
def diagnostic() -> Dict[str, Any]:
    """Relit chaque source en ignorant le cache et dit ce qui repond."""
    with _verrou:
        for k in list(_cache):
            if k.startswith(("brs:", "abc", "x:")):
                _cache.pop(k, None)
    rapport: Dict[str, Any] = {}
    for nom, fn in (("boursorama_taux", lambda: souverains("FRA")),
                    ("boursorama_taux_allemagne", lambda: souverains("DEU")),
                    ("boursorama_cds", cds),
                    ("abcbourse_taux", abc)):
        t0 = time.time()
        try:
            d = fn()
            if nom.startswith("boursorama_taux"):
                pays = "DEU" if nom.endswith("allemagne") else "FRA"
                bench = d["bench"].get(pays, {})
                ech = {"%g ans" % a: r["v"] for a, r in sorted(bench.items())[:4]}
                if pays == "FRA":
                    ech = {"TEC %g" % a: r["v"] for a, r in sorted(d["tec"].items())[:5]}
                n = sum(len(v) for v in d["bench"].values()) + len(d["tec"]) + len(d["dix"])
                rapport[nom] = {"ok": True, "n": n, "echantillon": ech, "fraicheur": "J-1",
                                "dix_ans_pays": len(d["dix"])}
            elif nom == "boursorama_cds":
                rapport[nom] = {"ok": True, "n": len(d["souverains"]) + len(d["entreprises"]),
                                "souverains": len(d["souverains"]), "entreprises": len(d["entreprises"]),
                                "dernier_calcul": d["asof"], "date_lue_sur_le_site": d["asof_exact"],
                                "echantillon": {r["nom"]: r["spread"] for r in d["souverains"]
                                                if r["nom"] in ("France", "Allemagne", "Italie")}}
            else:
                rapport[nom] = {"ok": True, "n": len(d), "fraicheur": "a confirmer",
                                "echantillon": {k: v["v"] for k, v in list(d.items())[:5]}}
        except Exception as exc:
            rapport[nom] = {"ok": False, "err": str(exc)[:200]}
        rapport[nom]["ms"] = int((time.time() - t0) * 1000)
    return rapport
