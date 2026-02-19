from datetime import datetime
from io import StringIO
import csv
import time
from typing import List
from dotenv import load_dotenv
import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .analysis import Transaction, assemble_analysis_result
from .schemas import AnalysisResult, FullAnalysisResponse, GraphData


REQUIRED_COLUMNS = [
    "transaction_id",
    "sender_id",
    "receiver_id",
    "amount",
    "timestamp",
]


app = FastAPI(title="Money Muling Detection Engine")


load_dotenv()
origins = os.getenv("CORS_ORIGINS", "").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



def parse_csv(file_bytes: bytes) -> List[Transaction]:
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded.")

    reader = csv.DictReader(StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="CSV file has no header row.")

    missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"CSV missing required columns: {', '.join(missing)}",
        )

    transactions: List[Transaction] = []
    for idx, row in enumerate(reader, start=2):  # row 1 is header
        try:
            tx_id = str(row["transaction_id"]).strip()
            sender = str(row["sender_id"]).strip()
            receiver = str(row["receiver_id"]).strip()
            amount_str = str(row["amount"]).strip()
            ts_str = str(row["timestamp"]).strip()

            if not (tx_id and sender and receiver and amount_str and ts_str):
                raise ValueError("Empty required field")

            amount = float(amount_str)
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid data at CSV line {idx}: {exc}",
            ) from exc

        transactions.append(
            Transaction(
                transaction_id=tx_id,
                sender_id=sender,
                receiver_id=receiver,
                amount=amount,
                timestamp=ts,
            )
        )

    if not transactions:
        raise HTTPException(status_code=400, detail="CSV contains no transactions.")

    return transactions



@app.get("/")
async def root():
    return {"message": "Money Muling Detection Engine is running"}

    
@app.post(
    "/analyze",
    response_model=FullAnalysisResponse,
    summary="Analyze uploaded CSV and detect money muling patterns.",
)
async def analyze_file(file: UploadFile = File(...)) -> FullAnalysisResponse:
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    file_bytes = await file.read()
    start = time.perf_counter()

    transactions = parse_csv(file_bytes)

    result, graph_data = assemble_analysis_result(
        transactions,
        processing_time_seconds=0.0,  # placeholder, set below
    )

    end = time.perf_counter()
    processing_time = end - start

    # Update processing_time_seconds in summary
    result.summary.processing_time_seconds = round(processing_time, 3)

    return FullAnalysisResponse(result=result, graph=graph_data)


@app.get("/health")
async def health_check():
    return {"status": "ok"}

