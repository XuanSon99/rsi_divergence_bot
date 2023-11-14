import requests
import datetime
import time
import io
import pandas as pd
import threading
from telegram import __version__ as TG_VER
from pytz import timezone
import talib
from talib import BBANDS
import decimal
from telegram.constants import ParseMode

try:
    from telegram import __version_info__
except ImportError:
    __version_info__ = (0, 0, 0, 0, 0)  # type: ignore[assignment]

if __version_info__ < (20, 0, 0, "alpha", 1):
    raise RuntimeError(
        f"This example is not compatible with your current PTB version {TG_VER}. To view the "
        f"{TG_VER} version of this example, "
        f"visit https://docs.python-telegram-bot.org/en/v{TG_VER}/examples.html"
    )
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# Define key
TOKEN = "6445050105:AAGaFyxd5d0Mp-_kUfQOhAg7ZFhnQv53IXU"  # bot ma scalp
# TOKEN = "6643863300:AAF2OhcI9g70Q4boORLB_XHdBxE9NnFsNwI"  # mailisa bot
BASE_URL = "https://contract.mexc.com/api/v1"
INTERVAL = "1h"
CHAT_ID = "-1001883104059"  # nhóm rsi phân kỳ
# CHAT_ID = "-1001862379259"  # test group

# Define main code


def get_all_future_pairs():
    url = f"{BASE_URL}/contract/detail"
    response = requests.get(url)
    data = response.json()

    if data.get("success", False):
        data = data["data"]
        symbols = [symbol["symbol"] for symbol in data]
        return symbols
    else:
        print("Error: Data retrieval unsuccessful.")
        return None


def get_symbol_data(symbol, interval="Min15"):
    url = f"{BASE_URL}/contract/kline/{symbol}?interval={interval}"
    response = requests.get(url)
    data = response.json()

    if data.get("success", False):
        data = data["data"]
        data_dict = {
            "time": data["time"],
            "open": data["open"],
            "close": data["close"],
            "high": data["high"],
            "low": data["low"],
            "vol": data["vol"],
        }
        df = pd.DataFrame(data_dict)
        df["close"] = df["close"].astype(float)
        return df
    else:
        print("Error: Data retrieval unsuccessful.")
        return None


# NOTE: Cao hơn 10% so với MA 20
def check_confirm_volume(df, threshold=1.1):
    latest_volume = df["vol"].iloc[-2]
    ma_20_vol = talib.MA(df["vol"].values, timeperiod=20)
    if latest_volume > (ma_20_vol[-2] * threshold):
        return True
    else:
        return False


def find_latest_rsi_bullish_divergence(df, threshold=25, lookback_period=20):
    period = 14  # RSI period
    df["RSI"] = talib.RSI(df["close"].values, timeperiod=period)
    df["RSI"] = df["RSI"].round(2)
    bullish_divergence_detected = False
    checkpoint_close = df["close"].iloc[-3]
    checkpoint_rsi = df["RSI"].iloc[-3]
    second_last_close = df["close"].iloc[-2]
    second_last_open = df["open"].iloc[-2]
    detected_index = None
    confirm_vol = check_confirm_volume(df)

    if checkpoint_rsi <= threshold:
        # Find RSI value 20 bars ago
        if len(df) >= lookback_period:
            rsi_20_bars_ago = df["RSI"].iloc[-lookback_period - 2 : -2]
            close_20_bars_ago = df["close"].iloc[-lookback_period - 2 : -2]
        else:
            rsi_20_bars_ago = df["RSI"].iloc[0]
            close_20_bars_ago = df["close"].iloc[0]

        for i in range(len(rsi_20_bars_ago) - 1, 1, -1):
            if checkpoint_close < close_20_bars_ago.iloc[i]:
                if checkpoint_rsi > rsi_20_bars_ago.iloc[i]:
                    bullish_divergence_detected = True
                    detected_index = i
                    break

    if (
        (second_last_close > second_last_open)
        and confirm_vol
        and bullish_divergence_detected
    ):
        return True

    return False


def find_latest_rsi_bearish_divergence(df, threshold=75, lookback_period=20):
    period = 14  # RSI period
    df["RSI"] = talib.RSI(df["close"].values, timeperiod=period)
    df["RSI"] = df["RSI"].round(2)
    bearish_divergence_detected = False
    checkpoint_close = df["close"].iloc[-3]
    checkpoint_rsi = df["RSI"].iloc[-3]
    second_last_close = df["close"].iloc[-2]
    second_last_open = df["open"].iloc[-2]
    detected_index = None
    confirm_vol = check_confirm_volume(df)

    if checkpoint_rsi >= threshold:
        # Find RSI value 20 bars ago
        if len(df) >= lookback_period:
            rsi_20_bars_ago = df["RSI"].iloc[-lookback_period - 2 : -2]
            close_20_bars_ago = df["close"].iloc[-lookback_period - 2 : -2]
        else:
            rsi_20_bars_ago = df["RSI"].iloc[0]
            close_20_bars_ago = df["close"].iloc[0]

        for i in range(len(rsi_20_bars_ago) - 1, 1, -1):
            if checkpoint_close > close_20_bars_ago.iloc[i]:
                if checkpoint_rsi < rsi_20_bars_ago.iloc[i]:
                    bearish_divergence_detected = True
                    detected_index = i
                    break

    if (
        (second_last_close < second_last_open)
        and confirm_vol
        and bearish_divergence_detected
    ):
        return True
    return False


def cal_percent(entry, sl):
    return abs(round((entry - sl) / entry * 100, 2))


def et_sl_tp(df, option="long"):
    d = abs(decimal.Decimal(str(df["close"].iloc[-1])).as_tuple().exponent)
    if option == "short":
        stop_loss = round(df["high"].iloc[-2] * 1.01, d)
        entry = df["close"].iloc[-2]
        loss_percent = cal_percent(entry, stop_loss)
        upperband, middleband, lowerband = BBANDS(
            df["close"], timeperiod=20, nbdevup=2, nbdevdn=2, matype=0
        )
        # tp_1 = round(middleband.iloc[-1], d)
        # tp_2 = round(lowerband.iloc[-1], d)
        tp_1 = round(entry - (entry * 0.015), d)
        tp_2 = round(entry - (entry * 0.03), d)
        return entry, stop_loss, loss_percent, tp_1, tp_2
    elif option == "long":
        stop_loss = round(df["low"].iloc[-2] - (df["low"].iloc[-2] * 0.01), d)
        entry = df["close"].iloc[-2]
        loss_percent = cal_percent(entry, stop_loss)
        upperband, middleband, lowerband = BBANDS(
            df["close"], timeperiod=20, nbdevup=2, nbdevdn=2, matype=0
        )
        # tp_1 = round(middleband.iloc[-1], d)
        # tp_2 = round(upperband.iloc[-1], d)
        tp_1 = round(entry + (entry * 0.015), d)
        tp_2 = round(entry + (entry * 0.03), d)

        return entry, stop_loss, loss_percent, tp_1, tp_2


async def check_conditions_and_send_message(context: ContextTypes.DEFAULT_TYPE):
    print("Checking conditions...")
    job = context.job
    flag_bullish = True
    flag_bearish = True
    note = "\n\n_ __ LƯU Ý __: TP chỉ là tham khảo nếu có lời rồi thì chủ động, còn muốn gồng to thì phải xem chart và stl dương để an toàn\!\ _"
    try:
        tokens_to_check = get_all_future_pairs()
        # tokens_to_check = ["BTC_USDT"]
        for symbol in tokens_to_check:
            df_m15 = get_symbol_data(symbol)
            df_m5 = get_symbol_data(symbol, interval="Min5")

            bearish_divergence = find_latest_rsi_bearish_divergence(df_m15)
            bullish_divergence = find_latest_rsi_bullish_divergence(df_m15)

            if bearish_divergence:
                flag_bearish = False
                et, sl, lp, tp_1, tp_2 = et_sl_tp(df_m15, option="short")
                message = f"🔴 Tín hiệu short cho *{symbol}* \n RSI phân kỳ giảm trên khung M15 \n\n 🐳Entry: `{et}` \n\n 💀SL: `{sl}` \({lp}%\) \n\n ✨TP1: `{tp_1}` \(1,5%\) \n ✨TP2: `{tp_2}` \(3%\) \n ✨TP3: Tùy mồm"
                message = message.replace("_", "\\_").replace(".", "\\.")
                await context.bot.send_message(
                    CHAT_ID, text=message + note, parse_mode=ParseMode.MARKDOWN_V2
                )

            if bullish_divergence:
                flag_bullish = False
                et, sl, lp, tp_1, tp_2 = et_sl_tp(df_m15, option="long")
                message = f"🟢 Tín hiệu long cho *{symbol}* \n RSI phân kỳ giảm trên khung M15 \n\n 🐳Entry: `{et}` \n\n 💀SL: `{sl}` \({lp}%\) \n\n ✨TP1: `{tp_1}` \(1,5%\) \n ✨TP2: `{tp_2}` \(3%\) \n ✨TP3: Tùy mồm"
                message = message.replace("_", "\\_").replace(".", "\\.")
                await context.bot.send_message(
                    CHAT_ID, text=message + note, parse_mode=ParseMode.MARKDOWN_V2
                )
    except Exception as e:
        print(f"Error: {e} at {symbol}")
        message = f"Error: {e} at {symbol}"
        # await context.bot.send_message(CHAT_ID, text=message)

    # if flag_bullish and flag_bearish:
    #     message = f"Không có tín hiệu nào được tìm thấy!"
    #     await context.bot.send_message(CHAT_ID, text=message)


async def start_checking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Starting bot...")
    chat_id = update.effective_message.chat_id
    # chat_id = CHAT_ID
    try:
        job_removed = remove_job_if_exists(str(chat_id), context)
        if job_removed:
            text = "Previous checking is stopped!"
            await update.effective_message.reply_text(text)
        time_to_wait = time_to_next_15_minutes()
        if time_to_wait < 0:
            time_to_wait += 3600
        context.job_queue.run_repeating(
            check_conditions_and_send_message,
            interval=900,
            first=time_to_wait,
            chat_id=chat_id,
            name=str(chat_id),
        )

        text = "Checking conditions every hour..."
        await update.effective_message.reply_text(
            f"{text} Time to wait: {time_to_wait} seconds"
        )
    except (IndexError, ValueError):
        await update.effective_message.reply_text("Checking failed!")


def remove_job_if_exists(name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Remove job with given name. Returns whether job was removed."""
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


def time_to_next_15_minutes(current_time=None):
    if current_time is None:
        current_time = datetime.datetime.now()

    # Calculate the next 15-minute mark
    next_15_minute = current_time.replace(second=0, microsecond=0) + datetime.timedelta(
        minutes=(15 - current_time.minute % 15)
    )

    # If the current time is already past the next 15-minute mark, add 15 minutes
    if current_time >= next_15_minute:
        next_15_minute += datetime.timedelta(minutes=15)

    time_to_wait = (next_15_minute - current_time).total_seconds()
    return round(time_to_wait)


async def stop_checking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Stopping bot...")
    chat_id = update.effective_message.chat_id
    job_removed = remove_job_if_exists(str(chat_id), context)
    text = "Checking stopped!" if job_removed else "You have no active checking."
    await update.effective_message.reply_text(text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends explanation on how to use the bot."""
    await update.message.reply_text(
        "Hi! Use /start_checking to start checking conditions every 15 minute."
    )


def main() -> None:
    """Run bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler(["start", "help"], start))
    application.add_handler(CommandHandler("start_checking", start_checking))
    application.add_handler(CommandHandler("stop_checking", stop_checking))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
