#!/usr/bin/env python3
import os, signal, subprocess, time, json, multiprocessing, threading
from pathlib import Path
from faster_whisper import WhisperModel
from llama_cpp import Llama
import re, random

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
REPLY_MAX_SENT = int(CONF.get("reply_max_sentences", 3))
REPLY_MAX_TOKENS = int(CONF.get("reply_max tokens", 180))
SYSTEM_PROMPT = CONF.get("system_prompt", "").strip()

#===状態
listening = False
recording_proc = None
mode = "normal"
lock = threading.Lock()

#=== ASR/LLM 準備===
asr = WhisperModel(ASR_DIR, device="cpu", compute_type="int8")
llm = Llama(model_path=LLM_PATH, n_ctx=8192,n_threads=max(4, multiprocessing.cpu_count()-1))

def style_hint_for_lang(lang: str, n: int) -> str:
    if lang.lower().startswith("bg"):
            return f"Отговаряй възможно най-накратко - до {n} изречения."
    if lang.lower().startswith("ja"):
            return f"回答はできるだけ簡潔に、最大{n}文以内にまとめてください。"
    return f"Answer as concisely as possible in at most {n} sentences."

def pronounce_numbers(text: str, lang: str) -> str:
    if not CONF.get("normalize_numbers", True): #オフならそのまま
        return text

    #連続する数字を1枚ずつ音読用に展開
    map_bg = {"0":"нула", "1":"едно", "2":"две", "3":"три", "4":"четири", "5":"пет", "6":"шест", "7":"седем", "8":"осем", "9":"девет"}

    def repl(mobj):
        s = mobj.group(0)
        return "".join(map_bg.get(ch, ch) for ch in s)
        
    return re.sub(r"[-]?\d+(?:\.\d+)?", repl, text)

def correct_grammar(user_text: str) -> str:
    if LANG.lower().startswith("bg"):
        ins = "Коригирай граматически следния текст и върни само коригирания вариант, без обяснения."
    else:
        ins = "Correct grammar and return only the corrected sentence."

    prompt = "<bos><start_of_turn>user\n" + ins + "\n" + user_text + "\n<end_of_turn>\n<start_of_turn>model\n"

    out = llm(prompt, max_tokens=200, temperature=0.1, top_k=25, top_p=1.0, repeat_penalty=1.05, stop=["<eos>","<end_of_turn>"])
    return out["choices"][0]["text"].strip()

def gemma_prompt(user_text: str) -> str:
    s = "<bos>"
    s += "<start_of_turn>user\n" + SYSTEM_PROMPT + style_hint_for_lang(LANG, REPLY_MAX_SENT) + "\n<end_of_turn>\n<start_of_turn>model\nOK.<end_of_turn>\n"
    s += "<start_of_turn>user\n" + user_text + "\n<end_of_turn>\n<start_of_turn>model\n"
    return s

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

def sig_off(sig, frame):
    global listening
    with lock:
        listening = False
    stop_recording()
    print("[SIG] listening OFF")
signal.signal(signal.SIGHUP, sig_off)

def sig_mode_lang(sig, frame):
    global mode; mode = "lang"
signal.signal(signal.SIGRTMIN + 1, sig_mode_lang)

def sig_mode_memory(sig, frame):
    global mode; mode = "memory"
signal.signal(signal.SIGRTMIN + 2, sig_mode_memory)

def sig_system_topic(sig, frame):
    topics = CONF.get("topics", {}).get(LANG, []) or CONF.get("topics", {}).get(LANG.split("-")[0], [])
    if not topics: return
    lead = random.choice(topics)

    #履歴にも「システムが話題をふった」ことを残す(次の応答品質が上がる) +

    history.append(("", lead))
    speak(lead)
    #すぐ録音を開始して相手の返答を待つ

    with lock:
        if not listening:
            globals()["listening"] = True
            start_recording()
signal.signal(signal.SIGRTMIN + 3, sig_system_topic)

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
                    #=== 入力テキスト(語学モードなら修正してから続行)===
                    user_for_llm = text
                    if mode == "lang":
                        corrected = correct_grammar(text)
                        if corrected:
                            speak(corrected)
                            print("[Grammar Corrected]", corrected)
                            user_for_llm = corrected

                    #=== プロンプト構築(記憶モードなら5往復ぶん含める) ===  
                    eff_hist = 5 if mode == "memory" else 0
                    def build_prompt(user_text: str) -> str:
                        s = "<bos>"
                        #簡潔に(2~3文)のヒント
                        if CONF.get("style_hint", True):
                            s += "<start_of_turn>user\n" + style_hint_for_lang(LANG, int(CONF.get('reply max sentences',3))) + "<end_of_turn>\n<start_of_turn>model\nOK.<end_of_turn>\n"

                        # for u, a in history[-eff_hist:]:
                        #     if u: s += "<start_of_turn>user\n"+u+"<end_of_turn>\n"
                        #     if a: s += "<start_of_turn>model\n"+a+"<end_of_turn>\n"
                        s += "<start_of_turn>user\n" + user_text + "<end_of_turn>\n"
                        s += "<start_of_turn>model\n"
                        return s

                    #===LLM ===
                    out = llm(
                        build_prompt(user_for_llm),
                        max_tokens=int(CONF.get("reply_max_tokens",180)),
                        temperature=0.1, top_k=25, top_p=1.0,
                        repeat_penalty=1.1, stop=["<eos>","<end_of_turn>"]
                    )
                    # reply = truncate_sentences(out["choices"][0]["text"].strip(),
                    #     int(CONF.get("reply_max_sentences",3)))

                    #メモリ更新
                    # history.append((user_for_llm, reply))
                    # if len(history) > HIST_MAX:
                    #     history = history[-HIST_MAX:]
                    # save_pair(text, reply)

                    # out = llm(
                    #     gemma_prompt(text),
                    #     max_tokens=REPLY_MAX_TOKENS, temperature=0.1, top_k=25, top_p=1.0,
                    #     repeat_penalty=1.1, stop=["<eos>","<end_of_turn>"]
                    # )
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
        