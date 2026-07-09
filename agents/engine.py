["""
agents/engine.py
─────────────────
Motor genérico dos personagens: existe UM código só (este arquivo) que
sabe conversar com a IA. A personalidade de cada personagem mora só no
arquivo .txt dele, em `agents/personas/<id>.txt`.

Pra ajustar a personalidade de qualquer um dos 4 (Victor, Rafael, Aurora,
Eduardo), edite o .txt correspondente — não precisa mexer em Python.
"""]

import os              # ler a variável de ambiente GROQ_API_KEY
from groq import Groq   # cliente oficial da API da Groq (o "cérebro" dos personagens)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))  # cria o cliente já autenticado

# Limite de tokens (tamanho) de resposta por personagem — reflete a
# personalidade de cada um (Aurora fala mais, os outros são mais objetivos).
_MAX_TOKENS = {
    "aurora": 420,
    "victor": 120,
    "rafael": 150,
    "eduardo": 180,
}
_MAX_TOKENS_PADRAO = 200   # usado se algum agente novo não estiver na lista acima

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))       # pasta agents/
_PERSONAS_DIR = os.path.join(_BASE_DIR, "personas")            # pasta agents/personas/

# Cache simples: cada persona só é lida do disco uma vez por execução do servidor.
_cache_personas = {}


def _caminho_persona(agent_id):
    """Caminho do arquivo .txt daquele personagem."""
    return os.path.join(_PERSONAS_DIR, f"{agent_id}.txt")


def _carregar_persona(agent_id):
    """Lê o .txt do personagem (usando cache pra não reler toda hora)."""
    if agent_id in _cache_personas:
        return _cache_personas[agent_id]           # já leu antes, devolve do cache

    caminho = _caminho_persona(agent_id)
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            conteudo = f.read()
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Arquivo de persona não encontrado em: {caminho}. "
            f"Crie o arquivo agents/personas/{agent_id}.txt com a personalidade dele."
        )

    _cache_personas[agent_id] = conteudo   # guarda em cache pra próxima vez
    return conteudo


def get_system_prompt(agent_id):
    """Retorna o conteúdo do .txt daquele personagem (usado como system prompt)."""
    return _carregar_persona(agent_id)


def get_agent_response(agent_id, mensagens):
    """Chama a IA (Groq) com a lista de mensagens (persona + histórico) e
    devolve só o texto da resposta."""
    chat = client.chat.completions.create(
        model="llama-3.3-70b-versatile",                          # modelo usado pela Groq
        messages=mensagens,                                        # persona + histórico da conversa
        temperature=0.8,                                           # criatividade moderada (nem robótico, nem aleatório demais)
        max_tokens=_MAX_TOKENS.get(agent_id, _MAX_TOKENS_PADRAO),   # limite de tamanho da resposta
    )
    return chat.choices[0].message.content   # extrai só o texto da resposta gerada
