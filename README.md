# MONEY MULING DETECTION CHALLENGE

A comprehensive graph-based fraud detection system that identifies money muling patterns in financial transaction data. The system analyzes transaction networks to detect suspicious cycles, smurfing patterns, shell networks, and high-velocity transactions.

## 🔗 Live Demo

**Live Demo URL:** _[To be submitted]_

## Tech Stack

### Backend
- **Framework:** FastAPI 0.115.5
- **ASGI Server:** Uvicorn 0.32.1 (with Gunicorn for production)
- **Graph Analysis:** NetworkX 3.4.2
- **Data Validation:** Pydantic
- **Environment Management:** python-dotenv
- **Python Version:** 3.11.9

### Frontend
- **Framework:** React 18.3.1
- **Build Tool:** Vite 6.0.3
- **HTTP Client:** Axios 1.7.9
- **Graph Visualization:** Cytoscape.js 3.30.3 + react-cytoscapejs 1.2.1

## System Architecture

The application follows a **monorepo architecture** with clear separation between backend and frontend:

```
blitz/
├── backend/              # Python FastAPI backend
│   ├── app/
│   │   ├── main.py       # API endpoints & CSV parsing
│   │   ├── analysis.py   # Core fraud detection algorithms
│   │   ├── schemas.py    # Pydantic data models
│   │   └── config.py     # Detection thresholds & scoring
│   ├── requirements.txt
│   └── runtime.txt
│
└── frontend/            # React + Vite frontend
    ├── src/
    │   ├── App.jsx       # Main React component
    │   ├── main.jsx      # React entry point
    │   └── styles.css    # Application styles
    ├── index.html
    ├── package.json
    └── vite.config.mts
```

### Architecture Flow

1. **Frontend** → User uploads CSV file via React UI
2. **Backend API** → FastAPI endpoint receives and validates CSV
3. **Graph Construction** → NetworkX builds directed transaction graph
4. **Pattern Detection** → Multiple algorithms analyze the graph
5. **Scoring** → Suspicion scores computed for each account
6. **Response** → Analysis results + graph data returned to frontend
7. **Visualization** → Cytoscape.js renders interactive graph

### API Endpoints

- **POST `/analyze`** - Analyzes uploaded CSV file and returns fraud detection results
- **GET `/health`** - Health check endpoint

## 🔍 Algorithm Approach

The system employs four complementary detection algorithms to identify different money muling patterns:

### 1. Cycle Ring Detection

**Purpose:** Detects circular transaction flows (A→B→C→A) indicating money laundering cycles.

**Algorithm:**
- Filters nodes with total degree < 2 (cannot form cycles)
- Computes Strongly Connected Components (SCCs) for efficiency
- Runs bounded-depth DFS (max depth 5) only within SCCs of size 3-100
- Detects cycles of length 3-5 nodes
- Deduplicates cycles using canonical node-set keys

**Complexity Analysis:**
- **Time Complexity:** O(V + E + SCC_count × SCC_size × d^max_depth)
  - V = vertices, E = edges
  - SCC computation: O(V + E)
  - DFS per SCC: O(SCC_size × d^max_depth) where d = average degree, max_depth = 5
  - In practice: O(V + E) for sparse graphs, O(V × d^5) worst case for dense SCCs
- **Space Complexity:** O(V + E) for graph storage + O(V) for DFS recursion stack
- **Optimization:** SCC-based pruning reduces search space significantly

**Risk Score:** 70-100 (based on cycle length)

### 2. Smurf Ring Detection

**Purpose:** Identifies structured transactions designed to avoid detection thresholds.

**Patterns Detected:**
- **Fan-in:** Multiple senders → one receiver (within 72-hour window)
- **Fan-out:** One sender → multiple receivers (within 72-hour window)

**Algorithm:**
- Groups transactions by sender/receiver
- Uses sliding window technique (72-hour window)
- Tracks unique counterparties within window
- Flags accounts with ≥10 counterparties
- Applies merchant/payroll heuristics to reduce false positives

**Complexity Analysis:**
- **Time Complexity:** O(T × log T + A × W)
  - T = total transactions (for sorting)
  - A = unique accounts
  - W = average transactions per account in window
  - Sliding window: O(T) amortized per account
- **Space Complexity:** O(A + T) for transaction grouping and window tracking
- **Optimization:** Sliding window avoids redundant calculations

**Risk Score:** 75 (for both fan-in and fan-out patterns)

### 3. Shell Ring Detection

**Purpose:** Detects layering patterns where money flows through intermediate "shell" accounts.

**Algorithm:**
- BFS traversal with max depth 4 edges
- Identifies paths where intermediate accounts have ≤3 transactions
- Requires minimum 3 hops (source → intermediate → ... → destination)
- Filters out high-activity intermediate nodes

**Complexity Analysis:**
- **Time Complexity:** O(V × (d^max_depth))
  - V = vertices with ≤3 transactions
  - d = average out-degree
  - max_depth = 4
  - Worst case: O(V × d^4) but pruned by transaction count filter
- **Space Complexity:** O(V + E) for graph + O(V × max_depth) for BFS queue
- **Optimization:** Early termination for high-activity nodes

**Risk Score:** 60-100 (based on chain length)

### 4. High Velocity Detection

**Purpose:** Flags accounts with abnormally high transaction frequency.

**Algorithm:**
- Tracks all transactions per account
- Uses sliding window (24-hour) to count transactions
- Flags accounts with ≥30 transactions within window
- Only boosts suspicion score (does not create rings)

**Complexity Analysis:**
- **Time Complexity:** O(T × log T + A × W)
  - T = total transactions
  - A = unique accounts
  - W = window size (24 hours)
  - Sorting: O(T log T)
  - Sliding window per account: O(transactions_per_account)
- **Space Complexity:** O(A + T) for timestamp storage

**Score Boost:** +10 points (additive only, applied to already suspicious accounts)

### Overall Complexity

- **Graph Construction:** O(T) where T = number of transactions
- **Pattern Detection:** O(V + E + V × d^5) worst case (dominated by cycle detection)
- **Scoring:** O(V + R) where R = number of rings
- **Graph Data Building:** O(V + E)

**Total:** O(V + E + V × d^5) ≈ O(V × d^5) for dense graphs, but optimized to O(V + E) for typical sparse transaction graphs.

## 📊 Suspicion Score Methodology

The system uses a **weighted scoring system** where different patterns contribute points to an account's suspicion score:

### Scoring Weights

| Pattern Type | Base Score | Description |
|-------------|------------|-------------|
| **Cycle** | 40 points | Detected in cycle ring (length 3-5) |
| **Fan-in** | 30 points | Multiple senders → one receiver |
| **Fan-out** | 30 points | One sender → multiple receivers |
| **Shell** | 35 points | Part of layering chain |
| **High Velocity** | 10 points | ≥30 transactions in 24 hours (additive only) |

### Score Calculation

1. **Pattern Detection:** Each algorithm identifies fraud rings and assigns accounts to rings
2. **Score Aggregation:** For each account, sum scores from all detected patterns
3. **Multi-Signal Boost:** High velocity adds 10 points only if account already has suspicion score > 0
4. **Score Capping:** Maximum score is capped at 100 points

### Risk Score vs Suspicion Score

- **Risk Score:** Assigned to fraud rings (70-100 based on pattern type and characteristics)
- **Suspicion Score:** Assigned to individual accounts (0-100, aggregated from pattern scores)

### Thresholds

- **High Velocity:** 30 transactions within 24 hours
- **Smurfing:** 10 unique counterparties within 72 hours
- **Shell:** Minimum 3 hops, max 3 transactions for intermediates
- **Merchant Filter:** ≥300 transactions, CV ≤0.3, ≥14 days observation
- **Payroll Filter:** ≥100 transactions, CV ≤0.2, ≥3 distinct pay dates

## 🚀 Installation & Setup

### Prerequisites

- **Python 3.11.9**
- **Node.js** (v16 or higher)
- **npm** or **yarn**

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment 
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the `backend` directory:
```env
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

5. Run the backend server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Create a `.env` file in the `frontend` directory:
```env
VITE_API_URL=http://localhost:8000
```

4. Start the development server:
```bash
npm run dev
```

The frontend will be available at `http://localhost:5173`

### Production Build

**Backend:**
```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

**Frontend:**
```bash
npm run build
npm run preview
```

## 📖 Usage Instructions

### CSV File Format

The system expects CSV files with the following required columns:

- `transaction_id` - Unique identifier for each transaction (String)
- `sender_id` - Account ID of the sender (String)
- `receiver_id` - Account ID of the receiver (String)
- `amount` - Transaction amount (float) 
- `timestamp` - Transaction timestamp in format: `YYYY-MM-DD HH:MM:SS` (Date time)

**Example CSV:**
```csv
transaction_id,sender_id,receiver_id,amount,timestamp
TXN001,ACC001,ACC002,1000.50,2024-01-15 10:30:00
TXN002,ACC002,ACC003,1000.50,2024-01-15 11:00:00
TXN003,ACC003,ACC001,1000.50,2024-01-15 11:30:00
```

### Using the Application

1. **Upload CSV File:**
   - Click "Choose File" and select your CSV file
   - Click "Analyze CSV" button

2. **View Results:**
   - **Summary Dashboard:** Overview of total accounts, suspicious accounts, fraud rings, and processing time
   - **Interactive Graph:** Visual representation of transaction network
     - Red nodes = Suspicious accounts
     - Blue nodes = Normal accounts
     - Node size = Proportional to suspicion score
   - **Fraud Ring Table:** List of detected fraud rings with details
   - **Suspicious Accounts Table:** List of flagged accounts sorted by suspicion score

3. **Interact with Graph:**
   - **View Modes:**
     - "All accounts" - Shows complete transaction network
     - "Cycle rings" - Shows only accounts involved in cycle patterns
   - **Ring Highlighting:** Click any row in the Fraud Ring Table to highlight that ring in the graph
   - **Fullscreen:** Toggle fullscreen mode for better visualization

4. **Export Results:**
   - Click "Download JSON" to export analysis results as JSON file

### API Usage

**Analyze CSV File:**
```bash
curl -X POST "http://localhost:8000/analyze" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@transactions.csv"
```

**Health Check:**
```bash
curl http://localhost:8000/health
```

## ⚠️ Known Limitations

1. **Stateless Processing:** The system does not maintain a database. Each analysis is independent and does not learn from historical data.

2. **CSV File Size:** Very large CSV files (>100MB) may cause performance issues or timeout errors. Consider preprocessing large datasets.

3. **Graph Visualization:** Cytoscape.js performance degrades with very large graphs (>10,000 nodes). The visualization is optimized for datasets with <5,000 accounts.

4. **Pattern Detection:**
   - Cycle detection limited to cycles of length 3-5 (longer cycles not detected)
   - Shell detection limited to 4-hop paths (deeper layering may be missed)
   - Smurf detection requires ≥10 counterparties (smaller rings may be missed)

5. **False Positives:**
   - Merchant and payroll heuristics reduce false positives but may not cover all legitimate patterns
   - High-velocity detection may flag legitimate high-frequency traders

6. **Real-time Processing:** The system processes files synchronously. Large files may take several seconds to process.

7. **No Authentication:** The API currently has no authentication or authorization mechanisms.

8. **Single File Processing:** Only one CSV file can be analyzed at a time. Batch processing is not supported.

9. **Memory Constraints:** Very large transaction graphs may consume significant memory. Consider processing in batches for datasets with >1M transactions.

10. **Timestamp Format:** Only supports `YYYY-MM-DD HH:MM:SS` timestamp format. Other formats will cause parsing errors.

## 📝 License

This project is part of the Money Muling Detection Challenge.

---

**Note:** This system is designed for educational and demonstration purposes. For production use in financial systems, additional security, compliance, and validation measures should be implemented.
