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
│   AI Analysis   │  Claude Sonnet — генерує summary заявки
│  (Claude API)   │  та класифікує ліда: 🔥 HOT / 🟡 WARM / ❄️ COLD
└────────┬────────┘
         │
    ┌────┴────┐  (паралельно)
    ▼         ▼
┌───────┐ ┌──────────┐
│Sheets │ │ Telegram │
│  API  │ │   Bot    │
└───────┘ └──────────┘
```

---

## Швидкий старт

### 1. Встановлення залежностей

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Налаштування `.env`

```bash
cp .env.example .env
# Відкрий .env і заповни свої ключі
```

| Змінна | Опис |
|--------|------|
| `GEMINI_API_KEY` | Безкоштовний ключ Gemini API ([aistudio.google.com/apikey](https://aistudio.google.com/apikey)) — без кредитки, 1500 req/day |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | JSON ключ сервісного акаунту Google (однорядковий) |
| `GOOGLE_SHEET_ID` | ID таблиці з URL (частина між `/d/` та `/edit`) |
| `GOOGLE_SHEET_NAME` | Назва листа, за замовчуванням `Leads` |
| `TELEGRAM_BOT_TOKEN` | Токен від @BotFather |
| `TELEGRAM_CHAT_ID` | ID чату/каналу (для каналу починається з `-100`) |

#### Google Sheets: як отримати Service Account
1. [console.cloud.google.com](https://console.cloud.google.com) → IAM → Service Accounts → Create
2. Завантаж JSON-ключ
3. **Поділись таблицею** з email сервісного акаунту (Editor доступ)
4. Скопіюй весь JSON в одному рядку в змінну `GOOGLE_SERVICE_ACCOUNT_JSON`

#### Telegram: як знайти Chat ID
```bash
# Додай бота в чат, надішли будь-яке повідомлення, потім:
curl https://api.telegram.org/bot<TOKEN>/getUpdates
# Знайди "chat":{"id": ...}
```

### 3. Запуск

```bash
python main.py
# або
uvicorn main:app --reload
```

Сервер стартує на `http://localhost:8000`

---

## Тестування

### Тест через curl

```bash
curl -X POST http://localhost:8000/webhook/lead \
  -H "Content-Type: application/json" \
  -d @test_payload.json
```

### Тест через Python

```python
import httpx, json

payload = json.load(open("test_payload.json"))
r = httpx.post("http://localhost:8000/webhook/lead", json=payload)
print(r.json())
```

### Тест через Swagger UI

Відкрий `http://localhost:8000/docs` — інтерактивна документація.

---

## Приклад відповіді

```json
{
  "success": true,
  "lead_id": "A3F7B2C1",
  "received_at": "2025-06-10 14:32 UTC",
  "classification": "🔥 HOT",
  "ai_summary": "Петро Іванов з компанії ТОВ Технології Майбутнього (50-200 осіб) шукає партнера для автоматизації відділу продажів з бюджетом від 15 000 USD. Потрібна інтеграція Bitrix24 з маркетплейсами та автоматичне виставлення рахунків — проект терміновий.",
  "destinations": {
    "google_sheets": true,
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

При недоступності AI API — автоматичний fallback на rule-based класифікацію.

---

## Структура проекту

```
lead_processor/
├── main.py          # FastAPI app, endpoint /webhook/lead
├── models.py        # Pydantic схеми + нормалізація
├── ai_service.py    # Anthropic Claude: summary + класифікація
├── sheets.py        # Google Sheets API: запис рядка
├── telegram.py      # Telegram Bot API: сповіщення
├── requirements.txt
├── .env.example
├── test_payload.json
└── README.md
```

---

## Деплой на Railway (безкоштовно)

```bash
# 1. Встанови Railway CLI
npm install -g @railway/cli

# 2. Логін та деплой
railway login
railway init
railway up

# 3. Додай змінні оточення в Railway Dashboard → Variables
```

Або використай **Render.com** → New Web Service → підключи GitHub репо.
