# Quick Start Guide

## Prerequisites

- Docker & Docker Compose
- Node.js 18+ (for local frontend development)
- Python 3.11+ (for local backend development)

## Docker Compose (Easiest)

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Start all services
docker-compose up --build

# 3. Access the application
# Frontend: http://localhost:5173
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

The app will auto-login with username `dev` / password `dev`.

## Local Development

### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Initialize database
python scripts/init_db.py

# Run server
uvicorn main:app --reload

# In another terminal, run worker
python -m rq worker --url redis://localhost:6379/0 default
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

## Testing the Flow

1. **Send a message**: Type in the input box and click "Send"
2. **Create a chart job**: Click "Generate Chart" button
3. **Watch progress**: The async placeholder will show progress updates
4. **See final result**: Chart will render when job completes

## API Testing with curl

```bash
# 1. Get JWT token
TOKEN=$(curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=dev&password=dev" | jq -r '.access_token')

# 2. Create conversation
CONV_ID=$(curl -X POST http://localhost:8000/conversations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test"}' | jq -r '.id')

# 3. Send message
curl -X POST http://localhost:8000/conversations/$CONV_ID/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"Hello!","role":"user"}'

# 4. Create job
curl -X POST http://localhost:8000/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"chart","params":{"range":30},"conversation_id":'$CONV_ID'}'
```

## Troubleshooting

- **Database errors**: Run `python backend/scripts/init_db.py` to initialize tables
- **Redis connection errors**: Ensure Redis is running (`docker-compose up redis`)
- **WebSocket not connecting**: Check CORS settings in `.env` and backend config
- **Worker not processing jobs**: Verify worker is running and connected to Redis


