from smf.db_engine import DbEngine
import smf.reuters_api as reuters

import smf.yahoo_api as y
import smf.utils as u

import datetime as dt
import pandas as pd
import time
import numpy as np
import csv
import eikon as ek

if __name__ == "__main__":
    # Initialise eikon and db connections -- The app_key can be set on the "Developer" (?) section in the Eikon window.
    try:
        with open(f"smf\eikon_app_key.json") as ek_app_key:
                ek_app_key = json.load(ek_app_key)
        ek.set_app_key(ek_app_key["key"])
    except:
        ek.set_app_key("403255e90c7647afafbfb5c0000d60ac4c8cc536") 

    db = DbEngine()

#     DONE
#     # Create ticker symbol table
#     ticker_symbol_table_name = "ticker_symbols"
#     ticker_symbol_table_columns = {
#        "ric": "VARCHAR(10)"
#     }
#     db.create_table(ticker_symbol_table_name, ticker_symbol_table_columns)

#     # Populate ticker symbol table
#     snp_tickers = reuters.get_tickers()
#     rus_tickers = []
#     ric_extensions = ["OQ", "N"]

#     # I couldn't find a list of Russell 2000 stocks anywhere so I had to look for it somewhere online,
#     # and this CSV file was all that I could really find.
#     with open("data files/Russell 2000 Constituents.csv") as csv_file:
#         csv_reader = csv.reader(csv_file, delimiter=",")
#         for row in csv_reader:
#             rus_tickers.append(row[0])

#     # The Russell2000 CSV file didn't contain any of the RIC extensions, e.g. the "O" in "MSFT.O", so
#     # we compiled a list of possible RIC extensions (only two) and searched for each of these, e.g. ["MSFT.OQ", "MSFT.N"].
#     # Only one of these should have a valid return value, in which case the corresponding extension is the correct one.
#     for count, ticker in enumerate(rus_tickers):
#         full_rics = list(map(lambda extension: f"{ticker}.{extension}", ric_extensions))
#         try:
#             df = ek.get_data(full_rics, "TR.PrimaryQuote")
#             real_rics = df[0]['Primary Quote RIC']
#             real_ric = next(ric for ric in real_rics if ric is not None)
#         except:
#             print(f"-W- Could not find RIC extension for {ticker}.")
#             continue
#         rus_tickers[count] = real_ric

#     # Combine list of S&P500 and RUSSELL2000 tickers and insert into ticker symbols table
#     tickers_list = snp_tickers + rus_tickers
#     db.truncate_table(ticker_symbol_table_name)
#     db.insert_values_by_column(ticker_symbol_table_name, "ric", tickers_list)


#     DONE
#     sectors_table_name = "tickers_and_classifications"
#     db_data = db.fetch_table("ticker_symbols")
#     tickers_list = db_data["ric"].values.tolist()
#     eikon_data = ek.get_data(tickers_list, ["TR.TRBCEconomicSector",
#                            "TR.TRBCBusinessSector",
#                            "TR.TRBCIndustryGroup"])

#     sectors_df = pd.DataFrame(data=eikon_data[0])
#     sectors_df.columns = ["ric", "economic_sector", "business_sector", "industry_group"]
#     sectors_df = sectors_df.set_index("ric")

#     db.append_df_as_row(sectors_df, sectors_table_name, if_exists="replace", index=True)
#     db.set_primary_key(sectors_table_name, "ric")

    # Didn't really use these tables in the end since volatilities could be calculated from the close_price anyway.
    # Historical volatility
    tickers_list = db.fetch_table("ticker_symbols")["ric"].values.tolist()
    volatilities_days = [2, 5, 10, 20, 25, 30, 40, 50, 60, 80, 90, 100, 120, 150, 160, 180, 200, 240, 250, 260]
    volatilities_fields = list(map(lambda num:f"TR.Volatility{str(num)}D", volatilities_days))
    eikon_data, err = ek.get_data(tickers_list, volatilities_fields)
    volatilities_df = pd.DataFrame(eikon_data)
    volatilities_df.columns = ["ric"] + list(map(lambda num:f"{str(num)}_day_volatility", volatilities_days))

    today = dt.datetime.now().strftime("%Y_%m_%d")
    volatilities_table_name = f"volatilities_as_at_{today}"
    db.append_df_as_row(volatilities_df, volatilities_table_name, if_exists="replace")
    
    
    # Here's where the beef was cooking. I designed the DB so that each stock would have its own table, with
    # columns corresponding to closing price, PE values, PB values, etc. and each row corresponded to a given day.
    # The main reason I did it this way was the limitations in the DB. SQL DOES NOT like having 2000+ columns
    # (where each column would have been a stock, and the row would be a given day for, say, a close_price table).
    # It largely prefers 2000+ tables with only a few columns, leading to my DB design choice.
    #
    # Each column required different treatment, but essentially the aim was to fetch the stock data and populate
    # the corresponding table for that ticker with the data. The ideal scenario would have been every table
    # out of ~2300 would have 4 columns filled with values, and following for loop would run with no issues.
    #
    # This was absolutely impossible for many reasons, hence the try/except:
    #     1. All other stock data except for closing price are posted quarterly, so only 4 values out of ~365 days.
    #        We later decided to just apply forward filling to the NA values.
    #     2. Some gopher from Maynooth or wherever else, with whom we had to share the Eikon account/s, kept logging into
    #        the same account, consequently logging me out of the Eikon platform and causing the script to fail.
    #     3. Eikon has a daily query limit. This limit wouldn't ordinarily be reached even with the total no. of queries needed,
    #        but when things keep failing and you have to re-run some bits, it tends to rack up.
    #     4. Sometimes an issue would occur with the DB connection. Couldn't really figure it out since it happened quite randomly.
    #     5. The Eikon (student) account doesn't have 'privileges' for fetching data for some stocks, so had to skip 'em.
    #
    # After a full run of the script, which took several hours, I'd skim through the printed logs and see for which stocks
    # the script failed, and then try to re-run the script with just these stocks (e.g. if it failed for AMZN.O and MSFT.O, 
    # then I set tickers_list = ["AMZN.O", "MSFT.O"]), and it usually worked. Otherwise we just had to discard those stocks.
    # A very manual process indeed, but because of the diversity of 'uncatchable' errors (and the time constraints), this was the best I
    # could do.
    #
    # In terms of the field variables, figuring out where to get these codes and how to use them took the longest, but after that,
    # it was pretty much a matter of taking the return value, preprocessing it a bit, and then storing it into the ticker_info_df.
    # Each data (close_price, PE, etc.) had to be treated separately, because the return values of the queries were very different
    # to each other.
    #
    # If you'll be using a similar procedure, I'd recommend starting with the date_field and field, and then running the ek.get_data()
    # function. Then take your time to understand the structure of the return value and preprocess it as needed. If you're using other
    # data items, the code should be available in the Eikon interface, when you type "Data item browser" for a given stock. This is quite
    # a bit funky though; sometimes, the DIB shows up in the search, sometimes it doesn't. If it doesn't, maybe restart the program.
    
    tickers_list= db.fetch_table("ticker_symbols")["ric"].values.tolist()
    start = dt.date(2016, 6, 30).strftime("%Y-%m-%d")
    end = dt.datetime.today().strftime("%Y-%m-%d")

    for (count, ticker) in enumerate(tickers_list):
        try:
            # Closing prices
            ek_closing_prices = ek.get_timeseries(ticker, ["Close"], start_date=start, end_date=end)
            ticker_info_df = pd.DataFrame(ek_closing_prices)
            ticker_info_df.columns = ["close_price"]

            # Price-earnings
            date_field = f"TR.HistPE(SDate={start},EDate={end},Period=FI0,Frq=FI).date"
            field = f"TR.HistPE(SDate={start},EDate={end},Period=FI0,Frq=FI)"
            eik_data, err = ek.get_data(ticker, [date_field, field])
            data_df = pd.DataFrame(eik_data, columns=["Date", "Historic P/E"]).set_index("Date")
            if data_df["Historic P/E"].isna().all():
                ticker_info_df["price_earnings"] = np.nan
            else:
                data_df.columns = ["price_earnings"]
                data_df.index = data_df.index.str[0:10]#pd.to_datetime(data_df.index, format="%Y-%m-%dT%H:%M:%SZ")
                ticker_info_df = ticker_info_df.join(data_df)
                ticker_info_df = ticker_info_df.fillna(method="ffill")

            # Price-to-book
            date_field = f"TR.PriceToBVPerShare(SDate={start},EDate={end},Frq=D).date"
            field = f"TR.PriceToBVPerShare(SDate={start},EDate={end},Frq=D)"
            eik_data, err = ek.get_data(ticker, [date_field, field])
            data_df = pd.DataFrame(eik_data, columns=["Date", "Price To Book Value Per Share (Daily Time Series Ratio)"]).set_index("Date")
            if data_df["Price To Book Value Per Share (Daily Time Series Ratio)"].isna().all():
                ticker_info_df["price_to_book"] = np.nan
            else:
                data_df.columns = ["price_to_book"]
                data_df.index = data_df.index.str[0:10]#pd.to_datetime(data_df.index, format="%Y-%m-%dT%H:%M:%SZ")
                ticker_info_df = ticker_info_df.join(data_df)
                ticker_info_df["price_to_book"] = ticker_info_df["price_to_book"].fillna(method="ffill")

            # Price-to-free-cashflow
            date_field = f"TR.HistPricetoFreeOperatingCashFlowperShareAvgDilutedSharesOut(SDate={start},EDate={end},Period=FI0,Frq=FI).date"
            field = f"TR.HistPricetoFreeOperatingCashFlowperShareAvgDilutedSharesOut(SDate={start},EDate={end},Period=FI0,Frq=FI)"
            eik_data, err = ek.get_data(ticker, [date_field, field])
            data_df = pd.DataFrame(eik_data, columns=["Date", "Historic Price/FOCF/Shr (dil.)"]).set_index("Date")
            if data_df["Historic Price/FOCF/Shr (dil.)"].isna().all():
                ticker_info_df["price_to_fcf"] = np.nan
            else:
                data_df.columns = ["price_to_fcf"]
                data_df.index = data_df.index.str[0:10]#pd.to_datetime(data_df.index, format="%Y-%m-%dT%H:%M:%SZ")
                ticker_info_df = ticker_info_df.join(data_df)
                ticker_info_df["price_to_fcf"] = ticker_info_df["price_to_fcf"].fillna(method="ffill")

            # EV-EBITDA
            date_field = f"TR.HistEnterpriseValueEBITDA(SDate={start},EDate={end},Period=FY0,Frq=FY).date"
            field = f"TR.HistEnterpriseValueEBITDA(SDate={start},EDate={end},Period=FY0,Frq=FY)"
            eik_data, err = ek.get_data(ticker, [date_field, field])
            data_df = pd.DataFrame(eik_data, columns=["Date", "Historic EV/EBITDA, FY"]).set_index("Date")
            if data_df["Historic EV/EBITDA, FY"].isna().all():
                ticker_info_df["ev_ebitda"] = np.nan
            else:
                data_df.columns = ["ev_ebitda"]
                data_df.index = data_df.index.str[0:10]#pd.to_datetime(data_df.index, format="%Y-%m-%dT%H:%M:%SZ")
                ticker_info_df = ticker_info_df.join(data_df)
                ticker_info_df["ev_ebitda"] = ticker_info_df["ev_ebitda"].fillna(method="ffill")

#             # Commented out these 3 (current ratio, quick ratio and dollar turnover) because they weren't needed in the end.
#             # Current ratio
#             date_field = f"TR.CurrentRatio(SDate={start},EDate={end},Frq=Y).date"
#             field = f"TR.CurrentRatio(SDate={start},EDate={end},Frq=Y)"
#             eik_data, err = ek.get_data(ticker, [date_field, field])
#             data_df = pd.DataFrame(eik_data, columns=["Date", "Current Ratio"]).set_index("Date")
#             data_df.columns = ["current_ratio"]
#             data_df.index = data_df.index.str[0:10]#pd.to_datetime(data_df.index, format="%Y-%m-%dT%H:%M:%SZ")
#             ticker_info_df = ticker_info_df.join(data_df)
#             ticker_info_df["current_ratio"] = ticker_info_df["current_ratio"].fillna(method="ffill")

#             # Quick Ratio
#             date_field = f"TR.QuickRatio(SDate={start},EDate={end},Frq=Y).date"
#             field = f"TR.QuickRatio(SDate={start},EDate={end},Frq=Y)"
#             eik_data, err = ek.get_data(ticker, [date_field, field])
#             data_df = pd.DataFrame(eik_data, columns=["Date", "Quick Ratio"]).set_index("Date")
#             data_df.columns = ["quick_ratio"]
#             data_df.index = data_df.index.str[0:10]#pd.to_datetime(data_df.index, format="%Y-%m-%dT%H:%M:%SZ")
#             ticker_info_df = ticker_info_df.join(data_df)
#             ticker_info_df["quick_ratio"] = ticker_info_df["quick_ratio"].fillna(method="ffill")

#             # Dollar Turnover
#             date_field = f"TR.TURNOVER(SDate={start},EDate={end},Frq=D).date"
#             field = f"TR.TURNOVER(SDate={start},EDate={end},Frq=D)"
#             eik_data, err = ek.get_data(ticker, [date_field, field])
#             data_df = pd.DataFrame(eik_data, columns=["Date", "Turnover"]).set_index("Date")
#             data_df.columns = ["dollar_turnover"]
#             data_df.index = data_df.index.str[0:10]#pd.to_datetime(data_df.index, format="%Y-%m-%dT%H:%M:%SZ")
#             ticker_info_df = ticker_info_df.join(data_df)

            ticker_info_df = ticker_info_df.loc[~ticker_info_df.index.duplicated(keep='first')]
            db.append_df_as_row(ticker_info_df, ticker.replace(".","_"), if_exists="replace", index=True) 
            db.set_primary_key(ticker.replace(".","_"), "Date")
            print(f"-I- Successfully stored table for ({count}) {ticker}. {len(tickers_list)-(count+1)} more to go.")

        except Exception as e:
            print(f"-W- Could not store table for ({count}) {ticker}. Error message: {str(e)}")


    print("\n",f"Whole thing took {time.time() - time_} seconds")
