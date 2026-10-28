# ARTEMIS IA TERMINAL - mise en ligne

Objectif : servir le terminal et son flux de marche depuis la meme origine,
ce qui supprime le probleme de CORS et autorise le rafraichissement a 15 secondes.

Ce dossier est pret a pousser tel quel. Rien a modifier.

---

## Etape 1 : deposer le code sur GitHub

1. github.com, bouton **New repository**
2. Nom : `artemis-ia-terminal`, visibilite **Private**, ne rien cocher d'autre
3. **Create repository**
4. Dans un terminal, depuis ce dossier :

```bash
git init
git add .
git commit -m "ARTEMIS IA TERMINAL - terminal et backend de donnees"
git branch -M main
git remote add origin https://github.com/VOTRE-COMPTE/artemis-ia-terminal.git
git push -u origin main
```

Sans Git en local : sur la page du depot vide, **uploading an existing file**,
glisser les cinq fichiers de ce dossier, puis **Commit changes**.

---

## Etape 2 : creer le service sur Render

1. render.com, **New** puis **Blueprint**
2. Connecter le compte GitHub, autoriser l'acces au depot `artemis-ia-terminal`
3. Render lit `render.yaml` et propose le service `artemis-ia-terminal`
4. **Apply**

Si le Blueprint n'est pas propose, passer par **New** puis **Web Service** et saisir :

| Champ | Valeur |
|---|---|
| Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/health` |
| Instance Type | Free |
| Region | Frankfurt |

---

## Etape 3 : verifier

Le service recoit une URL du type `https://artemis-ia-terminal.onrender.com`.

1. `https://.../health` doit repondre `{"ok":true,...}`
2. Ouvrir la racine : le terminal s'affiche
3. En haut a droite, le voyant doit passer au vert sur **BACKEND LIVE**

La page detecte seule son origine : servie par le backend, elle l'utilise
comme source sans aucun reglage. Si le voyant reste rouge, cliquer **BACKEND**
dans la barre d'outils et saisir l'URL du service.

---

## A savoir

- Le plan gratuit met le service en veille apres quinze minutes sans trafic.
  Le premier appel au reveil prend une dizaine de secondes, les suivants sont immediats.
  Un plan Starter supprime la veille.
- `allow_origins=["*"]` dans `main.py` ouvre l'API a tous les domaines. Une fois
  l'URL connue, la remplacer par la liste de vos domaines.
- Les taux souverains europeens (`DE10Y`, `FR10Y`, swaps EUR) ne sont pas servis
  par Yahoo et restent simules tant qu'une source dediee n'est pas branchee.
- `yfinance` est un scraping non contractuel, sans engagement de disponibilite.
  Pour une diffusion aupres des CGP, prevoir une source sous licence.

---

## Contenu du dossier

| Fichier | Role |
|---|---|
| `ARTEMIS_IA_TERMINAL.html` | le terminal, servi sur `/` |
| `main.py` | API FastAPI : quotes, history, consensus |
| `requirements.txt` | dependances epinglees |
| `render.yaml` | configuration Blueprint Render |
| `.gitignore` | exclusions Git |
