import logging
from fyers_apiv3 import fyersModel
import webbrowser

# Get a logger instance for this module
logger = logging.getLogger(__name__)

def generate_access_token(client_id: str, secret_key: str, redirect_uri: str, log_path=""):
    """
    Guides the user through the browser-based Fyers authentication process
    to generate a valid access token.
    """
    session = fyersModel.SessionModel(
        client_id=client_id,
        secret_key=secret_key,
        redirect_uri=redirect_uri,
        response_type="code",
        grant_type="authorization_code"
    )

    generate_token_url = session.generate_authcode()

    # Use the logger to provide instructions
    logger.info("=" * 80)
    logger.info("FYERS AUTHENTICATION REQUIRED")
    logger.info("1. A new tab should have opened in your web browser.")
    logger.info("2. Please log in to your Fyers account in that tab.")
    logger.info("3. After logging in, you will be redirected to your Redirect URI.")
    logger.info("4. From the new URL in your browser's address bar, copy the value of the 'auth_code' parameter.")
    logger.info(f"\nIf the tab did not open, please manually copy this URL into your browser:\n{generate_token_url}\n")

    try:
        webbrowser.open(generate_token_url, new=1)
    except Exception as e:
        logger.error(f"Could not automatically open web browser: {e}")

    logger.info("=" * 80)

    # Prompt the user to paste the auth code. Input still goes to console.
    auth_code = input("Please paste the auth_code here and press Enter: ")

    if not auth_code:
        logger.warning("Authentication cancelled. No auth_code provided.")
        return None

    session.set_token(auth_code)
    response = session.generate_token()

    if response.get("s") == "ok":
        access_token = response.get("access_token")
        logger.info("Successfully generated access token!")
        return access_token
    else:
        logger.error(f"Error generating access token: {response.get('message')}")
        return None
