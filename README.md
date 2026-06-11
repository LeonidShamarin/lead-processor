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
│   AI Analysis   │  Groq — Llama 3.3 70B (безкоштовно, 14400 req/day)
│  (Groq API)     │  генерує summary та класифікує: 🔥 HOT / 🟡 WARM / ❄️ COLD
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

> ℹ️ Сервіс розгорнуто на безкоштовному плані Render. Після 15 хв неактивності засинає — перший запит може зайняти ~30 сек.

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
  "lead_id": "8C6E6FAD",
  "received_at": "2026-06-11 10:23 UTC",
  "classification": "🔥 HOT",
  "ai_summary": "Іван Сірко з ТОВ Технології Майбутнього шукає партнера для автоматизації відділу продажів, зокрема інтеграцію з маркетплейсами та автоматичне виставлення рахунків, з терміновим стартом наступного місяця.",
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

При недоступності Groq API — автоматичний fallback на rule-based класифікацію (система не падає).

---

## Структура проекту

```
lead_processor/
├── main.py           # FastAPI app, endpoint /webhook/lead
├── models.py         # Pydantic схеми + нормалізація даних
├── ai_service.py     # Groq Llama 3.3 70B: summary + класифікація
├── airtable.py       # Airtable API: запис рядка в таблицю
├── telegram.py       # Telegram Bot API: HTML-сповіщення
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
| `GROQ_API_KEY` | Безкоштовно: [console.groq.com/keys](https://console.groq.com/keys) — 14,400 req/day, без кредитки |
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

## Деплой (Render.com)

Проект задеплоєний на **Render.com** (безкоштовний план):

1. New Web Service → Connect GitHub repo
2. Build Command: `pip install -r requirements.txt`
3. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Додати Environment Variables у вкладці Variables
