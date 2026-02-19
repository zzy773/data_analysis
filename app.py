import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor

# 1. 页面配置与 CSS 优化
st.set_page_config(page_title="A股极速回测系统", layout="wide")

st.markdown(
    """
    <style>
    * { -webkit-touch-callout: none !important; -webkit-user-select: none !important; }
    .js-plotly-plot .plotly .main-svg { touch-action: pan-y !important; }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("🚀 A股组合分层分析系统 (并行加速版)")

# --- 侧边栏参数 ---
st.sidebar.header("参数设置")
start_date_input = st.sidebar.text_input("起始时间 (YYYYMMDD)", "20230101")
end_date_input = st.sidebar.text_input("结束时间 (YYYYMMDD)", "20240101")
tickers_input = st.sidebar.text_input("股票代码", "002851,002865,603061,603667")

# --- 核心函数：利用缓存减少重复抓取 ---
@st.cache_data(ttl=3600) # 缓存有效时间1小时
def get_single_stock_data(ticker, start, end):
    """并行调用的单个数据抓取任务"""
    try:
        df = ak.stock_zh_a_hist(symbol=ticker, period="daily", start_date=start, end_date=end, adjust="qfq")
        if not df.empty:
            df['日期'] = pd.to_datetime(df['日期'])
            return ticker, df[['日期', '收盘']]
    except:
        return ticker, None

@st.cache_data(ttl=86400)
def get_all_names():
    """一次性获取全市场代码名称映射"""
    try:
        df = ak.stock_zh_a_spot_em()
        return dict(zip(df['代码'], df['名称']))
    except:
        return {}

if st.sidebar.button("开始回测"):
    tickers = [t.strip() for t in tickers_input.replace('，', ',').split(',') if t.strip()]
    
    with st.spinner('正在并行抓取全球数据节点...'):
        start_dt = datetime.strptime(start_date_input, "%Y%m%d")
        fetch_start_str = (start_dt - timedelta(days=15)).strftime("%Y%m%d")
        
        # --- 优化1：多线程并行下载 ---
        all_data = []
        with ThreadPoolExecutor(max_workers=len(tickers)) as executor:
            futures = [executor.submit(get_single_stock_data, t, fetch_start_str, end_date_input) for t in tickers]
            all_data = [f.result() for f in futures]
        
        # --- 优化2：名称映射异步获取 ---
        name_dict = get_all_names()
        
        close_prices = pd.DataFrame()
        stock_names = {}
        
        for ticker, df in all_data:
            if df is not None:
                df = df.set_index('日期')
                close_prices[ticker] = df['收盘']
                stock_names[ticker] = name_dict.get(ticker, ticker)
        
        close_prices.dropna(inplace=True)
        if close_prices.empty:
            st.error("数据节点连接失败，请重试")
            st.stop()

        # --- 计算逻辑 ---
        daily_returns = close_prices.pct_change().dropna()
        daily_returns = daily_returns[daily_returns.index >= pd.to_datetime(start_date_input)]
        
        portfolio_return = daily_returns.mean(axis=1)
        cumulative_return = (1 + portfolio_return).cumprod()
        individual_cum_returns = (1 + daily_returns).cumprod()
        drawdown = (cumulative_return - cumulative_return.cummax()) / cumulative_return.cummax()

        # --- 绘图逻辑：4层子图 ---
        dt_breaks = pd.date_range(start=cumulative_return.index.min(), end=cumulative_return.index.max()).difference(cumulative_return.index).strftime('%Y-%m-%d').tolist()

        fig = make_subplots(
            rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04, 
            row_heights=[0.3, 0.2, 0.2, 0.3],
            subplot_titles=("1. 组合累积净值", "2. 组合每日涨跌 (%)", "3. 组合最大回撤 (%)", "4. 个股累积贡献对比")
        )

        date_display = cumulative_return.index.strftime('%Y年%m月%d日')

        # 子图数据填充（保持百分比与中文日期显示）
        fig.add_trace(go.Scatter(x=cumulative_return.index, y=cumulative_return, name='组合', line=dict(color='#ff4b4b', width=3),
                                 customdata=list(zip(date_display, [f"{(y-1)*100:+.2f}%" for y in cumulative_return])),
                                 hovertemplate='<b>组合总计</b><br>%{customdata[0]}<br>净值: %{y:.4f}<br>累计增长: %{customdata[1]}<extra></extra>'), row=1, col=1)

        fig.add_trace(go.Bar(x=portfolio_return.index, y=portfolio_return, name='涨跌', marker_color='#3b82f6', opacity=0.7,
                             customdata=list(zip(date_display, [f"{v*100:+.2f}%" for v in portfolio_return])),
                             hovertemplate='<b>%{customdata[0]}</b><br>当日涨跌: %{customdata[1]}<extra></extra>'), row=2, col=1)

        fig.add_trace(go.Scatter(x=drawdown.index, y=drawdown, name='回撤', fill='tozeroy', fillcolor='rgba(34, 197, 94, 0.2)', line=dict(color='#22c55e'),
                                 customdata=list(zip(date_display, [f"{v*100:.2f}%" for v in drawdown])),
                                 hovertemplate='<b>%{customdata[0]}</b><br>动态回撤: %{customdata[1]}<extra></extra>'), row=3, col=1)

        colors = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3']
        for i, ticker in enumerate(tickers):
            if ticker in individual_cum_returns.columns:
                name = stock_names.get(ticker, ticker)
                y_val = individual_cum_returns[ticker]
                fig.add_trace(go.Scatter(x=individual_cum_returns.index, y=y_val, name=name, mode='lines',
                                         line=dict(width=1.8, color=colors[i % len(colors)]),
                                         customdata=list(zip(date_display, [f"{v*100-100:+.2f}%" for v in y_val])),
                                         hovertemplate=f'<b>{name}</b><br>%{{customdata[0]}}<br>累计增长: %{{customdata[1]}}<extra></extra>'), row=4, col=1)

        fig.update_layout(height=950, margin=dict(l=10, r=10, t=50, b=20), hovermode="closest", dragmode=False, showlegend=False)
        fig.update_xaxes(rangebreaks=[dict(values=dt_breaks)], tickformat="%y-%m-%d", showspikes=True, spikemode='across')
        fig.update_yaxes(fixedrange=True)

        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        
        st.subheader("📊 表现排名")
        final_perf = (individual_cum_returns.iloc[-1] - 1).sort_values(ascending=False)
        st.table(pd.DataFrame({"股票": [stock_names.get(c, c) for c in final_perf.index], "收益": final_perf.values}).style.format({"收益": "{:.2%}"}))
