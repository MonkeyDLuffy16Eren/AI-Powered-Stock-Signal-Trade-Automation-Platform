from flask import Flask, render_template, request
import pandas as pd
from datetime import datetime
import os

# Custom modules
from strategy import get_signals
from google_sheets import (
    log_to_google_sheets,
    get_signals_from_sheet,
    log_summary_metrics
)
from utils import fetch_stock_data, calculate_indicators
from ml_model import predict_movement
from telegram_alert import send_telegram_alert

app = Flask(__name__)


def append_to_trades_csv(symbol, signal, price, profit=None):
    """
    Append a new trade signal to trades.csv with basic info.
    Creates the file if it doesn't exist.
    """
    file_exists = os.path.isfile(TRADES_CSV)

    with open(TRADES_CSV, mode='a', newline='') as file:
        if not file_exists:
            file.write("date,stock,action,entry_price,exit_price,pnl\n")

        line = f"{datetime.now().strftime('%Y-%m-%d')},{symbol},{signal},{price},,{profit or ''}\n"
        file.write(line)


def run_trading_logic():
    """
    Runs main trading logic: fetches data, detects signals, logs, alerts, and updates CSVs.
    """
    stocks = ['RELIANCE.NS', 'TCS.NS', 'INFY.NS']
    for stock in stocks:
        print(f"\n[+] Processing {stock}...")

        try:
            df = fetch_stock_data(stock)
            df = calculate_indicators(df)
            df, signals = get_signals(df)
            print(f"[✓] {len(signals)} signals generated.")

            log_to_google_sheets(stock, df, signals)

            if not signals.empty:
                latest_signal = signals.iloc[-1]
                if latest_signal['Signal'].lower() == "buy":
                    price = latest_signal['Close']
                    date_str = latest_signal.name.strftime('%Y-%m-%d')

                    # 🔔 Send Telegram alert
                    signal_msg = f"""📢 *Buy Signal Alert*

📌 Stock: {stock}
📅 Date: {date_str}
💰 Price: ₹{price:.2f}
"""
                    send_telegram_alert(signal_msg)

                    # 💾 Log to trades CSV
                    append_to_trades_csv(stock, "Buy", price)

        except Exception as e:
            print(f"[!] Error processing {stock}: {e}")

    # Log summary metrics
    log_summary_metrics()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/signals")
def signals():
    signal_data = get_signals_from_sheet()
    return render_template("signals.html", signals=signal_data)


@app.route("/summary")
def summary():
    # ✅ Fetch trades from Google Sheet (Sheet1)
    trades_df = get_sheet_df("Sheet1")

    # ✅ Fetch summary PnL from Summary_PnL sheet (assume 1st row)
    try:
        summary_df = get_sheet_df("Summary_PnL")
        summary_dict = summary_df.iloc[0].to_dict() if not summary_df.empty else {}
    except Exception as e:
        summary_dict = {}

    return render_template(
        "summary.html",
        trades=trades_df.to_dict(orient="records"),
        summary=summary_dict
    )



@app.route("/predict", methods=["GET", "POST"])
def predict():
    result = None
    selected_stock = None

    if request.method == "POST":
        selected_stock = request.form.get("symbol")

        if not selected_stock:
            result = {
                "stock": "N/A",
                "prediction": "❌ No stock selected."
            }
        else:
            try:
                df = fetch_stock_data(selected_stock)
                df = calculate_indicators(df)
                latest = df.iloc[-1]

                prediction = predict_movement(
                    latest["RSI"],
                    latest["MACD"],
                    latest["Volume"]
                )

                result = {
                    "stock": selected_stock,
                    "prediction": "✅ Buy Signal" if prediction == 1 else "⛔ No Signal"
                }

            except Exception as e:
                result = {
                    "stock": selected_stock,
                    "prediction": f"⚠️ Error: {e}"
                }

    return render_template("predict.html", result=result, selected_stock=selected_stock)


if __name__ == "__main__":
    run_trading_logic()
    app.run(debug=True)
