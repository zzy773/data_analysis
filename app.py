import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Streamlit 页面配置
st.set_page_config(page_title="A股组合多维度回测系统", layout="wide")

# 注入 CSS 优化手机端触摸滑动体验
st.markdown(
    """
    <style>
    * { -webkit-touch-callout: none !important; -webkit-user-select: none !important; }
    .js-plotly-plot .plotly .main-svg { touch-action: pan-y !important; }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("📈 A股组合贡献度分层分析系统")

# --- 侧边栏参数 ---
st.sidebar.header("参数设置")
start_date_input = st.sidebar.text_input("起始时间 (YYYYMMDD)", "20230101")
end_date_input = st.sidebar.text_input("结束时间 (YYYYMMDD)", "20240101")
# 默认填入您关注的相关标的
tickers_input = st.sidebar.text_input("股票代码 (逗号分隔)", "002851,002865,603061,603667")

if st.sidebar.button("开始回测"):
    tickers_input = tickers_input.replace('，', ',')
    tickers = [t.strip() for t in tickers_input.split(',')]
    
    with st.spinner('正在获取数据及个股名称...'):
        start_dt = datetime.strptime(start_date_input, "%Y%m%d")
        fetch_start_str = (start_dt - timedelta(days=10)).strftime("%Y%m%d")
        
        close_prices = pd.DataFrame()
        stock_names = {}
        
        for ticker in tickers:
            if not ticker: continue
            try:
                # 获取中文简称
                info_df = ak.stock_individual_info_em(symbol=ticker)
                stock_names[ticker] = info_df[info_df['item'] == '股票简称']['value'].values[0]
                
                # 获取复权历史行情
                df = ak.stock_zh_a_hist(symbol=ticker, period="daily", start_date=fetch_start_str, end_date=end_date_input, adjust="qfq")
                if not df.empty:
                    df.set_index("日期", inplace=True)
                    df.index = pd.to_datetime(df.index)
                    close_prices[ticker] = df["收盘"]
            except Exception:
                stock_names[ticker] = ticker

        close_prices.dropna(inplace=True)
        if close_prices.empty:
            st.error("数据不足，请检查日期或代码")
            st.stop()

        # 计算收益率
        daily_returns = close_prices.pct_change().dropna()
        target_start_date = pd.to_datetime(start_date_input)
        daily_returns = daily_returns[daily_returns.index >= target_start_date]
        
        # 1. 组合净值
        portfolio_return = daily_returns.mean(axis=1)
        cumulative_return = (1 + portfolio_return).cumprod()
        # 2. 个股独立累计贡献
        individual_cum_returns = (1 + daily_returns).cumprod()
        # 3. 最大回撤
        drawdown = (cumulative_return - cumulative_return.cummax()) / cumulative_return.cummax()

        # --- 绘图逻辑：重排子图顺序 ---
        dt_breaks = pd.date_range(start=cumulative_return.index.min(), end=cumulative_return.index.max()).difference(cumulative_return.index).strftime('%Y-%m-%d').tolist()

        fig = make_subplots(
            rows=4, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.04, 
            row_heights=[0.3, 0.2, 0.2, 0.3],
            subplot_titles=("1. 组合累积净值走势", "2. 组合每日涨跌幅 (%)", "3. 组合动态回撤 (%)", "4. 个股累积贡献对比")
        )

        date_display = cumulative_return.index.strftime('%Y年%m月%d日')

        # 第一层：组合总净值
        total_growth_hover = [f"{(y-1)*100:+.2f}%" for y in cumulative_return]
        fig.add_trace(go.Scatter(
            x=cumulative_return.index, y=cumulative_return, 
            name='组合总净值', line=dict(color='#ff4b4b', width=3),
            customdata=list(zip(date_display, total_growth_hover)),
            hovertemplate='<b>组合总计</b><br>%{customdata[0]}<br>总净值: %{y:.4f}<br>总增长: %{customdata[1]}<extra></extra>'
        ), row=1, col=1)

        # 第二层：每日涨跌幅
        daily_ret_hover = [f"{v*100:+.2f}%" for v in portfolio_return]
        fig.add_trace(go.Bar(
            x=portfolio_return.index, y=portfolio_return, 
            name='每日涨跌', marker_color='#3b82f6', opacity=0.7,
            customdata=list(zip(date_display, daily_ret_hover)),
            hovertemplate='<b>%{customdata[0]}</b><br>当日涨跌: %{customdata[1]}<extra></extra>'
        ), row=2, col=1)

        # 第三层：动态回撤
        drawdown_hover = [f"{v*100:.2f}%" for v in drawdown]
        fig.add_trace(go.Scatter(
            x=drawdown.index, y=drawdown, 
            name='回撤', fill='tozeroy', 
            fillcolor='rgba(34, 197, 94, 0.2)', line=dict(color='#22c55e'),
            customdata=list(zip(date_display, drawdown_hover)),
            hovertemplate='<b>%{customdata[0]}</b><br>动态回撤: %{customdata[1]}<extra></extra>'
        ), row=3, col=1)

        # 第四层：个股贡献曲线
        colors = ['#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A', '#19D3F3', '#FF6692', '#B6E880']
        for i, ticker in enumerate(tickers):
            if ticker in individual_cum_returns.columns:
                name = stock_names[ticker]
                y_val = individual_cum_returns[ticker]
                hover_growth = [f"{v*100-100:+.2f}%" for v in y_val]
                
                fig.add_trace(go.Scatter(
                    x=individual_cum_returns.index, y=y_val, 
                    name=name, mode='lines',
                    line=dict(width=1.8, color=colors[i % len(colors)]),
                    customdata=list(zip(date_display, hover_growth)),
                    hovertemplate=f'<b>{name}</b><br>%{{customdata[0]}}<br>个股净值: %{{y:.4f}}<br>累计贡献: %{{customdata[1]}}<extra></extra>'
                ), row=4, col=1)

        # 布局全局优化
        fig.update_layout(
            height=950, 
            margin=dict(l=10, r=10, t=60, b=20),
            hovermode="closest", 
            dragmode=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
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

        # 底部个股总结
        st.subheader("📊 周期内个股贡献度排名")
        final_perf = (individual_cum_returns.iloc[-1] - 1).sort_values(ascending=False)
        summary_df = pd.DataFrame({
            "股票简称": [stock_names[c] for c in final_perf.index],
            "周期累计收益 (个股独立)": final_perf.values
        })
        st.table(summary_df.style.format({"周期累计收益 (个股独立)": "{:.2%}"}))
