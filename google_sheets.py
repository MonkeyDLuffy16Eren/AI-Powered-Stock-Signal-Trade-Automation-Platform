import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pandas as pd
from telegram_alert import send_telegram_alert  # ✅ Telegram alert integration

# Constants
SHEET_ID = "1Nme2_dmlFSYKJy6UkbiJHmmwamGAgHXYnwq5ulEb2xM"
SHEET_NAME = "Sheet1"
JSON_KEYFILE_PATH = r"E:\algo_training_project\woven-honor-428007-v9-15267f1ec52f.json"

# Setup Google Sheets access
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEYFILE_PATH, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID)
signal_sheet = sheet.worksheet(SHEET_NAME)


# 1. Log Buy/Sell signals
def log_to_google_sheets(stock, df, signals):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for index, row in signals.iterrows():
        signal_value = row['Signal']
        rows.append([
            now,
            stock,
            str(index.date()),
            signal_value,
            row['Close']
        ])
    if rows:
        signal_sheet.append_rows(rows, value_input_option='RAW')
        print(f"[✓] Logged {len(rows)} signals to Google Sheets.")

        for row_data in rows:
            signal_type = str(row_data[3]).strip().lower()
            if signal_type == "buy":
                stock_name = row_data[1]
                signal_date = row_data[2]
                price = row_data[4]
                alert = f"📢 *Buy Signal Alert*\n\n📌 Stock: *{stock_name}*\n📅 Date: {signal_date}\n💰 Price: ₹{price}"
                send_telegram_alert(alert)
    else:
        print("[i] No signals to log.")


# 2. Read logged signals (for UI display)
def get_signals_from_sheet():
    try:
        signal_data = signal_sheet.get_all_records()
        if signal_data:
            print(f"[✓] Fetched {len(signal_data)} signals from sheet.")
        else:
            print("[i] Sheet is empty.")
        return signal_data
    except Exception as e:
        print(f"[!] Error reading sheet: {e}")
        return []


# 3. Log summary P&L and win ratio based on actual Buy-Sell pairing
def log_summary_metrics():
    try:
        data = signal_sheet.get_all_values()
        if len(data) <= 1:
            print("[i] Sheet is empty or only contains header.")
            return

        df = pd.DataFrame(data[1:], columns=data[0])
        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        df = df.dropna(subset=['Close', 'Date'])
        df = df.sort_values('Date')

        trades = []
        buy_tracker = {}

        for _, row in df.iterrows():
            stock = row['Stock']
            signal = str(row['Signal']).strip().lower()
            price = row['Close']
            date = row['Date']

            if signal == 'buy':
                buy_tracker[stock] = (date, price)
            elif signal == 'sell' and stock in buy_tracker:
                buy_date, buy_price = buy_tracker.pop(stock)
                sell_price = price
                pnl = round(sell_price - buy_price, 2)

                trades.append({
                    'Buy Date': buy_date.strftime("%Y-%m-%d"),
                    'Sell Date': date.strftime("%Y-%m-%d"),
                    'Stock': stock,
                    'Buy Price': round(buy_price, 2),
                    'Sell Price': round(sell_price, 2),
                    'P&L': pnl
                })

        if not trades:
            print("[i] No Buy-Sell pairs found.")
            return

        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t['P&L'] > 0)
        total_pnl = sum(t['P&L'] for t in trades)
        win_ratio = round((winning_trades / total_trades) * 100, 2)

        # Update Summary_PnL
        try:
            pnl_sheet = sheet.worksheet("Summary_PnL")
        except:
            pnl_sheet = sheet.add_worksheet("Summary_PnL", rows=100, cols=6)

        pnl_sheet.clear()
        pnl_sheet.update('A1', [['Buy Date', 'Sell Date', 'Stock', 'Buy Price', 'Sell Price', 'P&L']])
        pnl_sheet.append_rows([
            [t['Buy Date'], t['Sell Date'], t['Stock'], t['Buy Price'], t['Sell Price'], t['P&L']]
            for t in trades
        ])
        print(f"[✓] {total_trades} trades logged to Summary_PnL.")

        # Update Win_Ratio
        try:
            win_sheet = sheet.worksheet("Win_Ratio")
        except:
            win_sheet = sheet.add_worksheet("Win_Ratio", rows=10, cols=4)

        win_sheet.clear()
        win_sheet.update('A1', [['Total Trades', 'Winning Trades', 'Win Ratio (%)', 'Total P&L']])
        win_sheet.update('A2', [[total_trades, winning_trades, win_ratio, round(total_pnl, 2)]])
        print(f"[✓] Summary logged: {winning_trades}/{total_trades} wins, Total P&L={total_pnl}, Win Ratio={win_ratio}%")

    except Exception as e:
        print(f"[!] Error calculating summary: {e}")
