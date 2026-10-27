#!/usr/bin/env python3
# Gerador de voz da Tamaki: Kokoro ou Piper (voz treinada), local, sem internet e sem limite.
# Precisa de: numpy, onnxruntime e espeak-ng.
import argparse, json, os, re, shutil, subprocess, sys, tempfile, time, unicodedata, wave, zipfile
import numpy as np
import onnxruntime as ort

PASTA = os.environ.get("KOKORO_DIR", os.path.expanduser("~/kokoro"))
MODELO = os.path.join(PASTA, "kokoro-v1.0.onnx")  # versão completa (a int8 gera áudio quebrado)
VOZES = os.path.join(PASTA, "voices-v1.0.bin")
PASTA_PIPER = os.path.join(PASTA, "piper")  # vozes treinadas: NOME.onnx + NOME.onnx.json
VERSAO = 9  # sobe a cada atualização; o "voz --atualizar" usa isso
# Tudo fica em: Armazenamento interno > Download > tamaki_personagem > Baixado
PASTA_BASE = os.path.expanduser("~/storage/downloads/tamaki_personagem")
PASTA_VOZ = os.path.join(PASTA_BASE, "Baixado")  # fala.txt entra e os áudios saem aqui
PASTA_TREINADA = os.path.join(PASTA_BASE, "voz-treinada")  # o .zip (ou .onnx + .onnx.json) do treino entra aqui
PIPER_VERSAO = "1.8.0"  # mesma versão do notebook de treino: a pronúncia tem que ser igual à do treino
TAXA = 24000
MAX_FON = 480
ALVO = 220  # junta frases curtas até esse tamanho: a fala fica mais natural e menos robótica
VOCAB = json.loads('{";":1,":":2,",":3,".":4,"!":5,"?":6,"—":9,"…":10,"\\"":11,"(":12,")":13,"“":14,"”":15," ":16,"̃":17,"ʣ":18,"ʥ":19,"ʦ":20,"ʨ":21,"ᵝ":22,"ꭧ":23,"A":24,"I":25,"O":31,"Q":33,"S":35,"T":36,"W":39,"Y":41,"ᵊ":42,"a":43,"b":44,"c":45,"d":46,"e":47,"f":48,"h":50,"i":51,"j":52,"k":53,"l":54,"m":55,"n":56,"o":57,"p":58,"q":59,"r":60,"s":61,"t":62,"u":63,"v":64,"w":65,"x":66,"y":67,"z":68,"ɑ":69,"ɐ":70,"ɒ":71,"æ":72,"β":75,"ɔ":76,"ɕ":77,"ç":78,"ɖ":80,"ð":81,"ʤ":82,"ə":83,"ɚ":85,"ɛ":86,"ɜ":87,"ɟ":90,"ɡ":92,"ɥ":99,"ɨ":101,"ɪ":102,"ʝ":103,"ɯ":110,"ɰ":111,"ŋ":112,"ɳ":113,"ɲ":114,"ɴ":115,"ø":116,"ɸ":118,"θ":119,"œ":120,"ɹ":123,"ɾ":125,"ɻ":126,"ʁ":128,"ɽ":129,"ʂ":130,"ʃ":131,"ʈ":132,"ʧ":133,"ʊ":135,"ʋ":136,"ʌ":138,"ɣ":139,"ɤ":140,"χ":142,"ʎ":143,"ʒ":147,"ʔ":148,"ˈ":156,"ˌ":157,"ː":158,"ʰ":162,"ʲ":164,"↓":169,"→":171,"↗":172,"↘":173,"ᵻ":177}')
PONT = ';:,.!?—…"()“”'
ESPEAK = None
TEXTO_TESTE = ("Gente, você não tem noção do que aconteceu! Nem relógio trabalha de graça, amiga. "
               "Eu vou contar tintim por tintim, então senta que lá vem história.")

# padrões da Tamaki (mude aqui depois de escolher no --comparar)
BASE = dict(voz="pf_dora", vel=1.05, tom=0.0, energia=0.0)
# padrão atual = combinação do que você gostou nos testes 3 e 6
PADRAO = dict(voz="pf_dora:0.7+af_heart:0.3", vel=1.12, tom=2.0, energia=0.0, pausa=0.4)
# a voz treinada já tem o timbre certo: sem os ajustes que o Kokoro precisa
PADRAO_PIPER = dict(vel=1.0, tom=0.0, energia=0.0, pausa=0.4)


def espeak(txt, lang, dados=None):
    """dados = pasta com o espeak-ng-data do Piper (a pronúncia do treino)."""
    global ESPEAK
    extra = [f"--path={dados}"] if dados else []
    for exe in ([ESPEAK] if ESPEAK else ["espeak-ng", "espeak"]):
        try:
            r = subprocess.run([exe, *extra, "-q", "--ipa", "-v", lang, "--stdin"], input=txt,
                               capture_output=True, text=True, encoding="utf-8")
            ESPEAK = exe
            return r.stdout
        except FileNotFoundError:
            continue
    sys.exit("espeak não encontrado. Rode: pkg install espeak")


def fonemas(txt, lang):
    """Texto -> fonemas, mantendo a pontuação (igual ao kokoro-onnx)."""
    pt = "[" + re.escape(PONT) + "]+"
    partes = re.split("(" + pt + ")", txt)
    saida = ""
    for i, p in enumerate(partes):
        if not p.strip():
            continue
        if re.fullmatch(pt, p):
            saida = saida.rstrip() + p + " "
        else:
            # o espeak só pronuncia a vogal final se o trecho terminar em pontuação
            prox = partes[i + 1] if i + 1 < len(partes) else ""
            fim = prox[0] if prox and re.fullmatch(pt, prox) else "."
            f = espeak(p.strip() + fim, lang)
            f = re.sub(r"\([a-zA-Z\-]+\)", "", f)
            saida += " ".join(f.split()) + " "
    return "".join(ch for ch in saida if ch in VOCAB).strip()


def blocos(txt, lang):
    """Frases curtas são juntadas (até ~ALVO fonemas); frases longas são quebradas."""
    acc = ""
    for fr in re.split(r"(?<=[.!?…])\s+", txt.strip()):
        if not fr.strip():
            continue
        f = fonemas(fr, lang)
        if not f:
            continue
        if len(f) > MAX_FON:
            if acc:
                yield acc
                acc = ""
            atual = ""
            for pedaco in re.split(r"(?<=[,;:])\s+", fr):
                tent = (atual + " " + pedaco).strip()
                if atual and len(fonemas(tent, lang)) > MAX_FON:
                    yield fonemas(atual, lang)
                    atual = pedaco
                else:
                    atual = tent
            if atual:
                yield fonemas(atual, lang)
        elif acc and len(acc) + 1 + len(f) > ALVO:
            yield acc
            acc = f
        else:
            acc = (acc + " " + f).strip()
    if acc:
        yield acc


def sessao(onnx):
    op = ort.SessionOptions()
    op.intra_op_num_threads = os.cpu_count() or 4
    return ort.InferenceSession(onnx, op, providers=["CPUExecutionProvider"])


def eh_piper(voz):
    return voz == "piper" or voz.startswith("piper:")


def modelos_piper():
    """{'tamaki': '~/kokoro/piper/pt_BR-tamaki-medium.onnx', ...}"""
    if not os.path.isdir(PASTA_PIPER):
        return {}
    achados = {}
    for arq in sorted(os.listdir(PASTA_PIPER)):
        cam = os.path.join(PASTA_PIPER, arq)
        if arq.endswith(".onnx") and os.path.exists(cam + ".json"):
            partes = arq[:-5].split("-")  # pt_BR-tamaki-medium -> tamaki
            achados[partes[1] if len(partes) == 3 else arq[:-5]] = cam
    return achados


class Piper:
    """Voz treinada no Piper. Vira fonemas do mesmo jeito que o treino (piper.phonemize_espeak)."""

    def __init__(self, onnx):
        with open(onnx + ".json", encoding="utf-8") as f:
            cfg = json.load(f)
        self.taxa = cfg["audio"]["sample_rate"]
        self.mapa = cfg["phoneme_id_map"]
        self.lang = cfg.get("espeak", {}).get("voice", "pt-br")
        inf = cfg.get("inference", {})
        self.escalas = (inf.get("noise_scale", 0.667), inf.get("length_scale", 1.0), inf.get("noise_w", 0.8))
        self.sid = cfg.get("default_speaker_id", 0) if cfg.get("num_speakers", 1) > 1 else None
        self.grupos = sorted({tuple(g) for g in cfg.get("vowel_clusters") or []}, key=len, reverse=True)
        self.dados = PASTA_PIPER if os.path.isdir(os.path.join(PASTA_PIPER, "espeak-ng-data")) else None
        self.sess = sessao(onnx)

    def fonemas(self, frase):
        pt = r"[.,;:!?]"
        partes = re.split("(" + pt + "+)", frase.replace("…", "."))
        saida = ""
        for i, p in enumerate(partes):
            if not p.strip() or re.fullmatch(pt + "+", p):
                continue
            prox = partes[i + 1] if i + 1 < len(partes) else ""
            fim = prox[0] if prox and re.fullmatch(pt + "+", prox) and not prox.startswith("..") else ""
            f = espeak(p.strip() + (fim or "."), self.lang, self.dados)
            saida += " ".join(re.sub(r"\([^)]+\)", "", f).split()) + fim + (" " if fim in (",", ";", ":") else "")
        fon = list(unicodedata.normalize("NFD", saida))
        if self.grupos:  # junta ditongos que o modelo conhece como um fonema só
            junto, i = [], 0
            while i < len(fon):
                g = next((g for g in self.grupos if tuple(fon[i:i + len(g)]) == g), None)
                junto.append("".join(g) if g else fon[i])
                i += len(g) if g else 1
            fon = junto
        return [p for p in fon if p in self.mapa]

    def falar(self, frase, vel):
        fon = self.fonemas(frase)
        if not fon:
            return np.zeros(0, dtype=np.float32)
        ids = [*self.mapa["^"], *self.mapa["_"]]
        for p in fon:
            ids += [*self.mapa[p], *self.mapa["_"]]
        ids += self.mapa["$"]
        ent = {"input": np.array([ids], dtype=np.int64), "input_lengths": np.array([len(ids)], dtype=np.int64),
               "scales": np.array([self.escalas[0], self.escalas[1] / vel, self.escalas[2]], dtype=np.float32)}
        if self.sid is not None:
            ent["sid"] = np.array([self.sid], dtype=np.int64)
        audio = self.sess.run(None, ent)[0].ravel().astype(np.float32)
        pico = float(np.max(np.abs(audio))) if audio.size else 0.0
        audio = audio * (0.95 / pico) if pico > 1e-8 else audio * 0  # o Piper normaliza cada frase
        if self.taxa != TAXA:
            n = max(2, int(len(audio) * TAXA / self.taxa))
            audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)
        return audio


class Motor:
    def __init__(self):
        self.pipers = modelos_piper()
        self._piper = {}
        self._cache = {}
        self.kokoro = os.path.exists(MODELO) and os.path.exists(VOZES)
        if not self.kokoro:
            if not self.pipers:
                sys.exit("Nenhuma voz instalada. Rode o comando de instalação (app > Palco) ou: voz --importar")
            self.vozes = None
            return
        self.vozes = np.load(VOZES)
        self.sess = sessao(MODELO)
        nomes = [i.name for i in self.sess.get_inputs()]
        self.entrada = "input_ids" if "input_ids" in nomes else "tokens"

    def piper(self, spec):
        """'piper' (a tamaki, ou a única treinada) ou 'piper:nome'."""
        nome = spec.partition(":")[2].strip()
        if not self.pipers:
            sys.exit("Nenhuma voz treinada. Ponha o .zip do treino em Download/tamaki_personagem/voz-treinada e rode: voz --importar")
        if not nome:
            nome = "tamaki" if "tamaki" in self.pipers else next(iter(self.pipers))
        if nome not in self.pipers:
            sys.exit(f"Voz treinada '{nome}' não existe. Tem: {', '.join(self.pipers)}")
        if nome not in self._piper:
            self._piper[nome] = Piper(self.pipers[nome])
        return self._piper[nome]

    def estilo(self, spec):
        """'pf_dora' ou mistura 'pf_dora:0.7+ef_dora:0.3'."""
        if spec in self._cache:
            return self._cache[spec]
        if not self.kokoro:
            sys.exit("O Kokoro não está instalado. Use a voz treinada: -v piper")
        itens = []
        for item in spec.split("+"):
            nome, _, peso = item.partition(":")
            nome = nome.strip()
            if nome not in self.vozes.files:
                sys.exit(f"Voz '{nome}' não existe. Use --listar para ver as vozes.")
            itens.append((nome, float(peso) if peso else 1.0))
        total = sum(p for _, p in itens)
        est = sum(self.vozes[n] * (p / total) for n, p in itens).astype(np.float32)
        self._cache[spec] = est
        return est

    def falar(self, fon, estilo_todos, vel):
        tok = [VOCAB[c] for c in fon if c in VOCAB]
        estilo = estilo_todos[min(len(tok), len(estilo_todos)) - 1]
        saida = self.sess.run(None, {self.entrada: np.array([[0, *tok, 0]], dtype=np.int64),
                                     "style": np.asarray(estilo, dtype=np.float32),
                                     "speed": np.array([vel], dtype=np.float32)})
        return saida[0].ravel()


def mudar_tom(audio, semitons):
    """Sobe/desce o tom reamostrando (a duração é compensada na velocidade do modelo)."""
    if not semitons:
        return audio
    f = 2 ** (semitons / 12)
    n = max(2, int(len(audio) / f))
    return np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)


# Emoções por linha: escreva (animada) antes da frase. Sozinha numa linha, vale até a próxima marca.
EMOCOES = {
    "normal": {},
    "animada": dict(vel=1.10, tom=1.5),
    "empolgada": dict(vel=1.15, tom=2.5),
    "calma": dict(vel=0.92, tom=-1.0),
    "triste": dict(vel=0.88, tom=-1.5),
    "brava": dict(vel=1.08, tom=-0.5, vol=1.1),
    "sussurro": dict(vel=0.92, tom=-0.5, vol=0.45),
    "dramatica": dict(vel=0.85, tom=-1.0, pausa=0.8),
    "rapida": dict(vel=1.20),
    "devagar": dict(vel=0.85),
}


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").lower().strip()


def ler_tag(linha):
    """'(animada) Oi!' -> ('animada', 'Oi!').  Sem marca -> (None, linha)."""
    m = re.match(r"^\s*[\(\[]\s*([^\)\]]+?)\s*[\)\]]\s*(.*)$", linha)
    if not m:
        return None, linha
    return sem_acento(m.group(1)), m.group(2)


def gerar(motor, txt, voz, vel, pausa, tom, energia, lang, falar_progresso=True):
    pp = motor.piper(voz) if eh_piper(voz) else None
    estilo = None if pp else motor.estilo(voz)
    partes = []
    t0 = time.time()
    linhas = [l for l in txt.splitlines() if l.strip()]
    fixa = {}  # emoção que vale até a próxima marca
    for n, linha in enumerate(linhas, 1):
        tag, resto = ler_tag(linha)
        so_desta = None
        if tag is not None:
            if tag.startswith("pausa"):
                m = re.search(r"[\d.,]+", tag)
                seg = float(m.group(0).replace(",", ".")) if m else 1.0
                partes.append(np.zeros(int(TAXA * seg), dtype=np.float32))
            elif tag in EMOCOES:
                if resto.strip():
                    so_desta = EMOCOES[tag]
                else:
                    fixa = EMOCOES[tag]
            else:
                print(f"aviso: marca ({tag}) desconhecida, ignorada. Veja: voz --emocoes", flush=True)
            linha = resto
        if not linha.strip():
            continue
        em = so_desta if so_desta is not None else fixa
        forte = energia > 0 and ("!" in linha or re.search(r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,}\b", linha))
        st = tom + em.get("tom", 0.0) + (1.5 * energia if forte else 0.0)
        vl = vel * em.get("vel", 1.0) * (1 + 0.10 * energia if forte else 1.0)
        f = 2 ** (st / 12)
        if pp:  # o Piper fala uma frase por vez, como no treino
            audios = [pp.falar(fr, vl / f) for fr in re.split(r"(?<=[.!?…])\s+", linha.strip()) if fr.strip()]
        else:
            audios = [motor.falar(fon, estilo, vl / f) for fon in blocos(linha, lang)]
        for au in audios:
            partes.append(mudar_tom(au, st) * em.get("vol", 1.0))
        partes.append(np.zeros(int(TAXA * em.get("pausa", pausa)), dtype=np.float32))
        if falar_progresso:
            print(f"linha {n}/{len(linhas)} pronta ({time.time() - t0:.1f}s)", flush=True)
    if not partes:
        sys.exit("Nada para falar.")
    return np.nan_to_num(np.concatenate(partes), nan=0.0, posinf=0.0, neginf=0.0)


def salvar(caminho, wav):
    pcm = (np.clip(wav, -1, 1) * 32767).astype(np.int16)
    with wave.open(caminho, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes(pcm.tobytes())


def bonito(caminho):
    """Mostra o caminho como aparece no Meus Arquivos."""
    return caminho.replace(os.path.expanduser("~/storage/downloads"), "Armazenamento interno/Download")


def carimbo():
    return time.strftime("%Y-%m-%d_%H-%M-%S")


def pasta_saida():
    try:
        os.makedirs(PASTA_VOZ, exist_ok=True)
    except OSError:
        pass
    if os.path.isdir(PASTA_VOZ):
        return PASTA_VOZ
    d = os.path.expanduser("~/storage/downloads")
    return d if os.path.isdir(d) else "."


def atualizar():
    """Baixa a versão nova do seu site (o endereço fica em ~/kokoro/origem.txt)."""
    from urllib.request import urlopen
    arq = os.path.join(PASTA, "origem.txt")
    if not os.path.exists(arq):
        sys.exit("Não sei o endereço do seu site. Cole de novo o comando de instalação (app > Palco).")
    base = open(arq, encoding="utf-8").read().strip().rstrip("/")

    def pegar(nome):
        with urlopen(f"{base}/{nome}?v={int(time.time())}", timeout=30) as r:
            return r.read()

    try:
        voz_nova, servidor = pegar("tamaki_voz.py"), pegar("palco_server.py")
    except OSError as e:
        sys.exit(f"Não consegui baixar de {base} ({e}). Confira se subiu os arquivos no GitHub e a internet.")
    m = re.search(rb"^VERSAO\s*=\s*(\d+)", voz_nova, re.M)
    nova = int(m.group(1)) if m else 0
    mudou = False
    if nova > VERSAO:
        open(os.path.join(PASTA, "tamaki_voz.py"), "wb").write(voz_nova)
        print(f"Programa da voz atualizado: versão {VERSAO} -> {nova}")
        mudou = True
    dest = os.path.join(PASTA, "palco_server.py")
    if not os.path.exists(dest) or open(dest, "rb").read() != servidor:
        open(dest, "wb").write(servidor)
        print("Servidor do Palco atualizado.")
        mudou = True
    print("Tudo atualizado." if mudou else f"Já está na versão mais nova ({VERSAO}).")


def baixar_pronuncia():
    """Copia o espeak-ng-data do pacote piper-tts (PyPI): é a pronúncia que o treino usou."""
    from urllib.request import urlopen
    alvo = os.path.join(PASTA_PIPER, "espeak-ng-data")
    if os.path.isdir(alvo):
        return
    print(f"Baixando a pronúncia do Piper {PIPER_VERSAO} (~34 MB, só uma vez)...", flush=True)
    try:
        with urlopen(f"https://pypi.org/pypi/piper-tts/{PIPER_VERSAO}/json", timeout=30) as r:
            url = next(u["url"] for u in json.load(r)["urls"] if u["filename"].endswith(".whl"))
        raiz, parte = "piper/espeak-ng-data/", alvo + ".part"
        shutil.rmtree(parte, ignore_errors=True)
        with tempfile.TemporaryFile() as tmp:
            with urlopen(url, timeout=300) as r:
                shutil.copyfileobj(r, tmp)
            with zipfile.ZipFile(tmp) as z:
                for i in z.infolist():
                    rel = i.filename[len(raiz):]
                    if not i.filename.startswith(raiz) or i.is_dir() or ".." in rel.split("/"):
                        continue
                    if rel.endswith("_dict") and rel != "pt_dict":  # só o dicionário do português
                        continue
                    os.makedirs(os.path.dirname(os.path.join(parte, rel)), exist_ok=True)
                    with z.open(i) as o, open(os.path.join(parte, rel), "wb") as d:
                        shutil.copyfileobj(o, d)
        os.replace(parte, alvo)
    except (OSError, StopIteration, zipfile.BadZipFile, ValueError) as e:
        print(f"Não consegui baixar a pronúncia ({e}). Vai usar a do espeak do Termux (pode pronunciar um pouco diferente).")


def importar():
    """Copia a voz treinada de Download/tamaki_personagem/voz-treinada para ~/kokoro/piper."""
    os.makedirs(PASTA_PIPER, exist_ok=True)
    try:
        os.makedirs(PASTA_TREINADA, exist_ok=True)
    except OSError:
        pass
    copiados = []
    for arq in sorted(os.listdir(PASTA_TREINADA)) if os.path.isdir(PASTA_TREINADA) else []:
        cam = os.path.join(PASTA_TREINADA, arq)
        if arq.endswith(".zip"):
            with zipfile.ZipFile(cam) as z:
                for nome in z.namelist():
                    base = os.path.basename(nome)
                    if base.endswith((".onnx", ".onnx.json")):
                        with z.open(nome) as o, open(os.path.join(PASTA_PIPER, base), "wb") as d:
                            shutil.copyfileobj(o, d)
                        copiados.append(base)
        elif arq.endswith((".onnx", ".onnx.json")):
            shutil.copyfile(cam, os.path.join(PASTA_PIPER, arq))
            copiados.append(arq)
    if copiados:
        print("Copiados:", ", ".join(copiados))
    vozes = modelos_piper()
    if not vozes:
        sys.exit(f"Nenhuma voz treinada. Ponha o .zip do treino (ou o .onnx + .onnx.json) em:\n  {bonito(PASTA_TREINADA)}\ne rode de novo: voz --importar")
    baixar_pronuncia()
    print("Vozes treinadas prontas:", ", ".join(vozes))
    print('Teste:  voz -v piper "Gente, nem te conto!"   (no editor: Voz > Termux > Tamaki treinada)')


def ler_texto(a):
    if a.texto:
        return " ".join(a.texto)
    for cam in (os.path.join(PASTA_VOZ, "fala.txt"), os.path.join(PASTA_BASE, "voz-tamaki", "fala.txt"),
                os.path.expanduser("~/storage/downloads/fala.txt"), os.path.expanduser("~/fala.txt")):
        if os.path.exists(cam):
            print("Lendo", bonito(cam))
            return open(cam, encoding="utf-8").read()
    return None


VARIANTES = [
    ("base (como estava)", dict(tom=0.0, energia=0.0)),
    ("tom +2", dict(tom=2.0)),
    ("tom +2 e mais rápida", dict(tom=2.0, vel=1.12)),
    ("animada: energia nas frases com ! ou MAIÚSCULAS", dict(tom=1.0, energia=1.0)),
    ("mistura com ef_dora (espanhol), tom +1", dict(voz="pf_dora:0.7+ef_dora:0.3", tom=1.0)),
    ("mistura com af_heart (inglês), tom +1", dict(voz="pf_dora:0.7+af_heart:0.3", tom=1.0)),
    ("combinação do 3 e do 6: mistura af_heart, tom +2, mais rápida (padrão atual)",
     dict(voz="pf_dora:0.7+af_heart:0.3", tom=2.0, vel=1.12)),
]


def valor(a, nome):
    """Ordem: o que você digitou > preset (-P) > padrão."""
    v = getattr(a, nome)
    if v is not None:
        return v
    if nome != "voz" and not a.preset and eh_piper(valor(a, "voz")):
        return PADRAO_PIPER[nome]
    if a.preset:
        if not 1 <= a.preset <= len(VARIANTES):
            sys.exit(f"Preset vai de 1 a {len(VARIANTES)}.")
        return {**BASE, **VARIANTES[a.preset - 1][1]}.get(nome, PADRAO.get(nome))
    if nome == "voz" and not os.path.exists(MODELO) and modelos_piper():
        return "piper"  # sem Kokoro instalado, usa a voz treinada
    return PADRAO[nome]


def main():
    ap = argparse.ArgumentParser(description="Gera a voz da Tamaki (Kokoro local).")
    ap.add_argument("texto", nargs="*", help="fala (ou deixe vazio para ler o fala.txt)")
    ap.add_argument("-v", "--voz", default=None, help="ex.: pf_dora ou pf_dora:0.7+ef_dora:0.3")
    ap.add_argument("-s", "--vel", type=float, default=None)
    ap.add_argument("-p", "--pausa", type=float, default=None)
    ap.add_argument("-t", "--tom", type=float, default=None, help="semitons (ex.: 2 deixa mais aguda)")
    ap.add_argument("-e", "--energia", type=float, default=None,
                    help="0 a 1: acelera e agudiza frases com ! ou MAIÚSCULAS")
    ap.add_argument("-P", "--preset", type=int, default=None, help="usa a versão N do --comparar (ex.: -P 3)")
    ap.add_argument("-l", "--lang", default="pt-br")
    ap.add_argument("-o", "--saida", default=None)
    ap.add_argument("--listar", action="store_true", help="lista todas as vozes")
    ap.add_argument("--atualizar", action="store_true", help="baixa a versão nova do seu site")
    ap.add_argument("--importar", action="store_true", help="instala a voz treinada (pasta voz-treinada)")
    ap.add_argument("--emocoes", action="store_true", help="lista as marcas de emoção, ex.: (animada)")
    ap.add_argument("--onde", action="store_true", help="mostra a pasta onde os áudios são salvos")
    ap.add_argument("--comparar", action="store_true", help="gera 7 versões da mesma fala para você escolher")
    a = ap.parse_args()

    if a.atualizar:
        atualizar()
        return
    if a.importar:
        importar()
        return
    if a.emocoes:
        print("Escreva a marca antes da frase, ex.:  (animada) Gente, nem te conto!")
        print("Sozinha numa linha, vale até a próxima marca.  (normal) volta ao padrão.")
        print("Marcas:", ", ".join(k for k in EMOCOES))
        print("Pausa em segundos numa linha só:  (pausa 2)")
        return
    if a.onde:
        print("Os áudios ficam em:", bonito(pasta_saida()))
        return
    motor = Motor()
    if a.listar:
        if motor.kokoro:
            print("Kokoro:", " ".join(sorted(motor.vozes.files)))
        if motor.pipers:
            print("Treinadas (Piper):", " ".join("piper:" + n for n in motor.pipers))
        return
    texto = ler_texto(a)
    d = pasta_saida()

    if a.comparar:
        if a.texto:
            txt = texto
        else:
            txt = TEXTO_TESTE
        print("Fala de teste:", txt.replace("\n", " ")[:120])
        marca = carimbo()
        for n, (nome, ajuste) in enumerate(VARIANTES, 1):
            p = {**BASE, "pausa": valor(a, "pausa"), **ajuste}
            wav = gerar(motor, txt, p["voz"], p["vel"], p["pausa"], p["tom"], p["energia"], a.lang, False)
            arq = os.path.join(d, f"tamaki_{marca}_teste-{n}.wav")
            salvar(arq, wav)
            print(f"{n}: {nome}", flush=True)
        print(f"Salvos em: {bonito(d)}\nOs arquivos começam com tamaki_{marca}_teste-1 até teste-7. Ouça e me diga qual soou melhor.")
        return

    if texto is None:
        sys.exit('Sem texto. Use: voz "sua fala"  ou crie o arquivo fala.txt')
    t0 = time.time()
    wav = gerar(motor, texto, valor(a, "voz"), valor(a, "vel"), valor(a, "pausa"), valor(a, "tom"), valor(a, "energia"), a.lang)
    saida = a.saida or os.path.join(d, f"tamaki_{carimbo()}.wav")
    salvar(saida, wav)
    print(f"Pronto! ({len(wav) / TAXA:.1f}s de áudio, gerado em {time.time() - t0:.1f}s)\nArquivo: {os.path.basename(saida)}\nPasta: {bonito(os.path.dirname(os.path.abspath(saida)))}")


if __name__ == "__main__":
    main()
