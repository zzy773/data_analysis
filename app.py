import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Streamlit 页面配置
st.set_page_config(page_title="A股组合回测系统", layout="wide")

# 注入 CSS 优化触摸体验，解决手机端滑动死锁
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

# --- 侧边栏输入区域 ---
st.sidebar.header("参数设置")
start_date_input = st.sidebar.text_input("回测起始时间 (YYYYMMDD)", "20230101")
end_date_input = st.sidebar.text_input("回测结束时间 (YYYYMMDD)", "20240101")
tickers_input = st.sidebar.text_input("股票代码 (逗号分隔)", "002050,600118")

if st.sidebar.button("开始回测"):
    tickers_input = tickers_input.replace('，', ',')
    tickers = [ticker.strip() for ticker in tickers_input.split(',')]
    
    with st.spinner('正在获取数据及股票名称...'):
        start_dt = datetime.strptime(start_date_input, "%Y%m%d")
        fetch_start_dt = start_dt - timedelta(days=10)
        fetch_start_str = fetch_start_dt.strftime("%Y%m%d")
        
        close_prices = pd.DataFrame()
        stock_names = {}
        
        # 获取 A 股实时行情快照以获取中文名称
        try:
            spot_df = ak.stock_zh_a_spot_em()
        except:
            spot_df = pd.DataFrame()

        for ticker_code in tickers:
            if not ticker_code: continue
            try:
                # 匹配中文名称
                if not spot_df.empty:
                    name_match = spot_df[spot_df['代码'] == ticker_code]['名称']
                    stock_names[ticker_code] = name_match.values[0] if not name_match.empty else ticker_code
                else:
                    stock_names[ticker_code] = ticker_code
                
                # 获取历史行情
                df = ak.stock_zh_a_hist(symbol=ticker_code, period="daily", start_date=fetch_start_str, end_date=end_date_input, adjust="qfq")
                if not df.empty:
                    df.set_index("日期", inplace=True)
                    df.index = pd.to_datetime(df.index)
                    close_prices[ticker_code] = df["收盘"]
            except Exception as e:
                st.error(f"获取 {ticker_code} 数据失败: {e}")

        close_prices.dropna(inplace=True)
        if close_prices.empty:
            st.error("数据不足，请检查代码或日期。")
            st.stop()

        # 计算每日收益
        daily_returns = close_prices.pct_change().dropna()
        target_start_date = pd.to_datetime(start_date_input)
        daily_returns = daily_returns[daily_returns.index >= target_start_date]
        
        if daily_returns.empty:
            st.error("指定日期段内无有效交易日数据。")
            st.stop()

        # 计算组合及个股累计贡献
        # 个股累计收益 = (1+r1)*(1+r2)...
        individual_cum_returns = (1 + daily_returns).cumprod()
        portfolio_daily_return = daily_returns.mean(axis=1)
        cumulative_return = (1 + portfolio_daily_return).cumprod()
        
        running_max = cumulative_return.cummax()
        drawdown = (cumulative_return - running_max) / running_max

        # --- Plotly 绘图逻辑 ---
        dt_all = pd.date_range(start=cumulative_return.index.min(), end=cumulative_return.index.max())
        dt_breaks = dt_all.difference(cumulative_return.index).strftime('%Y-%m-%d').tolist()

        # 构造复杂的悬浮文本：包含日期、总净值、个股各自的累计收益
        customdata_list = []
        for i in range(len(cumulative_return)):
            date_str = cumulative_return.index[i].strftime('%Y年%m月%d日')
            total_growth = f"{(cumulative_return.iloc[i]-1)*100:+.2f}%"
            
            # 拼接个股贡献
            indiv_parts = []
            for t in tickers:
                val = (individual_cum_returns[t].iloc[i] - 1) * 100
                indiv_parts.append(f"{stock_names[t]}: {val:+.2f}%")
            indiv_str = "<br>".join(indiv_parts)
            
            customdata_list.append([date_str, total_growth, indiv_str])

        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.05, 
                            row_heights=[0.5, 0.25, 0.25])

        x_dates = cumulative_return.index

        # 1. 净值曲线
        fig.add_trace(
            go.Scatter(
                x=x_dates, y=cumulative_return, 
                mode='lines', name='组合净值',
                line=dict(color='#ff4b4b', width=2),
                customdata=customdata_list,
                hovertemplate='<b>%{customdata[0]}</b><br>' +
                              '组合净值: %{y:.4f}<br>' +
                              '组合累计收益: %{customdata[1]}<br>' +
                              '------------------<br>' +
                              '%{customdata[2]}<extra></extra>'
            ),
            row=1, col=1
        )

        # 2. 每日涨跌幅
        fig.add_trace(
            go.Bar(
                x=x_dates, y=portfolio_daily_return, 
                name='每日涨跌', marker_color='#3b82f6', opacity=0.8,
                hovertemplate='当日涨跌幅: %{y:.2%}<extra></extra>'
            ),
            row=2, col=1
        )

        # 3. 最大回撤
        fig.add_trace(
            go.Scatter(
                x=x_dates, y=drawdown, 
                mode='lines', name='回撤',
                fill='tozeroy', fillcolor='rgba(34, 197, 94, 0.3)', line=dict(color='#22c55e'),
                hovertemplate='回撤比例: %{y:.2%}<extra></extra>'
            ),
            row=3, col=1
        )

        fig.update_layout(
            height=750,
            margin=dict(l=10, r=10, t=30, b=20),
            hovermode="closest",
            dragmode=False,
            showlegend=False,
            plot_bgcolor='rgba(0,0,0,0)',
            hoverlabel=dict(
                bgcolor="rgba(255, 255, 255, 0.9)", 
                bordercolor="#888",                   
                font=dict(color="#000000", size=12),
                align="left"                          
            )
        )
        
        fig.update_xaxes(
            rangebreaks=[dict(values=dt_breaks)], 
            tickformat="%y-%m-%d", 
            showgrid=True, gridcolor='rgba(128,128,128,0.2)',
            showspikes=True, spikemode='across', spikesnap='cursor', spikethickness=1, spikedash='solid'
        )
        
        fig.update_yaxes(showgrid=True, gridcolor='rgba(128,128,128,0.2)', fixedrange=True)

        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        # 底部个股贡献总结表
        st.subheader("个股最终贡献排名")
        final_indiv = (individual_cum_returns.iloc[-1] - 1).sort_values(ascending=False)
        summary_df = pd.DataFrame({
            "股票名称": [stock_names[code] for code in final_indiv.index],
            "累计贡献": final_indiv.values
        })
        st.table(summary_df.style.format({"累计贡献": "{:.2%}"}))
