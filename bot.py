{\rtf1\ansi\ansicpg1251\cocoartf2868
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\paperw11900\paperh16840\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 from telethon import TelegramClient, events\
from openai import OpenAI\
\
# 1. Sizning shaxsiy kalitlaringiz (To'g'ridan-to'g'ri kodga yozilgan)\
API_ID = 38549581\
API_HASH = '326b6c537276564e823391ec0bb66fa8'\
BOT_TOKEN = '8694308467:AAGZubwjJHn3pD6_dS0GJukt274PNXAyXFg'\
OPENAI_API_KEY = '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'\
\
# 2. OpenAI (ChatGPT) ni ishga tushirish\
client = OpenAI(api_key=OPENAI_API_KEY)\
\
# 3. AI uchun tizimli yo'riqnoma (Prompt)\
SYSTEM_PROMPT = """Sen Yunusjonning shaxsiy biznes yordamchisisan.\
Vazifang mijozlar bilan Telegram orqali xushmuomala, qisqa va aniq muloqot qilish.\
Mijoz savol bersa, qo'lingdan kelgancha yordam berishga harakat qil. \
Agar savol murakkab bo'lsa yoki narxlar haqida aniq ma'lumot so'ralsa, "Buni Yunusjonning o'zlari bilan aniqlashtirib, sizga tez orada aniq xabar beraman" deb javob qaytar.\
"""\
\
# 4. Telegram botni ishga tushirish\
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)\
\
@bot.on(events.NewMessage)\
async def handler(event):\
    # O'zimiz yozgan xabarlarga yoki guruhlardagi umumiy xabarlarga javob bermaslik\
    if event.out or event.is_group:\
        return\
\
    # SINOV REJIMI: Faqat bitta akkauntga javob berish filtri (@dr_radiologist_valiyev)\
    sender = await event.get_sender()\
    if not sender or getattr(sender, 'username', None) != "dr_radiologist_valiyev":\
        return \
\
    user_msg = event.raw_text\
    if not user_msg:\
        return\
\
    try:\
        # Mijoz xabarini ChatGPT ga jo'natish\
        response = client.chat.completions.create(\
            model="gpt-4o-mini", # Eng tez va hamyonbop model\
            messages=[\
                \{"role": "system", "content": SYSTEM_PROMPT\},\
                \{"role": "user", "content": user_msg\}\
            ]\
        )\
        \
        # ChatGPT tayyorlagan javobni yuborish\
        reply_text = response.choices[0].message.content\
        await event.reply(reply_text)\
        \
    except Exception as e:\
        print(f"Xatolik yuz berdi: \{e\}")\
\
print("ChatGPT yordamchisi ishga tushdi va xabarlarni kutmoqda...")\
bot.run_until_disconnected()}