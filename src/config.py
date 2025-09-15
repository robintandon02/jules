# Fyers API configuration
API_ID = "YOUR_API_ID"
API_SECRET = "YOUR_API_SECRET"
REDIRECT_URL = "http://localhost:3000/callback"

# === Strategy Configuration ===
# Format for the weekly option symbol's expiry part.
# This needs to be updated manually each week before the first run.
# Example: For a Nifty option expiring on Sep 26, 2024, the format might be "24926".
# For NIFTY24SEP25000CE, this value should be "24SEP".
# Please check the exact format from the Fyers platform for the desired week.
OPTION_EXPIRY_FORMAT = "24SEP"
