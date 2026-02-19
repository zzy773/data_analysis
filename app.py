import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Streamlit 页面配置
st.set_page_config(page_title="A股组合回测系统", layout="wide")

# 注入 CSS 优化手机端触摸滑动体验，防止遮挡和长按菜单
st.markdown(
    """
    <style>
    * { -webkit-touch-callout: none !important; -webkit-user-select: none !important; }
    .js-plotly-plot .plotly .main-svg { touch-action: pan-y !important; }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("📈 A股组合等权重回测系统")

# --- 侧边栏参数 ---
st.sidebar.header("参数设置")
start_date_input = st.sidebar.text_input("回测起始时间 (YYYYMMDD)", "20230101")
end_date_input = st.sidebar.text_input("回测结束时间 (YYYYMMDD)", "20240101")
tickers_input = st.sidebar.text_input("股票代码 (逗号分隔)", "002050,600118")

if st.sidebar.button("开始回测"):
    tickers_input = tickers_input.replace('，', ',')
    tickers = [t.strip() for t in tickers_input.split(',')]
    
    with st.spinner('正在获取数据及股票名称...'):
        start_dt = datetime.strptime(start_date_input, "%Y%m%d")
        # 往前推 10 天以确保能计算出起始首日的涨跌幅
        fetch_start_str = (start_dt - timedelta(days=10)).strftime("%Y%m%d")
        
        close_prices = pd.DataFrame()
        stock_names = {}
        
        for ticker in tickers:
            if not ticker: continue
            try:
                # 获取个股中文名称
                info_df = ak.stock_individual_info_em(symbol=ticker)
                stock_names[ticker] = info_df[info_df['item'] == '股票简称']['value'].values[0]
                
                # 获取复权历史行情
                df = ak.stock_zh_a_hist(symbol=ticker, period="daily", start_date=fetch_start_str, end_date=end_date_input, adjust="qfq")
                if not df.empty:
                    df.set_index("日期", inplace=True)
                    df.index = pd.to_datetime(df.index)
                    close_prices[ticker] = df["收盘"]
            except Exception:
                stock_names[ticker] = ticker  # 失败则显示代码

        close_prices.dropna(inplace=True)
        if close_prices.empty:
            st.error("未获取到足够的数据，请检查代码或日期。")
            st.stop()

        # 计算收益率逻辑
        daily_returns = close_prices.pct_change().dropna()
        target_start_date = pd.to_datetime(start_date_input)
        daily_returns = daily_returns[daily_returns.index >= target_start_date]
        
        if daily_returns.empty:
            st.error("指定时间段内无有效交易数据。")
            st.stop()

        # 计算各项指标
        individual_cum_returns = (1 + daily_returns).cumprod()
        portfolio_return = daily_returns.mean(axis=1)
        cumulative_return = (1 + portfolio_return).cumprod()
        drawdown = (cumulative_return - cumulative_return.cummax()) / cumulative_return.cummax()

        # --- 绘图逻辑：优化中文日期与百分比显示 ---
        # 排除非交易日断层
        dt_breaks = pd.date_range(start=cumulative_return.index.min(), end=cumulative_return.index.max()).difference(cumulative_return.index).strftime('%Y-%m-%d').tolist()

        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.5, 0.25, 0.25])

        # 准备悬浮窗自定义数据
        date_display = cumulative_return.index.strftime('%Y年%m月%d日')
        
        # 1. 组合净值曲线
        cum_growth_hover = [f"{(y-1)*100:+.2f}%" for y in cumulative_return]
        indiv_contributions = []
        for i in range(len(cumulative_return)):
            parts = [f"{stock_names[t]}: {(individual_cum_returns[t].iloc[i]-1)*100:+.2f}%" for t in tickers if t in individual_cum_returns.columns]
            indiv_contributions.append("<br>".join(parts))

        fig.add_trace(go.Scatter(
            x=cumulative_return.index, y=cumulative_return, name='净值',
            line=dict(color='#ff4b4b', width=2),
            customdata=list(zip(date_display, cum_growth_hover, indiv_contributions)),
            hovertemplate='<b>%{customdata[0]}</b><br>组合净值: %{y:.4f}<br>累计增长: %{customdata[1]}<br>------------------<br>%{customdata[2]}<extra></extra>'
        ), row=1, col=1)

        # 2. 每日涨跌幅柱状图 (悬浮显示百分比)
        daily_ret_hover = [f"{v*100:+.2f}%" for v in portfolio_return]
        fig.add_trace(go.Bar(
            x=portfolio_return.index, y=portfolio_return, name='涨跌',
            marker_color='#3b82f6', opacity=0.8,
            customdata=list(zip(date_display, daily_ret_hover)),
            hovertemplate='<b>%{customdata[0]}</b><br>当日涨跌: %{customdata[1]}<extra></extra>'
        ), row=2, col=1)

        # 3. 最大回撤面积图 (悬浮显示百分比)
        drawdown_hover = [f"{v*100:.2f}%" for v in drawdown]
        fig.add_trace(go.Scatter(
            x=drawdown.index, y=drawdown, name='回撤',
            fill='tozeroy', fillcolor='rgba(34, 197, 94, 0.2)', line=dict(color='#22c55e'),
            customdata=list(zip(date_display, drawdown_hover)),
            hovertemplate='<b>%{customdata[0]}</b><br>动态回撤: %{customdata[1]}<extra></extra>'
        ), row=3, col=1)

        # 全局布局优化
        fig.update_layout(
            height=700, margin=dict(l=10, r=10, t=30, b=20),
            hovermode="closest", dragmode=False, showlegend=False,
            plot_bgcolor='rgba(0,0,0,0)',
            hoverlabel=dict(
                bgcolor="rgba(255, 255, 255, 0.9)", 
                font=dict(color="#000000", size=12),
                align="left"
            )
        )
        
        # 坐标轴格式化
        fig.update_xaxes(
            rangebreaks=[dict(values=dt_breaks)],
            tickformat="%y-%m-%d",
            hoverformat="%Y年%m月%d日",
            showgrid=True, gridcolor='rgba(128,128,128,0.2)',
            showspikes=True, spikemode='across', spikesnap='cursor', spikethickness=1, spikedash='solid'
        )
        
        fig.update_yaxes(showgrid=True, gridcolor='rgba(128,128,128,0.2)', fixedrange=True)

        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        # 底部个股表现总结
        st.subheader("📊 组合个股贡献总结")
        final_perf = (individual_cum_returns.iloc[-1] - 1).sort_values(ascending=False)
        summary_df = pd.DataFrame({
            "股票简称": [stock_names[c] for c in final_perf.index],
            "周期累计贡献": final_perf.values
        })
        st.table(summary_df.style.format({"周期累计贡献": "{:.2%}"}))
