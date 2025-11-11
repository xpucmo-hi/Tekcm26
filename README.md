# ブルガリア語音声会話システム

## 準備

### ハードウェア構成

- ASUS NUC 14 Pro+ Kit (本体)
- Crucial CT2K24G56C46S5 (メモリ)
- Solidigm P44 Pro SSDPFKKW020X7X1 (SSD)
- Elecom TK-TDM017BK (テンキー)
- スピーカーフォン

### OS

- Ubuntu 24.04 LTS

### 必要なライブラリのインストール

```
sudo apt update && sudo apt -y full-upgrade
sudo apt install -y build-essential git curl unzip python3.12-venv python3-pip ffmpeg htop nvtop
sudo apt install -y intel-media-va-driver-non-free vainfo
sudo apt install -y mesa-vulkan-drivers vulkan-tools
sudo apt install -y ocl-icd-libopencl1 intel-opencl-icd
sudo apt install -y python3-venv
sudo apt install -y libsndfile1
python -m pip install --upgrade pip
pip install --upgrade llama-cpp-python
pip install --upgrade faster-whisper
pip install --upgrade 'transformers>=4.38' accelerate
pip install --upgrade openwakeword
sudo snap install --beta intel-npu-driver
pip install --upgrade openvino
python -m pip install --upgrade pip
python3 -m venv ~/venvs/ai && source ~/venvs/ai/bin/activate
python -m pip install -U pip wheel setuptools
pip install "huggingface_hub[cli]" llama-cpp-python faster-whisper "transformers>=4.38" accelerate soundfile
pip install torch --index-url https://download.pytorch.org/whl/cpu
echo 'source ~/venvs/ai/bin/activate' >> ~/.bashrc
```

### BgGPTインストール
```
sudo mkdir -p /opt/models/bggpt/{9b, 27b}
sudo chown -R $USER /opt/models
huggingface-cli download INSAIT-Institute/BgGPT-Gemma-2-9B-IT-v1.0-GGUF --include "BgGPT-Gemma-2-9B-IT-v1.0.Q4_K_M.gguf" --local-dir /opt/models/bggpt/9b --local-dir-use-symlinks False
huggingface-cli download INSAIT-Institute/BgGPT-Gemma-2-27B-IT-v1.0-GGUF --include "BgGPT-Gemma-2-27B-IT-v1.0.Q4_K_S.gguf" --local-dir /opt/models/bggpt/27b --local-dir-use-symlinks False
```

### 音声モデルインストール
```
sudo mkdir -p /opt/models/{whisper,mms-tss/facebook}
sudo chown -R $USER /opt/models
huggingface-cli download Systran/faster-whisper-large-v3 --local-dir /opt/models/whisper/large-v3-ct2 --local-dir-use-symlinks False
```

### その他のソフト
```
sudo apt install -y emacs-nox build-essential cmake ninja-build pkg-config wget jq ripgrep fzf tmux pipewire-audio wireplumber pavucontrol qpwgraph alsa-utils sox
```

### キー入力受付の設定
```
sudo groupadd -f plugdev
sudo usermod -aG plugdev $USER
sudo udevadm control --reload && sudo udevadm trigger
```