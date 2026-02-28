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

    await update.message.reply_text(f"📊 Đang quét động (Dynamic Scan) {len(files)} file JSON...")

    # Mapping round: Lấy mốc index thực tế
    target_rounds_mapping = {
        19: 20, 
        39: 40, 
        59: 60, 
        79: 80, 
        99: 100
    }
    
    data_list = [] 
    summary_records = []
    global_metrics = set() # Lưu trữ tất cả các metrics phát hiện được

    # --- BƯỚC 1: ĐỌC VÀ PHÁT HIỆN METRICS ĐỘNG ---
    for file in files:
        file_path = os.path.join(folder_path, file)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Lấy tên thuật toán (Krum, Median, Trimmed Mean...)
            algo_name = data.get('algo_name', [file.replace('.json', '')])[0]
            rounds = data.get('rounds', [])
            
            if not rounds:
                continue
                
            # Tạo Dictionary để dựng DataFrame
            df_dict = {'Round': rounds}
            file_metrics = []
            
            # Quét các keys để tìm metrics hợp lệ
            for key, val in data.items():
                if key == 'rounds': continue
                # Tiêu chí 1 metric hợp lệ: là list, cùng độ dài với rounds, phần tử là số
                if isinstance(val, list) and len(val) == len(rounds) and len(val) > 0:
                    if isinstance(val[0], (int, float)):
                        df_dict[key] = val
                        global_metrics.add(key)
                        file_metrics.append(key)
            
            df = pd.DataFrame(df_dict)
            data_list.append({'label': algo_name, 'df': df})
            
            # --- TRÍCH XUẤT CHỈ SỐ THEO MAPPING CHO FILE CSV ---
            for actual_r, display_r in target_rounds_mapping.items():
                row = df[df['Round'] == actual_r]
                if not row.empty:
                    record = {
                        'Algorithm': algo_name,
                        'Round (Display)': display_r,
                        'Round (Actual index)': actual_r
                    }
                    # Đưa toàn bộ metrics tìm được vào record
                    for metric in file_metrics:
                        val = row[metric].values[0]
                        record[metric] = round(val, 4) if not pd.isna(val) else None
                    
                    summary_records.append(record)
                    
        except Exception as e:
            print(f"Error {file}: {e}")

    if not data_list:
        await update.message.reply_text("❌ Không trích xuất được dữ liệu hợp lệ.")
        return

    data_list.sort(key=lambda x: str(x['label']))
    output_files = []

    # --- BƯỚC 2: VẼ ĐỘNG (DYNAMIC PLOTTING) TỪNG METRIC ---
    for metric in global_metrics:
        fig, ax = plt.subplots(figsize=(10, 6))
        has_valid_data = False
        
        for item in data_list:
            df = item['df']
            label = item['label']
            
            if metric in df.columns:
                metric_data = df[metric]
                # Kiểm tra nếu metric không rỗng toàn bộ
                if not metric_data.isna().all():
                    has_valid_data = True
                    # Tùy biến style đường kẻ dựa trên tên metric (Ví dụ: loss thì kẻ đứt)
                    linestyle = '--' if 'error' in metric.lower() or 'loss' in metric.lower() else '-'
                    marker = 's' if 'asr' in metric.lower() else 'o'
                    
                    ax.plot(df['Round'], metric_data, marker=marker, markersize=4, linestyle=linestyle, label=f"{label}")

        if has_valid_data:
            metric_display_name = metric.replace('_', ' ').title()
            ax.set_title(f"{metric_display_name} Comparison - {current}")
            ax.set_xlabel("Rounds")
            ax.set_ylabel(metric_display_name)
            ax.legend()
            ax.grid(True)
            
            p_metric = f"metric_{metric}_{current}.png"
            fig.savefig(p_metric)
            output_files.append(p_metric)
            
        plt.close(fig)

    # --- BƯỚC 3: CONVERGENCE BAR CHART ĐỘNG ---
    # Tự động tìm metric đại diện cho Accuracy (ví dụ: clean_acc, avg_acc)
    acc_metric = next((m for m in global_metrics if 'acc' in m.lower()), None)
    
    if acc_metric:
        CONV_THRESHOLD = 0.75  
        convergence_data = []
        for item in data_list:
            df = item['df']
            if acc_metric in df.columns:
                reached = df[df[acc_metric] >= CONV_THRESHOLD]
                val = reached['Round'].min() if not reached.empty else df['Round'].max()
                convergence_data.append((str(item['label']), val))

        if convergence_data:
            fig_bar, ax_bar = plt.subplots(figsize=(10, 6))
            lbls, rnds = zip(*convergence_data)
            bars = ax_bar.bar(lbls, rnds, color='darkorange')
            ax_bar.set_title(f"Convergence Speed (To {CONV_THRESHOLD*100}% on {acc_metric})")
            ax_bar.bar_label(bars)
            p_conv = f"conv_{current}.png"; fig_bar.savefig(p_conv); output_files.append(p_conv)
            plt.close(fig_bar)

    # --- BƯỚC 4: GỬI TẤT CẢ ẢNH ---
    for p in output_files:
        with open(p, 'rb') as f: await update.message.reply_photo(f)
        os.remove(p)

    # --- BƯỚC 5: TẠO VÀ GỬI FILE SUMMARY CSV ĐỘNG ---
    if summary_records:
        summary_df = pd.DataFrame(summary_records)
        summary_df = summary_df.sort_values(by=['Algorithm', 'Round (Actual index)'])
        
        # Sắp xếp lại thứ tự cột cho đẹp: Algorithm, Round, rồi đến các metrics
        cols = ['Algorithm', 'Round (Display)', 'Round (Actual index)']
        metrics_cols = [c for c in summary_df.columns if c not in cols]
        summary_df = summary_df[cols + sorted(metrics_cols)]
        
        summary_csv = f"Dynamic_Summary_{current}.csv"
        summary_df.to_csv(summary_csv, index=False)
        
        with open(summary_csv, 'rb') as f:
            await update.message.reply_document(
                document=f, 
                filename=f"Metrics_Summary_Rounds_{current}.csv", 
                caption=f"✅ File tổng hợp {len(metrics_cols)} chỉ số động!"
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
