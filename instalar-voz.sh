#!/data/data/com.termux/files/usr/bin/bash
# Instala (ou reinstala) a voz local da Tamaki no Termux.
# O app gera o comando certo: aba Palco > "Instalar ou reinstalar a voz no Termux".
set -e
ORIGEM="${1%/}"
if [ -z "$ORIGEM" ]; then
  echo "Faltou o endereco do site. Copie o comando pelo app (aba Palco)."
  exit 1
fi

echo "== 1/4 Instalando pacotes =="
if command -v pkg >/dev/null 2>&1; then
  pkg install -y python python-numpy python-onnxruntime espeak curl
fi

echo "== 2/4 Baixando modelo e vozes (~350 MB, use Wi-Fi) =="
mkdir -p "$HOME/kokoro"
mkdir -p "$HOME/storage/downloads/tamaki_personagem/Baixado" 2>/dev/null || true
cd "$HOME/kokoro"
baixar() {
  if [ -s "$1" ]; then echo "$1 ja existe, pulando"; else
    echo "Baixando $1 ..."
    curl -L --fail -C - -o "$1.part" "$2" && mv "$1.part" "$1"
  fi
}
BASE=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
baixar voices-v1.0.bin "$BASE/voices-v1.0.bin"
baixar kokoro-v1.0.onnx "$BASE/kokoro-v1.0.onnx"

echo "== 3/4 Baixando o programa do seu site =="
echo "$ORIGEM" > "$HOME/kokoro/origem.txt"
T=$(date +%s)
for f in tamaki_voz.py palco_server.py; do
  curl -fsSL "$ORIGEM/$f?v=$T" -o "$f.novo"
  mv "$f.novo" "$f"
done
BIN="${PREFIX:-/data/data/com.termux/files/usr}/bin"
mkdir -p "$BIN"
printf '#!/usr/bin/env bash\nexec python "$HOME/kokoro/tamaki_voz.py" "$@"\n' > "$BIN/voz"
printf '#!/usr/bin/env bash\nexec python "$HOME/kokoro/palco_server.py" "$@"\n' > "$BIN/palco"
printf '#!/usr/bin/env bash\nexec python "$HOME/kokoro/palco_server.py" falar "$@"\n' > "$BIN/falar"
chmod +x "$BIN/voz" "$BIN/palco" "$BIN/falar"
if [ ! -d "$HOME/storage/downloads" ] && command -v termux-setup-storage >/dev/null 2>&1; then
  termux-setup-storage
fi

echo "== Voz treinada (Piper) =="
python "$HOME/kokoro/tamaki_voz.py" --importar 2>/dev/null || echo "Nenhuma voz treinada ainda. Depois do treino, ponha o .zip em Download/tamaki_personagem/voz-treinada e rode: voz --importar"

echo "== 4/4 Conferindo =="
python -c "import numpy, onnxruntime; print('python ok, onnxruntime', onnxruntime.__version__)" 2>&1 | grep -v -i warn
(espeak-ng -q --ipa -v pt-br "bom dia" 2>/dev/null || espeak -q --ipa -v pt-br "bom dia")
echo
echo "Pronto!"
echo '  voz "Gente, nem te conto!"   gera a voz (sai em Download/tamaki_personagem/Baixado)'
echo "  palco                        liga a voz dentro do app (deixe o Termux aberto)"
echo "  voz --atualizar              baixa a versao nova do seu site"
echo "  voz --importar               instala a voz treinada (Piper)"
echo '  voz -v piper "Oi gente!"     fala com a voz treinada'
