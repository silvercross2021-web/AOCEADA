"""Client de test des tests du laboratoire, sur les vues Django d'AOCEDA.

Au laboratoire, les tests parlaient au serveur FastAPI (TestClient(serveur.app).post("/api/message", json=...)). Ici, le
MÊME appel passe par les vues Django (/api/assistant/...), connecté avec un vrai compte CLIENT de test (jeton JWT) : les
tests du labo vérifient ainsi le serveur d'AOCEDA sans être réécrits.
  /api/xxx  -> /api/assistant/xxx      /  -> page de l'assistant (/ia/assistant/)
"""
import json as _json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client as ClientDjango


def compte_client(email="essai-assistant@test.ci", administrateur=False):
    """Un compte CLIENT de test (créé une fois par test) et son jeton d'accès ; `administrateur` : compte du personnel
    d'AOCEDA (banque d'exemples baoulé, crédit du GPU relu de force)."""
    from rest_framework_simplejwt.tokens import RefreshToken

    from apps.accounts.models import Client
    client = Client.objects.filter(email=email).first()
    if client is None:
        client = Client(email=email, nom="Client Essai", role="client", is_staff=administrateur)
        client.set_password("Essai-2026!")
        client.save()
    return client, str(RefreshToken.for_user(client).access_token)


def chemin_aoceda(chemin):
    if chemin == "/":
        return "/ia/assistant/"
    if chemin.startswith("/api/") and not chemin.startswith("/api/assistant/"):
        return "/api/assistant/" + chemin[len("/api/"):]
    return chemin


class Entetes(dict):
    """En-têtes d'une réponse, sans tenir compte des majuscules (comme ceux de FastAPI)."""
    def __init__(self, r):
        super().__init__({k.lower(): v for k, v in r.items()})

    def __getitem__(self, k):
        return super().__getitem__(k.lower())

    def get(self, k, d=None):
        return super().get(k.lower(), d)

    def __contains__(self, k):
        return super().__contains__(k.lower())


class Reponse:
    def __init__(self, r):
        self.status_code = r.status_code
        self.headers = Entetes(r)
        if getattr(r, "streaming", False):
            contenu = r.streaming_content
            if hasattr(contenu, "__aiter__"):          # réponse en flux asynchrone (/api/assistant/message)
                from asgiref.sync import async_to_sync

                async def tout():
                    return [m async for m in contenu]
                contenu = async_to_sync(tout)()
            self.content = b"".join(m if isinstance(m, bytes) else m.encode("utf-8") for m in contenu)
        else:
            self.content = r.content
        self.text = self.content.decode("utf-8", "replace")

    def json(self):
        return _json.loads(self.text)

    def iter_lines(self):
        return iter(self.text.splitlines())


class TestClient:
    """Même usage que fastapi.testclient.TestClient (l'application passée est ignorée : c'est Django qui répond)."""
    __test__ = False                                  # pas une classe de tests pour pytest

    def __init__(self, app=None, base_url=None, client=None, raise_server_exceptions=True, headers=None,
                 email="essai-assistant@test.ci", administrateur=False, jeton=True):
        self.django = ClientDjango(raise_request_exception=raise_server_exceptions)
        self.adresse = client[0] if client else "127.0.0.1"
        self.entetes = dict(headers or {})
        self.administrateur, self.avec_jeton, self._jeton = administrateur, jeton, None
        self.email = "admin-" + email if administrateur else email

    def _meta(self, headers):
        # compte recréé au besoin à chaque demande : la base de test est vidée entre deux tests (client gardé au niveau
        # d'un module de tests)
        meta = {"REMOTE_ADDR": self.adresse}
        if self.avec_jeton:                       # jeton=False : une demande SANS le jeton du client (refusée)
            self.compte, self._jeton = compte_client(self.email, self.administrateur)
            meta["HTTP_AUTHORIZATION"] = f"Bearer {self._jeton}"
        for k, v in {**self.entetes, **(headers or {})}.items():
            k = k.lower()
            meta["HTTP_HOST" if k == "host" else "HTTP_" + k.upper().replace("-", "_")] = v
        return meta

    def get(self, chemin, headers=None, params=None):
        return Reponse(self.django.get(chemin_aoceda(chemin), params or {}, **self._meta(headers)))

    def post(self, chemin, json=None, data=None, files=None, headers=None, content=None):
        meta = self._meta(headers)
        if files:
            corps = dict(data or {})
            for nom, f in files.items():
                nom_fichier, octets, type_ = (f + (None,) * 3)[:3] if isinstance(f, tuple) else ("fichier", f, None)
                corps[nom] = SimpleUploadedFile(nom_fichier or "fichier", octets.read() if hasattr(octets, "read") else octets,
                                                content_type=type_ or "application/octet-stream")
            return Reponse(self.django.post(chemin_aoceda(chemin), corps, **meta))
        if json is not None:
            return Reponse(self.django.post(chemin_aoceda(chemin), _json.dumps(json), content_type="application/json", **meta))
        if content is not None:
            return Reponse(self.django.post(chemin_aoceda(chemin), content, content_type="application/json", **meta))
        return Reponse(self.django.post(chemin_aoceda(chemin), data or {}, **meta))

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False
