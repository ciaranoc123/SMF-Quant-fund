import smf.yahoo_api as y
import smf.reuters_api as reuters
import smf.ranking as ranking
import smf.random_generator_optimiser as opt
import smf.utils as u
import smf.scipy_optimiser as sci_opt
from smf.db_engine import DbEngine

import pandas as pd
import time
import numpy as np



# Initial user inputs
test = True
risk_free_rate = 0.0
number_of_ranked_stocks = 30 if not test else 3
new_portfolio_allocation = 100000
num_of_simulations = 5000 if not test else 50
info_log_frequency = 5
num_of_portfolios = 20000
db=DbEngine()
start = time.time()

"""os
    Data Retrieval
"""
print("-I- Retrieving data.")

# Retrieve list of tickers (via Eikon)
stock_ticker_list_RIC = sorted(reuters.get_tickers("SPX")) if not test else sorted(reuters.get_tickers("SPX")[0:15])
stock_ticker_list = sorted([u.eikon_to_yahoo(new_stock_ticker_RIC) for new_stock_ticker_RIC in stock_ticker_list_RIC])

# Stock price retrieval (via Yahoo Finance)
start1 = time.time()
stock_prices_df = y.get_price_dataframe(stock_ticker_list) # Adj Close prices
print("-I- Yahoo price data query: {} seconds".format(time.time()-start1))


# PE value retrieval (via Eikon)

pe_df = reuters.get_pe(stock_ticker_list_RIC)
pe_df['Ticker'] = pe_df['Ticker'].apply(u.eikon_to_yahoo)
pe_df.set_index("Ticker", inplace=True)

print("-I- Finished retrieving data.\n")




"""
    Ranking
"""


print("-I- Ranking stocks.")

pct_change = (stock_prices_df.iloc[-1] - stock_prices_df.iloc[0])/stock_prices_df.iloc[0]
ranked_by_pct_change = pct_change.rank(ascending=False) 

ranked_by_pe = pe_df['PE'].rank()
ranking_scores = ranked_by_pct_change + ranked_by_pe

ranking_scores_df = pd.DataFrame({"Ranking_Score": ranking_scores})
ranking_scores_df.index.name = "Tickers"
ranking_scores_df['Tickers'] = list(ranking_scores_df.index)
print("-I- Finished ranking stocks.\n")

"""

scipy optimiser


"""

mu, cov = sci_opt.calculate_optimiser_inputs(db, number_of_ranked_stocks, ranking_scores_df, stock_prices_df)

optimizer = sci_opt.Optimizer(mu, cov)
portfolio = optimizer.portfolio


"""
    Optimisation
"""

optimizer

print("-I- Running optimiser.")

# Pick the top n stocks to be included in the optimised portfolio
top_ranking_scores = ranking_scores_df.nsmallest(number_of_ranked_stocks, "Ranking_Score")
top_stocks_ticker_list = [stock for stock in top_ranking_scores.index]

# Calculate the mean returns and covariance of returns
mean_historical_returns, covariance_of_returns = opt.calculate_optimiser_inputs(stock_prices_df, top_stocks_ticker_list)

# Generate a random set of portfolios and store the max-sharpe-ratio portfolio from each run
max_sharpe_portfolio_per_simulation = opt.run_simulations(top_stocks_ticker_list, num_of_simulations, num_of_portfolios, mean_historical_returns, covariance_of_returns, risk_free_rate, info_log_frequency)

# Get the portfolio with the greatest sharpe ratio
best_sharpe_ratio = max_sharpe_portfolio_per_simulation['Sharpe Ratio'].max()
best_portfolio = max_sharpe_portfolio_per_simulation.loc[max_sharpe_portfolio_per_simulation['Sharpe Ratio'] == best_sharpe_ratio].reset_index()

print("-I- Finished running optimiser\n")
optimizer.print_summary()
for i in range(0,len(portfolio.index)):
    print(portfolio.index[i], round(optimizer.weights[i], 3))

print ("Portfolio allocations:")
for ticker in portfolio.columns:
    if ticker in ["index", "Annual Log Return", "Volatility", "Sharpe Ratio"]:
        pass
    else:
        print("{}: €{:.2f}".format(ticker, best_portfolio.loc[:, ticker].values[0]*new_portfolio_allocation))

print("\nPlotting the efficient frontier.")
portfolios = opt.simulate_portfolios(top_stocks_ticker_list, 200000, mean_historical_returns, covariance_of_returns, risk_free_rate)
opt.plot_portfolios(portfolios, best_portfolio)
