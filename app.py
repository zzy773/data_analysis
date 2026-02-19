import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor

# 1. 页面配置与手机端触摸优化
st.set_page_config(page_title="A股组合深度分析系统", layout="wide")

st.markdown(
    """
    <style>
    /* 解决手机端长按弹出菜单遮挡 */
    * { -webkit-touch-callout: none !important; -webkit-user-select: none !important; }
    /* 允许垂直滚动网页，优化图表触摸追踪 */
    .js-plotly-plot .plotly .main-svg { touch-action: pan-y !important; }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("📊 A股组合全维度分析系统")

# --- 极速优化：内存级缓存函数 ---
@st.cache_data(ttl=86400) # 缓存24小时，避免重复抓取全市场5000只股票名称
def get_cached_name_map():
    """获取全市场股票代码到中文简称的映射"""
    try:
        df = ak.stock_zh_a_spot_em()
        return dict(zip(df['代码'], df['名称']))
    except:
        return {}

@st.cache_data(ttl=3600) # 历史行情缓存1小时
def fetch_stock_data(ticker, start, end):
    """并行调用的单股抓取任务"""
    try:
        df = ak.stock_zh_a_hist(symbol=ticker, period="daily", start_date=start, end_date=end, adjust="qfq")
        if not df.empty:
            df['日期'] = pd.to_datetime(df['日期'])
            return ticker, df[['日期', '收盘']].set_index('日期')
    except:
        return ticker, None

# --- 侧边栏参数 ---
st.sidebar.header("回测配置")
start_input = st.sidebar.text_input("起始时间 (YYYYMMDD)", "20230101")
end_input = st.sidebar.text_input("结束时间 (YYYYMMDD)", "20240101")
tickers_input = st.sidebar.text_input("股票代码 (逗号分隔)", "002851,002865,603061,603667")

if st.sidebar.button("开始极速回测"):
    tickers = [t.strip() for t in tickers_input.replace('，', ',').split(',') if t.strip()]
    
    with st.spinner('正在执行并行计算与名称解析...'):
        # 1. 获取名称映射（走缓存，极快）
        name_map = get_cached_name_map()
        stock_names = {t: name_map.get(t, t) for t in tickers}
        
        # 2. 并行抓取个股行情
        start_dt = datetime.strptime(start_input, "%Y%m%d")
        fetch_start = (start_dt - timedelta(days=15)).strftime("%Y%m%d")
        
        with ThreadPoolExecutor(max_workers=len(tickers)) as executor:
            results = list(executor.map(lambda t: fetch_stock_data(t, fetch_start, end_input), tickers))
        
        close_prices = pd.DataFrame()
        for ticker, df in results:
            if df is not None:
                close_prices[ticker] = df['收盘']
        
        close_prices.index = pd.to_datetime(close_prices.index)
        close_prices.dropna(inplace=True)
        
        if close_prices.empty:
            st.error("数据节点连接超时，请再次尝试。")
            st.stop()

        # 3. 计算指标
        daily_returns = close_prices.pct_change().dropna()
        daily_returns = daily_returns[daily_returns.index >= pd.to_datetime(start_input)]
        
        portfolio_ret = daily_returns.mean(axis=1)
        cum_ret = (1 + portfolio_ret).cumprod()
        indiv_cum_ret = (1 + daily_returns).cumprod()
        drawdown = (cum_ret - cum_ret.cummax()) / cum_ret.cummax()

        # --- 4. 绘图逻辑：4层结构 ---
        dt_breaks = pd.date_range(start=cum_ret.index.min(), end=cum_ret.index.max()).difference(cum_ret.index).strftime('%Y-%m-%d').tolist()
        date_disp = cum_ret.index.strftime('%Y年%m月%d日')

        fig = make_subplots(
            rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04, 
            row_heights=[0.3, 0.2, 0.2, 0.3],
            subplot_titles=("1. 组合累积净值", "2. 每日涨跌幅 (%)", "3. 动态回撤 (%)", "4. 个股累积贡献对比")
        )

        # 1. 组合净值
        total_growth_hover = [f"{(y-1)*100:+.2f}%" for y in cum_ret]
        fig.add_trace(go.Scatter(
            x=cum_ret.index, y=cum_ret, name='组合总资产', line=dict(color='#ff4b4b', width=3),
            customdata=list(zip(date_disp, total_growth_hover)),
            hovertemplate='<b>%{customdata[0]}</b><br>总净值: %{y:.4f}<br>总增长: %{customdata[1]}<extra></extra>'
        ), row=1, col=1)

        # 第一幅图右上角标注成分
        comp_text = "组合成分: " + ", ".join([stock_names[t] for t in tickers])
        fig.add_annotation(
            text=comp_text, xref="paper", yref="paper", x=1, y=1, 
            showarrow=False, font=dict(size=12, color="#666"), align="right", bgcolor="rgba(255,255,255,0.7)"
        )

        # 2. 每日涨跌
        fig.add_trace(go.Bar(
            x=portfolio_ret.index, y=portfolio_ret, name='当日涨跌', marker_color='#3b82f6', opacity=0.7,
            customdata=list(zip(date_disp, [f"{v*100:+.2f}%" for v in portfolio_ret])),
            hovertemplate='<b>%{customdata[0]}</b><br>当日涨跌: %{customdata[1]}<extra></extra>'
        ), row=2, col=1)

        # 3. 回撤
        fig.add_trace(go.Scatter(
            x=drawdown.index, y=drawdown, name='回撤', fill='tozeroy', fillcolor='rgba(34, 197, 94, 0.2)', line=dict(color='#22c55e'),
            customdata=list(zip(date_disp, [f"{v*100:+.2f}%" for v in drawdown])),
            hovertemplate='<b>%{customdata[0]}</b><br>动态回撤: %{customdata[1]}<extra></extra>'
        ), row=3, col=1)

        # 4. 个股贡献 (开启中文图例)
        colors = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3', '#FF6692']
        for i, t in enumerate(tickers):
            if t in indiv_cum_ret.columns:
                name = stock_names[t]
                y_val = indiv_cum_ret[t]
                fig.add_trace(go.Scatter(
                    x=indiv_cum_ret.index, y=y_val, name=name, mode='lines',
                    line=dict(width=1.8, color=colors[i % len(colors)]),
                    showlegend=True,
                    customdata=list(zip(date_disp, [f"{v*100-100:+.2f}%" for v in y_val])),
                    hovertemplate=f'<b>{name}</b><br>%{{customdata[0]}}<br>累计贡献: %{{customdata
