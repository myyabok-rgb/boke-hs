import streamlit as st
import pandas as pd
import os
import io
import json
import requests
import urllib3
import math

# ==========================================
# 0. 环境与安全配置
# ==========================================
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('all_proxy', None)

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# 【宋总专用】API Key
MY_GEMINI_KEY = "AIzaSyASNbmrtVz6eOoqb7mo73TsUUPEk46FeM4"

# ==========================================
# 1. 界面配置
# ==========================================
st.set_page_config(page_title="博克智能·全库算力版", page_icon="🏭", layout="wide")

st.markdown("""
<style>
/* 按钮样式 */
div.stButton > button:first-child {
    background-color: #FF6600 !important;
    color: white !important;
    border: none;
    font-size: 18px !important;
    font-weight: bold;
    padding: 0.5rem 2rem;
    border-radius: 8px;
    width: 100%;
}
/* 结果卡片样式 */
.ai-card {
    background-color: #e8f4f8;
    border-left: 5px solid #00a0e9;
    padding: 10px;
    border-radius: 5px;
    margin-bottom: 10px;
    font-size: 14px;
    color: #333;
}
.audit-box {
    background-color: #f0f2f6;
    border-left: 5px solid #FF6600;
    padding: 15px;
    border-radius: 5px;
    margin-bottom: 20px;
    font-size: 14px;
}
.opt-box {
    background-color: #fff3cd;
    border-left: 5px solid #ffc107;
    padding: 10px;
    margin-top: 5px;
    font-size: 14px;
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 基础功能模块
# ==========================================
def find_key_file():
    candidates = ['boke_key.json', 'drive_key.json', 'client_secret.json']
    for f in candidates:
        if os.path.exists(f): return f
    return None

KEY_FILE = find_key_file()
TARGET_FILE_KEYWORD = "配件价格"

@st.cache_resource
def init_drive_service():
    if not KEY_FILE: return None, "❌ 未找到密钥文件"
    try:
        creds = service_account.Credentials.from_service_account_file(
            KEY_FILE, scopes=['https://www.googleapis.com/auth/drive.readonly'])
        service = build('drive', 'v3', credentials=creds)
        return service, "OK"
    except Exception as e:
        return None, str(e)

# ==========================================
# 3. AI核心函数
# ==========================================
def call_gemini_direct_v30(prompt):
    if not MY_GEMINI_KEY: return None, "Key未配置"
    models = ["gemini-1.5-flash", "gemini-pro"]
    headers = {'Content-Type': 'application/json'}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    session = requests.Session()
    session.trust_env = False 

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={MY_GEMINI_KEY}"
        try:
            response = session.post(url, headers=headers, json=data, timeout=10, verify=False)
            if response.status_code == 200:
                result = response.json()
                text = result['candidates'][0]['content']['parts'][0]['text']
                return text, model
        except: continue
    return None, "网络阻断"

def ask_ai_chemist(medium, vol):
    prompt = f"""
    作为化工设备专家，请根据介质【{medium}】和容积【{vol}立方】：
    1. 估算介质常温粘度。
    2. 推荐搅拌器形式(锚式/桨式/涡轮)。
    3. 估算电机功率(kW)。
    请仅返回标准JSON格式，不要Markdown: {{"viscosity": "xx cP", "type": "xx式", "power": 数值, "reason": "简短理由"}}
    """
    ai_text, info = call_gemini_direct_v30(prompt)
    fallback = {"viscosity": "AI连接失败", "type": "通用桨式", "power": 5.5, "reason": "本地兜底"}
    if not ai_text: return fallback
    try:
        clean = ai_text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean)
    except: return fallback

def ask_ai_market(query):
    prompt = f"作为采购专家回答，请简练给出数据：{query}"
    text, info = call_gemini_direct_v30(prompt)
    return text if text else f"⚠️ 查询失败: {info}"

def real_search_and_download(service):
    logs = ["📡 连接云端数据库..."]
    try:
        query = f"name contains '{TARGET_FILE_KEYWORD}' and mimeType contains 'spreadsheet' and trashed=false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        if not files: return None, logs
        target = files[0]
        request = service.files().get_media(fileId=target['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False: status, done = downloader.next_chunk()
        fh.seek(0)
        return pd.read_excel(fh), logs
    except: return None, logs

# ==========================================
# 4. 侧边栏 (保持原样)
# ==========================================
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_container_width=True)
else:
    st.sidebar.markdown("## 🔆 **Bok Smart**")

st.sidebar.markdown("---")
service, status_msg = init_drive_service()
if service:
    st.sidebar.success(f"🟢 云端在线")
else:
    st.sidebar.warning(f"🟡 本地模式")

if MY_GEMINI_KEY:
    st.sidebar.success(f"🧠 AI 引擎就绪")

st.sidebar.subheader("⚙️ 实时基价 (元/kg)")
p_304 = st.sidebar.number_input("S30408", value=45.0, step=0.5)
p_314 = st.sidebar.number_input("S31403", value=55.0, step=0.5)
p_31608 = st.sidebar.number_input("S31608", value=25.0, step=0.5)
p_31603 = st.sidebar.number_input("S31603", value=55.0, step=0.5)
p_345 = st.sidebar.number_input("Q345R", value=25.0, step=0.5)
p_235 = st.sidebar.number_input("Q235", value=20.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.markdown("**🔹 自定义材质**")
custom_mat_name = st.sidebar.text_input("材质名称", placeholder="如: 钛材 TA2")
custom_mat_price = st.sidebar.number_input("材质单价 (元/kg)", value=0.0, step=10.0)

st.sidebar.markdown("---")
st.sidebar.subheader("🛠️ 加工费率")
cost_fab_ton = st.sidebar.number_input("设备制作费 (元/吨)", value=2500.0, step=100.0)
cost_weld_m = st.sidebar.number_input("半管焊接费 (元/米)", value=50.0, step=5.0)
cost_polish_m2 = st.sidebar.number_input("抛光费 (元/平方)", value=200.0, step=10.0)
cost_ndt_m = st.sidebar.number_input("探伤费 (元/米)", value=100.0, step=10.0)
cost_cold_stretch = 300.0 # 隐形参数

st.sidebar.markdown("---")
st.sidebar.markdown("**🔹 自定义费用**")
custom_fee_name = st.sidebar.text_input("费用名称", placeholder="如: 设计费/运输费")
custom_fee_amount = st.sidebar.number_input("费用金额 (元)", value=0.0, step=100.0)

PRICES = {
    "S30408": p_304, "S31403": p_314, "S31608": p_31608,
    "S31603": p_31603, "Q345R": p_345, "Q235": p_235,
    "CUSTOM_MAT_PRICE": custom_mat_price,
    "FAB_TON": cost_fab_ton, "WELD_M": cost_weld_m,
    "POLISH_M2": cost_polish_m2, "NDT_M": cost_ndt_m,
    "CUSTOM_FEE": custom_fee_amount,
    "COLD_STRETCH_VOL": cost_cold_stretch
}

# ==========================================
# 5. 核心计算 (隐形冷拉伸逻辑)
# ==========================================
def calculate_cost_internal(vol, mat, press, heat_type, dn, qty, polish, is_cold_stretch, prices):
    dia = 1600 if vol <= 5 else 2000
    if vol > 20: dia = 2400
    height = (vol * 1e9 / (3.14 * (dia/2)**2)) + 600
    
    P_c = max(abs(press) * 1.1, 0.2)
    # 许用应力判断
    if is_cold_stretch and ("304" in mat or "316" in mat or "314" in mat):
        sigma = 305
        phi = 0.85
        t_calc = (P_c * dia) / (2 * sigma * phi - P_c)
        delta = math.ceil(t_calc + 0.5) 
    else:
        sigma = 137
        if "345" in mat: sigma = 189
        if "235" in mat: sigma = 113
        phi = 0.85
        t_calc = (P_c * dia) / (2 * sigma * phi - P_c)
        delta = math.ceil(t_calc + 1.0)
        
    if delta < 3: delta = 3

    density = 7.93 if "304" in mat else 7.85
    w_body = ((3.14*dia*height/1e6)*delta*density + 2*(1.25*(dia/1000)**2*(delta+2)*density))
    
    u_price = prices.get(mat, 45)
    if mat == "自定义": u_price = prices["CUSTOM_MAT_PRICE"]
    
    cost_mat = w_body * u_price
    w_ag = 300 + vol*30
    cost_ag = 3500 + w_ag*35
    w_heat = vol * 150 if "半管" in str(heat_type) else 0
    cost_heat = w_heat * (u_price + 10)
    cost_fab = ((w_body + w_heat)/1000) * prices["FAB_TON"]
    
    cost_cs_op = 0
    if is_cold_stretch:
        cost_cs_op = vol * prices["COLD_STRETCH_VOL"]
        
    cost_misc = qty*300 + 3500 + (vol*800 if "抛光" in str(polish) else 0)
    
    total = cost_mat + cost_ag + cost_heat + cost_fab + cost_cs_op + cost_misc
    return total, delta

def run_calculation_v30(eq_type, vol, mat, press, medium, polish, heat_type, nozzle_dn, nozzle_qty, sidebar_prices, real_df, file_obj):
    logs = []
    opts = []
    
    # 1. 常规计算
    total_std, delta_std = calculate_cost_internal(vol, mat, press, heat_type, nozzle_dn, nozzle_qty, polish, False, sidebar_prices)
    
    # 2. 隐形冷拉伸测算
    if "304" in mat or "316" in mat or "314" in mat:
        total_cs, delta_cs = calculate_cost_internal(vol, mat, press, heat_type, nozzle_dn, nozzle_qty, polish, True, sidebar_prices)
        saving = total_std - total_cs
        if saving > 0:
            opts.append(f"💡 **冷拉伸工艺降本**：壁厚可由 {delta_std}mm 减至 {delta_cs}mm，预估节省 ¥{saving:,.0f}")
            
    if press < 0: opts.append("⚠️ **真空降本**：建议采用加强圈方案，筒体壁厚可进一步减薄。")
    if "304" in str(mat): opts.append(f"💡 **材积互换**：若介质允许，改用 Q345R+衬里 可省约 ¥{total_std*0.25:,.0f}。")
    
    audit_data = {
        "设计规范": "GB/T 150-2011", 
        "计算压力": f"{max(abs(press)*1.1, 0.2):.2f} MPa",
        "常规方案壁厚": f"{delta_std} mm"
    }
    
    ai_data = ask_ai_chemist(medium, vol)
    
    df_bom = pd.DataFrame([
        {"项目": "设备主体", "描述": f"常规设计 ({delta_std}mm)", "金额": int(total_std * 0.5)},
        {"项目": "搅拌系统(AI)", "描述": ai_data.get('type'), "金额": int(total_std * 0.15)},
        {"项目": "制作与辅材", "描述": "含法兰/接管/工费", "金额": int(total_std * 0.35)}
    ])
    
    if file_obj:
        logs.append(f"📄 **图纸已关联**: {file_obj.name}")

    return df_bom, total_std, logs, opts, audit_data, ai_data

# ==========================================
# 6. 主界面布局 (严格按截图对齐)
# ==========================================
st.title("🏭 博克智能 · 全库算力终端")
st.markdown("---")

col1, col2 = st.columns(2)

# --- 左列 ---
with col1:
    st.subheader("📝 设备参数")
    eq_type = st.selectbox("设备类型", ["反应釜", "换热器", "储罐", "塔器"])
    
    # 材质 + 压力 (在同一行)
    c1_sub, c2_sub = st.columns(2)
    with c1_sub:
        eq_mat = st.selectbox("主体材质", ["S30408", "S31403", "S31608", "S31603", "Q345R", "Q235", "自定义"])
    with c2_sub:
        eq_press = st.number_input("压力 (MPa)", value=-0.10, step=0.01)
        
    eq_polish = st.selectbox("表面精度", ["酸洗钝化", "机械抛光Ra0.4", "机械抛光Ra0.6", "机械抛光Ra0.8"])
    st.text_area("备注", "如有特殊要求请注明", height=80)

# --- 右列 ---
with col2:
    st.subheader("🔧 工艺条件")
    # 容积 + 介质 (在同一行)
    c3_sub, c4_sub = st.columns(2)
    with c3_sub:
        eq_vol = st.number_input("容积 (m³)", value=5.00, step=0.5)
    with c4_sub:
        eq_medium = st.text_input("介质", "二元醇")
        
    eq_heat = st.selectbox("换热形式", ["外盘管 (半管)", "整体夹套", "内盘管", "无"])
    
    # 口径 + 数量 (在同一行)
    c5_sub, c6_sub = st.columns(2)
    with c5_sub:
        eq_dn = st.selectbox("接管口径", ["DN25", "DN50", "DN60", "DN80", "DN100", "DN150"])
    with c6_sub:
        eq_qty = st.number_input("接管数量", value=8, step=1)
    
    # 【关键修改】去掉 st.markdown 标题，直接写在 label 里，保证绝对对齐
    uploaded_file = st.file_uploader("上传图片", type=['png', 'jpg', 'pdf'])

st.markdown("---")

if st.button("🚀 全库检索并计算"):
    with st.status("📡 正在执行博克智能计算程序...", expanded=True) as status:
        real_df, d_logs = None, []
        if service:
            real_df, d_logs = real_search_and_download(service)
        
        st.write(f"🧠 AI 正在分析介质【{eq_medium}】特性...")
        
        df_bom, total, c_logs, opts, audit, ai_res = run_calculation_v30(
            eq_type, eq_vol, eq_mat, eq_press, eq_medium, eq_polish,
            eq_heat, eq_dn, eq_qty, PRICES, real_df, uploaded_file
        )
        
        status.update(label="✅ 计算完成", state="complete", expanded=False)
        
        # 结果展示
        st.markdown("### 📊 详细统计报告")
        
        st.markdown(f"""
        <div class="ai-card">
        <strong>🤖 AI搅拌选型建议：</strong><br>
        介质特性：{ai_res.get('viscosity', '未知')} | 推荐桨型：{ai_res.get('type', '通用')}<br>
        匹配功率：{ai_res.get('power', 0)} kW | 理由：{ai_res.get('reason', 'AI未返回')}
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(f"""
        <div class="audit-box">
        <strong>🛡️ 技术审计：</strong>
        规范：{audit['设计规范']} | 常规方案壁厚：{audit['常规方案壁厚']} | 计算压力：{audit['计算压力']}
        </div>
        """, unsafe_allow_html=True)
        
        c_res1, c_res2 = st.columns([3, 1])
        with c_res1:
            st.dataframe(df_bom, use_container_width=True, hide_index=True)
            st.markdown("#### 💡 成本优化建议")
            if not opts: st.info("✅ 当前方案已最优")
            else:
                for opt in opts:
                    st.markdown(f'<div class="opt-box">{opt}</div>', unsafe_allow_html=True)
                    
        with c_res2:
            st.metric("含税总价", f"¥{total:,.0f}")
            
    with st.expander("🔮 AI 市场行情与技术查询"):
        q = st.text_input("向AI提问", "查询S30408今日行情")
        if st.button("查询"):
            st.info("AI 检索中...")