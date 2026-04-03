#!/usr/bin/env python3
"""Voxtral TTS: convert text to speech using the speaker's voice.

Calls the Mistral audio.speech API with an optional voice sample for cloning.
"""

import base64
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_API_URL = "https://api.mistral.ai/v1/audio/speech"
_MODEL = os.environ.get("TTS_MODEL", "voxtral-mini-tts-2603")

# Default voice when no language mapping or voice sample is available.
# Set TTS_DEFAULT_VOICE_ID="" in .env to use API auto-selection instead.
_DEFAULT_VOICE_ID = os.environ.get("TTS_DEFAULT_VOICE_ID", "c69964a6-ab8b-4f8a-9465-ec0925096ec8")  # Paul - Neutral (EN)

# Preset voice mapping by language code → voice_id (Mistral UUID).
# Only languages with voices currently available in the API are listed.
# French voices (all Marie): neutral, happy, sad, excited, curious, angry.
# English voices: Paul (en_us) + Oliver/Jane (en_gb) with emotion variants.
# Other languages: no Mistral preset voices available yet.
#   fr_marie_neutral 5a271406-039d-46fe-835b-fbbb00eaf08d  ← default fr
#   fr_marie_happy   49d024dd-981b-4462-bb17-74d381eb8fd7
#   fr_marie_sad     4adeb2c6-25a3-44bc-8100-5234dfc1193b
#   fr_marie_excited 2f62b1af-aea3-4079-9d10-7ca665ee7243
#   fr_marie_curious e0580ce5-e63c-4cbe-88c8-a983b80c5f1f
#   fr_marie_angry   a7c07cdc-1c35-4d87-a938-c610a654f600
#   en_paul_neutral  c69964a6-ab8b-4f8a-9465-ec0925096ec8  ← default en
#   gb_oliver_neutral e3596645-b1af-469e-b857-f18ddedc7652
#   gb_jane_neutral   82c99ee6-f932-423f-a4a3-d403c8914b8d
_LANG_VOICE_MAP: dict[str, str] = {
    "fr": "e0580ce5-e63c-4cbe-88c8-a983b80c5f1f",  # fr_marie_curious
    "en": "c69964a6-ab8b-4f8a-9465-ec0925096ec8",  # en_paul_neutral
    # Other languages not yet available — falls back to TTS_DEFAULT_VOICE_ID.
}

_REQUEST_RETRIES = int(os.environ.get("TTS_REQUEST_RETRIES", "2"))
_RETRY_DELAY = 2.0

_TRANSIENT_HTTP_CODES = (429, 500, 502, 503)

_CHUNK_MAX_CHARS = int(os.environ.get("TTS_CHUNK_SIZE", "800"))


_AI_CLEAN_SYSTEM = (
    "Tu es un assistant d'accessibilité pour malvoyants. Tu reçois un texte brut copié-collé depuis "
    "une page web et tu dois le préparer pour une lecture vocale complète par un moteur TTS.\n\n"
    "ÉTAPE 1 — DÉTECTION DU TYPE DE CONTENU :\n"
    "Identifie silencieusement le type parmi : news_article, email, wikipedia, social_media, generic.\n\n"
    "ÉTAPE 2 — NETTOYAGE selon le type détecté :\n\n"
    "RÈGLES COMMUNES à tous les types :\n"
    "- OBJECTIF ABSOLU : que l'utilisateur entende TOUT le contenu éditorial, sans rien sauter\n"
    "- Conserver : titre principal, sous-titres et intertitres (intégralement), corps complet "
    "(tous les paragraphes sans exception), citations et discours rapportés\n"
    "- Citations et discours directs (les passages avec «, \" ou \u201C) : "
    "les conserver comme passages/paragraphes SÉPARÉS avec leur propre ligne vide avant et après, "
    "ne jamais les fusionner avec le texte qui les précède ou suit. Les citations entre guillemets "
    "doivent clairement être séparées du reste des paragraphes pour permettre une lecture avec une "
    "autre voix si nécessaire.\n"
    "- Légendes de photos : introduire chaque légende par 'Photo : ' suivi de son texte "
    "(l'utilisateur voit les images mais a du mal à lire)\n"
    "- Supprimer : boutons UI ('Partager', 'Tweeter', 'Lire plus tard', compteurs), "
    "métadonnées (auteur, date, temps de lecture, crédit photo seul comme 'AFP'), "
    "annotations de liens ('(Nouvelle fenêtre)', '(new window)'), URLs brutes, adresses email\n"
    "- Format de sortie : texte brut sans markdown (pas de **, *, #, tirets), "
    "paragraphes séparés par une seule ligne vide, aucun commentaire de ta part\n\n"
    "RÈGLES SPÉCIFIQUES par type :\n"
    "- news_article : supprimer aussi les encarts 'Lire aussi : [titre]', 'Sur le même sujet', "
    "'À lire aussi', 'À voir aussi', les fils d'Ariane ('Accueil > Rubrique > ...'), "
    "les blocs newsletter, et tous les liens inline éditoriaux insérés dans le corps\n"
    "- wikipedia : supprimer les références numériques [1], [2], [note 1], les bandeaux "
    "d'avertissement ('Cet article...', 'La neutralité de cet article est contestée'), "
    "les boîtes d'information latérales répétées, les catégories en bas de page\n"
    "- email : supprimer les en-têtes techniques (De :, À :, Cc :, Date :, Objet :), "
    "les pieds de page automatiques ('Ce message a été envoyé par...', 'Se désabonner', "
    "'Unsubscribe', 'Ce courriel est confidentiel'), les signatures automatiques d'entreprise\n"
    "- social_media : supprimer les compteurs (likes, retweets, vues, partages), "
    "les hashtags purs (#mot) s'ils n'apportent pas de sens, les mentions @user si ce sont "
    "des artefacts de navigation plutôt que du contenu\n"
    "- generic : appliquer uniquement les règles communes\n\n"
    """
EXEMPLE DÉTAILLÉ (news_article) — modèle à reproduire :
AVANT : {

«Aujourd’hui est votre dernier jour» : Oracle licencie des milliers de salariés par un simple e-mail
Par Ségolène Forgar
Il y a 1 jour

Sujets
Oracle
￼
Copier le lien
￼
Écouter cet article
￼
00:00/04:25
￼
L’entreprise du milliardaire Larry Ellison a procédé, ce mardi, à une vague de licenciements d’ampleur. En cause : sa réorientation stratégique vers l’intelligence artificielle.

PASSER LA PUBLICITÉ
PASSER LA PUBLICITÉ
Un e-mail laconique, envoyé aux aurores. Ce mardi 31 mars, des milliers de salariés d’Oracle ont découvert, avec stupeur, que leur poste avait tout bonnement été supprimé. Le géant de l’informatique à distance (cloud), fondé par le milliardaire Larry Ellison et basé à Austin (Texas), a en effet procédé à une vague de licenciements d’ampleur, qui toucherait près de 10.000 personnes selon un employé interrogé par la BBC. L’entreprise, qui comptait 162.000 salariés en mai 2025 d’après un document déposé auprès de la Securities and Exchange Commission (SEC), justifie ces départs par «les besoins actuels de l’entreprise».

Emploi & EntrepriseNewsletter
Tous les lundis

Recevez tous les lundis l’actualité de l’Entreprise : emploi, formation, vie de bureau, entrepreneurs, social…

Adresse e-mail
￼￼S'INSCRIRE
Le message adressé aux licenciés, révélé par Business Insider, ne laisse aucune place à l’ambiguïté. «Après un examen attentif des besoins actuels d’Oracle, nous avons pris la décision de supprimer votre poste dans le cadre d’une réorganisation plus large. Par conséquent, aujourd’hui est votre dernier jour de travail», peut-on y lire.

PASSER LA PUBLICITÉ
Publicité
Les employés congédiés ont été informés que leur accès aux outils informatiques, à leur messagerie et à leurs fichiers serait désactivé dans les heures suivantes. Ils se sont, par ailleurs, vu proposer une indemnité de départ équivalente à un mois de salaire, selon la BBC.

Investissements massifs dans l’IA
D’après les publications LinkedIn d’employés remerciés, les réductions d’effectifs concernent plusieurs départements : Oracle Health, Ventes, Cloud, Customer Success et NetSuite. Michael Shepard, cadre supérieur non touché par le plan, a précisé sur LinkedIn que des «ingénieurs seniors, architectes, responsables opérationnels, chefs de programme et spécialistes techniques» figuraient parmi les licenciés. Il a insisté sur le fait que cette «coupe significative des effectifs» n’était pas liée à la performance individuelle. «Les personnes concernées n’ont pas été licenciées en raison de ce qu’elles ont fait ou n’ont pas fait (...) Ceci est la fin d’un chapitre, pas de votre histoire», a-t-il ajouté. Sollicité par la presse américaine, Oracle se refuse pour l’heure à tout commentaire.

Il n’empêche, ces suppressions de postes interviennent alors qu’Oracle investit massivement dans l’intelligence artificielle (IA). Cette année, l’entreprise prévoit de consacrer au moins 50 milliards de dollars (43,2 milliards d’euros) au développement de ses infrastructures IA. L’objectif ? «Pouvoir répondre à la demande qu’il a déjà contractée auprès de clients tels que Nvidia, Meta Platforms, TikTok, OpenAI, xAI d’Elon Musk et le fabricant de puces Advanced Micro Devices», nous apprenaient nos confrères du Wall Street Journal  en février.

Oracle est par ailleurs partenaire du projet Stargate, une initiative à 500 milliards de dollars lancée aux côtés d’OpenAI, de SoftBank et de MGX, un fonds d’investissement soutenu par le président Donald Trump, et destinée à développer les capacités de centres de données aux États-Unis.

Wall Street applaudit, la Silicon Valley tremble
En interne, l’IA transforme déjà les méthodes de travail. «L’utilisation d’outils de codage par IA au sein d’Oracle permet à des équipes d’ingénieurs plus réduites de fournir des solutions plus complètes à nos clients, plus rapidement», déclarait Mike Sicilia, co-directeur général d’Oracle, au début du mois.

￼
PASSER LA PUBLICITÉ
Publicité
En attendant, la Bourse de Wall Street a réagi favorablement. L’action Oracle a ainsi progressé de 2,5% mardi à la mi-journée, une éclaircie pour un titre qui a perdu plus de 27% depuis le début de l’année, note Forbes .

Oracle n’est pas un cas isolé. Ces licenciements s’inscrivent dans une tendance du secteur de la tech aux États-Unis. En janvier, Amazon avait annoncé la suppression de 16.000 postes. La conséquence d’une nouvelle stratégie consistant à «réduire les niveaux hiérarchiques et à supprimer la bureaucratie». Tandis qu’on apprenait encore la semaine dernière que Meta songeait à licencier au moins 20% de ses effectifs. La maison mère de Facebook, Instagram et WhatsApp - qui emploie 79.000 personnes dans le monde - chercherait à compenser l’augmentation de ses investissements en IA et à se préparer aux changements d’organisation apportés par les assistants conversationnels.

La rédaction vous conseille
Cloud : l'américain Oracle veut lever jusqu'à 50 milliards de dollars en 2026
«Le personnage me fait peur» : Larry Ellison, le puissant magnat de la tech qui murmure à l’oreille de Donald Trump 
PASSER LA PUBLICITÉ
Publicité
«Aujourd’hui est votre dernier jour» : Oracle licencie des milliers de salariés par un simple e-mail

￼
124 commentaires
￼
S'ABONNER
PASSER LA PUBLICITÉ
PASSER LA PUBLICITÉ
124 commentaires   }

APRÈS : {

«Aujourd’hui est votre dernier jour»

Oracle licencie des milliers de salariés par un simple e-mail

Article rédigé par Ségolène Forgar, il y a 1 jour.

Photo d’illustration: L’entreprise du milliardaire Larry Ellison a procédé, ce mardi, à une vague de licenciements d’ampleur. En cause : sa réorientation stratégique vers l’intelligence artificielle.

Un e-mail laconique, envoyé aux aurores. Ce mardi 31 mars, des milliers de salariés d’Oracle ont découvert, avec stupeur, que leur poste avait tout bonnement été supprimé. Le géant de l’informatique à distance (cloud), fondé par le milliardaire Larry Ellison et basé à Austin (Texas), a en effet procédé à une vague de licenciements d’ampleur, qui toucherait près de 10.000 personnes selon un employé interrogé par la BBC. L’entreprise, qui comptait 162.000 salariés en mai 2025 d’après un document déposé auprès de la Securities and Exchange Commission (SEC), justifie ces départs par

«les besoins actuels de l’entreprise».

Le message adressé aux licenciés, révélé par Business Insider, ne laisse aucune place à l’ambiguïté. 

«Après un examen attentif des besoins actuels d’Oracle, nous avons pris la décision de supprimer votre poste dans le cadre d’une réorganisation plus large. Par conséquent, aujourd’hui est votre dernier jour de travail»,

 peut-on y lire.

Les employés congédiés ont été informés que leur accès aux outils informatiques, à leur messagerie et à leurs fichiers serait désactivé dans les heures suivantes. Ils se sont, par ailleurs, vu proposer une indemnité de départ équivalente à un mois de salaire, selon la BBC.

Investissements massifs dans l’IA
D’après les publications LinkedIn d’employés remerciés, les réductions d’effectifs concernent plusieurs départements : Oracle Health, Ventes, Cloud, Customer Success et NetSuite. Michael Shepard, cadre supérieur non touché par le plan, a précisé sur LinkedIn que des

«ingénieurs seniors, architectes, responsables opérationnels, chefs de programme et spécialistes techniques»

figuraient parmi les licenciés. Il a insisté sur le fait que cette

«coupe significative des effectifs»

n’était pas liée à la performance individuelle.

«Les personnes concernées n’ont pas été licenciées en raison de ce qu’elles ont fait ou n’ont pas fait (...) Ceci est la fin d’un chapitre, pas de votre histoire»,

a-t-il ajouté. Sollicité par la presse américaine, Oracle se refuse pour l’heure à tout commentaire.

Il n’empêche, ces suppressions de postes interviennent alors qu’Oracle investit massivement dans l’intelligence artificielle (IA). Cette année, l’entreprise prévoit de consacrer au moins 50 milliards de dollars (43,2 milliards d’euros) au développement de ses infrastructures IA. L’objectif ? 

«Pouvoir répondre à la demande qu’il a déjà contractée auprès de clients tels que Nvidia, Meta Platforms, TikTok, OpenAI, xAI d’Elon Musk et le fabricant de puces Advanced Micro Devices»,

nous apprenaient nos confrères du Wall Street Journal  en février.

Oracle est par ailleurs partenaire du projet Stargate, une initiative à 500 milliards de dollars lancée aux côtés d’OpenAI, de SoftBank et de MGX, un fonds d’investissement soutenu par le président Donald Trump, et destinée à développer les capacités de centres de données aux États-Unis.

Wall Street applaudit, la Silicon Valley tremble
En interne, l’IA transforme déjà les méthodes de travail.

«L’utilisation d’outils de codage par IA au sein d’Oracle permet à des équipes d’ingénieurs plus réduites de fournir des solutions plus complètes à nos clients, plus rapidement»,

déclarait Mike Sicilia, co-directeur général d’Oracle, au début du mois.

En attendant, la Bourse de Wall Street a réagi favorablement. L’action Oracle a ainsi progressé de 2,5% mardi à la mi-journée, une éclaircie pour un titre qui a perdu plus de 27% depuis le début de l’année, note Forbes .

Oracle n’est pas un cas isolé. Ces licenciements s’inscrivent dans une tendance du secteur de la tech aux États-Unis. En janvier, Amazon avait annoncé la suppression de 16.000 postes. La conséquence d’une nouvelle stratégie consistant à

«réduire les niveaux hiérarchiques et à supprimer la bureaucratie».

Tandis qu’on apprenait encore la semaine dernière que Meta songeait à licencier au moins 20% de ses effectifs. La maison mère de Facebook, Instagram et WhatsApp - qui emploie 79.000 personnes dans le monde - chercherait à compenser l’augmentation de ses investissements en IA et à se préparer aux changements d’organisation apportés par les assistants conversationnels.

Fin de l’article.

La rédaction vous conseille :

Cloud : l'américain Oracle veut lever jusqu'à 50 milliards de dollars en 2026

«Le personnage me fait peur» :

Larry Ellison, le puissant magnat de la tech qui murmure à l’oreille de Donald Trump 

«Aujourd’hui est votre dernier jour» :

Oracle licencie des milliers de salariés par un simple e-mail

}

"""
    "Retourne uniquement le texte nettoyé, rien d'autre."
)

_AI_CLEAN_MODEL = "devstral-latest"


def _clean_text(text: str) -> str:
    """Minimal pre-filter: remove only unreadable binary artifacts."""
    text = text.replace("\ufffc", "")  # Unicode object replacement char (icons/images)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting that would be read aloud by TTS."""
    text = re.sub(r"\*{1,3}([^*\n]+)\*{1,3}", r"\1", text)  # bold/italic
    text = re.sub(r"#{1,6}\s+", "", text)                    # headings
    text = re.sub(r"`+([^`\n]+)`+", r"\1", text)             # inline code
    return text


def _ai_clean_text(text: str) -> str:
    """Use Mistral to extract clean editorial content from web-selected text.

    Falls back to heuristic _clean_text() if the AI call fails.
    """
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("\u26a0\ufe0f  No MISTRAL_API_KEY — skipping AI cleaning.", file=sys.stderr)
        return _clean_text(text)

    print("\U0001f9f9 Cleaning text via AI...", file=sys.stderr)
    payload = {
        "model": _AI_CLEAN_MODEL,
        "messages": [
            {"role": "system", "content": _AI_CLEAN_SYSTEM},
            {"role": "user", "content": text},
        ],
        "max_tokens": 4096,
        "temperature": 0.0,
    }
    try:
        resp = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()["choices"][0]["message"]["content"].strip()
        if result:
            print(f"\u2705 AI cleaning done ({len(result)} chars).", file=sys.stderr)
            return result
    except Exception as exc:
        print(f"\u26a0\ufe0f  AI cleaning failed ({exc}), using raw text.", file=sys.stderr)
    return _clean_text(text)


def _is_quoted_paragraph(para: str) -> bool:
    """Return True if the paragraph is a direct quotation or citation.

    Matches paragraphs that begin with an opening quotation mark («, ", "),
    which covers both complete quotes («…») and attribution-style quotes
    («Citation», a-t-il dit.).
    """
    s = para.strip()
    return s.startswith(('"', "\u00AB", "\u201C"))  # ", «, "


def _split_sentences(para: str, max_chars: int) -> list[str]:
    """Sub-split a paragraph at sentence boundaries when it exceeds max_chars."""
    sentences = re.split(r'(?<=[.!?…])\s+|(?<=[.!?…]["\u00BB\u201D)])\s+', para)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return [para] if para else []
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        while len(sentence) > max_chars:
            split_at = -1
            for sep in [", ", "; ", " – ", " — "]:
                pos = sentence.rfind(sep, 0, max_chars)
                if pos > 0:
                    split_at = pos + len(sep)
                    break
            if split_at <= 0:
                split_at = sentence.rfind(" ", 0, max_chars)
            if split_at <= 0:
                split_at = max_chars
            if current:
                chunks.append(current)
                current = ""
            chunks.append(sentence[:split_at].rstrip())
            sentence = sentence[split_at:].lstrip()
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= max_chars:
            current += " " + sentence
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def _make_chunks(
    text: str,
    max_chars: int = _CHUNK_MAX_CHARS,
    quote_voice_id: Optional[str] = None,
) -> list[tuple[str, Optional[str]]]:
    """Split text into chunks preserving paragraph structure.

    Splits on double-newline paragraph boundaries first; groups consecutive small
    paragraphs into a single chunk when they fit; sub-splits oversized paragraphs
    at sentence boundaries. Never cuts mid-paragraph.

    Returns a list of (chunk_text, voice_id) tuples. voice_id is quote_voice_id
    for paragraphs that are entirely a quotation (when quote_voice_id is set),
    None otherwise.
    """
    paragraphs = re.split(r"\n\n+", text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    if not paragraphs:
        return [(text.strip(), None)] if text.strip() else []

    result: list[tuple[str, Optional[str]]] = []
    group: list[str] = []
    group_len = 0  # len("\n\n".join(group))

    def _flush_group() -> None:
        nonlocal group, group_len
        if group:
            result.append(("\n\n".join(group), None))
            group = []
            group_len = 0

    for para in paragraphs:
        quoted = quote_voice_id and _is_quoted_paragraph(para)

        if quoted:
            # Quoted paragraph: emit with quote voice, isolated from the group
            _flush_group()
            if len(para) > max_chars:
                for sub in _split_sentences(para, max_chars):
                    result.append((sub, quote_voice_id))
            else:
                result.append((para, quote_voice_id))
        elif len(para) > max_chars:
            # Oversized paragraph: flush group, then sub-split at sentence level
            _flush_group()
            for sub in _split_sentences(para, max_chars):
                result.append((sub, None))
        else:
            # Normal paragraph: try to group with previous paragraphs
            separator_len = 2 if group else 0  # "\n\n" is 2 chars
            if group and group_len + separator_len + len(para) > max_chars:
                _flush_group()
            group.append(para)
            group_len += separator_len + len(para)

    _flush_group()
    return result


def _resolve_voice_id() -> Optional[str]:
    """Resolve voice ID from environment (TTS_LANG → map, TTS_VOICE_ID, or default)."""
    tts_lang = os.environ.get("TTS_LANG", "")
    tts_voice_id_env = os.environ.get("TTS_VOICE_ID", None)
    if tts_lang and tts_lang in _LANG_VOICE_MAP:
        resolved: Optional[str] = _LANG_VOICE_MAP[tts_lang]
        print(f"\U0001f508 Voice: {tts_lang} preset ({resolved})", file=sys.stderr)
    elif tts_voice_id_env is not None:
        resolved = tts_voice_id_env or None
        label = resolved or _DEFAULT_VOICE_ID or "none"
        print(f"\U0001f508 Voice: {label}", file=sys.stderr)
    else:
        resolved = _DEFAULT_VOICE_ID or None
        print(f"\U0001f508 Voice: {resolved or 'none (will fail)'}", file=sys.stderr)
    return resolved


def _encode_voice_sample(sample_path: str) -> str:
    """Read and base64-encode a voice sample file."""
    data = Path(sample_path).read_bytes()
    return base64.b64encode(data).decode("ascii")


def synthesize(
    text: str,
    output_path: str,
    *,
    voice_sample: Optional[str] = None,
    voice_id: Optional[str] = _DEFAULT_VOICE_ID,
    voice_format: str = "mp3",
    output_format: str = "mp3",
) -> None:
    """Call Voxtral TTS and write the result to output_path.

    Args:
        text: The text to convert to speech.
        output_path: Where to write the output audio file.
        voice_sample: Path to a voice sample for cloning (optional).
        voice_id: Preset voice UUID. See GET /v1/audio/voices for available IDs.
        voice_format: Format of the voice sample file.
        output_format: Desired output audio format.
    """
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is not set. Check your .env file.")

    # API requires voice_id (preset) OR ref_audio (base64 for cloning).
    # Include language when known for correct pronunciation.
    # Response is JSON {"audio_data": "<base64>"} — must decode to get audio bytes.
    base_payload: dict = {
        "model": _MODEL,
        "input": text,
        "response_format": output_format,
    }

    ref_audio_b64: Optional[str] = None
    if voice_sample and Path(voice_sample).exists():
        ref_audio_b64 = _encode_voice_sample(voice_sample)

    # Estimate timeout: ~1s per 100 chars + base overhead
    timeout = max(10, len(text) // 100 + 15)

    # Try with voice cloning first, then fallback to preset/auto voice.
    attempts = []
    if ref_audio_b64:
        attempts.append(("with voice cloning", {**base_payload, "ref_audio": ref_audio_b64}))
    # The API requires either ref_audio or voice_id — auto mode is not supported.
    resolved_preset = voice_id or _DEFAULT_VOICE_ID
    if resolved_preset:
        attempts.append(("preset voice", {**base_payload, "voice_id": resolved_preset}))
    else:
        # No voice configured at all: this will fail — surface a clear error.
        attempts.append(("no voice", base_payload))

    for label, payload in attempts:
        last_exc: Exception = RuntimeError("unreachable")
        for attempt in range(1 + _REQUEST_RETRIES):
            if attempt > 0:
                print(
                    f"\u23f3  TTS ({label}) — retry {attempt}/{_REQUEST_RETRIES} "
                    f"(waiting {_RETRY_DELAY:.0f}s)\u2026",
                    file=sys.stderr,
                )
                time.sleep(_RETRY_DELAY)
            try:
                response = requests.post(
                    _API_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=timeout,
                )
                response.raise_for_status()
                # Response is JSON: {"audio_data": "<base64-encoded audio>"}
                audio_b64 = response.json()["audio_data"]
                Path(output_path).write_bytes(base64.b64decode(audio_b64))
                return
            except requests.HTTPError as exc:
                code = exc.response.status_code if exc.response is not None else None
                if exc.response is not None:
                    print(
                        f"\u274c TTS API error {code} ({label}): {exc.response.text[:500]}",
                        file=sys.stderr,
                    )
                if code in _TRANSIENT_HTTP_CODES:
                    last_exc = exc
                    continue
                # Non-transient error (422, etc.) — skip to next attempt mode
                last_exc = exc
                break
            except requests.Timeout as exc:
                print(f"\u23f1\ufe0f  TTS timed out ({timeout}s) \u2014 will retry\u2026", file=sys.stderr)
                last_exc = exc
                continue
        else:
            # All retries exhausted for this mode — try next
            if len(attempts) > 1 and label != "default voice":
                print(
                    f"\u26a0\ufe0f  Voice cloning failed \u2014 falling back to default voice.",
                    file=sys.stderr,
                )
                continue
        # Non-transient error broke out of retry loop — try next mode
        if len(attempts) > 1 and label != "default voice":
            print(
                f"\u26a0\ufe0f  Voice cloning failed \u2014 falling back to default voice.",
                file=sys.stderr,
            )
            continue
        raise last_exc
    raise last_exc  # type: ignore[possibly-undefined]


if __name__ == "__main__":
    # ── Chunked mode: --chunked <output_dir> ──────────────────────────────────
    # Splits text into sentence-boundary chunks, generates them with up to 2
    # parallel workers, and prints each output file path to stdout as soon as
    # it is ready — allowing the caller to start playback immediately.
    if len(sys.argv) >= 3 and sys.argv[1] == "--chunked":
        chunks_dir = sys.argv[2]
        Path(chunks_dir).mkdir(parents=True, exist_ok=True)

        text = sys.stdin.read().strip()
        if not text:
            print("\u274c No input text received.", file=sys.stderr)
            sys.exit(1)

        text = _strip_markdown(_ai_clean_text(text))
        if not text:
            print("\u274c Text is empty after cleaning.", file=sys.stderr)
            sys.exit(1)

        # Display cleaned text in terminal with blue background
        _BG = "\033[44m\033[97m"
        _RST = "\033[0m"
        print(f"{_BG}{'─' * 64}{_RST}", file=sys.stderr)
        print(f"{_BG}  Texte nettoyé — prêt pour la lecture vocale :{_RST}", file=sys.stderr)
        print(f"{_BG}{'─' * 64}{_RST}", file=sys.stderr)
        for _line in text.splitlines():
            print(f"{_BG}{_line}{_RST}", file=sys.stderr)
        print(f"{_BG}{'─' * 64}{_RST}", file=sys.stderr)

        resolved_voice_id = _resolve_voice_id()
        quote_voice_id: Optional[str] = os.environ.get("TTS_QUOTE_VOICE_ID") or None
        if quote_voice_id:
            print(f"\U0001f4ac Quote voice: {quote_voice_id}", file=sys.stderr)

        chunk_tuples = _make_chunks(text, quote_voice_id=quote_voice_id)
        total = len(chunk_tuples)
        print(
            f"\U0001f50a Generating {total} chunk(s) via {_MODEL} ({len(text)} chars)...",
            file=sys.stderr,
        )

        _CHUNK_MAX_ATTEMPTS = 5
        _CHUNK_RETRY_DELAYS = [2, 4, 8, 15]  # escalating delays between retries
        _MIN_AUDIO_BYTES = 1024  # valid mp3 should be > 1 KB

        def _gen_chunk(args: tuple[int, str, Optional[str]]) -> str:
            idx, chunk_text, chunk_voice_id = args
            citation_voice = chunk_voice_id if chunk_voice_id is not None else resolved_voice_id
            out = str(Path(chunks_dir) / f"chunk_{idx:03d}.mp3")
            Path(chunks_dir, f"chunk_{idx:03d}.txt").write_text(chunk_text, encoding="utf-8")
            last_exc: Exception = RuntimeError("unknown")
            # Attempts 0-2 use the requested voice; attempts 3-4 fall back to
            # resolved_voice_id so the text is always read even if citation voice
            # is wrong for the language or temporarily unavailable.
            _FALLBACK_AT = 3
            for attempt in range(_CHUNK_MAX_ATTEMPTS):
                use_voice = citation_voice
                if attempt >= _FALLBACK_AT and citation_voice != resolved_voice_id:
                    if attempt == _FALLBACK_AT:
                        print(
                            f"  \u26a0\ufe0f  Voix citation \u00e9chou\u00e9e \u2014 repli sur la voix normale.",
                            file=sys.stderr,
                        )
                    use_voice = resolved_voice_id
                try:
                    synthesize(chunk_text, out, voice_id=use_voice)
                    out_size = Path(out).stat().st_size if Path(out).exists() else 0
                    if out_size < _MIN_AUDIO_BYTES:
                        raise RuntimeError(f"audio trop petit ({out_size} octets)")
                    print(f"  \u2705 Passage {idx + 1}/{total} OK ({out_size:,} octets)", file=sys.stderr)
                    return out
                except Exception as exc:
                    last_exc = exc
                    delay = _CHUNK_RETRY_DELAYS[min(attempt, len(_CHUNK_RETRY_DELAYS) - 1)]
                    print(
                        f"  \u26a0\ufe0f  Passage {idx + 1}/{total} tentative {attempt + 1}/{_CHUNK_MAX_ATTEMPTS}"
                        f" \u00e9chou\u00e9e: {exc}",
                        file=sys.stderr,
                    )
                    if attempt < _CHUNK_MAX_ATTEMPTS - 1:
                        print(f"     Nouvelle tentative dans {delay}s\u2026", file=sys.stderr)
                        time.sleep(delay)
            raise last_exc

        with ThreadPoolExecutor(max_workers=3) as executor:
            # Submit with a slight stagger (0.5s between submissions) to avoid
            # hitting Mistral rate limits while keeping 2-3 chunks pre-generating.
            futures = []
            for i, (chunk_text, chunk_voice) in enumerate(chunk_tuples):
                futures.append(executor.submit(_gen_chunk, (i, chunk_text, chunk_voice)))
                if i < len(chunk_tuples) - 1:
                    time.sleep(0.5)
            for i, fut in enumerate(futures):
                try:
                    print(fut.result(), flush=True)
                except Exception as exc:
                    # Signal bash that this position failed — bash will offer retry
                    print(f"CHUNK_FAILED:{i}", flush=True)
                    print(f"\u274c Chunk {i + 1}/{total} definitively failed: {exc}", file=sys.stderr)

        sys.exit(0)

    # ── Single-file mode (default) ────────────────────────────────────────────
    if len(sys.argv) < 2:
        print(
            "Usage: tts.py <output_mp3> [voice_sample]\n"
            "       tts.py --chunked <output_dir>  (reads stdin, prints chunk paths)\n"
            "       Text is read from stdin.\n"
            "       voice_sample is optional (enables voice cloning).",
            file=sys.stderr,
        )
        sys.exit(1)

    output_file = sys.argv[1]
    sample_file = sys.argv[2] if len(sys.argv) > 2 else None

    text = sys.stdin.read().strip()
    if not text:
        print("\u274c No input text received.", file=sys.stderr)
        sys.exit(1)

    voice_fmt = "mp3"
    if sample_file and sample_file.endswith(".wav"):
        voice_fmt = "wav"

    resolved_voice_id = _resolve_voice_id()

    print(
        f"\U0001f50a Generating speech via {_MODEL} ({len(text)} chars)...",
        file=sys.stderr,
    )
    synthesize(
        text,
        output_file,
        voice_sample=sample_file,
        voice_format=voice_fmt,
        voice_id=resolved_voice_id,
    )
    print(f"\u2705 Audio saved to {output_file}", file=sys.stderr)
