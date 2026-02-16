from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "YOUR_TOKEN"

# Lệnh /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Xin chào! Gõ /square <số> để tính bình phương.")

# Lệnh /square
async def square(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        number = int(context.args[0])
        result = number ** 2
        await update.message.reply_text(f"Bình phương của {number} là {result}")
    except:
        await update.message.reply_text("Vui lòng nhập số hợp lệ. Ví dụ: /square 5")

# Main
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("square", square))

print("Bot đang chạy...")
app.run_polling()
