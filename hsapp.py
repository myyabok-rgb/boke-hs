import streamlit as st
import pandas as pd
import os
import io
import json
import requests
import urllib3
import math

# ==========================================
# 0. 安全配置
# ==========================================
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# 【宋总专用】API Key
MY_GEMINI_KEY = "AIzaSyASNbmrtVz6eOoqb7mo73TsUUPEk46FeM4"

# ==========================================
# 1. 界面样式 (强制对齐)
# ==========================================
st.set_page_config(page_title="博克智能·全库算力终端", page_icon="🏭", layout="wide")

st.markdown("""
<style>
/* 按钮高度强制与输入框对齐 */
div.stButton > button {
    height: 43px; /* 标准输入框高度 */
    margin-top: 0px;
    padding-top: 0px;
    padding-bottom: 0px;
    width: 100%;
}
/* 调整列间距，让加号和发送键紧贴输入框 */
[data-testid="column"] {
    padding-left: 5px !important;
    padding-right: 5px !important;
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 基础功能
# ==========================================
def find_key_file():
    candidates = ['boke_key.json', 'drive_key.json', 'client_secret.json']
    for f in candidates:
        if os.path.exists(f): return f
    return None

KEY_FILE = find_key_file()

@st.cache_resource
def init_drive_service():
    if not KEY_FILE: return None, "❌ 密钥缺失"
    try:
        creds = service_account.Credentials.from_service_account_file(
            KEY_FILE, scopes=['https://www.googleapis.com/auth/drive.readonly'])
        service = build('drive', 'v3', credentials=creds)
        return service, "OK"
    except Exception as e:
        return None, str(e)

# ==========================================
# 3. AI 核心函数 (手动代理通道)
# ==========================================
def setup_proxy(user_port):
    """如果用户填了端口，强制设置代理"""
    if user_port:
        proxy_url = f"http://127.0.0.1:{user_port}"
        os.environ["HTTP_PROXY"] = proxy_url
        os.environ["HTTPS_PROXY"] = proxy_url
        return True
    return False

def call_gemini_direct_v30(prompt):
    if not MY_GEMINI_KEY: return None, "Key未配置"
    
    # 使用 v1 稳定版
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent?key={MY_GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    session = requests.Session()
    session.trust_env = True # 信任系统/手动设置的代理
    
    try:
        response = session.post(url, headers=headers, json=data, timeout=15, verify=False)
        if response.status_code == 200:
            result = response.json()
            if 'candidates' in result and result['candidates']:
                return result['candidates'][0]['content']['parts'][0]['text'], "OK"
        return None, f"谷歌拒绝: {response.status_code}"
    except Exception as e:
        return None, f"连不上: {str(e)}"

def ask_ai_market_with_context(query, service):
    data_context = ""
    if service:
        try:
            query_files = "mimeType contains 'spreadsheet' and trashed=false"
            results = service.files().list(q=query_files, fields="files(id, name)").execute()
            files = results.get('files', [])
            dfs = []
            for file in files[:1]: # 只读1个最新的，求快
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False: _, done = downloader.next_chunk()
                fh.seek(0)
                df = pd.read_excel(fh)
                dfs.append(df.head(50))
            if dfs:
                full_df = pd.concat(dfs, ignore_index=True)
                data_context = f"\n【云端数据】:\n{full_df.to_string(index=False)}\n"
        except: pass

    prompt = f"你是博克业务助手。{data_context} 用户问: {query}"
    text, info = call_gemini_direct_v30(prompt)
    return text if text else f"⚠️ {info}"

def ask_ai_chemist(medium, vol):
    prompt = f"""
    作为化工设备专家，请根据介质【{medium}】和容积【{vol}立方】：
    1. 估算介质常温粘度。
    2. 推荐搅拌器形式。
    3. 估算电机功率(kW)。
    请仅返回JSON: {{"viscosity": "xx", "type": "xx", "power": 数值, "reason": "xx"}}
    """
    ai_text, info = call_gemini_direct_v30(prompt)
    fallback = {"viscosity": "网络中断", "type": "通用桨式", "power": 5.5, "reason": "无法连接AI"}
    if not ai_text: return fallback
    try:
        clean = ai_text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean)
    except: return fallback

# ==========================================
# 4. 侧边栏 (原封不动还原)
# ==========================================
if os.path.exists("logo.png"):
    st.sidebar.image("logo.png", use_container_width=True)
else:
    st.sidebar.markdown("## 🔆 **Bok Smart**")

st.sidebar.markdown("---")

# 🔥【新功能】代理修复通道
with st.sidebar.expander("🛠️ 网络修复 (连不上点这里)", expanded=False):
    st.caption("如果您开了快连还是报错，请查看快连设置里的'HTTP端口'，填入下方：")
    user_proxy_port = st.text_input("代理端口", placeholder="例如 10809")
    if user_proxy_port:
        setup_proxy(user_proxy_port)
        st.sidebar.success(f"已强制指向端口: {user_proxy_port}")

service, status_msg = init_drive_service()
if service: st.sidebar.success("🟢 云端在线")
else: st.sidebar.warning("🟡 离线模式")

# 1. 材质基价
st.sidebar.subheader("⚙️ 实时基价 (元/kg)")
p_304 = st.sidebar.number_input("S30408", value=45.0, step=0.5)
p_314 = st.sidebar.number_input("S31403", value=55.0, step=0.5)
p_31608 = st.sidebar.number_input("S31608", value=25.0, step=0.5)
p_31603 = st.sidebar.number_input("S31603", value=55.0, step=0.5)
p_345 = st.sidebar.number_input("Q345R", value=25.0, step=0.5)
p_235 = st.sidebar.number_input("Q235", value=20.0, step=0.5)

st.sidebar.markdown("---")
# 2. 自定义材质
st.sidebar.markdown("**🔹 自定义材质**")
custom_mat_name = st.sidebar.text_input("材质名称", placeholder="如: 钛材 TA2")
custom_mat_price = st.sidebar.number_input("材质单价 (元/kg)", value=0.0, step=10.0)

st.sidebar.markdown("---")
# 3. 加工费率
st.sidebar.subheader("🛠️ 加工费率")
cost_fab_ton = st.sidebar.number_input("设备制作费 (元/吨)", value=2500.0, step=100.0)
cost_weld_m = st.sidebar.number_input("半管焊接费 (元/米)", value=50.0, step=5.0)
cost_polish_m2 = st.sidebar.number_input("抛光费 (元/平方)", value=200.0, step=10.0)
cost_ndt_m = st.sidebar.number_input("探伤费 (元/米)", value=100.0, step=10.0)
cost_cold_stretch = 300.0 

st.sidebar.markdown("---")
# 4. 自定义费用
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
# 5. 计算逻辑
# ==========================================
def run_calculation_v30(vol, mat, press, medium, polish, heat_type, qty, prices):
    dia = 1600 if vol <= 5 else 2000
    if vol > 20: dia = 2400
    height = (vol * 1e9 / (3.14 * (dia/2)**2)) + 600
    P_c = max(abs(press) * 1.1, 0.2)
    
    sigma = 137
    if "345" in mat: sigma = 189
    if "235" in mat: sigma = 113
    
    t_calc = (P_c * dia) / (2 * sigma * 0.85 - P_c)
    delta = math.ceil(t_calc + 1.0)
    if delta < 3: delta = 3

    density = 7.93 if "304" in mat else 7.85
    w_body = ((3.14*dia*height/1e6)*delta*density + 2*(1.25*(dia/1000)**2*(delta+2)*density))
    
    u_price = prices.get(mat, 45)
    if mat == "自定义": u_price = prices["CUSTOM_MAT_PRICE"]
    
    total = w_body * u_price * 1.5 
    
    ai_res = ask_ai_chemist(medium, vol)
    
    df_bom = pd.DataFrame([
        {"项目": "设备主体", "金额": int(total * 0.6)},
        {"项目": "搅拌系统", "金额": int(total * 0.2)},
        {"项目": "辅材/抛光", "金额": int(total * 0.2)},
    ])
    return df_bom, total, delta, ai_res

# ==========================================
# 6. 主界面 (按图纸严丝合缝)
# ==========================================
st.title("🏭 博克智能 · 全库算力终端")
st.markdown("---")

col1, col2 = st.columns(2)

# ================== 左侧列 ==================
with col1:
    st.subheader("📝 设备参数")
    eq_type = st.selectbox("设备类型", ["反应釜", "换热器", "储罐", "塔器"])
    
    c1a, c1b = st.columns(2)
    with c1a: eq_mat = st.selectbox("主体材质", ["S30408", "S31403", "S31608", "S31603", "Q345R", "Q235", "自定义"])
    with c1b: eq_press = st.number_input("压力 (MPa)", -0.10, step=0.01)
        
    eq_polish = st.selectbox("表面精度", ["酸洗钝化", "机械抛光Ra0.4", "机械抛光Ra0.6", "机械抛光Ra0.8"])
    
    st.markdown("---")
    st.markdown("**AI 业务助手**")
    
    # 🔥 1:6:2 完美比例布局
    chat_c1, chat_c2, chat_c3 = st.columns([1, 6, 2])
    
    with chat_c1:
        # 小+号: 使用 popover 完美实现折叠上传
        with st.popover("➕", use_container_width=True):
            uploaded_file = st.file_uploader("选文件", type=['png', 'jpg', 'pdf', 'xlsx'], label_visibility="collapsed")
            
    with chat_c2:
        # 输入框: label_visibility="collapsed" 去掉标题占位
        chat_input_val = st.text_input("msg", placeholder="输入...", label_visibility="collapsed")
        
    with chat_c3:
        # 发送键: 宽度填满
        send_pressed = st.button("发送", use_container_width=True)

    # 消息反馈区
    if send_pressed and chat_input_val:
        with st.spinner("Connecting..."):
            ans = ask_ai_market_with_context(chat_input_val, service)
            if uploaded_file: st.caption(f"已传: {uploaded_file.name}")
            st.info(f"🤖 {ans}")

    # 开始计算按钮 (左侧最底)
    st.markdown("<br>", unsafe_allow_html=True)
    calc_btn = st.button("🚀 开始AI核算", use_container_width=True)

# ================== 右侧列 ==================
with col2:
    st.subheader("🔧 工艺条件")
    c2a, c2b = st.columns(2)
    with c2a: eq_vol = st.number_input("容积 (m³)", 5.0, step=0.5)
    with c2b: eq_medium = st.text_input("介质", "二元醇")
    
    eq_heat = st.selectbox("换热形式", ["外盘管 (半管)", "整体夹套", "内盘管", "无"])
    
    c2c, c2d = st.columns(2)
    with c2c: eq_dn = st.selectbox("接管口径", ["DN25", "DN50", "DN60", "DN80", "DN100", "DN150"])
    with c2d: eq_qty = st.number_input("接管数量", 8)
    
    st.markdown("---")
    st.markdown("**备注**")
    # 备注框高度设为 130，和左边对话区高度强行对齐
    st.text_area("Remarks", "如有特殊要求请注明", height=130, label_visibility="collapsed")

# ==========================================
# 7. 计算执行
# ==========================================
if calc_btn:
    st.markdown("---")
    st.markdown("### 📊 详细统计报告")
    
    with st.spinner("AI核算中..."):
        df_bom, total, delta, ai_res = run_calculation_v30(
            eq_vol, eq_mat, eq_press, eq_medium, eq_polish, eq_heat, eq_qty, PRICES
        )
    
    st.markdown(f"""
    <div class="ai-card">
    <strong>🤖 AI分析：</strong> 建议搅拌: {ai_res.get('type')} | 功率: {ai_res.get('power')}kW<br>
    理由: {ai_res.get('reason')}
    </div>
    """, unsafe_allow_html=True)
    
    c_res1, c_res2 = st.columns([3, 1])
    with c_res1:
        st.dataframe(df_bom, use_container_width=True, hide_index=True)
    
    with c_res2:
        st.metric("预估总价", f"¥{total:,.0f}")
        st.success("✅ 完成")
