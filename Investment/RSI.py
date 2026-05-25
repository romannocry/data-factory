import pandas as pd

prices = pd.Series([
    100, 102, 101, 103, 104,
    103, 105, 107, 106, 108
])

# Price changes
delta = prices.diff()

# Separate gains and losses
gains = delta.clip(lower=0)
losses = -delta.clip(upper=0)

# Rolling averages
window = 5

avg_gain = gains.rolling(window).mean()
avg_loss = losses.rolling(window).mean()

# Relative strength
rs = avg_gain / avg_loss

# RSI
rsi = 100 - (100 / (1 + rs))

print(rsi)