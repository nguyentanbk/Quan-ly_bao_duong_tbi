import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import io

# Kết nối đến SQLite
def init_db():
    conn = sqlite3.connect("bao_duong.db", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lich_bao_duong (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ngay DATE,
            thiet_bi TEXT,
            hang_muc TEXT,
            noi_dung TEXT,
            tan_suat TEXT,
            danh_gia_chuan TEXT,
            ket_qua_thuc_te TEXT,
            trang_thai TEXT
        )
    """)
    conn.commit()
    return conn

# Tạo lịch từ Excel
def load_schedule_from_excel(file):
    df = pd.read_excel(file)
    df.columns = df.columns.str.strip()
    st.write("🧾 Các cột được nhận từ Excel:", df.columns.tolist())

    start_date = datetime(2025, 4, 24)

    def get_interval(freq):
        freq = str(freq).upper()
        if "WEEK" in freq:
            parts = freq.split()
            num = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
            return timedelta(weeks=num)
        elif "MONTH" in freq:
            parts = freq.split()
            num = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
            return timedelta(days=30 * num)
        return None

    records = []
    for _, row in df.iterrows():
        interval = get_interval(row['Tần suất'])
        if interval is None:
            continue
        current_date = start_date
        while current_date < start_date + timedelta(days=365):
            records.append({
                "ngay": current_date.date(),
                "thiet_bi": row['Tên thiết bị'],
                "hang_muc": row['Hạng mục'],
                "noi_dung": row['Nội dung'],
                "tan_suat": row['Tần suất'],
                "danh_gia_chuan": row['Đánh giá sau bảo dưỡng'],
                "ket_qua_thuc_te": "",
                "trang_thai": "Chưa thực hiện"
            })
            current_date += interval

    return pd.DataFrame(records)

# Ghi dữ liệu
def insert_or_replace(conn, record):
    record = dict(record)
    record['ngay'] = record['ngay'].isoformat() if isinstance(record['ngay'], pd.Timestamp) else record['ngay']
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM lich_bao_duong WHERE
            ngay = ? AND thiet_bi = ? AND hang_muc = ? AND noi_dung = ?
    """, (record['ngay'], record['thiet_bi'], record['hang_muc'], record['noi_dung']))

    result = cursor.fetchone()
    if result:
        cursor.execute("""
            UPDATE lich_bao_duong
            SET tan_suat = ?, danh_gia_chuan = ?, ket_qua_thuc_te = ?, trang_thai = ?
            WHERE id = ?
        """, (
            record['tan_suat'], record['danh_gia_chuan'], record['ket_qua_thuc_te'], record['trang_thai'], result[0]
        ))
    else:
        cursor.execute("""
            INSERT INTO lich_bao_duong
            (ngay, thiet_bi, hang_muc, noi_dung, tan_suat, danh_gia_chuan, ket_qua_thuc_te, trang_thai)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record['ngay'], record['thiet_bi'], record['hang_muc'], record['noi_dung'],
            record['tan_suat'], record['danh_gia_chuan'], record['ket_qua_thuc_te'], record['trang_thai']
        ))
    conn.commit()

# Giao diện
conn = init_db()

# Hàm lấy danh sách mục quá hạn từ cơ sở dữ liệu
def get_overdue_df(start_date, end_date):
    df = pd.read_sql("SELECT * FROM lich_bao_duong", conn, parse_dates=['ngay'])
    df = df[(df['ngay'] >= pd.to_datetime(start_date)) & (df['ngay'] <= pd.to_datetime(end_date))]

    today = datetime.today().date()
    df['delay'] = [
        (today - d.date()).days if t != 'Hoàn thành' and d.date() < today else 0
        for d, t in zip(df['ngay'], df['trang_thai'])]

    return df[df['delay'] > 0]

st.title("📋 Quản lý kế hoạch bảo dưỡng thiết bị")
        
tabs = st.tabs(["📋 Kế hoạch", "📈 Báo cáo"])

# Tab 0: Kế hoạch
with tabs[0]:
    st.subheader("📌 Upload kế hoạch bảo dưỡng từ Excel")
    uploaded_file = st.file_uploader("Tải lên file kế hoạch bảo dưỡng (.xlsx)", type=["xlsx"])
    if uploaded_file:
        df_preview = load_schedule_from_excel(uploaded_file)
        st.dataframe(df_preview, use_container_width=True)

        if st.button("📤 Ghi vào hệ thống"):
            for _, row in df_preview.iterrows():
                insert_or_replace(conn, row.to_dict())
            st.success("✅ Đã ghi toàn bộ dữ liệu kế hoạch vào hệ thống.")
            st.rerun()

    # Nhập và cập nhật dữ liệu
    st.subheader("📝 Cập nhật kết quả bảo dưỡng hôm nay")
    today = datetime.today().date()
    today_df = pd.read_sql("SELECT * FROM lich_bao_duong WHERE ngay = ?", conn, params=(today,), parse_dates=['ngay'])

    if today_df.empty:
        st.info("Hôm nay không có mục bảo dưỡng nào.")
    else:
        hide_completed = st.checkbox("Ẩn mục đã hoàn thành", value=False, key="hide_completed_today")
        if hide_completed:
            today_df = today_df[today_df['trang_thai'] != 'Hoàn thành']
            today_df['ngay'] = today_df['ngay'].dt.date
            
        for thiet_bi in today_df['thiet_bi'].unique():
            st.subheader(f"🔧 Thiết bị: {thiet_bi}")
            thiet_bi_df = today_df[today_df['thiet_bi'] == thiet_bi]
            thiet_bi_df['ngay'] = thiet_bi_df['ngay'].dt.date
            
            for idx, row in thiet_bi_df.iterrows():
                with st.form(key=f"form_today_{idx}"):
                    st.write(f"**Hạng mục:** {row['hang_muc']}")
                    st.write(f"**Nội dung:** {row['noi_dung']}")
                    st.write(f"**Yêu cầu:** {row['danh_gia_chuan']}")

                    ket_qua = st.text_area("Kết quả thực tế", value=row['ket_qua_thuc_te'] or "", key=f"ketqua_today_{idx}")
                    hoan_thanh = st.checkbox("Đã hoàn thành", value=(row['trang_thai'] == "Hoàn thành"), key=f"hoanthanh_today_{idx}")

                    submitted = st.form_submit_button("💾 Lưu kết quả")
                    if submitted:
                        record = row.to_dict()
                        record['ket_qua_thuc_te'] = ket_qua
                        record['trang_thai'] = "Hoàn thành" if hoan_thanh else "Chưa thực hiện"
                        insert_or_replace(conn, record)
                        st.success("✅ Đã lưu kết quả!")
                        st.rerun()

    # Cập nhật kết quả các mục bị trễ
    st.subheader("🛠️ Cập nhật kết quả các mục bị trễ")
    df_all = pd.read_sql("SELECT * FROM lich_bao_duong", conn, parse_dates=['ngay'])
    today = datetime.today().date()
    overdue_df = df_all[(df_all['ngay'].dt.date < today) & (df_all['trang_thai'] != 'Hoàn thành')]
    overdue_df['ngay'] = overdue_df['ngay'].dt.date
    
    if not overdue_df.empty:
        with st.form(key="update_overdue_form"):
            updated_rows = []
            for i, row in overdue_df.reset_index().iterrows():
                st.markdown(f"**🔧 {row['thiet_bi']} - {row['hang_muc']} ({row['ngay'].strftime('%d/%m/%Y')})**")
                col1, col2 = st.columns([3, 2])
                with col1:
                    ket_qua = st.text_area("Kết quả thực tế", value=row['ket_qua_thuc_te'] or "", key=f"overdue_kq_{i}")
                with col2:
                    hoan_thanh = st.checkbox("Hoàn thành", value=(row['trang_thai'] == "Hoàn thành"), key=f"overdue_ht_{i}")
                updated_rows.append((row.to_dict(), ket_qua, hoan_thanh))
            
            submitted = st.form_submit_button("✅ Lưu kết quả các mục trễ")
            if submitted:
                for old_record, kq, ht in updated_rows:
                    old_record['ket_qua_thuc_te'] = kq
                    old_record['trang_thai'] = "Hoàn thành" if ht else "Chưa thực hiện"
                    insert_or_replace(conn, old_record)
                st.success("✅ Đã cập nhật các mục bị trễ!")
                st.rerun()
    else:
        st.info("Không có mục bảo dưỡng nào bị trễ.")
    # Xóa dữ liệu (chỉ cho giám đốc)
    st.subheader("🗑️ Xóa toàn bộ dữ liệu bảo dưỡng")
    if "verified" not in st.session_state:
        st.session_state.verified = False

    if not st.session_state.verified:
        password = st.text_input("🔐 Nhập mật khẩu giám đốc", type="password", key="admin_pass")
        if st.button("✅ Xác nhận", key="verify_admin"):
            if password == "giamdoc123":
                st.session_state.verified = True
                st.success("✅ Xác thực thành công. Bạn có thể xoá dữ liệu.")
            else:
                st.error("❌ Sai mật khẩu.")
    else:
        if st.button("🗑️ Xác nhận xoá toàn bộ dữ liệu", key="confirm_delete"):
            cursor = conn.cursor()
            cursor.execute("DELETE FROM lich_bao_duong")
            conn.commit()
            st.session_state.verified = False
            st.success("Đã xoá toàn bộ dữ liệu bảo dưỡng!")
            st.rerun()
            
# Tab 1: Báo cáo
with tabs[1]:
    st.subheader("📆 Thống kê tiến độ bảo dưỡng")
    
    # Sử dụng session state để lưu trữ phạm vi ngày
    if 'start_date' not in st.session_state:
        st.session_state.start_date = datetime.today() - timedelta(days=30)
    if 'end_date' not in st.session_state:
        st.session_state.end_date = datetime.today()

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Từ ngày", value=st.session_state.start_date, key="start_date_report")
    with col2:
        end_date = st.date_input("Đến ngày", value=st.session_state.end_date, key="end_date_report")

    # Lấy dữ liệu mới nhất từ database
    @st.cache_data(ttl=1)  # Cache trong 1 giây để đảm bảo luôn có dữ liệu mới
    def get_report_data(start_date, end_date):
        df = pd.read_sql("SELECT * FROM lich_bao_duong", conn, parse_dates=['ngay'])
        df = df[(df['ngay'] >= pd.to_datetime(start_date)) & (df['ngay'] <= pd.to_datetime(end_date))]
        return df

    df_filtered = get_report_data(start_date, end_date)

    device_options = ["Tất cả"] + sorted(df_filtered['thiet_bi'].dropna().unique())
    selected_device = st.selectbox("Thiết bị", device_options, key="device_select")

    status_options = ["Tất cả", "Hoàn thành", "Chưa thực hiện"]
    selected_status = st.radio("Trạng thái", status_options, horizontal=True, key="status_radio")

    if selected_device != "Tất cả":
        df_filtered = df_filtered[df_filtered['thiet_bi'] == selected_device]

    if selected_status == "Hoàn thành":
        df_filtered = df_filtered[df_filtered['trang_thai'] == "Hoàn thành"]
    elif selected_status == "Chưa thực hiện":
        df_filtered = df_filtered[df_filtered['trang_thai'] != "Hoàn thành"]

    today = datetime.today().date()
    df_filtered['delay'] = [
        (today - d.date()).days if t != 'Hoàn thành' and d.date() < today else 0
        for d, t in zip(df_filtered['ngay'], df_filtered['trang_thai'])
    ]

    show_delay_only = st.checkbox("Chỉ hiện mục đã quá hạn", value=False, key="show_delay_only")
    if show_delay_only:
        df_filtered = df_filtered[df_filtered['delay'] > 0]

    # Hiển thị các chỉ số
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Tổng số mục", len(df_filtered))
    with col2:
        st.metric("Đã hoàn thành", (df_filtered['trang_thai'] == "Hoàn thành").sum())
    with col3:
        st.metric("Chưa thực hiện", (df_filtered['trang_thai'] != "Hoàn thành").sum())

    overdue_df = get_overdue_df(start_date, end_date)
    if not overdue_df.empty:
        st.warning(f"⚠️ Có {len(overdue_df)} mục bảo dưỡng đã quá hạn!")

    def highlight_delay(row):
        # Kiểm tra xem cột 'delay' có tồn tại không
        if 'delay' not in row:
            return [''] * len(row)
    
        # Kiểm tra giá trị delay
        if row['delay'] > 0:
            return ['background-color: #ffcccc'] * len(row)
        elif 'trang_thai' in row and row['trang_thai'] == "Hoàn thành":
            return ['background-color: #ccffcc'] * len(row)
        return [''] * len(row)

    st.subheader("📋 Chi tiết các mục bảo dưỡng")
    df_display = df_filtered.copy()
    df_display['Số ngày trễ'] = df_display['delay']
    df_filtered['delay'] = [
    (today - d.date()).days if t != 'Hoàn thành' and d.date() < today else 0
    for d, t in zip(df_filtered['ngay'], df_filtered['trang_thai'])]
    
    st.dataframe(
    df_display[['ngay', 'thiet_bi', 'hang_muc', 'noi_dung', 'trang_thai', 'Số ngày trễ', 'ket_qua_thuc_te']]
    .style.apply(highlight_delay, axis=1),
    use_container_width=True)

    # Biểu đồ
    st.subheader("📊 Biểu đồ thống kê")
    tab1, tab2 = st.tabs(["Theo thiết bị", "Theo tuần"])
    
    with tab1:
        device_summary = df_filtered.groupby('thiet_bi')['trang_thai'].value_counts().unstack().fillna(0)
        
        # Đảm bảo có cả 2 cột dù dữ liệu có hay không
        for status in ["Hoàn thành", "Chưa thực hiện"]:
            if status not in device_summary.columns:
                device_summary[status] = 0
        
        if not device_summary.empty:
            device_summary = device_summary[["Hoàn thành", "Chưa thực hiện"]]
            fig, ax = plt.subplots(figsize=(10, 6))
            device_summary.plot(kind='bar', stacked=True, ax=ax, color=['#4CAF50', '#F44336'])
            ax.set_ylabel("Số lượng")
            ax.set_title("Tình trạng bảo dưỡng theo thiết bị")
            ax.legend(title="Trạng thái")
            st.pyplot(fig)
        else:
            st.info("Không có dữ liệu để hiển thị biểu đồ theo thiết bị")

    with tab2:
        df_filtered['week'] = df_filtered['ngay'].dt.to_period("W").apply(lambda r: r.start_time)
        weekly_progress = df_filtered[df_filtered['trang_thai'] == "Hoàn thành"].groupby('week').size()
        
        if not weekly_progress.empty:
            fig2, ax2 = plt.subplots(figsize=(10, 4))
            weekly_progress.plot(kind='line', marker='o', ax=ax2, color='#2196F3')
            ax2.set_ylabel("Số mục hoàn thành")
            ax2.set_xlabel("Tuần")
            ax2.set_title("Tiến độ bảo dưỡng theo tuần")
            ax2.grid(True)
            st.pyplot(fig2)
        else:
            st.info("Không có mục hoàn thành để hiển thị biểu đồ tuần")

    # Xuất Excel
    st.subheader("📁 Xuất kết quả bảo dưỡng")
    if st.button("📤 Tải file Excel", key="export_excel"):
        towrite = io.BytesIO()
        with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
            df_filtered.to_excel(writer, index=False, sheet_name="Bao_duong")
        towrite.seek(0)
        st.download_button(
            "📥 Tải về", 
            data=towrite, 
            file_name=f"bao_duong_{start_date}_{end_date}.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    
