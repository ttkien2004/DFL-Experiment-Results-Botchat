import os
import pandas as pd
import matplotlib.pyplot as plt
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import shutil

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
# BIẾN DÙNG CHUNG CHO TẤT CẢ USER
shared_context = {"current_folder": None}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = shared_context['current_folder'] or "Chưa chọn"
    await update.message.reply_text(
        f"👥 **Chế độ dùng chung (Shared Mode)**\n"
        f"📂 Thư mục hiện tại: `{status}`\n\n"
        "/list - Xem tất cả kịch bản đang có\n"
        "/create <tên> - Tạo kịch bản mới\n"
        "/set <tên> - Chọn kịch bản (áp dụng cho mọi người)\n"
        "/export - Vẽ biểu đồ dữ liệu chung\n"
        "/delete - Xóa dữ liệu trong kịch bản hiện tại"
    )

# Xem danh sách các kịch bản đang có
async def list_folders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    folders = [d for d in os.listdir(BASE_DATA_DIR) if os.path.isdir(os.path.join(BASE_DATA_DIR, d))]
    if not folders:
        await update.message.reply_text("Chưa có kịch bản nào được tạo.")
    else:
        text = "📂 **Danh sách kịch bản:**\n" + "\n".join([f"- `{f}`" for f in folders])
        await update.message.reply_text(text)

async def create_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    for folder_name in context.args:
        path = os.path.join(BASE_DATA_DIR, folder_name)
        if not os.path.exists(path):
            os.makedirs(path)
            await update.message.reply_text(f"✅ Đã tạo: {folder_name}")

async def set_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    folder_name = context.args[0]
    if os.path.exists(os.path.join(BASE_DATA_DIR, folder_name)):
        shared_context["current_folder"] = folder_name
        await update.message.reply_text(f"📢 Đã chuyển sang kịch bản: `{folder_name}`\n(Mọi file upload bây giờ sẽ vào đây)")
    else:
        await update.message.reply_text("❌ Không tìm thấy thư mục.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = shared_context["current_folder"]
    if not current:
        await update.message.reply_text("⚠️ Hãy dùng /set để chọn thư mục trước.")
        return
    
    file = await update.message.document.get_file()
    file_name = update.message.document.file_name
    if file_name.endswith('.csv'):
        path = os.path.join(BASE_DATA_DIR, current, file_name)
        await file.download_to_drive(path)
        user_name = update.effective_user.first_name
        await update.message.reply_text(f"📥 {user_name} đã upload: `{file_name}` vào `{current}`")

# Xuất biểu đồ tách riêng
async def export_charts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = shared_context["current_folder"]
    if not current:
        await update.message.reply_text("⚠️ Hãy dùng /set để chọn thư mục dữ liệu trước.")
        return

    folder_path = os.path.join(BASE_DATA_DIR, current)
    files = [f for f in os.listdir(folder_path) if f.endswith('.csv')]
    
    if not files:
        await update.message.reply_text(f"Thư mục `{current}` không có dữ liệu.")
        return

    await update.message.reply_text("📊 Đang phân tích dữ liệu kịch bản hỗn hợp...")

    CONV_THRESHOLD = 0.75  # Ngưỡng tính tốc độ hội tụ
    convergence_data = []
    
    # Khởi tạo 4 khung hình (Figure) cho tất cả các kịch bản có thể xảy ra
    fig_acc, ax_acc = plt.subplots(figsize=(10, 6))
    fig_loss, ax_loss = plt.subplots(figsize=(10, 6))
    fig_asr, ax_asr = plt.subplots(figsize=(10, 6))
    
    has_loss = False
    has_asr = False
    data_list = []

    # 1. Đọc và phân loại dữ liệu
    for file in files:
        try:
            # Tự động nhận diện dấu phẩy hoặc Tab
            df = pd.read_csv(os.path.join(folder_path, file), sep=None, engine='python')
            # Lấy phần định danh cuối cùng (ví dụ: ubar, fedavg hoặc 30, 50, 70)
            raw_label = file.replace('.csv', '').split('-')[-1]
            data_list.append({'label': raw_label, 'df': df})
        except Exception as e:
            print(f"Lỗi đọc file {file}: {e}")

    # Sắp xếp nhãn để biểu đồ bar chart và đường vẽ được đẹp (ưu tiên số nếu là kịch bản node)
    data_list.sort(key=lambda x: int(x['label']) if x['label'].isdigit() else 0)

    # 2. Vẽ biểu đồ dựa trên các cột dữ liệu hiện có
    for item in data_list:
        df = item['df']
        label = item['label']

        # Luôn vẽ Accuracy
        ax_acc.plot(df['Round'], df['Accuracy'], marker='o', markersize=4, label=f"Model: {label}")

        # Vẽ Loss nếu có (Kịch bản Stability/Normal)
        if 'Loss' in df.columns and not df['Loss'].dropna().empty:
            has_loss = True
            ax_loss.plot(df['Round'], df['Loss'], label=f"Loss: {label}")

        # Vẽ ASR nếu có (Kịch bản Tấn công)
        if 'ASR' in df.columns and not df['ASR'].dropna().empty:
            if df['ASR'].sum() > 0: # Chỉ vẽ nếu có dữ liệu tấn công thực tế
                has_asr = True
                ax_asr.plot(df['Round'], df['ASR'], marker='s', linestyle='--', label=f"ASR: {label}")

        # Tính tốc độ hội tụ cho Bar Chart
        reached = df[df['Accuracy'] >= CONV_THRESHOLD]
        if not reached.empty:
            convergence_data.append((label, reached['Round'].min()))
        else:
            convergence_data.append((label, df['Round'].max()))

    # 3. Xử lý lưu và gửi ảnh
    output_files = []

    # Lưu Accuracy (Bắt buộc)
    ax_acc.set_title(f"Accuracy Comparison - {current}")
    ax_acc.set_xlabel("Rounds"); ax_acc.set_ylabel("Accuracy")
    ax_acc.legend(); ax_acc.grid(True)
    p_acc = f"acc_{current}.png"; fig_acc.savefig(p_acc); output_files.append(p_acc)

    # Lưu Loss (Nếu có)
    if has_loss:
        ax_loss.set_title(f"Model Stability (Loss) - {current}")
        ax_loss.set_xlabel("Rounds"); ax_loss.set_ylabel("Loss")
        ax_loss.legend(); ax_loss.grid(True)
        p_loss = f"loss_{current}.png"; fig_loss.savefig(p_loss); output_files.append(p_loss)

    # Lưu ASR (Nếu có - Kịch bản tấn công)
    if has_asr:
        ax_asr.set_title(f"Attack Success Rate (ASR) - {current}")
        ax_asr.set_xlabel("Rounds"); ax_asr.set_ylabel("ASR")
        ax_asr.legend(); ax_asr.grid(True)
        p_asr = f"asr_{current}.png"; fig_asr.savefig(p_asr); output_files.append(p_asr)

    # Lưu Convergence Speed Bar Chart (Bắt buộc cho kịch bản nhiều Nodes/Rounds)
    if convergence_data:
        fig_bar, ax_bar = plt.subplots(figsize=(10, 6))
        labels, rounds = zip(*convergence_data)
        bars = ax_bar.bar(labels, rounds, color='teal')
        ax_bar.set_title(f"Convergence Speed (Rounds to {CONV_THRESHOLD*100}%)")
        ax_bar.set_ylabel("Rounds"); ax_bar.set_xlabel("Scenario")
        for bar in bars:
            ax_bar.annotate(f'{bar.get_height()}', xy=(bar.get_x() + bar.get_width()/2, bar.get_height()),
                            xytext=(0, 3), textcoords="offset points", ha='center')
        p_conv = f"conv_{current}.png"; fig_bar.savefig(p_conv); output_files.append(p_conv)

    # 4. Gửi ảnh và dọn dẹp
    for p in output_files:
        with open(p, 'rb') as f:
            await update.message.reply_photo(f)
        if os.path.exists(p): os.remove(p)

    plt.close('all')

# Thêm Handler delete như yêu cầu cũ nhưng áp dụng cho shared_context
async def delete_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = shared_context["current_folder"]
    if context.args and context.args[0] == "all":
        shutil.rmtree(BASE_DATA_DIR)
        os.makedirs(BASE_DATA_DIR)
        shared_context["current_folder"] = None
        await update.message.reply_text("💥 Toàn bộ hệ thống đã bị xóa sạch.")
    elif current:
        path = os.path.join(BASE_DATA_DIR, current)
        for f in os.listdir(path): os.remove(os.path.join(path, f))
        await update.message.reply_text(f"🗑️ Đã xóa sạch dữ liệu trong `{current}`")

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
    app_bot.add_handler(CommandHandler("delete", delete_data))
    app_bot.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    print("Flask và Bot đang chạy đồng thời...")
    app_bot.run_polling()




