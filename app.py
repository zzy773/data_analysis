import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor

# Streamlit 页面配置
st.set_page_config(page_title="A股极速回测系统", layout="wide")

# 注入 CSS 优化触控
st.markdown(
    """<style>
    * { -webkit-touch-callout: none !important; -webkit-user-select: none !important; }
    .js-plotly-plot .plotly .main-svg { touch-action: pan-y !important; }
    </style>""", 
    unsafe_allow_html=True
)

st.title("⚡ A股分层分析 (极致加速版)")

# --- 侧边栏 ---
st.sidebar.header("参数设置")
start_input = st.sidebar.text_input("起始时间", "20230101")
end_input = st.sidebar.text_input("结束时间", "20240101")
tickers_input = st.sidebar.text_input("股票代码", "002851,002865,603061,603667")

# --- 极速数据抓取函数 ---
@st.cache_data(ttl=3600)
def fetch_data(ticker, start, end):
    """只抓取收盘价，不执行任何额外逻辑"""
    try:
        df = ak.stock_zh_a_hist(symbol=ticker, period="daily", start_date=start, end_date=end, adjust="qfq")
        if not df.empty:
            return ticker, df[['日期', '收盘']].set_index('日期')
    except:
        return ticker, None

if st.sidebar.button("开始回测"):
    tickers = [t.strip() for t in tickers_input.replace('，', ',').split(',') if t.strip()]
    
    with st.spinner('并发抓取中...'):
        start_dt = datetime.strptime(start_input, "%Y%m%d")
        fetch_start = (start_dt - timedelta(days=15)).strftime("%Y%m%d")
        
        # 优化：开启多线程并发，数量等于代码数量
        with ThreadPoolExecutor(max_workers=len(tickers)) as executor:
            results = list(executor.map(lambda t: fetch_data(t, fetch_start, end_input), tickers))
        
        close_prices = pd.DataFrame()
        for ticker, df in results:
            if df is not None:
                close_prices[ticker] = df['收盘']
        
        close_prices.index = pd.to_datetime(close_prices.index)
        close_prices.dropna(inplace=True)
        
        if close_prices.empty:
            st.error("接口响应超时，请重试。")
            st.stop()

        # --- 计算指标 ---
        daily_returns = close_prices.pct_change().dropna()
        daily_returns = daily_returns[daily_returns.index >= pd.to_datetime(start_input)]
        
        portfolio_ret = daily_returns.mean(axis=1)
        cum_ret = (1 + portfolio_ret).cumprod()
        indiv_cum_ret = (1 + daily_returns).cumprod()
        drawdown = (cum_ret - cum_ret.cummax()) / cum_ret.cummax()

        # --- 四层绘图逻辑 ---
        dt_breaks = pd.date_range(start=cum_ret.index.min(), end=cum_ret.index.max()).difference(cum_ret.index).strftime('%Y-%m-%d').tolist()
        date_disp = cum_ret.index.strftime('%Y年%m月%d日')

        fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04, 
                            row_heights=[0.3, 0.2, 0.2, 0.3],
                            subplot_titles=("1. 组合累积净值", "2. 组合当日涨跌 (%)", "3. 组合最大回撤 (%)", "4. 个股累积贡献对比"))

        # 1. 组合净值
        fig.add_trace(go.Scatter(x=cum_ret.index, y=cum_ret, name='组合', line=dict(color='#ff4b4b', width=3),
                                 customdata=list(zip(date_disp, [f"{(y-1)*100:+.2f}%" for y in cum_ret])),
                                 hovertemplate='<b>%{customdata[0]}</b><br>净值: %{y:.4f}<br>累计增长: %{customdata[1]}<extra></extra>'), row=1, col=1)

        # 2. 每日涨跌
        fig.add_trace(go.Bar(x=portfolio_ret.index, y=portfolio_ret, marker_color='#3b82f6',
                             customdata=list(zip(date_disp, [f"{v*100:+.2f}%" for v in portfolio_ret])),
                             hovertemplate='<b>%{customdata[0]}</b><br>当日涨跌: %{customdata[1]}<extra></extra>'), row=2, col=1)

        # 3. 回撤
        fig.add_trace(go.Scatter(x=drawdown.index, y=drawdown, fill='tozeroy', fillcolor='rgba(34, 197, 94, 0.2)', line=dict(color='#22c55e'),
                                 customdata=list(zip(date_disp, [f"{v*100:.2f}%" for v in drawdown])),
                                 hovertemplate='<b>%{customdata[0]}</b><br>回撤: %{customdata[1]}<extra></extra>'), row=3, col=1)

        # 4. 个股贡献
        colors = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A']
        for i, t in enumerate(tickers):
            if t in indiv_cum_ret.columns:
                y_val = indiv_cum_ret[t]
                fig.add_trace(go.Scatter(x=indiv_cum_ret.index, y=y_val, name=t, mode='lines', line=dict(width=1.8, color=colors[i % len(colors)]),
                                         customdata=list(zip(date_disp, [f"{v*100-100:+.2f}%" for v in y_val])),
                                         hovertemplate=f'<b>代码:{t}</b><br>%{{customdata[0]}}<br>累计: %{{customdata[1]}}<extra></extra>'), row=4, col=1)

        fig.update_layout(height=900, margin=dict(l=10, r=10, t=50, b=20), hovermode="closest", dragmode=False, showlegend=False)
        fig.update_xaxes(rangebreaks=[dict(values=dt_breaks)], tickformat="%y-%m-%d", showspikes=True, spikemode='across')
        fig.update_yaxes(fixedrange=True)

        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
