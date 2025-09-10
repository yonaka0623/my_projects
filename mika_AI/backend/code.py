from dotenv import load_dotenv
import os
import time
import re
import threading

from openai import OpenAI
import boto3
import speech_recognition as sr
import pygame

# ==== APIサーバ（Flutter用） ====
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# .env を読み込む
load_dotenv()

# .env の中の値を取得
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-1")

# OpenAIクライアント
client = OpenAI(api_key=OPENAI_API_KEY)

# AWS Polly クライアント
polly = boto3.client(
    "polly",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)

# ====== 再生初期化 ======
pygame.mixer.init()

# ====== Flutter向けの最新状態（返答＆感情） ======
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # まずは全部許可でOK（検証が終わったら絞る）
    allow_methods=["*"],
    allow_headers=["*"],
)

latest = {"text": "", "emotion": "NEUTRAL"}

@app.get("/last")
def read_last():
    return latest

def run_api():
    # 127.0.0.1:8000 で待受
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")

# アプリ起動時にAPIサーバを別スレッドで起動
threading.Thread(target=run_api, daemon=True).start()

# ====== 音声認識 ======
def recognize_speech():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("🎤 Talk to me...")
        r.adjust_for_ambient_noise(source, duration=0.5)
        audio = r.listen(source)
    try:
        return r.recognize_google(audio)  # 簡易STT。精度UPはWhisperに差し替え可
    except sr.UnknownValueError:
        return ""  # 聞き取れなかったら空文字を返す
    except sr.RequestError:
        return ""

# ====== キャラ設定と会話履歴（Mika & 感情タグ指示） ======
conversation_history = [
    {
        "role": "system",
        "content": (
            "You are Mika, a cheerful, cute anime-girl English tutor. "
            "Persona: friendly, gentle, playful, always encouraging. "
            "Reply in simple, natural English as Mika. "
            "At the VERY BEGINNING of EVERY reply, output exactly one emotion tag from "
            "{NEUTRAL, HAPPY, SAD, SHY, ANGRY} in the format: [EMOTION=XYZ]\n"
            "After the tag, write your normal reply.\n"
            "Do NOT correct grammar by default.\n"
            "ONLY when the user explicitly says phrases like "
            "'please correct the grammar of my previous statement' "
            "(or 'correct my grammar', or similar; Japanese equivalents like '文法を直して' are also allowed), "
            "perform a brief correction and then prompt for repetition.\n"
            "When correction is requested, output EXACTLY these two lines after your normal reply (no extra questions):\n"
            "What you want to say is: <natural corrected English>\n"
            "Now, please repeat after me: <same corrected English>\n"
            "During the repeat step, do not ask any new questions or introduce new topics.\n"
            "If the user mixes Japanese and English in the same sentence, "
            "convert the meaning into a single, natural English-only sentence, "
            "then present it as a correction using the same format:\n"
            "What you want to say is: <English-only version>\n"
            "Now, please repeat after me: <English-only version>\n"
            "If the user says '日本語で答えて' (or similar in Japanese), then repeat your most recent English reply in natural Japanese.\n"
            "After finishing your spoken reply, imagine waiting about 5 seconds before expecting the user's response.\n"
            "Do not use any emojis in your replies."
        ),
    }
]


emotion_pattern = re.compile(
    r"^\s*\[EMOTION=(NEUTRAL|HAPPY|SAD|SHY|ANGRY)\]\s*(.*)",
    re.IGNORECASE | re.DOTALL,
)

def extract_emotion_and_text(reply: str):
    """Mikaの返答から [EMOTION=...] を抜き出し、(EMOTION, 本文) を返す"""
    m = emotion_pattern.match(reply or "")
    if m:
        return m.group(1).upper(), m.group(2).strip()
    return "NEUTRAL", (reply or "").strip()

# ====== ChatGPT 呼び出し（Mika版・会話履歴）======
def ask_gpt(prompt: str) -> str:
    conversation_history.append({"role": "user", "content": prompt})
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=conversation_history,
    )
    reply = res.choices[0].message.content.strip()
    conversation_history.append({"role": "assistant", "content": reply})
    # 履歴が長くなりすぎないように制限
    MAX_TURNS = 6
    conversation_history[:] = [conversation_history[0]] + conversation_history[-MAX_TURNS * 2 :]
    return reply

# ====== Pollyで読み上げ（毎回ユニークなファイル名）======
def speak_with_polly(text: str, voice_id="Ivy"):
    # 念のため前の再生を停止
    try:
        pygame.mixer.music.stop()
    except Exception:
        pass

    res = polly.synthesize_speech(Text=text, OutputFormat="mp3", VoiceId=voice_id)
    filename = f"response_{int(time.time() * 1000)}.mp3"
    with open(filename, "wb") as f:
        f.write(res["AudioStream"].read())
    pygame.mixer.music.load(filename)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pass
    # 必要なら削除するなら下を有効化
    # try:
    #     os.remove(filename)
    # except OSError:
    #     pass

# ====== メインループ ======
def main():
    print("✅ Mika is ready. Say 'stop' to exit.")
    while True:
        spoken = recognize_speech()
        if not spoken:
            print("⚠️ 音声が認識できませんでした。もう一度どうぞ。")
            continue

        print(f"👂 You said: {spoken}")

        if "stop" in spoken.lower():
            print("👋 Goodbye!")
            break

        # GPT応答（感情タグ付き）
        raw_reply = ask_gpt(spoken)
        emotion, clean_text = extract_emotion_and_text(raw_reply)

        # Flutter向けに保存
        latest.update({"text": clean_text, "emotion": emotion})

        # コンソールにも表示
        print(f"EMOTION: {emotion}")
        print(f"🤖 GPT: {clean_text}")


        # 読み上げは本文のみ（タグは外す）
        speak_with_polly(clean_text, voice_id="Ivy")

if __name__ == "__main__":
    # 環境変数チェック（任意）
    if not OPENAI_API_KEY or not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
        print("❌ 環境変数が未設定です。OPENAI_API_KEY / AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY を設定してください。")
    else:
        main()
