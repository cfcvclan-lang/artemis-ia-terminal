# ARTEMIS IA TERMINAL en local, sans aucun compte

Le backend tourne sur votre poste, le terminal est servi sur la meme origine,
donc flux reel et rafraichissement 15 secondes, sans GitHub ni Render.

## Prerequis
Python 3.10 ou plus. Verifier dans un terminal :

    python --version

Sinon : python.org/downloads (cocher **Add Python to PATH** sous Windows).

## Lancement

Ouvrir un terminal dans ce dossier.

Windows, PowerShell :

    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    uvicorn main:app --port 8000

macOS ou Linux :

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    uvicorn main:app --port 8000

Puis ouvrir http://127.0.0.1:8000 dans Chrome.

Le voyant en haut a droite doit afficher **BACKEND LIVE** en vert.

## Les fois suivantes

Reactiver l'environnement et relancer, l'installation n'est a faire qu'une fois :

    .venv\Scripts\Activate.ps1      (Windows)
    source .venv/bin/activate       (macOS / Linux)
    uvicorn main:app --port 8000

## Limite

Le terminal n'est accessible que depuis ce poste, et seulement tant que la
commande tourne. Pour y acceder depuis un autre appareil ou le partager,
il faut l'heberger : voir DEPLOIEMENT.md.
