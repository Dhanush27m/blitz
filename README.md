## Money Muling Detection Engine (Local Setup)

### Backend (FastAPI + NetworkX)

- **Tech**: FastAPI, NetworkX, pure-Python CSV parsing.
- **Location**: `backend/`

#### Install backend dependencies

From the project root:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # on Windows
pip install -r requirements.txt
```

#### Run backend locally

```bash
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000` and exposes:

- `GET /health` – basic health check.
- `POST /analyze` – multipart file upload (`file` field, CSV) returning:
  - `result`: JSON that matches the required `suspicious_accounts`, `fraud_rings`, and `summary` schema.
  - `graph`: nodes and edges for visualization.

CSV requirements:

- Columns: `transaction_id,sender_id,receiver_id,amount,timestamp`
- `timestamp` format: `YYYY-MM-DD HH:MM:SS`

### Frontend (React + Cytoscape.js)

- **Tech**: React, Vite, Cytoscape.js, `react-cytoscapejs`.
- **Location**: `frontend/`

#### Install frontend dependencies

From the project root:

```bash
cd frontend
npm install
```

#### Run frontend locally

```bash
npm run dev
```

Then open the printed Vite dev URL (default: `http://localhost:5173`).

### End-to-end usage

1. Start the backend (`uvicorn ...`) on port `8000`.
2. Start the frontend (`npm run dev`) on port `5173`.
3. Open the frontend in a browser.
4. Upload a CSV using the upload control and click **Analyze CSV**.
5. Inspect:
   - **Summary dashboard**: key counts and processing time.
   - **Interactive graph viewer**: suspicious nodes highlighted (larger, red, bordered) with directed edges.
   - **Fraud ring table**: one row per detected ring with ring ID, pattern type, member count, risk score, and accounts.
   - **Suspicious accounts table**: sorted descending by suspicion score.
6. Click **Download JSON** to download a file whose structure matches the mandatory JSON format from the problem statement.

