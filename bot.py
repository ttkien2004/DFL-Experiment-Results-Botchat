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
        await update.message.reply_text("⚠️ Hãy dùng /set để chọn thư mục.")
        return

    folder_path = os.path.join(BASE_DATA_DIR, current)
    if not os.path.exists(folder_path):
        await update.message.reply_text(f"❌ Thư mục {current} không tồn tại.")
        return

    files = [f for f in os.listdir(folder_path) if f.endswith('.csv')]
    if not files:
        await update.message.reply_text("📂 Thư mục trống, không có file CSV nào.")
        return

    await update.message.reply_text(f"📊 Đang xử lý {len(files)} file dữ liệu...")

    CONV_THRESHOLD = 0.75  
    convergence_data = []
    
    # Khởi tạo Figure
    fig_acc, ax_acc = plt.subplots(figsize=(10, 6))
    fig_loss, ax_loss = plt.subplots(figsize=(10, 6))
    fig_asr, ax_asr = plt.subplots(figsize=(10, 6))
    
    has_loss = False
    has_asr = False
    data_list = [] 

    # --- BƯỚC 1: Đọc file thông minh (Smart Read) ---
    for file in files:
        file_path = os.path.join(folder_path, file)
        try:
            # Lớp 1: Tự động dò tìm engine python 
            try:
                df = pd.read_csv(file_path, sep=None, engine='python')
            except:
                df = pd.DataFrame() # Fallback

            # Lớp 2: Nếu đọc ra < 2 cột, thử ép buộc đọc bằng Tab hoặc Phẩy
            if len(df.columns) < 2:
                try:
                    df = pd.read_csv(file_path, sep='\t')
                except:
                    pass
            if len(df.columns) < 2:
                 try:
                    df = pd.read_csv(file_path, sep=',')
                 except:
                    pass

            # Chuẩn hóa tên cột: Xóa khoảng trắng & đưa về dạng chuẩn
            df.columns = df.columns.str.strip()
            
            # Map tên cột (xử lý case-insensitive: 'round' -> 'Round')
            col_map = {c.lower(): c for c in df.columns}
            if 'round' in col_map: df.rename(columns={col_map['round']: 'Round'}, inplace=True)
            if 'accuracy' in col_map: df.rename(columns={col_map['accuracy']: 'Accuracy'}, inplace=True)
            if 'loss' in col_map: df.rename(columns={col_map['loss']: 'Loss'}, inplace=True)
            if 'asr' in col_map: df.rename(columns={col_map['asr']: 'ASR'}, inplace=True)

            # Kiểm tra bắt buộc phải có Round và Accuracy
            if 'Round' not in df.columns or 'Accuracy' not in df.columns:
                print(f"⚠️ Bỏ qua {file}: Không tìm thấy cột Round/Accuracy. (Columns: {list(df.columns)})")
                continue

            # Ép kiểu dữ liệu về số (tránh lỗi nếu file chứa text lạ)
            df['Round'] = pd.to_numeric(df['Round'], errors='coerce')
            df['Accuracy'] = pd.to_numeric(df['Accuracy'], errors='coerce')
            df.dropna(subset=['Round', 'Accuracy'], inplace=True) # Xóa dòng lỗi

            # Lấy nhãn từ tên file
            raw_label = file.replace('.csv', '').split('-')[-1]
            data_list.append({'label': raw_label, 'df': df})
            
        except Exception as e:
            print(f"❌ Lỗi nghiêm trọng file {file}: {e}")

    if not data_list:
        await update.message.reply_text("❌ Không đọc được dữ liệu hợp lệ. Vui lòng kiểm tra file CSV.")
        return

    # --- BƯỚC 2: Sắp xếp (Sort) ---
    # Sắp xếp theo số (nếu nhãn là số) để biểu đồ 10, 20, 30 hiển thị đúng thứ tự
    def sort_key(item):
        val = item['label']
        return int(val) if val.isdigit() else val

    data_list.sort(key=sort_key)

    # --- BƯỚC 3: Vẽ biểu đồ ---
    for item in data_list:
        df = item['df']
        label = item['label']

        # 1. Vẽ Accuracy
        ax_acc.plot(df['Round'], df['Accuracy'], marker='o', markersize=4, label=f"Model: {label}")

        # 2. Vẽ Loss (Chỉ vẽ nếu cột tồn tại và có dữ liệu > 0)
        if 'Loss' in df.columns:
            # Chuyển về số và bỏ NaN
            loss_clean = pd.to_numeric(df['Loss'], errors='coerce').dropna()
            if not loss_clean.empty:
                has_loss = True
                # Vẽ dựa trên index của loss_clean để khớp với Round tương ứng
                valid_rounds = df.loc[loss_clean.index, 'Round']
                ax_loss.plot(valid_rounds, loss_clean, linestyle='--', label=f"Loss: {label}")

        # 3. Vẽ ASR (Attack)
        if 'ASR' in df.columns:
            asr_clean = pd.to_numeric(df['ASR'], errors='coerce').fillna(0)
            if asr_clean.max() > 0: 
                has_asr = True
                ax_asr.plot(df['Round'], asr_clean, marker='s', linestyle='-.', label=f"ASR: {label}")

        # 4. Tính Convergence
        reached = df[df['Accuracy'] >= CONV_THRESHOLD]
        if not reached.empty:
            convergence_data.append((str(label), reached['Round'].min()))
        else:
            convergence_data.append((str(label), df['Round'].max()))

    # --- BƯỚC 4: Xuất ảnh và Gửi ---
    output_files = []

    # Lưu Acc
    ax_acc.set_title(f"Accuracy Comparison - {current}")
    ax_acc.set_xlabel("Rounds"); ax_acc.set_ylabel("Accuracy")
    ax_acc.legend(); ax_acc.grid(True)
    p_acc = f"acc_{current}.png"; fig_acc.savefig(p_acc); output_files.append(p_acc)

    # Lưu Loss
    if has_loss:
        ax_loss.set_title(f"Model Stability (Loss) - {current}")
        ax_loss.set_xlabel("Rounds"); ax_loss.set_ylabel("Loss")
        ax_loss.legend(); ax_loss.grid(True)
        p_loss = f"loss_{current}.png"; fig_loss.savefig(p_loss); output_files.append(p_loss)

    # Lưu ASR
    if has_asr:
        ax_asr.set_title(f"Attack Success Rate (ASR) - {current}")
        ax_asr.set_xlabel("Rounds"); ax_asr.set_ylabel("ASR")
        ax_asr.legend(); ax_asr.grid(True)
        p_asr = f"asr_{current}.png"; fig_asr.savefig(p_asr); output_files.append(p_asr)

    # Lưu Bar Chart
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

    # Gửi tất cả
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







