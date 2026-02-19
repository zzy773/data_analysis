import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from concurrent.futures import ThreadPoolExecutor

# 1. 页面配置
st.set_page_config(page_title="A股组合深度分析系统", layout="wide")

# 注入优化 CSS
st.markdown(
    """<style>
    * { -webkit-touch-callout: none !important; -webkit-user-select: none !important; }
    .js-plotly-plot .plotly .main-svg { touch-action: pan-y !important; }
    </style>""", 
    unsafe_allow_html=True
)

st.title("📊 A股组合全维度回测系统")

# --- 缓存函数：极速获取名称映射 ---
@st.cache_data(ttl=86400)
def get_stock_name_map():
    """获取全市场股票代码到中文简称的映射"""
    try:
        df = ak.stock_zh_a_spot_em()
        return dict(zip(df['代码'], df['名称']))
    except:
        return {}

# --- 缓存函数：极速并发抓取数据 ---
@st.cache_data(ttl=3600)
def fetch_single_stock(ticker, start, end):
    try:
        df = ak.stock_zh_a_hist(symbol=ticker, period="daily", start_date=start, end_date=end, adjust="qfq")
        if not df.empty:
            return ticker, df[['日期', '收盘']].set_index('日期')
    except:
        return ticker, None

# --- 侧边栏 ---
st.sidebar.header("回测配置")
start_input = st.sidebar.text_input("起始时间 (YYYYMMDD)", "20230101")
end_input = st.sidebar.text_input("结束时间 (YYYYMMDD)", "20240101")
tickers_input = st.sidebar.text_input("股票代码 (逗号分隔)", "002851,002865,603061,603667")

if st.sidebar.button("开始深度回测"):
    tickers = [t.strip() for t in tickers_input.replace('，', ',').split(',') if t.strip()]
    
    with st.spinner('正在并发抓取行情并解析中文名称...'):
        # 1. 异步获取名称映射
        name_map = get_stock_name_map()
        stock_names = {t: name_map.get(t, t) for t in tickers}
        
        # 2. 并行下载历史行情
        start_dt = datetime.strptime(start_input, "%Y%m%d")
        fetch_start = (start_dt - timedelta(days=15)).strftime("%Y%m%d")
        
        with ThreadPoolExecutor(max_workers=len(tickers)) as executor:
            results = list(executor.map(lambda t: fetch_single_stock(t, fetch_start, end_input), tickers))
        
        # 3. 整理数据
        close_prices = pd.DataFrame()
        for ticker, df in results:
            if df is not None:
                close_prices[ticker] = df['收盘']
        
        close_prices.index = pd.to_datetime(close_prices.index)
        close_prices.dropna(inplace=True)
        
        if close_prices.empty:
            st.error("数据连接异常，请重试。")
            st.stop()

        # --- 核心计算 ---
        daily_returns = close_prices.pct_change().dropna()
        target_start_date = pd.to_datetime(start_input)
        daily_returns = daily_returns[daily_returns.index >= target_start_date]
        
        portfolio_ret = daily_returns.mean(axis=1)
        cum_ret = (1 + portfolio_ret).cumprod()
        indiv_cum_ret = (1 + daily_returns).cumprod()
        drawdown = (cum_ret - cum_ret.cummax()) / cum_ret.cummax()

        # --- 绘图配置 ---
        dt_breaks = pd.date_range(start=cum_ret.index.min(), end=cum_ret.index.max()).difference(cum_ret.index).strftime('%Y-%m-%d').tolist()
        date_disp = cum_ret.index.strftime('%Y年%m月%d日')

        fig = make_subplots(
            rows=4, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.04, 
            row_heights=[0.3, 0.2, 0.2, 0.3],
            subplot_titles=("1. 组合累积净值走势", "2. 每日涨跌幅 (%)", "3. 动态回撤 (%)", "4. 个股累积贡献对比")
        )

        # 1. 组合净值图
        fig.add_trace(go.Scatter(
            x=cum_ret.index, y=cum_ret, name='组合总资产', 
            line=dict(color='#ff4b4b', width=3),
            customdata=list(zip(date_disp, [f"{(y-1)*100:+.2f}%" for y in cum_ret])),
            hovertemplate='<b>%{customdata[0]}</b><br>组合净值: %{y:.4f}<br>累计增长: %{customdata[1]}<extra></extra>'
        ), row=1, col=1)

        # 【新增：第一幅图右上角标注成分股】
        comp_text = "组合成分: " + ", ".join([stock_names[t] for t in tickers])
        fig.add_annotation(
            text=comp_text, xref="paper", yref="paper",
            x=1, y=1, showarrow=False, font=dict(size=12, color="gray"),
            align="right", bgcolor="rgba(255,255,255,0.7)"
        )

        # 2. 每日涨跌幅
        fig.add_trace(go.Bar(
            x=portfolio_ret.index, y=portfolio_ret, name='每日涨跌', marker_color='#3b82f6', opacity=0.7,
            customdata=list(zip(date_disp, [f"{v*100:+.2f}%" for v in portfolio_ret])),
            hovertemplate='<b>%{customdata[0]}</b><br>当日涨跌: %{customdata[1]}<extra></extra>'
        ), row=2, col=1)

        # 3. 动态回撤
        fig.add_trace(go.Scatter(
            x=drawdown.index, y=drawdown, name='回撤', fill='tozeroy', 
            fillcolor='rgba(34, 197, 94, 0.2)', line=dict(color='#22c55e'),
            customdata=list(zip(date_disp, [f"{v*100:+.2f}%" for v in drawdown])),
            hovertemplate='<b>%{customdata[0]}</b><br>动态回撤: %{customdata[1]}<extra></extra>'
        ), row=3, col=1)

        # 4. 个股贡献曲线 (开启中文名称和图例)
        colors = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3', '#FF6692', '#B6E880']
        for i, t in enumerate(tickers):
            if t in indiv_cum_ret.columns:
                name = stock_names[t]
                y_val = indiv_cum_ret[t]
                hover_growth = [f"{v*100-100:+.2f}%" for v in y_val]
                
                fig.add_trace(go.Scatter(
                    x=indiv_cum_ret.index, y=y_val, 
                    name=name,  # 这里设置中文名称，会显示在图例中
                    mode='lines',
                    line=dict(width=1.8, color=colors[i % len(colors)]),
                    showlegend=True, # 确保个股曲线在图例中显示
                    customdata=list(zip(date_disp, hover_growth)),
                    hovertemplate=f'<b>{name}</b><br>%{{customdata[0]}}<br>累计贡献: %{{customdata[1]}}<extra></extra>'
                ), row=4, col=1)

        # 全局布局优化
        fig.update_layout(
            height=950, 
            margin=dict(l=10, r=10, t=60, b=20),
            hovermode="closest", 
            dragmode=False,
            # 将图例放在第四张图的右上方区域
            legend=dict(
                orientation="v", 
                yanchor="top", y=0.3, 
                xanchor="right", x=1.02,
                font=dict(size=10),
                bgcolor="rgba(255,255,255,0.5)"
            ),
            plot_bgcolor='rgba(0,0,0,0)',
            hoverlabel=dict(bgcolor="rgba(255, 255, 255, 0.9)", font=dict(color="#000000", size=12), align="left")
        )
        
        # 统一轴配置
        fig.update_xaxes(
            rangebreaks=[dict(values=dt_breaks)], 
            tickformat="%y-%m-%d", 
            showgrid=True, gridcolor='rgba(128,128,128,0.15)',
            showspikes=True, spikemode='across', spikesnap='cursor', spikethickness=1, spikedash='solid'
        )
        fig.update_yaxes(showgrid=True, gridcolor='rgba(128,128,128,0.15)', fixedrange=True)

        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        # 底部详情表
        st.subheader("📊 最终贡献排名详情")
        final_perf = (indiv_cum_ret.iloc[-1] - 1).sort_values(ascending=False)
        summary_df = pd.DataFrame({
            "股票名称": [stock_names[c] for c in final_perf.index],
            "周期累计收益": final_perf.values
        })
        st.table(summary_df.style.format({"周期累计收益": "{:.2%}"}))
