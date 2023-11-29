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
# TOKEN = "6649758324:AAGNvtZ6e4CTaEPwACa9o3IzUcXzmN7zZz0"  # test bot
BASE_URL = "https://contract.mexc.com/api/v1"
INTERVAL = "Min60"
CHAT_ID = "-1001883104059"  # nhóm rsi phân kỳ
# CHAT_ID = "-1001862379259"  # test group
# CHAT_ID = "-1002127588410"  # nhóm private
MINUTES = [50]
TRACKING_INTERVAL = 3600
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


def cal_percent(entry, sl):
    return abs(round((entry - sl) / entry * 100, 2))


# NOTE: Cao hơn 10% so với MA 20
def check_confirm_volume(df, threshold=1.1):
    latest_volume = df["vol"].iloc[-1]
    ma_20_vol = talib.MA(df["vol"].values, timeperiod=20)
    if latest_volume > (ma_20_vol[-1] * threshold):
        return True
    else:
        return False


def find_latest_rsi_bullish_divergence(df, threshold=25, lookback_period=20):
    period = 14  # RSI period
    df["RSI"] = talib.RSI(df["close"].values, timeperiod=period)
    df["RSI"] = df["RSI"].round(2)
    bullish_divergence_detected = False
    checkpoint_close = df["close"].iloc[-2]
    checkpoint_rsi = df["RSI"].iloc[-2]
    second_last_close = df["close"].iloc[-1]
    second_last_open = df["open"].iloc[-1]
    detected_index = None
    confirm_vol = check_confirm_volume(df)

    if checkpoint_rsi <= threshold:
        # Find RSI value 20 bars ago
        if len(df) >= lookback_period:
            rsi_20_bars_ago = df["RSI"].iloc[-lookback_period - 2 : -1]
            close_20_bars_ago = df["close"].iloc[-lookback_period - 2 : -1]
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
    checkpoint_close = df["close"].iloc[-2]
    checkpoint_rsi = df["RSI"].iloc[-2]
    second_last_close = df["close"].iloc[-1]
    second_last_open = df["open"].iloc[-1]
    detected_index = None
    confirm_vol = check_confirm_volume(df)

    if checkpoint_rsi >= threshold:
        # Find RSI value 20 bars ago
        if len(df) >= lookback_period:
            rsi_20_bars_ago = df["RSI"].iloc[-lookback_period - 2 : -1]
            close_20_bars_ago = df["close"].iloc[-lookback_period - 2 : -1]
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


def find_signal_rsi(df, type="bullish"):
    period = 14  # RSI period
    df["RSI"] = talib.RSI(df["close"].values, timeperiod=period)
    df["RSI"] = df["RSI"].round(2)
    lasted_close = df["close"].iloc[-1]
    lasted_open = df["open"].iloc[-1]
    checkpoint_rsi = df["RSI"].iloc[-1]
    confirm_vol = check_confirm_volume(df)

    if checkpoint_rsi > 0:
        if type == "bullish":
            if (
                checkpoint_rsi <= 30
                and confirm_vol
                and lasted_close > lasted_open * 1.01
            ):
                return True

        elif type == "bearish":
            if (
                checkpoint_rsi >= 70
                and confirm_vol
                and lasted_close < lasted_open * 0.99
            ):
                return True

    return False


def find_signal_ema(df, type="bullish"):
    df["EMA34"] = talib.EMA(df["close"].values, timeperiod=34)
    df["EMA34"] = df["EMA34"].round(2)

    df["EMA89"] = talib.EMA(df["close"].values, timeperiod=89)
    df["EMA89"] = df["EMA89"].round(2)

    df["EMA200"] = talib.EMA(df["close"].values, timeperiod=200)
    df["EMA200"] = df["EMA200"].round(2)

    lasted_close = df["close"].iloc[-1]  # giá hiện tại
    lasted_low = df["low"].iloc[-1]  # giá thấp nhất
    lasted_high = df["high"].iloc[-1]  # giá cao nhất

    checkpoint_ema89 = df["EMA89"].iloc[-1]  # giá EMA89 hiện tại
    checkpoint_ema200 = df["EMA200"].iloc[-1]  # giá EMA200 hiện tại
    checkpoint_ema34 = df["EMA34"].iloc[-1]  # giá EMA34 hiện tại

    list_ema = [34, 89, 200]

    for ema in list_ema:
        if ema == 34:
            checkpoint_ema = checkpoint_ema34

        elif ema == 89:
            checkpoint_ema = checkpoint_ema89

        elif ema == 200:
            checkpoint_ema = checkpoint_ema200

        confirm_vol = check_confirm_volume(df)

        if type == "bullish":
            if (
                lasted_close
                > checkpoint_ema
                # and lasted_close > checkpoint_ema89
                # and lasted_close > checkpoint_ema200
            ):
                if lasted_low > checkpoint_ema:
                    if cal_percent(lasted_low, checkpoint_ema) <= 0.05:
                        return True, ema
                else:
                    return True, ema
        elif type == "bearish":
            if (
                lasted_close
                < checkpoint_ema
                # and lasted_close < checkpoint_ema89
                # and lasted_close < checkpoint_ema200
                # giá cao nhất cách EMA34 không quá 0.05%
            ):
                if lasted_high < checkpoint_ema:
                    if cal_percent(lasted_high, checkpoint_ema) <= 0.05:
                        return True, ema
                else:
                    return True, ema

    return False, 1


def et_sl_tp(df, option="long"):
    d = abs(decimal.Decimal(str(df["close"].iloc[-1])).as_tuple().exponent)
    if option == "short":
        stop_loss = round(df["high"].iloc[-1] * 1.01, d)
        entry = df["close"].iloc[-1]
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
        stop_loss = round(df["low"].iloc[-1] - (df["low"].iloc[-1] * 0.01), d)
        entry = df["close"].iloc[-1]
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
    note = "\n\n⚠⚠⚠\n_ __ LƯU Ý __:\n \-\ TP chỉ là tham khảo nếu có lời rồi thì chủ động, còn muốn gồng to thì phải xem chart và stl dương để an toàn\!\ \n \-\ Có thể vào hoặc không vào nếu thấy chart không đẹp hoặc xu hướng không ủng hộ _"
    try:
        tokens_to_check = get_all_future_pairs()
        # tokens_to_check = ["BTC_USDT"]
        for symbol in tokens_to_check:
            df_m15 = get_symbol_data(symbol, interval=INTERVAL)
            # df_m5 = get_symbol_data(symbol, interval="Min5")

            # !NOTE: RSI DIVERGENCE
            bearish_divergence = find_latest_rsi_bearish_divergence(df_m15)
            bullish_divergence = find_latest_rsi_bullish_divergence(df_m15)

            # !NOTE: Confirm Volume when RSI < 25 or RSI > 75
            signal_bullish_rsi = find_signal_rsi(df_m15, type="bullish")
            signal_bearish_rsi = find_signal_rsi(df_m15, type="bearish")

            # !NOTE: Price test trend line EMA 34, 89, 200
            # signal_bullish_ema, ema_long = find_signal_ema(df_m15, type="bullish")
            # signal_bearish_ema, ema_short = find_signal_ema(df_m15, type="bearish")

            if bearish_divergence:
                flag_bearish = False
                et, sl, lp, tp_1, tp_2 = et_sl_tp(df_m15, option="short")
                if lp < 5:
                    message = f"🔴 Tín hiệu short cho *{symbol}* \n RSI phân kỳ giảm trên khung {INTERVAL} \n\n 🐳Entry *tham khảo:* `{et}` \n\n 💀SL khi có bất kì cây nến nào *đóng qua:* `{sl}` \({lp}%\) \n\n ✨TP: Tùy mồm"
                    message = message.replace("_", "\\_").replace(".", "\\.")
                    await context.bot.send_message(
                        CHAT_ID, text=message + note, parse_mode=ParseMode.MARKDOWN_V2
                    )

            elif bullish_divergence:
                flag_bullish = False
                et, sl, lp, tp_1, tp_2 = et_sl_tp(df_m15, option="long")
                if lp < 5:
                    message = f"🟢 Tín hiệu long cho *{symbol}* \n RSI phân kỳ giảm trên khung {INTERVAL} \n\n 🐳Entry *tham khảo:* `{et}` \n\n 💀SL khi có bất kì cây nến nào *đóng qua:* `{sl}` \({lp}%\) \n\n ✨TP: Tùy mồm"
                    message = message.replace("_", "\\_").replace(".", "\\.")
                    await context.bot.send_message(
                        CHAT_ID, text=message + note, parse_mode=ParseMode.MARKDOWN_V2
                    )
            elif signal_bullish_rsi:
                flag_bullish = False
                et, sl, lp, tp_1, tp_2 = et_sl_tp(df_m15, option="long")
                if lp < 5:
                    message = f"🟢 Tín hiệu long cho *{symbol}* \n Có Volume mua mạnh khi RSI dưới 25 trên khung {INTERVAL} \n\n 🐳Entry *tham khảo:* `{et}` \n\n 💀SL khi có bất kì cây nến nào *đóng qua:* `{sl}` \({lp}%\) \n\n ✨TP: Tùy mồm"
                    message = message.replace("_", "\\_").replace(".", "\\.")
                    await context.bot.send_message(
                        CHAT_ID, text=message + note, parse_mode=ParseMode.MARKDOWN_V2
                    )
            elif signal_bearish_rsi:
                flag_bearish = False
                et, sl, lp, tp_1, tp_2 = et_sl_tp(df_m15, option="short")
                if lp < 5:
                    message = f"🔴 Tín hiệu short cho *{symbol}* \n Có Volume bán mạnh RSI trên 75 trên khung {INTERVAL} \n\n 🐳Entry *tham khảo:* `{et}` \n\n 💀SL khi có bất kì cây nến nào *đóng qua:* `{sl}` \({lp}%\) \n\n ✨TP: Tùy mồm"
                    message = message.replace("_", "\\_").replace(".", "\\.")
                    await context.bot.send_message(
                        CHAT_ID, text=message + note, parse_mode=ParseMode.MARKDOWN_V2
                    )
            # elif signal_bullish_ema:
            #     flag_bullish = False
            #     et, sl, lp, tp_1, tp_2 = et_sl_tp(df_m15, option="long")
            #     if lp < 5:
            #         message = f"🟢 Tín hiệu long cho *{symbol}* \n Giá đang test EMA{ema_long} trên khung {INTERVAL} \n\n 🐳Entry *tham khảo:* `{et}` \n\n 💀SL khi có bất kì cây nến nào *đóng qua:* `{sl}` \({lp}%\) \n\n ✨TP: Tùy mồm"
            #         message = message.replace("_", "\\_").replace(".", "\\.")
            #         await context.bot.send_message(
            #             CHAT_ID, text=message + note, parse_mode=ParseMode.MARKDOWN_V2
            #         )
            # elif signal_bearish_ema:
            #     flag_bearish = False
            #     et, sl, lp, tp_1, tp_2 = et_sl_tp(df_m15, option="short")
            #     if lp < 5:
            #         message = f"🔴 Tín hiệu short cho *{symbol}* \n Giá đang test EMA{ema_short} trên khung {INTERVAL} \n\n 🐳Entry *tham khảo:* `{et}` \n\n 💀SL khi có bất kì cây nến nào *đóng qua:* `{sl}` \({lp}%\) \n\n ✨TP: Tùy mồm"
            #         message = message.replace("_", "\\_").replace(".", "\\.")
            #         await context.bot.send_message(
            #             CHAT_ID, text=message + note, parse_mode=ParseMode.MARKDOWN_V2
            #         )
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
        time_to_wait = time_to_next_custom_minutes(minutes=MINUTES)
        if time_to_wait < 0:
            time_to_wait += 3600
        context.job_queue.run_repeating(
            check_conditions_and_send_message,
            interval=TRACKING_INTERVAL,  # 60 minutes
            first=time_to_wait,
            chat_id=chat_id,
            name=str(chat_id),
        )

        text = "Checking conditions every hour..."
        await update.effective_message.reply_text(
            f"{text} Time to wait: {time_to_wait} seconds"
        )
    except Exception as e:
        await update.effective_message.reply_text(f"Checking failed! {e}")


def remove_job_if_exists(name: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Remove job with given name. Returns whether job was removed."""
    current_jobs = context.job_queue.get_jobs_by_name(name)
    if not current_jobs:
        return False
    for job in current_jobs:
        job.schedule_removal()
    return True


def time_to_next_custom_minutes(current_time=None, minutes=[50]):
    if current_time is None:
        current_time = datetime.datetime.now()

    # Find the next occurrence of the specified minutes
    next_occurrence = min(
        (m for m in minutes if m > current_time.minute), default=minutes[0]
    )
    next_time = current_time.replace(second=0, microsecond=0, minute=next_occurrence)

    # If the next time is in the past, move to the next hour
    if current_time >= next_time:
        next_time = next_time.replace(hour=current_time.hour + 1, minute=minutes[0])

    time_to_wait = (next_time - current_time).total_seconds()
    return round(time_to_wait)


# def time_to_next_15_minutes(current_time=None):
#     if current_time is None:
#         current_time = datetime.datetime.now()

#     # Calculate the next 15-minute mark
#     next_15_minute = current_time.replace(second=0, microsecond=0) + datetime.timedelta(
#         minutes=(15 - current_time.minute % 15)
#     )

#     # If the current time is already past the next 15-minute mark, add 15 minutes
#     if current_time >= next_15_minute:
#         next_15_minute += datetime.timedelta(minutes=15)

#     time_to_wait = (next_15_minute - current_time).total_seconds()
#     return round(time_to_wait)


async def stop_checking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Stopping bot...")
    chat_id = update.effective_message.chat_id
    job_removed = remove_job_if_exists(str(chat_id), context)
    text = "Checking stopped!" if job_removed else "You have no active checking."
    await update.effective_message.reply_text(text)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message with three inline buttons attached."""
    keyboard = [
        [
            InlineKeyboardButton("M15", callback_data="15"),
            InlineKeyboardButton("H1", callback_data="1"),
            # InlineKeyboardButton("H4", callback_data="4"),
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Chọn khung thời gian để theo dõi", reply_markup=reply_markup
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Parses the CallbackQuery and updates the message text."""
    query = update.callback_query
    global INTERVAL
    global MINUTES
    global TRACKING_INTERVAL
    await query.answer()
    if query.data == "15":
        INTERVAL = "Min15"
        MINUTES = [12, 27, 42, 57]
        TRACKING_INTERVAL = 900
        await query.edit_message_text(text=f"Đã chọn khung theo dõi M15")
    elif query.data == "1":
        INTERVAL = "Min60"
        MINUTES = [50]
        TRACKING_INTERVAL = 3600
        await query.edit_message_text(text=f"Đã chọn khung theo dõi H1")
    elif query.data == "4":
        INTERVAL = "Hour4"
        MINUTES = [50]
        TRACKING_INTERVAL = 14400
        await query.edit_message_text(text=f"Đã chọn khung theo dõi H4")


def main() -> None:
    """Run bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler(["start", "help"], start))
    application.add_handler(CommandHandler("start_checking", start_checking))
    application.add_handler(CommandHandler("stop_checking", stop_checking))
    application.add_handler(CallbackQueryHandler(button))
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
