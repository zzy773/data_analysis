import streamlit as st
import akshare as ak
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from datetime import datetime, timedelta

# Streamlit 页面配置
st.set_page_config(page_title="A股组合回测系统", layout="wide")
st.title("📈 A股组合等权重回测系统")

# --- 侧边栏输入区域 ---
st.sidebar.header("参数设置")
start_date_input = st.sidebar.text_input("回测起始时间 (YYYYMMDD)", "20230101")
end_date_input = st.sidebar.text_input("回测结束时间 (YYYYMMDD)", "20240101")
tickers_input = st.sidebar.text_input("股票代码 (逗号分隔)", "002050,600118")

# 当用户点击按钮时才执行计算
if st.sidebar.button("开始回测"):
    
    # 替换中文逗号并拆分
    tickers_input = tickers_input.replace('，', ',')
    tickers = [ticker.strip() for ticker in tickers_input.split(',')]
    
    # 使用 st.spinner 在网页上显示加载动画
    with st.spinner('正在从 AKShare 获取 A 股前复权数据，请稍候...'):
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
                else:
                    st.warning(f"未获取到 {ticker_code} 的数据。")
            except Exception as e:
                st.error(f"获取 {ticker_code} 数据失败: {e}")

        close_prices.dropna(inplace=True)
        
        if close_prices.empty:
            st.error("未获取到足够的数据进行回测，请检查日期或代码。")
            st.stop() # 停止后续代码运行

        # 计算逻辑保持不变
        daily_returns = close_prices.pct_change().dropna()
        target_start_date = pd.to_datetime(start_date_input)
        daily_returns = daily_returns[daily_returns.index >= target_start_date]
        
        if daily_returns.empty:
            st.error("截取指定日期段后无有效数据。")
            st.stop()

        portfolio_daily_return = daily_returns.mean(axis=1)
        cumulative_return = (1 + portfolio_daily_return).cumprod()
        running_max = cumulative_return.cummax()
        drawdown = (cumulative_return - running_max) / running_max

        # --- 绘图逻辑 ---
        # 注意：由于 Linux 服务器缺少 Windows 字体，图表中的中文可能会变成方块。
        # 这里暂时使用基础英文标签，后续可升级为 Streamlit 原生图表解决此问题。
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 8), gridspec_kw={'height_ratios': [2, 1, 1]})
        
        x_data = range(len(cumulative_return))
        date_labels = cumulative_return.index.strftime('%Y-%m-%d').tolist()
        
        def format_date(x, pos=None):
            idx = int(x)
            if 0 <= idx < len(date_labels): return date_labels[idx]
            return ""

        ax1.plot(x_data, cumulative_return, label='Cumulative Return', color='red', linewidth=1.5, marker='o', markersize=4)
        ax1.set_ylabel('Net Value')
        ax1.legend(loc='upper left')
        
        for x, y in zip(x_data, cumulative_return):
            growth_pct = (y - 1) * 100 
            sign = "+" if growth_pct > 0 else "" 
            ax1.annotate(f"{sign}{growth_pct:.2f}%", (x, y), textcoords="offset points", xytext=(0, 8), ha='center', fontsize=8, color='darkred')
        
        ax2.bar(x_data, portfolio_daily_return, label='Daily Return', color='blue', alpha=0.6)
        ax2.set_ylabel('Pct Change')
        ax2.legend(loc='upper left')
        
        ax3.fill_between(x_data, drawdown, 0, label='Max Drawdown', color='green', alpha=0.4)
        ax3.set_ylabel('Drawdown')
        ax3.legend(loc='lower left')
        
        for ax in [ax1, ax2, ax3]:
            ax.xaxis.set_major_locator(ticker.MultipleLocator(1))
            ax.xaxis.set_major_formatter(ticker.FuncFormatter(format_date))
            plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=8)
            ax.grid(True, linestyle='--', alpha=0.6)
        
        plt.tight_layout()
        
        # 将 matplotlib 画好的图表输出到 Streamlit 网页上
        st.pyplot(fig)
        
        # 顺便在网页底部输出一个数据明细表
        st.subheader("数据明细")
        result_df = pd.DataFrame({
            "每日收益率": portfolio_daily_return,
            "累积净值": cumulative_return,
            "动态回撤": drawdown
        })
        st.dataframe(result_df.style.format("{:.2%}"))
