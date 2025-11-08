#!/usr/bin/env python3
import os, signal, subprocess, time, json, multiprocessing, threading
from pathlib import Path
from faster_whisper import WhisperModel
from llama_cpp import Llama

#===設定読み込み
CONF = json.load(open(str(Path.home()/"app"/"config.json"), "r"))

LANG = CONF["lang"]
ASR_DIR = CONF["asr_model"]
LLM_PATH = CONF["llm_model"]
TTS_MODE = CONF["tts"]
MMS_BG_DIR = CONF["mms_bg_dir"]
OJTALK_DIC = CONF["ojtalk_dic"]
OJTALK_VOICE = CONF["ojtalk_voice"]
RATE = int(CONF["record_rate"])
SIL_STOP= float(CONF["silence_stop_sec"])
TMP_WAV = CONF["tmp_wav"]

#===状態
listening = False
recording_proc = None
lock = threading.Lock()

#=== ASR/LLM 準備===
asr = WhisperModel(ASR_DIR, device="cpu", compute_type="int8")
llm = Llama(model_path=LLM_PATH, n_ctx=8192,n_threads=max(4, multiprocessing.cpu_count()-1))

def gemma_prompt(user_text: str) -> str:
    return "<bos><start_of_turn>user\n" + user_text + "\n<end_of_turn>\n<start_of_turn>model\n"

def speak(text: str):
    if TTS_MODE == "mms-bg":
        from transformers import AutoProcessor, VitsModel
        import torch, soundfile as sf
        processor = AutoProcessor.from_pretrained(MMS_BG_DIR,local_files_only=True)
        vits = VitsModel.from_pretrained(MMS_BG_DIR, local_files_only=True)

        with torch.no_grad():
            audio=vits(**processor (text=text,return_tensors="pt")).waveform.squeeze().cpu().numpy()

        sf.write("/tmp/out.wav", audio, 16000)
        subprocess.run(["aplay", "-q", "/tmp/out.wav"])

    elif TTS_MODE == "openjtalk-ja":
        cmd = [
            "bash","-Ic",
            f'echo "{text}" open jtalk -x {OJTALK_DIC} -m {OJTALK_VOICE} -r 1.0 -ow /tmp/out.wav && aplay -q /tmp/out.wav'
        ]

        subprocess.run(cmd, check=False)
    else:
        print("[TTS] disabled:", text)

#錄音:soxで1秒無音で停止”===
def start_recording():
    global recording_proc
    cmd = [
        "sox","-q",
        "-t","alsa","default",
        "-r", str(RATE),"-c","1","-b","16", TMP_WAV,
        "silence", "1", "0.1","1%","1", str(SIL_STOP), "1%"
    ]
    recording_proc = subprocess.Popen(cmd)


def stop_recording():
    global recording_proc
    if recording_proc and recording_proc.poll() is None:
        recording_proc.terminate()
        try:
            recording_proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            recording_proc.kill()
    recording_proc = None

#=== シグナル ===
def sig_toggle(sig, frame):
    global listening
    with lock:
        listening = not listening
    print("[SIG] toggle listening ->", listening)
    if listening and (recording_proc is None):
        start_recording()
signal.signal(signal.SIGUSR1, sig_toggle) #USR1 = トグル


def sig_on(sig, frame):
    global listening
    with lock:
        listening = True
    if recording_proc is None:
            start_recording()

    print("[SIG] listening ON")
signal.signal(signal.SIGUSR2, sig_on)

#USR2 = 強制 ON
def sig_off(sig, frame):
    global listening
    with lock:
        listening = False
    stop_recording()
    print("[SIG] listening OFF")


signal.signal(signal.SIGHUP, sig_off)

#メインループ ===
print("[voice] ready. send SIGUSR1 to toggle recording.")
while True:
    if listening:
        #soxが1秒無音で自動終了したらファイルができる
        if recording_proc and recording_proc.poll() is not None:
            #停止済み ファイルがあれば処理
            if os.path.exists(TMP_WAV) and os.path.getsize(TMP_WAV) > 0:
                print("[record] captured->", TMP_WAV)
                #ASR
                segments, _info = asr.transcribe(TMP_WAV, language=LANG, vad_filter=False)

                text = "".join(s.text for s in segments).strip()
                print("[ASR]", text)

                #LLM
                if text:
                    out = llm(
                        gemma_prompt(text),
                        max_tokens=400, temperature=0.1, top_k=25, top_p=1.0,
                        repeat_penalty=1.1, stop=["<cos>","<end_of_turn>"]
                    )
                    reply = out["choices"][0]["text"].strip()
                    print("[LLM]", reply)

                    #TTS
                    speak(reply)

                #次の録音に備える
                os.remove(TMP_WAV)

                if listening:
                    start_recording()

            else:
                #ファイル無し(即停止など)
                if listening:
                    start_recording()

        #100ms ボーリング
        time.sleep(0.1)
    else:
        time.sleep(0.2)
        