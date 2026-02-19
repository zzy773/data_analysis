import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Streamlit 页面配置
st.set_page_config(page_title="A股组合回测系统", layout="wide")
st.title("📈 A股组合等权重回测系统")

# --- 侧边栏输入区域 ---
st.sidebar.header("参数设置")
start_date_input = st.sidebar.text_input("回测起始时间 (YYYYMMDD)", "20230101")
end_date_input = st.sidebar.text_input("回测结束时间 (YYYYMMDD)", "20240101")
tickers_input = st.sidebar.text_input("股票代码 (逗号分隔)", "002050,600118")

if st.sidebar.button("开始回测"):
    
    tickers_input = tickers_input.replace('，', ',')
    tickers = [ticker.strip() for ticker in tickers_input.split(',')]
    
    with st.spinner('正在从 AKShare 获取 A 股前复权数据，请稍候...'):
        start_dt = datetime.strptime(start_date_input, "%Y%m%d")
        # 往前推 10 天，解决第一天收益计算为空的问题
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
                else:
                    st.warning(f"未获取到 {ticker_code} 的数据。")
            except Exception as e:
                st.error(f"获取 {ticker_code} 数据失败: {e}")

        close_prices.dropna(inplace=True)
        
        if close_prices.empty:
            st.error("未获取到足够的数据进行回测，请检查日期或代码。")
            st.stop()

        # 计算每日收益，并截取用户真正想要的日期段
        daily_returns = close_prices.pct_change().dropna()
        target_start_date = pd.to_datetime(start_date_input)
        daily_returns = daily_returns[daily_returns.index >= target_start_date]
        
        if daily_returns.empty:
            st.error("截取指定日期段后无有效数据。")
            st.stop()

        # 等权重组合计算
        portfolio_daily_return = daily_returns.mean(axis=1)
        cumulative_return = (1 + portfolio_daily_return).cumprod()
        running_max = cumulative_return.cummax()
        drawdown = (cumulative_return - running_max) / running_max

        # --- Plotly 交互式绘图逻辑 ---
        
        # 找出所有非交易日用于折叠隐藏
        dt_all = pd.date_range(start=cumulative_return.index.min(), end=cumulative_return.index.max())
        dt_breaks = dt_all.difference(cumulative_return.index).strftime('%Y-%m-%d').tolist()
        
        # 提前计算悬浮窗的百分比字符串
        hover_pct = [(y - 1) * 100 for y in cumulative_return]
        customdata_pct = [f"{'+' if p > 0 else ''}{p:.2f}%" for p in hover_pct]

        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.05, 
                            row_heights=[0.5, 0.25, 0.25])

        x_dates = cumulative_return.index

        # 1. 累积净值图
        fig.add_trace(
            go.Scatter(
                x=x_dates, y=cumulative_return, 
                mode='lines', name='组合累积净值',
                line=dict(color='#ff4b4b', width=2),
                customdata=customdata_pct,
                hovertemplate='净值: %{y:.4f}<br>累计增长: %{customdata}<extra></extra>'
            ),
            row=1, col=1
        )

        # 2. 每日涨跌幅
        fig.add_trace(
            go.Bar(
                x=x_dates, y=portfolio_daily_return, 
                name='每日综合涨跌幅', marker_color='#3b82f6', opacity=0.8,
                hovertemplate='涨跌幅: %{y:.2%}<extra></extra>'
            ),
            row=2, col=1
        )

        # 3. 动态回撤
        fig.add_trace(
            go.Scatter(
                x=x_dates, y=drawdown, 
                mode='lines', name='最大回撤',
                fill='tozeroy', fillcolor='rgba(34, 197, 94, 0.3)', line=dict(color='#22c55e'),
                hovertemplate='回撤比例: %{y:.2%}<extra></extra>'
            ),
            row=3, col=1
        )

        # 布局、背景与悬浮窗（半透明毛玻璃）样式设置
        fig.update_layout(
            height=700,
            margin=dict(l=20, r=20, t=30, b=20),
            hovermode="x unified",
            showlegend=False,
            plot_bgcolor='rgba(0,0,0,0)',
            hoverlabel=dict(
                bgcolor="rgba(255, 255, 255, 0.85)",  # 设置背景颜色为85%透明度的白色
                bordercolor="#888",                   # 浅灰色边框
                font_size=13,                         # 优化字体大小
                align="left"                          # 文本左对齐
            )
        )
        
        # 将横坐标和悬浮窗的时间格式升级为包含年份的完整中文格式
        fig.update_xaxes(
            rangebreaks=[dict(values=dt_breaks)], 
            tickformat="%Y年%m月%d日",                
            hoverformat="%Y年%m月%d日",               
            showgrid=True, 
            gridwidth=1, 
            gridcolor='rgba(128,128,128,0.2)', 
            tickangle=45
        )
        
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')

        # 将动态图表渲染到网页
        st.plotly_chart(fig, use_container_width=True)

        # 底部数据明细表
        st.subheader("数据明细")
        result_df = pd.DataFrame({
            "每日收益率": portfolio_daily_return,
            "累积净值": cumulative_return,
            "动态回撤": drawdown
        })
        st.dataframe(result_df.style.format("{:.2%}"))
