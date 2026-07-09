"""
storage.py
──────────
Guarda o progresso do jogo em um arquivo JSON simples (sem banco de dados).

Cada "jogador" (neste protótipo existe só um, veja ID_JOGADOR em app.py)
tem um arquivo em `data/<player_id>.json` com o histórico de cada
personagem, mais ou menos assim:

{
  "victor":  [{"role": "user", "content": "oi"}, {"role": "assistant", "content": "..."}],
  "rafael":  [...],
  "aurora":  [...],
  "eduardo": [...],
  "_meta":     {"inicio": "..."},   -> quando a missão começou (cronômetro)
  "_proativo": {"eduardo": [0, 1]}  -> quais pistas espontâneas já foram enviadas
}

Se o servidor for reiniciado, o arquivo continua no disco (não se perde
como perderia se tudo fosse guardado só em memória).
"""

import os                  # caminhos de arquivo/pasta
import json                # ler/escrever o histórico em formato JSON
import threading           # travar escrita pra dois pedidos não colidirem
import datetime as _dt      # guardar o horário de início da missão

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))   # pasta onde este arquivo está
_DATA_DIR = os.path.join(_BASE_DIR, "data")               # pasta data/, onde ficam os JSONs

# Trava simples: evita que duas requisições escrevam no mesmo arquivo ao
# mesmo tempo e corrompam o JSON.
_lock = threading.Lock()

# Os 4 personagens que estão de fato integrados com a IA.
AGENTES_VALIDOS = ["victor", "rafael", "aurora", "eduardo"]


def init_db():
    """Garante que a pasta `data/` existe. Chamado uma vez ao iniciar o servidor."""
    os.makedirs(_DATA_DIR, exist_ok=True)   # exist_ok: não dá erro se a pasta já existir


def _arquivo_jogador(player_id):
    """Caminho do arquivo JSON daquele jogador (ex.: data/jogador.json)."""
    return os.path.join(_DATA_DIR, f"{player_id}.json")


def _ler_arquivo(player_id):
    """Lê o JSON do jogador do disco. Se não existir ou estiver corrompido,
    devolve um progresso vazio em vez de derrubar o servidor."""
    caminho = _arquivo_jogador(player_id)
    if not os.path.exists(caminho):
        return {}
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}   # arquivo corrompido/ilegível -> recomeça do zero


def _escrever_arquivo(player_id, dados):
    """Salva o dicionário `dados` inteiro de volta no arquivo do jogador."""
    caminho = _arquivo_jogador(player_id)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)  # indent=2: fica legível se abrir manualmente


def salvar_mensagem(player_id, agent_id, role, content):
    """Adiciona uma mensagem ao histórico do jogador com aquele personagem."""
    with _lock:                                       # ninguém mais escreve enquanto isso roda
        dados = _ler_arquivo(player_id)                # carrega o progresso atual
        historico_agente = dados.setdefault(agent_id, [])  # cria a lista se ainda não existir
        historico_agente.append({"role": role, "content": content})  # adiciona a mensagem nova
        _escrever_arquivo(player_id, dados)             # grava tudo de volta no disco


def carregar_historico(player_id, agent_id):
    """Retorna a lista de mensagens salvas do jogador com aquele personagem."""
    dados = _ler_arquivo(player_id)
    return dados.get(agent_id, [])   # [] se ainda não teve nenhuma conversa com ele


def resetar_historico(player_id, agent_id=None):
    """Apaga o histórico de um personagem específico, ou de todos (agent_id=None)."""
    with _lock:
        dados = _ler_arquivo(player_id)
        if agent_id is None:
            dados = {}          # None = zera tudo (usado no botão "Reiniciar Missão")
        else:
            dados[agent_id] = []  # zera só aquele personagem
        _escrever_arquivo(player_id, dados)


# ──────────────────────────────────────────────────────────────
# Cronômetro da investigação (usado pelas mensagens espontâneas
# do Eduardo — ele "manda mensagem sozinho" depois de X segundos
# de missão, sem o jogador precisar chamá-lo).
# ──────────────────────────────────────────────────────────────

def obter_inicio_sessao(player_id):
    """Retorna (e cria, se ainda não existir) o horário em que a missão
    começou. Esse é o "tempo zero" do cronômetro."""
    with _lock:
        dados = _ler_arquivo(player_id)
        meta = dados.setdefault("_meta", {})       # cria a chave _meta se faltar
        if "inicio" not in meta:
            meta["inicio"] = _dt.datetime.utcnow().isoformat()  # grava o horário atual (1ª vez só)
            _escrever_arquivo(player_id, dados)
        return meta["inicio"]


def obter_proativos_enviados(player_id, agent_id):
    """Lista de índices de mensagens espontâneas já enviadas (pra não repetir
    a mesma pista duas vezes)."""
    dados = _ler_arquivo(player_id)
    return dados.get("_proativo", {}).get(agent_id, [])


def marcar_proativo_enviado(player_id, agent_id, indice):
    """Registra que a pista número `indice` já foi enviada pra esse personagem."""
    with _lock:
        dados = _ler_arquivo(player_id)
        proativo = dados.setdefault("_proativo", {})
        lista = proativo.setdefault(agent_id, [])
        if indice not in lista:
            lista.append(indice)
        _escrever_arquivo(player_id, dados)
