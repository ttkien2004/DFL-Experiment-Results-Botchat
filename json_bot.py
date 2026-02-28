import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import threading
import shutil
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- CẤU HÌNH ---
TOKEN = os.getenv("BOT_TOKEN", "YOUR_ACTUAL_BOT_TOKEN_HERE") 
PORT = int(os.environ.get("PORT", 10001)) # Đổi port tránh xung đột nếu chạy song song
BASE_DATA_DIR = "experiments_json" # Đổi tên thư mục để tách biệt với CSV

# --- FLASK SERVER ---
app_flask = Flask(__name__)
@app_flask.route('/')
def index(): return "Bot DFL JSON is Running!"
def run_flask(): app_flask.run(host='0.0.0.0', port=PORT)

if not os.path.exists(BASE_DATA_DIR): os.makedirs(BASE_DATA_DIR)

# --- QUẢN LÝ SESSION ---
user_sessions = {} 

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current = user_sessions.get(user_id, "Chưa chọn")
    await update.message.reply_text(
        f"🤖 **Bot DFL (JSON Mode)**\n"
        f"👤 Bạn đang làm việc tại: `{current}`\n\n"
        "📜 **Lệnh:**\n"
        "/create <tên> - Tạo folder mới\n"
        "/set <tên> - Chọn folder làm việc\n"
        "/export - Vẽ biểu đồ & Xuất file CSV (20-40-60-80-100)\n"
        "/delete - Xóa folder hiện tại\n"
        "📥 Vui lòng upload các file `.json`."
    )

async def create_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    for folder_name in context.args:
        path = os.path.join(BASE_DATA_DIR, folder_name)
        os.makedirs(path, exist_ok=True)
        await update.message.reply_text(f"✅ Đã tạo: `{folder_name}`")

async def set_folder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return
    folder_name = context.args[0]
    if os.path.exists(os.path.join(BASE_DATA_DIR, folder_name)):
        user_sessions[update.effective_user.id] = folder_name
        await update.message.reply_text(f"📂 Đã chuyển sang: `{folder_name}`")
    else:
        await update.message.reply_text(f"❌ Không tìm thấy `{folder_name}`.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current = user_sessions.get(user_id)
    if not current:
        await update.message.reply_text("⚠️ Dùng /set trước.")
        return
    
    file = await update.message.document.get_file()
    file_name = update.message.document.file_name
    
    # CHỈ NHẬN FILE JSON
    if file_name.endswith('.json'):
        save_path = os.path.join(BASE_DATA_DIR, current, file_name)
        await file.download_to_drive(save_path)
        await update.message.reply_text(f"📥 Đã lưu `{file_name}` vào `{current}`")
    else:
        await update.message.reply_text("❌ Kịch bản này chỉ chấp nhận file .json")

async def delete_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current = user_sessions.get(user_id)
    if context.args and context.args[0] == "all":
        shutil.rmtree(BASE_DATA_DIR); os.makedirs(BASE_DATA_DIR); user_sessions.clear()
        await update.message.reply_text("💥 Đã xóa sạch toàn bộ hệ thống.")
    elif current:
        path = os.path.join(BASE_DATA_DIR, current)
        for f in os.listdir(path): 
            if os.path.isfile(os.path.join(path, f)): os.remove(os.path.join(path, f))
        await update.message.reply_text(f"🗑️ Đã dọn sạch folder `{current}`")

async def export_charts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current = user_sessions.get(user_id)
    if not current: return

    folder_path = os.path.join(BASE_DATA_DIR, current)
    if not os.path.exists(folder_path): return

    files = [f for f in os.listdir(folder_path) if f.endswith('.json')]
    if not files:
        await update.message.reply_text(f"📂 `{current}` trống. Hãy upload file JSON.")
        return

    await update.message.reply_text(f"📊 Đang đọc {len(files)} file JSON...")

    CONV_THRESHOLD = 0.75  
    convergence_data = []
    summary_records = []
    target_rounds = [20, 40, 60, 80, 100] # Các round cần trích xuất báo cáo
    
    fig_acc, ax_acc = plt.subplots(figsize=(10, 6))
    fig_loss, ax_loss = plt.subplots(figsize=(10, 6))
    fig_asr, ax_asr = plt.subplots(figsize=(10, 6))
    
    has_loss, has_asr = False, False
    data_list = [] 

    # --- ĐỌC FILE JSON ---
    for file in files:
        file_path = os.path.join(folder_path, file)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Lấy tên thuật toán (Krum, Median, Trimmed Mean...)
            algo_name = data.get('algo_name', [file.replace('.json', '')])[0]
            
            # Khởi tạo DataFrame từ JSON
            df = pd.DataFrame({
                'Round': data.get('rounds', []),
                'Accuracy': data.get('clean_acc', data.get('avg_acc', [])),
                'ASR': data.get('asr', []),
                'Loss': data.get('consensus_error', [])
            })
            
            df = df.dropna(subset=['Round', 'Accuracy'])
            if df.empty: continue
            
            data_list.append({'label': algo_name, 'df': df})
            
            # --- TRÍCH XUẤT CHỈ SỐ SUMMARY ---
            for r in target_rounds:
                row = df[df['Round'] == r]
                if not row.empty:
                    summary_records.append({
                        'Algorithm': algo_name,
                        'Round': r,
                        'Accuracy': round(row['Accuracy'].values[0], 4),
                        'ASR': round(row['ASR'].values[0], 4) if not row['ASR'].isna().all() else None,
                        'Loss': round(row['Loss'].values[0], 4) if not row['Loss'].isna().all() else None
                    })
                    
        except Exception as e:
            print(f"Error {file}: {e}")

    if not data_list:
        await update.message.reply_text("❌ Không trích xuất được dữ liệu.")
        return

    # Sắp xếp theo tên thuật toán
    data_list.sort(key=lambda x: str(x['label']))

    # --- VẼ BIỂU ĐỒ ---
    for item in data_list:
        df, label = item['df'], item['label']

        ax_acc.plot(df['Round'], df['Accuracy'], marker='o', markersize=4, label=f"Model: {label}")

        if 'Loss' in df.columns and not df['Loss'].isna().all():
            has_loss = True
            ax_loss.plot(df['Round'], df['Loss'], linestyle='--', label=f"Loss: {label}")

        if 'ASR' in df.columns and not df['ASR'].isna().all():
            has_asr = True
            ax_asr.plot(df['Round'], df['ASR'], marker='s', linestyle='-.', label=f"ASR: {label}")

        reached = df[df['Accuracy'] >= CONV_THRESHOLD]
        val = reached['Round'].min() if not reached.empty else df['Round'].max()
        convergence_data.append((str(label), val))

    # --- LƯU ẢNH ---
    output_files = []
    
    ax_acc.set_title(f"Accuracy Comparison (JSON) - {current}"); ax_acc.legend(); ax_acc.grid(True)
    p_acc = f"acc_{current}.png"; fig_acc.savefig(p_acc); output_files.append(p_acc)

    if has_loss:
        ax_loss.set_title(f"Consensus Error / Loss - {current}"); ax_loss.legend(); ax_loss.grid(True)
        p_loss = f"loss_{current}.png"; fig_loss.savefig(p_loss); output_files.append(p_loss)

    if has_asr:
        ax_asr.set_title(f"Attack Success Rate (ASR) - {current}"); ax_asr.legend(); ax_asr.grid(True)
        p_asr = f"asr_{current}.png"; fig_asr.savefig(p_asr); output_files.append(p_asr)

    if convergence_data:
        fig_bar, ax_bar = plt.subplots(figsize=(10, 6))
        lbls, rnds = zip(*convergence_data)
        bars = ax_bar.bar(lbls, rnds, color='darkorange')
        ax_bar.set_title(f"Convergence Speed (To {CONV_THRESHOLD*100}%)")
        ax_bar.bar_label(bars)
        p_conv = f"conv_{current}.png"; fig_bar.savefig(p_conv); output_files.append(p_conv)

    # Gửi ảnh
    for p in output_files:
        with open(p, 'rb') as f: await update.message.reply_photo(f)
        os.remove(p)
    plt.close('all')

    # --- TẠO VÀ GỬI FILE SUMMARY CSV ---
    if summary_records:
        summary_df = pd.DataFrame(summary_records)
        # Sort cho đẹp mắt theo Thuật toán và Round
        summary_df = summary_df.sort_values(by=['Algorithm', 'Round'])
        
        summary_csv = f"Summary_{current}.csv"
        summary_df.to_csv(summary_csv, index=False)
        
        with open(summary_csv, 'rb') as f:
            await update.message.reply_document(
                document=f, 
                filename=f"Metrics_20_40_60_80_100_{current}.csv", 
                caption="✅ File tổng hợp các mốc Round quan trọng!"
            )
        os.remove(summary_csv)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    
    if "YOUR_ACTUAL_BOT_TOKEN_HERE" in TOKEN or not TOKEN:
        print("❌ LỖI: Chưa nhập TOKEN!")
    else:
        app_bot = ApplicationBuilder().token(TOKEN).build()
        app_bot.add_handler(CommandHandler("start", start))
        app_bot.add_handler(CommandHandler("create", create_folder))
        app_bot.add_handler(CommandHandler("set", set_folder))
        app_bot.add_handler(CommandHandler("export", export_charts))
        app_bot.add_handler(CommandHandler("delete", delete_data))
        app_bot.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        print("✅ Bot JSON đang chạy...")
        app_bot.run_polling()
