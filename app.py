import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 页面配置：强制锁定布局
st.set_page_config(page_title="A股组合回测系统", layout="wide")

# 2. 注入“绝杀”级别的 CSS 和 Meta 标签
# 核心：禁止图表区域的默认长按菜单，并优化触摸响应速度
st.markdown(
    """
    <style>
    /* 禁用长按弹出系统菜单 */
    * {
        -webkit-touch-callout: none !important;
        -webkit-user-select: none !important;
    }
    /* 允许垂直滚动网页，但优化图表的水平触摸追踪 */
    .js-plotly-plot .plotly .main-svg {
        touch-action: pan-y !important;
        cursor: crosshair !important;
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
        # 日期逻辑处理
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
        
        # 计算核心指标
        portfolio_return = daily_returns.mean(axis=1)
        cum_return = (1 + portfolio_return).cumprod()
        drawdown = (cum_return - cum_return.cummax()) / cum_return.cummax()

        # --- 绘图逻辑：针对手机端滑动优化 ---
        # 准备非交易日断层数据
        dt_breaks = pd.date_range(start=cum_return.index.min(), end=cum_return.index.max()).difference(cum_return.index).strftime('%Y-%m-%d').tolist()

        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.5, 0.25, 0.25])

        # 增加提示信息
        hover_data = [f"{(y-1)*100:+.2f}%" for y in cum_return]

        # 重点：使用 Scatter 模式并开启 spikelines
        fig.add_trace(go.Scatter(
            x=cum_return.index, y=cum_return, name='净值',
            line=dict(color='#ff4b4b', width=2),
            customdata=hover_data,
            hovertemplate='<b>日期: %{x}</b><br>净值: %{y:.4f}<br>累计: %{customdata}<extra></extra>'
        ), row=1, col=1)

        fig.add_trace(go.Bar(x=cum_return.index, y=portfolio_return, name='涨跌', marker_color='#3b82f6'), row=2, col=1)
        fig.add_trace(go.Scatter(x=cum_return.index, y=drawdown, name='回撤', fill='tozeroy', fillcolor='rgba(34,197,94,0.2)', line=dict(color='#22c55e')), row=3, col=1)

        fig.update_layout(
            height=600,
            margin=dict(l=10, r=10, t=20, b=20),
            # 【关键修改】：hovermode 设为 "closest" 在手机端更容易触发连续滑动
            hovermode="closest", 
            dragmode=False,
            hoverlabel=dict(bgcolor="rgba(255, 255, 255, 0.9)", font=dict(color="#000", size=12))
        )

        fig.update_xaxes(
            rangebreaks=[dict(values=dt_breaks)],
            tickformat="%Y-%m-%d",
            # 【关键修改】：启用并配置 SpikeLines (十字准星线)
            showspikes=True,
            spikemode='across+toaxis',
            spikesnap='cursor',
            spikethickness=1,
            spikedash='solid',
            spikecolor='#999'
        )
        
        # 锁定 Y 轴，防止滑动时误触发缩放
        fig.update_yaxes(fixedrange=True)

        # 【关键修改】：config 配置中开启 'staticPlot': False 但关闭所有按钮
        st.plotly_chart(fig, use_container_width=True, config={
            'displayModeBar': False,
            'scrollZoom': False,
            'doubleClick': False,
            'showAxisDragHandles': False
        })

        st.dataframe(pd.DataFrame({"净值": cum_return, "收益率": portfolio_return}).style.format("{:.2%}"))
