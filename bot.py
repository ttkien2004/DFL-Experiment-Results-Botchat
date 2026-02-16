import os
import pandas as pd
import matplotlib.pyplot as plt
import threading
import shutil
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- CẤU HÌNH ---
TOKEN = os.getenv("BOT_TOKEN") 
PORT = int(os.environ.get("PORT", 10000))
BASE_DATA_DIR = "experiments"

# --- FLASK SERVER ---
app_flask = Flask(__name__)
@app_flask.route('/')
def index(): return "Bot DFL Multi-User is Running!"
def run_flask(): app_flask.run(host='0.0.0.0', port=PORT)

if not os.path.exists(BASE_DATA_DIR): os.makedirs(BASE_DATA_DIR)

# --- QUẢN LÝ TRẠNG THÁI RIÊNG TỪNG USER ---
# Key: User_ID, Value: Tên thư mục người đó đang chọn
user_sessions = {} 

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current = user_sessions.get(user_id, "Chưa chọn")
    
    await update.message.reply_text(
        f"🤖 **Bot DFL (Multi-Session Mode)**\n"
        f"👤 Bạn đang làm việc tại: `{current}`\n\n"
        "📜 **Lệnh:**\n"
        "/list - Xem danh sách folder chung\n"
        "/create <tên> - Tạo folder mới\n"
        "/set <tên> - Vào folder để làm việc\n"
        "/export - Vẽ biểu đồ\n"
        "/delete - Xóa folder hiện tại"
    )

async def list_folders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    folders = [d for d in os.listdir(BASE_DATA_DIR) if os.path.isdir(os.path.join(BASE_DATA_DIR, d))]
    if not folders:
        await update.message.reply_text("📂 Hệ thống chưa có kịch bản nào.")
    else:
        text = "📂 **Kho dữ liệu chung:**\n" + "\n".join([f"- `{f}`" for f in folders])
        await update.message.reply_text(text)

async def create_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Nhập tên folder. Vd: /create kich_ban_A")
        return
    for folder_name in context.args:
        path = os.path.join(BASE_DATA_DIR, folder_name)
        if not os.path.exists(path):
            os.makedirs(path)
            await update.message.reply_text(f"✅ Đã tạo: `{folder_name}`")
        else:
            await update.message.reply_text(f"ℹ️ `{folder_name}` đã tồn tại.")

async def set_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Nhập tên folder cần vào. Vd: /set kich_ban_A")
        return
    
    folder_name = context.args[0]
    path = os.path.join(BASE_DATA_DIR, folder_name)
    user_id = update.effective_user.id
    
    if os.path.exists(path):
        user_sessions[user_id] = folder_name # Chỉ lưu cho user này
        await update.message.reply_text(f"📂 Bạn đã chuyển sang: `{folder_name}`\n(Người khác sẽ không bị ảnh hưởng)")
    else:
        await update.message.reply_text(f"❌ Không tìm thấy `{folder_name}`. Dùng /list để xem.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current = user_sessions.get(user_id)
    
    if not current:
        await update.message.reply_text("⚠️ Bạn chưa chọn folder. Dùng /set <tên> trước.")
        return
    
    file = await update.message.document.get_file()
    file_name = update.message.document.file_name
    
    if file_name.endswith('.csv'):
        save_path = os.path.join(BASE_DATA_DIR, current, file_name)
        await file.download_to_drive(save_path)
        await update.message.reply_text(f"📥 Đã lưu `{file_name}` vào `{current}`")
    else:
        await update.message.reply_text("❌ Chỉ nhận file .csv")

async def delete_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current = user_sessions.get(user_id)
    
    # Xóa toàn bộ hệ thống (Cần thận trọng)
    if context.args and context.args[0] == "all":
        shutil.rmtree(BASE_DATA_DIR)
        os.makedirs(BASE_DATA_DIR)
        user_sessions.clear()
        await update.message.reply_text("💥 Đã xóa sạch toàn bộ hệ thống.")
        return

    if current:
        path = os.path.join(BASE_DATA_DIR, current)
        for f in os.listdir(path):
            fp = os.path.join(path, f)
            if os.path.isfile(fp): os.remove(fp)
        await update.message.reply_text(f"🗑️ Đã dọn sạch folder `{current}`")
    else:
        await update.message.reply_text("⚠️ Chưa chọn folder nào để xóa.")

async def export_charts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Lấy folder của RIÊNG user đang gọi lệnh
    user_id = update.effective_user.id
    current = user_sessions.get(user_id)
    
    if not current:
        await update.message.reply_text("⚠️ Hãy dùng /set để chọn kịch bản trước.")
        return

    folder_path = os.path.join(BASE_DATA_DIR, current)
    if not os.path.exists(folder_path):
        await update.message.reply_text(f"❌ Thư mục `{current}` không còn tồn tại.")
        return

    files = [f for f in os.listdir(folder_path) if f.endswith('.csv')]
    if not files:
        await update.message.reply_text(f"📂 `{current}` trống. Hãy upload file CSV.")
        return

    await update.message.reply_text(f"📊 Đang xử lý {len(files)} file trong `{current}`...")

    CONV_THRESHOLD = 0.75  
    convergence_data = []
    
    fig_acc, ax_acc = plt.subplots(figsize=(10, 6))
    fig_loss, ax_loss = plt.subplots(figsize=(10, 6))
    fig_asr, ax_asr = plt.subplots(figsize=(10, 6))
    
    has_loss = False
    has_asr = False
    data_list = [] 

    # --- ĐỌC FILE (Logic Robust) ---
    for file in files:
        file_path = os.path.join(folder_path, file)
        try:
            try: df = pd.read_csv(file_path, skipinitialspace=True)
            except: df = pd.DataFrame()

            if len(df.columns) < 2:
                try: df = pd.read_csv(file_path, sep='\t')
                except: pass
            if len(df.columns) < 2:
                try: df = pd.read_csv(file_path, sep=None, engine='python')
                except: pass

            df.columns = df.columns.str.strip()
            col_map = {c.lower(): c for c in df.columns}
            if 'round' in col_map: df.rename(columns={col_map['round']: 'Round'}, inplace=True)
            if 'accuracy' in col_map: df.rename(columns={col_map['accuracy']: 'Accuracy'}, inplace=True)
            if 'loss' in col_map: df.rename(columns={col_map['loss']: 'Loss'}, inplace=True)
            if 'asr' in col_map: df.rename(columns={col_map['asr']: 'ASR'}, inplace=True)

            if 'Round' not in df.columns or 'Accuracy' not in df.columns:
                print(f"Skipping {file}: Missing columns")
                continue

            df['Round'] = pd.to_numeric(df['Round'], errors='coerce')
            df['Accuracy'] = pd.to_numeric(df['Accuracy'], errors='coerce')
            df = df.dropna(subset=['Round', 'Accuracy'])
            
            if df.empty: continue

            raw_label = file.replace('.csv', '').split('-')[-1]
            data_list.append({'label': raw_label, 'df': df})
            
        except Exception as e:
            print(f"Error {file}: {e}")

    if not data_list:
        await update.message.reply_text("❌ Không đọc được dữ liệu. Kiểm tra file CSV.")
        return

    # --- VẼ BIỂU ĐỒ ---
    data_list.sort(key=lambda x: int(x['label']) if x['label'].isdigit() else x['label'])

    for item in data_list:
        df = item['df']
        label = item['label']

        ax_acc.plot(df['Round'], df['Accuracy'], marker='o', markersize=4, label=f"Model: {label}")

        if 'Loss' in df.columns:
            loss = pd.to_numeric(df['Loss'], errors='coerce').dropna()
            if not loss.empty:
                has_loss = True
                ax_loss.plot(df.loc[loss.index, 'Round'], loss, linestyle='--', label=f"Loss: {label}")

        if 'ASR' in df.columns:
            asr = pd.to_numeric(df['ASR'], errors='coerce').fillna(0)
            if asr.max() > 0: 
                has_asr = True
                ax_asr.plot(df['Round'], asr, marker='s', linestyle='-.', label=f"ASR: {label}")

        reached = df[df['Accuracy'] >= CONV_THRESHOLD]
        val = reached['Round'].min() if not reached.empty else df['Round'].max()
        convergence_data.append((str(label), val))

    # --- LƯU & GỬI ---
    output_files = []

    ax_acc.set_title(f"Accuracy - {current}"); ax_acc.legend(); ax_acc.grid(True)
    p_acc = f"acc_{current}.png"; fig_acc.savefig(p_acc); output_files.append(p_acc)

    if has_loss:
        ax_loss.set_title(f"Loss Stability - {current}"); ax_loss.legend(); ax_loss.grid(True)
        p_loss = f"loss_{current}.png"; fig_loss.savefig(p_loss); output_files.append(p_loss)

    if has_asr:
        ax_asr.set_title(f"Attack ASR - {current}"); ax_asr.legend(); ax_asr.grid(True)
        p_asr = f"asr_{current}.png"; fig_asr.savefig(p_asr); output_files.append(p_asr)

    if convergence_data:
        fig_bar, ax_bar = plt.subplots(figsize=(10, 6))
        lbls, rnds = zip(*convergence_data)
        bars = ax_bar.bar(lbls, rnds, color='teal')
        ax_bar.set_title(f"Convergence Speed (To {CONV_THRESHOLD*100}%)")
        ax_bar.bar_label(bars)
        p_conv = f"conv_{current}.png"; fig_bar.savefig(p_conv); output_files.append(p_conv)

    for p in output_files:
        with open(p, 'rb') as f:
            await update.message.reply_photo(f)
        if os.path.exists(p): os.remove(p)
    
    plt.close('all')

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    
    if "YOUR_ACTUAL_BOT_TOKEN_HERE" in TOKEN or not TOKEN:
        print("❌ LỖI: Chưa nhập TOKEN!")
    else:
        app_bot = ApplicationBuilder().token(TOKEN).build()
        app_bot.add_handler(CommandHandler("start", start))
        app_bot.add_handler(CommandHandler("list", list_folders))
        app_bot.add_handler(CommandHandler("create", create_folder))
        app_bot.add_handler(CommandHandler("set", set_folder))
        app_bot.add_handler(CommandHandler("export", export_charts))
        app_bot.add_handler(CommandHandler("delete", delete_data))
        app_bot.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        print("✅ Bot đang chạy (Multi-Session Mode)...")
        app_bot.run_polling()
