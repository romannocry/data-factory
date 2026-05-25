import pandas as pd

prices = pd.Series([
    100,101,102,103,104,
    103,102,101,100,99,
    98,99,100,101,102
])

window = 5

# Moving average
sma = prices.rolling(window).mean()

# Standard deviation
std = prices.rolling(window).std()

# Bands
upper_band = sma + (2 * std)
lower_band = sma - (2 * std)

print(upper_band)
print(lower_band)