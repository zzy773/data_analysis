import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Streamlit 页面配置
st.set_page_config(page_title="A股组合回测系统", layout="wide")

# --- 【新增：彻底解决手机滑动死锁的 CSS】 ---
st.markdown(
    """
    <style>
    /* 强制 Plotly 图表容器允许触摸滚动网页 */
    .js-plotly-plot .plotly .main-svg {
        touch-action: pan-y !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("📈 A股组合等权重回测系统")

# --- 侧边栏输入区域 ---
st.sidebar.header("参数设置")
start_date_input = st.sidebar.text_input("回测起始时间 (YYYYMMDD)", "20230101")
end_date_input = st.sidebar.text_input("回测结束时间 (YYYYMMDD)", "20240101")
tickers_input = st.sidebar.text_input("股票代码 (逗号分隔)", "002050,600118")

if st.sidebar.button("开始回测"):
    tickers_input = tickers_input.replace('，', ',')
    tickers = [ticker.strip() for ticker in tickers_input.split(',')]
    
    with st.spinner('正在获取数据...'):
        start_dt = datetime.strptime(start_date_input, "%Y%m%d")
        fetch_start_dt = start_dt - timedelta(days=10)
        fetch_start_str = fetch_start_dt.strftime("%Y%m%d")
        
        close_prices = pd.DataFrame()
        for ticker_code in tickers:
            if not ticker_code: continue
            try:
                df = ak.stock_zh_a_hist(symbol=ticker_code, period="daily", start_date=fetch_start_str, end_date=end_date_input, adjust="qfq")
                if not df.empty:
                    df.set_index("日期", inplace=True)
                    df.index = pd.to_datetime(df.index)
                    close_prices[ticker_code] = df["收盘"]
            except: pass

        close_prices.dropna(inplace=True)
        if close_prices.empty:
            st.error("数据获取失败")
            st.stop()

        daily_returns = close_prices.pct_change().dropna()
        target_start_date = pd.to_datetime(start_date_input)
        daily_returns = daily_returns[daily_returns.index >= target_start_date]
        
        portfolio_daily_return = daily_returns.mean(axis=1)
        cumulative_return = (1 + portfolio_daily_return).cumprod()
        running_max = cumulative_return.cummax()
        drawdown = (cumulative_return - running_max) / running_max

        # --- 绘图逻辑 ---
        dt_all = pd.date_range(start=cumulative_return.index.min(), end=cumulative_return.index.max())
        dt_breaks = dt_all.difference(cumulative_return.index).strftime('%Y-%m-%d').tolist()
        
        hover_pct = [(y - 1) * 100 for y in cumulative_return]
        customdata_pct = [f"{'+' if p > 0 else ''}{p:.2f}%" for p in hover_pct]

        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.05, 
                            row_heights=[0.5, 0.25, 0.25])

        x_dates = cumulative_return.index

        fig.add_trace(go.Scatter(x=x_dates, y=cumulative_return, mode='lines', name='组合累积净值', line=dict(color='#ff4b4b', width=2),
                                 customdata=customdata_pct, hovertemplate='净值: %{y:.4f}<br>累计增长: %{customdata}<extra></extra>'), row=1, col=1)

        fig.add_trace(go.Bar(x=x_dates, y=portfolio_daily_return, name='每日综合涨跌幅', marker_color='#3b82f6', opacity=0.8,
                             hovertemplate='涨跌幅: %{y:.2%}<extra></extra>'), row=2, col=1)

        fig.add_trace(go.Scatter(x=x_dates, y=drawdown, mode='lines', name='最大回撤', fill='tozeroy', 
                                 fillcolor='rgba(34, 197, 94, 0.3)', line=dict(color='#22c55e'),
                                 hovertemplate='回撤比例: %{y:.2%}<extra></extra>'), row=3, col=1)

        fig.update_layout(
            height=700,
            margin=dict(l=10, r=10, t=30, b=20),
            hovermode="x unified",
            showlegend=False,
            plot_bgcolor='rgba(0,0,0,0)',
            dragmode=False, # 禁止拖拽，配合 CSS 允许上下滑动网页
            hoverlabel=dict(
                bgcolor="rgba(255, 255, 255, 0.85)", 
                bordercolor="#888",                   
                font=dict(color="#000000", size=13),
                align="left"                          
            )
        )
        
        fig.update_xaxes(rangebreaks=[dict(values=dt_breaks)], tickformat="%Y年%m月%d日", hoverformat="%Y年%m月%d日", 
                         showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)', tickangle=45)
        
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')

        # 将动态图表渲染到网页
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        st.subheader("数据明细")
        result_df = pd.DataFrame({"每日收益率": portfolio_daily_return, "累积净值": cumulative_return, "动态回撤": drawdown})
        st.dataframe(result_df.style.format("{:.2%}"))
