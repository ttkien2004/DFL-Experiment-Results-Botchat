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

    target_rounds_mapping = {19: 20, 39: 40, 59: 60, 79: 80, 99: 100}
    
    data_list = [] 
    summary_records = []
    global_metrics = set()

    # --- BƯỚC 1: ĐỌC VÀ PHÁT HIỆN METRICS ĐỘNG ---
    for file in files:
        file_path = os.path.join(folder_path, file)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            algo_name = data.get('algo_name', [file.replace('.json', '')])[0]
            rounds = data.get('rounds', [])
            
            if not rounds: continue
                
            df_dict = {'Round': rounds}
            file_metrics = []
            avg_latency = None
            
            for key, val in data.items():
                if key == 'rounds': continue
                
                # --- XỬ LÝ RIÊNG BIỂU ĐỒ LATENCY BREAKDOWN ---
                if key == 'latency_breakdown':
                    if isinstance(val, list) and len(val) > 0 and isinstance(val[0], dict):
                        avg_latency = {}
                        lat_keys = val[0].keys()
                        for k in lat_keys:
                            # Cộng tổng time của key đó qua các vòng rồi chia đều cho tổng số vòng
                            avg_latency[k] = sum(item.get(k, 0) for item in val) / len(val)
                    continue

                if isinstance(val, list) and len(val) == len(rounds) and len(val) > 0:
                    if isinstance(val[0], (int, float)):
                        df_dict[key] = val
                        global_metrics.add(key)
                        file_metrics.append(key)
            
            df = pd.DataFrame(df_dict)
            data_list.append({'label': algo_name, 'df': df, 'avg_latency': avg_latency})
            
            for actual_r, display_r in target_rounds_mapping.items():
                row = df[df['Round'] == actual_r]
                if not row.empty:
                    record = {
                        'Algorithm': algo_name,
                        'Round (Display)': display_r,
                        'Round (Actual index)': actual_r
                    }
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
                if not metric_data.isna().all():
                    has_valid_data = True
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

    # --- TÌM CHỈ SỐ ACCURACY VÀ TRAFFIC CHO CÁC BIỂU ĐỒ ĐẶC THÙ ---
    acc_metric = next((m for m in global_metrics if 'acc' in m.lower()), None)
    traffic_metric = next((m for m in global_metrics if 'traffic' in m.lower() or 'comm_traffic_mb' in m.lower()), None)

    # --- BƯỚC 3: CONVERGENCE BAR CHART ĐỘNG ---
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

    # --- BƯỚC 4: BIỂU ĐỒ BĂNG THÔNG (CUMULATIVE & SCATTER) ---
    if traffic_metric and acc_metric:
        fig_cum, ax_cum = plt.subplots(figsize=(10, 6))
        fig_scat, ax_scat = plt.subplots(figsize=(10, 6))
        
        has_traffic_data = False
        scatter_points = []

        for item in data_list:
            df = item['df']
            label = item['label']
            
            if traffic_metric in df.columns and acc_metric in df.columns:
                has_traffic_data = True
                cum_traffic = df[traffic_metric].cumsum()
                
                # Line Chart (Cumulative)
                ax_cum.plot(df['Round'], cum_traffic, marker='', linestyle='-', linewidth=2, label=f"{label}")
                
                # Scatter Plot (Efficiency)
                total_traffic = cum_traffic.iloc[-1]
                final_acc = df[acc_metric].iloc[-1]
                scatter_points.append((total_traffic, final_acc, label))

        if has_traffic_data:
            traffic_display = traffic_metric.replace('_', ' ').title()
            ax_cum.set_title(f"Cumulative {traffic_display} over Rounds - {current}")
            ax_cum.set_xlabel("Rounds")
            ax_cum.set_ylabel(f"Cumulative {traffic_display}")
            ax_cum.legend()
            ax_cum.grid(True)
            p_cum = f"cumulative_{traffic_metric}_{current}.png"
            fig_cum.savefig(p_cum)
            output_files.append(p_cum)
            
            for t_traf, f_acc, lbl in scatter_points:
                ax_scat.scatter(t_traf, f_acc, s=150, label=lbl, alpha=0.8, edgecolors='black')
                ax_scat.annotate(lbl, (t_traf, f_acc), xytext=(8, 8), textcoords='offset points', fontsize=10)
            
            ax_scat.set_title(f"Efficiency: Total {traffic_display} vs Final Accuracy")
            ax_scat.set_xlabel(f"Total {traffic_display}")
            ax_scat.set_ylabel(f"Final {acc_metric.replace('_', ' ').title()}")
            ax_scat.grid(True, linestyle='--')
            p_scat = f"efficiency_scatter_{current}.png"
            fig_scat.savefig(p_scat)
            output_files.append(p_scat)

        plt.close(fig_cum)
        plt.close(fig_scat)

    # --- BƯỚC 5: BIỂU ĐỒ CỘT CHỒNG LATENCY BREAKDOWN ---
    has_latency = any(item.get('avg_latency') for item in data_list)
    if has_latency:
        fig_lat, ax_lat = plt.subplots(figsize=(10, 6))
        
        lat_items = [item for item in data_list if item.get('avg_latency')]
        labels = [item['label'] for item in lat_items]
        
        # Tìm tất cả các thành phần thời gian
        all_keys = set()
        for item in lat_items:
            all_keys.update(item['avg_latency'].keys())
        all_keys = sorted(list(all_keys))
        
        totals = [sum(item['avg_latency'].values()) for item in lat_items]
        bottom = [0] * len(labels)
        
        # Danh sách màu nhạt (Pastel) và họa tiết (Hatches)
        # Các họa tiết: '..' (chấm bi), '//' (kẻ sọc), 'O' (vòng tròn lớn), 'xx' (lưới đan), '' (trơn)
        light_colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99', '#c2c2f0', '#ffb3e6', '#e6f69d']
        patterns = ['..', '', '//', 'O', 'xx', '*', '++']
        
        for idx, key in enumerate(all_keys):
            values = [item['avg_latency'].get(key, 0) for item in lat_items]
            display_name = key.replace('time_', '').replace('_', ' ').title()
            
            # Chọn màu và họa tiết theo vòng lặp
            c = light_colors[idx % len(light_colors)]
            h = patterns[idx % len(patterns)]
            
            # Vẽ khối với màu sáng, có họa tiết và viền xám mỏng
            bars = ax_lat.bar(
                labels, values, bottom=bottom, label=display_name, 
                color=c, edgecolor='dimgray', hatch=h
            )
            
            # Thêm Text (Thời gian + Phần trăm)
            for i, (bar, val, total) in enumerate(zip(bars, values, totals)):
                if total > 0 and val > 0:
                    pct = (val / total) * 100
                    if pct > 3:
                        y_center = bottom[i] + (val / 2)
                        # Vì nền sáng, ta dùng chữ đen để luôn dễ đọc
                        ax_lat.text(
                            bar.get_x() + bar.get_width() / 2, 
                            y_center, 
                            f"{val:.2f}s\n({pct:.1f}%)", 
                            ha='center', 
                            va='center', 
                            color='black', 
                            fontsize=9,
                            fontweight='bold'
                        )
            
            bottom = [b + v for b, v in zip(bottom, values)]
            
        ax_lat.set_title(f"Average Latency Breakdown per Round - {current}")
        ax_lat.set_ylabel("Average Time (seconds)")
        
        # Bảng chú giải ra ngoài biểu đồ
        ax_lat.legend(loc='center left', bbox_to_anchor=(1, 0.5))
        ax_lat.grid(axis='y', linestyle='--', alpha=0.5) # Làm mờ lưới nền để nổi khối
        
        # Hiển thị tổng số giây
        for i in range(len(labels)):
            if totals[i] > 0:
                ax_lat.text(
                    i, bottom[i] + (max(bottom)*0.02), 
                    f"Total:\n{totals[i]:.2f}s", 
                    ha='center', 
                    fontweight='bold', 
                    color='darkred'
                )

        plt.tight_layout()
        
        p_lat = f"latency_breakdown_{current}.png"
        fig_lat.savefig(p_lat)
        output_files.append(p_lat)
        plt.close(fig_lat)

    # --- BƯỚC 6: BIỂU ĐỒ CỘT FINAL ACCURACY ---
    if acc_metric:
        fig_acc_bar, ax_acc_bar = plt.subplots(figsize=(10, 6))
        acc_labels = []
        final_accs = []
        
        # Lấy Accuracy ở vòng cuối cùng của mỗi Model
        for item in data_list:
            df = item['df']
            label = item['label']
            if acc_metric in df.columns:
                # Tìm giá trị hợp lệ cuối cùng
                valid_acc_data = df[acc_metric].dropna()
                if not valid_acc_data.empty:
                    final_acc = valid_acc_data.iloc[-1]
                    acc_labels.append(label)
                    final_accs.append(final_acc)
        
        if final_accs:
            # Tạo màu Pastel đa dạng cho các cột
            bar_colors = ['#8dd3c7', '#ffffb3', '#bebada', '#fb8072', '#80b1d3', '#fdb462', '#b3de69']
            colors = [bar_colors[i % len(bar_colors)] for i in range(len(acc_labels))]
            
            bars_acc = ax_acc_bar.bar(acc_labels, final_accs, color=colors, edgecolor='dimgray', hatch='//')
            
            metric_display_name = acc_metric.replace('_', ' ').title()
            ax_acc_bar.set_title(f"Final {metric_display_name} Comparison - {current}")
            ax_acc_bar.set_ylabel(metric_display_name)
            
            # Ghi % trên đỉnh mỗi cột
            for bar in bars_acc:
                height = bar.get_height()
                ax_acc_bar.text(
                    bar.get_x() + bar.get_width() / 2, 
                    height + 0.01, 
                    f"{height:.2%}", # Format dạng 98.50%
                    ha='center', 
                    va='bottom',
                    fontweight='bold',
                    color='black'
                )
            
            # Tăng giới hạn trục Y thêm 1 chút để không bị cắt chữ
            max_val = max(final_accs)
            ax_acc_bar.set_ylim(0, max_val * 1.15)
            ax_acc_bar.grid(axis='y', linestyle='--', alpha=0.7)
            
            p_acc_bar = f"bar_final_{acc_metric}_{current}.png"
            fig_acc_bar.savefig(p_acc_bar)
            output_files.append(p_acc_bar)
            plt.close(fig_acc_bar)
    # --- BƯỚC 6: GỬI TẤT CẢ ẢNH ---
    for p in output_files:
        with open(p, 'rb') as f: await update.message.reply_photo(f)
        os.remove(p)

    # --- BƯỚC 7: TẠO VÀ GỬI FILE SUMMARY CSV ĐỘNG ---
    if summary_records:
        summary_df = pd.DataFrame(summary_records)
        summary_df = summary_df.sort_values(by=['Algorithm', 'Round (Actual index)'])
        
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
