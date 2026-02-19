import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 页面配置
st.set_page_config(page_title="A股组合回测系统", layout="wide")

# 注入 CSS 优化触摸体验并统一悬浮框样式
st.markdown(
    """
    <style>
    * {
        -webkit-touch-callout: none !important;
        -webkit-user-select: none !important;
    }
    .js-plotly-plot .plotly .main-svg {
        touch-action: pan-y !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("📈 A股组合等权重回测系统")

# --- 侧边栏参数 ---
st.sidebar.header("参数设置")
start_date_input = st.sidebar.text_input("起始时间", "20230101")
end_date_input = st.sidebar.text_input("结束时间", "20240101")
tickers_input = st.sidebar.text_input("股票代码", "002050,600118")

if st.sidebar.button("开始回测"):
    tickers_input = tickers_input.replace('，', ',')
    tickers = [t.strip() for t in tickers_input.split(',')]
    
    with st.spinner('数据加载中...'):
        start_dt = datetime.strptime(start_date_input, "%Y%m%d")
        fetch_start_str = (start_dt - timedelta(days=10)).strftime("%Y%m%d")
        
        close_prices = pd.DataFrame()
        for ticker in tickers:
            try:
                df = ak.stock_zh_a_hist(symbol=ticker, period="daily", start_date=fetch_start_str, end_date=end_date_input, adjust="qfq")
                if not df.empty:
                    df.set_index("日期", inplace=True)
                    df.index = pd.to_datetime(df.index)
                    close_prices[ticker] = df["收盘"]
            except: pass

        close_prices.dropna(inplace=True)
        daily_returns = close_prices.pct_change().dropna()
        daily_returns = daily_returns[daily_returns.index >= pd.to_datetime(start_date_input)]
        
        portfolio_return = daily_returns.mean(axis=1)
        cum_return = (1 + portfolio_return).cumprod()
        drawdown = (cum_return - cum_return.cummax()) / cum_return.cummax()

        # 准备非交易日断层数据
        dt_breaks = pd.date_range(start=cum_return.index.min(), end=cum_return.index.max()).difference(cum_return.index).strftime('%Y-%m-%d').tolist()

        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.5, 0.25, 0.25])

        # 准备自定义数据：格式化日期和增长率
        date_display = cum_return.index.strftime('%Y年%m月%d日')
        hover_growth = [f"{(y-1)*100:+.2f}%" for y in cum_return]

        # 1. 净值曲线 - 修改 hovertemplate 使日期和数据在一起
        fig.add_trace(go.Scatter(
            x=cum_return.index, y=cum_return, name='净值',
            line=dict(color='#ff4b4b', width=2),
            customdata=stack := list(zip(date_display, hover_growth)),
            # 【核心修改】：在模板中手动加入日期 %{customdata[0]}
            hovertemplate='<b>%{customdata[0]}</b><br>净值: %{y:.4f}<br>累计增长: %{customdata[1]}<extra></extra>'
        ), row=1, col=1)

        # 2. 涨跌幅柱状图
        fig.add_trace(go.Bar(
            x=cum_return.index, y=portfolio_return, name='涨跌', 
            marker_color='#3b82f6',
            customdata=date_display,
            hovertemplate='<b>%{customdata}</b><br>当日涨跌: %{y:.2%}<extra></extra>'
        ), row=2, col=1)

        # 3. 回撤面积图
        fig.add_trace(go.Scatter(
            x=cum_return.index, y=drawdown, name='回撤', 
            fill='tozeroy', fillcolor='rgba(34,197,94,0.2)', line=dict(color='#22c55e'),
            customdata=date_display,
            hovertemplate='<b>%{customdata}</b><br>动态回撤: %{y:.2%}<extra></extra>'
        ), row=3, col=1)

        fig.update_layout(
            height=650,
            margin=dict(l=10, r=10, t=20, b=20),
            hovermode="closest", 
            dragmode=False,
            hoverlabel=dict(
                bgcolor="rgba(255, 255, 255, 0.9)", 
                font=dict(color="#000", size=12),
                # 强制悬浮框内的日期不再出现在坐标轴上，而是跟随鼠标
                namelength=0
            )
        )

        fig.update_xaxes(
            rangebreaks=[dict(values=dt_breaks)],
            tickformat="%Y-%m-%d",
            showspikes=True,
            spikemode='across', 
            spikesnap='cursor',
            spikethickness=1,
            spikedash='solid',
            spikecolor='#999'
        )
        
        fig.update_yaxes(fixedrange=True, showgrid=True, gridcolor='rgba(128,128,128,0.2)')

        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        st.subheader("数据明细")
        st.dataframe(pd.DataFrame({"累计净值": cum_return, "当日涨跌": portfolio_return}).style.format("{:.2%}"))
