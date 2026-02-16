import os
import pandas as pd
import matplotlib.pyplot as plt
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Cấu hình Telegram Bot ---
TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))
BASE_DATA_DIR = "experiments"

# --- Cấu hình Flask ---
app_flask = Flask(__name__)

@app_flask.route('/')
def index():
    return "Bot DFL Monitoring is Running!"

def run_flask():
    # Chạy Flask ở port 8080 hoặc tùy chọn
    app_flask.run(host='0.0.0.0', port=PORT)

if not os.path.exists(BASE_DATA_DIR):
    os.makedirs(BASE_DATA_DIR)

# Biến để theo dõi thư mục hiện tại người dùng đang làm việc (mặc định)
user_context = {} 

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot DFL đa kịch bản đã sẵn sàng!\n\n"
        "1. /create <tên_thư_mục>: Tạo kịch bản mới (vd: /create label_flipping)\n"
        "2. /set <tên_thư_mục>: Chọn thư mục để upload file\n"
        "3. Gửi file .csv để lưu vào thư mục đã chọn\n"
        "4. /export: Xuất biểu đồ từ thư mục hiện tại"
    )

# Lệnh tạo thư mục kịch bản
async def create_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Vui lòng nhập tên thư mục. Ví dụ: /create label_flipping")
        return
    
    for folder_name in context.args:
        path = os.path.join(BASE_DATA_DIR, folder_name)
        if not os.path.exists(path):
            os.makedirs(path)
            await update.message.reply_text(f"✅ Đã tạo thư mục: {folder_name}")
        else:
            await update.message.reply_text(f"ℹ️ Thư mục {folder_name} đã tồn tại.")

# Lệnh chọn thư mục làm việc
async def set_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Vui lòng nhập tên thư mục đã tạo.")
        return
    
    folder_name = context.args[0]
    path = os.path.join(BASE_DATA_DIR, folder_name)
    
    if os.path.exists(path):
        user_context[update.effective_user.id] = folder_name
        await update.message.reply_text(f"📂 Đang làm việc tại: {folder_name}")
    else:
        await update.message.reply_text(f"❌ Thư mục {folder_name} không tồn tại. Hãy dùng /create trước.")

# Xử lý nhận file CSV
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_context:
        await update.message.reply_text("⚠️ Vui lòng dùng lệnh /set <tên_thư_mục> trước khi gửi file.")
        return

    file = await update.message.document.get_file()
    file_name = update.message.document.file_name
    current_folder = user_context[user_id]
    
    if file_name.endswith('.csv'):
        file_path = os.path.join(BASE_DATA_DIR, current_folder, file_name)
        await file.download_to_drive(file_path)
        await update.message.reply_text(f"📥 Đã lưu {file_name} vào thư mục {current_folder}")
    else:
        await update.message.reply_text("❌ Chỉ chấp nhận file .csv")

# Xuất biểu đồ tách riêng
async def export_charts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_context:
        await update.message.reply_text("⚠️ Hãy dùng /set để chọn thư mục dữ liệu.")
        return

    current_folder = user_context[user_id]
    folder_path = os.path.join(BASE_DATA_DIR, current_folder)
    files = [f for f in os.listdir(folder_path) if f.endswith('.csv')]
    
    if not files:
        await update.message.reply_text(f"Thư mục {current_folder} không có dữ liệu CSV.")
        return

    # Tạo figure riêng cho Accuracy và ASR
    fig_acc, ax_acc = plt.subplots(figsize=(10, 6))
    fig_asr, ax_asr = plt.subplots(figsize=(10, 6))

    for file in files:
        df = pd.read_csv(os.path.join(folder_path, file))
        # Lấy tên thuật toán từ phần cuối tên file để làm nhãn
        label_name = file.replace('.csv', '').split('-')[-1]

        ax_acc.plot(df['Round'], df['Accuracy'], marker='o', label=f"Acc: {label_name}")
        if 'ASR' in df.columns:
            ax_asr.plot(df['Round'], df['ASR'], marker='s', linestyle='--', label=f"ASR: {label_name}")

    # Cấu hình biểu đồ Accuracy
    ax_acc.set_title(f"Accuracy Comparison - {current_folder}")
    ax_acc.set_xlabel("Rounds")
    ax_acc.set_ylabel("Accuracy")
    ax_acc.legend()
    ax_acc.grid(True)
    acc_path = f"acc_{current_folder}.png"
    fig_acc.savefig(acc_path)

    # Cấu hình biểu đồ ASR
    ax_asr.set_title(f"Attack Success Rate - {current_folder}")
    ax_asr.set_xlabel("Rounds")
    ax_asr.set_ylabel("ASR")
    ax_asr.legend()
    ax_asr.grid(True)
    asr_path = f"asr_{current_folder}.png"
    fig_asr.savefig(asr_path)

    # Gửi 2 ảnh riêng biệt
    with open(acc_path, 'rb') as f1, open(asr_path, 'rb') as f2:
        await update.message.reply_photo(f1, caption=f"Biểu đồ Accuracy kịch bản: {current_folder}")
        await update.message.reply_photo(f2, caption=f"Biểu đồ ASR kịch bản: {current_folder}")

    plt.close(fig_acc)
    plt.close(fig_asr)

if __name__ == '__main__':
    # 1. Chạy Flask trong một thread riêng để không chặn Bot
    threading.Thread(target=run_flask, daemon=True).start()

    # 2. Khởi chạy Telegram Bot
    app_bot = ApplicationBuilder().token(TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("create", create_folder))
    app_bot.add_handler(CommandHandler("set", set_folder))
    app_bot.add_handler(CommandHandler("export", export_charts))
    app_bot.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    print("Flask và Bot đang chạy đồng thời...")
    app_bot.run_polling()
