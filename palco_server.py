#!/usr/bin/env python3
# Servidor do Palco da Tamaki (roda no Termux, só em 127.0.0.1).
# O app (aba Palco) conversa com ele:  GET /ping  GET /events  POST /say  POST /stop  POST /tts
# Usa o motor de voz tamaki_voz.py (mesma voz do comando "voz").
import json, os, queue, sys, threading, time, io, wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

PORTA = int(os.environ.get("PALCO_PORTA", "8765"))
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

clientes = []
trava_clientes = threading.Lock()
trava_voz = threading.Lock()
pronto = threading.Event()
estado = {"motor": None, "erro": None, "tv": None}


def carregar_motor():
    """Carrega o modelo uma vez, em segundo plano."""
    with trava_voz:
        try:
            import tamaki_voz
            estado["tv"] = tamaki_voz
            estado["motor"] = tamaki_voz.Motor()
        except BaseException as e:  # inclui SystemExit do motor
            estado["erro"] = str(e) or e.__class__.__name__
        finally:
            pronto.set()


def avisar(msg):
    dados = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    with trava_clientes:
        for q in list(clientes):
            q.put(dados)
        return len(clientes)


def parametros(d):
    """O app manda voz/velocidade/pausa. 'pf_dora' + 1.05 (padrão do app) = voz padrão da Tamaki."""
    tv = estado["tv"]
    P = tv.PADRAO
    voz = str(d.get("voice") or "").strip()
    try:
        vel = float(d.get("speed")) if d.get("speed") is not None else None
    except (TypeError, ValueError):
        vel = None
    try:
        pausa = float(d.get("pause")) if d.get("pause") is not None else P["pausa"]
    except (TypeError, ValueError):
        pausa = P["pausa"]
    if voz in ("", "pf_dora", "padrao", "tamaki") and not estado["motor"].kokoro:
        voz = "piper"  # sem Kokoro instalado, a voz da Tamaki é a treinada
    if tv.eh_piper(voz):  # voz treinada: já tem o timbre, sem tom extra
        tom, energia = 0.0, 0.0
        vel = vel if vel is not None else 1.0
    elif voz in ("", "pf_dora", "padrao", "tamaki"):
        voz, tom, energia = P["voz"], P["tom"], P["energia"]
        vel = P["vel"] if vel is None or abs(vel - 1.05) < 1e-6 else vel
    else:
        tom, energia = 0.0, 0.0
        vel = vel if vel is not None else 1.05
    return voz, vel, pausa, tom, energia


def sintetizar(d):
    texto = str(d.get("text") or "").strip()[:3000]
    if not texto:
        raise ValueError("texto vazio")
    pronto.wait(60)
    if not estado["motor"]:
        raise RuntimeError(estado["erro"] or "voz ainda carregando")
    tv = estado["tv"]
    np = tv.np
    voz, vel, pausa, tom, energia = parametros(d)
    with trava_voz:
        wav = tv.gerar(estado["motor"], texto, voz, vel, pausa, tom, energia, "pt-br", False)
    nz = np.flatnonzero(wav)  # tira o silêncio sobrando no fim
    if len(nz):
        wav = wav[: min(len(wav), nz[-1] + int(0.2 * tv.TAXA))]
    pcm = (np.clip(wav, -1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(tv.TAXA)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Max-Age", "600")

    def _resp(self, code, corpo=b"", tipo="application/json"):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        if corpo:
            self.wfile.write(corpo)

    def _json(self, code, obj):
        self._resp(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self._resp(204)

    def do_GET(self):
        rota = self.path.split("?")[0]
        if rota == "/ping":
            pronto.wait(30)
            m = estado["motor"]
            self._json(200, {"ok": True, "kokoro": bool(m and m.kokoro), "piper": list(m.pipers) if m else [],
                             "erro": estado["erro"]})
        elif rota == "/events":
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            q = queue.Queue()
            with trava_clientes:
                clientes.append(q)
            try:
                self.wfile.write(b": conectado\n\n")
                self.wfile.flush()
                while True:
                    try:
                        self.wfile.write(b"data: " + q.get(timeout=15) + b"\n\n")
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except OSError:
                pass
            finally:
                with trava_clientes:
                    if q in clientes:
                        clientes.remove(q)
        else:
            self._json(404, {"erro": "rota não existe"})

    def do_POST(self):
        rota = self.path.split("?")[0]
        try:
            n = int(self.headers.get("Content-Length") or 0)
            d = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except (ValueError, OSError):
            return self._json(400, {"erro": "json inválido"})
        if rota == "/say":
            texto = str(d.get("text") or "").strip()
            if not texto:
                return self._json(400, {"erro": "texto vazio"})
            self._json(200, {"ok": True, "apps": avisar({"text": texto})})
        elif rota == "/stop":
            self._json(200, {"ok": True, "apps": avisar({"cmd": "stop"})})
        elif rota == "/tts":
            try:
                self._resp(200, sintetizar(d), "audio/wav")
            except ValueError as e:
                self._json(400, {"erro": str(e)})
            except BaseException as e:
                self._json(503, {"erro": str(e) or e.__class__.__name__})
        else:
            self._json(404, {"erro": "rota não existe"})


def cliente(rota, corpo):
    req = Request(f"http://127.0.0.1:{PORTA}{rota}", data=json.dumps(corpo, ensure_ascii=False).encode("utf-8"),
                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=10) as r:
            return json.loads(r.read() or b"{}")
    except OSError:
        sys.exit('O servidor não está ligado. Abra outra sessão do Termux e digite: palco')


def main():
    args = sys.argv[1:]
    if args and args[0] == "falar":
        texto = " ".join(args[1:]).strip()
        if texto == "--parar":
            cliente("/stop", {})
            print("Parado.")
            return
        if not texto:
            sys.exit('Use: falar "oi gente"')
        r = cliente("/say", {"text": texto})
        print("Enviado para o app." if r.get("apps") else "Servidor ok, mas o app (aba Palco) não está conectado.")
        return
    if args and args[0] == "parar":
        cliente("/stop", {})
        print("Parado.")
        return
    threading.Thread(target=carregar_motor, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORTA), H)
    srv.daemon_threads = True
    print(f"Palco da Tamaki no ar: http://127.0.0.1:{PORTA}")
    print("Deixe esta tela do Termux aberta e abra a aba Palco no app.")
    print('Em outra sessão você pode usar:  falar "oi gente"   e   falar --parar')
    print("Para desligar: Ctrl+C")

    def avisa_pronto():
        pronto.wait()
        print("Voz pronta." if estado["motor"] else f"Voz indisponível ({estado['erro']}). O app vai usar a voz do navegador.")

    threading.Thread(target=avisa_pronto, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nDesligado.")


if __name__ == "__main__":
    main()
