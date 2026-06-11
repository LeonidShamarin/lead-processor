# 🎯 Lead Processor — MVP

FastAPI-сервіс для автоматичної обробки заявок з лендингу.

## Що робить

```
POST /webhook/lead
       │
       ▼
┌─────────────────┐
│  Validation &   │  Pydantic — валідація + нормалізація полів
│  Normalization  │  (ім'я, email, телефон, бюджет)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   AI Analysis   │  Gemini 2.0 Flash (безкоштовно) — генерує
│  (Gemini API)   │  summary та класифікує: 🔥 HOT / 🟡 WARM / ❄️ COLD
└────────┬────────┘
         │
    ┌────┴────┐  (паралельно)
    ▼         ▼
┌─────────┐ ┌──────────┐
│Airtable │ │ Telegram │
│   API   │ │   Bot    │
└─────────┘ └──────────┘
```

---

## Live Demo

- **API:** https://lead-processor-seap.onrender.com
- **Swagger UI:** https://lead-processor-seap.onrender.com/docs
- **Health check:** https://lead-processor-seap.onrender.com/health

---

## Тестовий payload

```json
{
  "name": "Іван Сірко",
  "email": "sirkoivan@gmail.com",
  "phone": "0671234567",
  "company": "ТОВ Технології Майбутнього",
  "employees": "50-200",
  "budget": "15k",
  "service": "Автоматизація бізнес-процесів",
  "source": "LinkedIn",
  "message": "Шукаємо партнера для автоматизації нашого відділу продажів. Маємо CRM на базі Bitrix24, потрібна інтеграція з маркетплейсами та автоматичне виставлення рахунків. Терміново, бажано стартувати наступного місяця."
}
```

```bash
curl -X POST https://lead-processor-seap.onrender.com/webhook/lead \
  -H "Content-Type: application/json" \
  -d @test_payload.json
```

---

## Приклад відповіді

```json
{
  "success": true,
  "lead_id": "2D6BC61C",
  "received_at": "2026-06-11 09:40 UTC",
  "classification": "🔥 HOT",
  "ai_summary": "Іван Сірко з компанії ТОВ Технології Майбутнього шукає партнера для автоматизації відділу продажів з бюджетом 15 000. Потрібна інтеграція Bitrix24 з маркетплейсами — проект терміновий.",
  "destinations": {
    "airtable": true,
    "telegram": true
  }
}
```

---

## Нормалізація даних

| Поле | Вхід | Після нормалізації |
|------|------|--------------------|
| `name` | `"  іванов петро  "` | `"Іванов Петро"` |
| `email` | `"Petro@EXAMPLE.COM"` | `"petro@example.com"` |
| `phone` | `"0671234567"` | `"+380671234567"` |
| `budget` | `"15k"` | `"15000"` |
| `source` | `"LinkedIn"` | `"social"` |

---

## Класифікація лідів

| Оцінка | Критерії |
|--------|----------|
| 🔥 **HOT** | Великий бюджет + компанія + конкретний запит + терміновість |
| 🟡 **WARM** | Є сигнали зацікавленості, але неповні дані |
| ❄️ **COLD** | Відсутній бюджет, нечіткий запит, ймовірний студент/дослідник |

При недоступності Gemini API — автоматичний fallback на rule-based класифікацію.

---

## Структура проекту

```
lead_processor/
├── main.py           # FastAPI app, endpoint /webhook/lead
├── models.py         # Pydantic схеми + нормалізація
├── ai_service.py     # Gemini 2.0 Flash: summary + класифікація
├── airtable.py       # Airtable API: запис рядка
├── telegram.py       # Telegram Bot API: сповіщення
├── requirements.txt
├── .env.example
├── test_payload.json
└── README.md
```

---

## Локальний запуск

### 1. Залежності

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Змінні оточення

```bash
cp .env.example .env
# Заповни свої ключі в .env
```

| Змінна | Опис |
|--------|------|
| `GEMINI_API_KEY` | Безкоштовно: [aistudio.google.com/apikey](https://aistudio.google.com/apikey) — 1500 req/day, без кредитки |
| `AIRTABLE_API_TOKEN` | [airtable.com/create/tokens](https://airtable.com/create/tokens) — scope: `data.records:write` |
| `AIRTABLE_BASE_ID` | ID бази з URL: `airtable.com/appXXXXXX/...` |
| `AIRTABLE_TABLE_ID` | ID таблиці з URL: `.../tblXXXXXX/...` |
| `TELEGRAM_BOT_TOKEN` | Токен від [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Отримати через `api.telegram.org/bot<TOKEN>/getUpdates` |

### 3. Запуск

```bash
uvicorn main:app --reload
# http://localhost:8000/docs
```

---

## Деплой

Проект задеплоєний на **Render.com** (безкоштовний план):

1. New Web Service → Connect GitHub repo
2. Build: `pip install -r requirements.txt`
3. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Додати Environment Variables
